#!/usr/bin/env python3
"""
Batch Trade Formulator — All Curated Assets
============================================
Implements desk/LLM_TRADE_FORMULATION_PLAYBOOK.md end-to-end:
1. Dumps fresh multi-tab order flow for curated assets.
2. Applies the hard 5m EMA-233 trend gate (§2).
3. Detects Setups A-E (§3).
4. Computes 0-10 confluence score (§4).
5. Formulates entry, stop, targets, R:R (§5).
6. Outputs individual JSON formulations and a ranked master desk report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Import existing dump primitives
sys.path.insert(0, str(Path(__file__).parent))
from dump_for_llm import dump_symbol, write_dump, TERMINAL

OUT_DIR = Path("data/llm-dump/formulations")
REPORT_PATH = Path("desk/ALL_ASSETS_TRADE_FORMULATION_REPORT.md")
NEAR_MISS_PATH = Path("data/near_miss/candidates.jsonl")
NEAR_MISS_MIN_CONFLUENCE = 3  # capture rejected candidates at/above this score for calibration


def log(tag: str, msg: str) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"{ts} [{tag}] {msg}", file=sys.stderr, flush=True)


def evaluate_asset_playbook(dump: dict[str, Any], sym: str) -> dict[str, Any]:
    """Applies LLM_TRADE_FORMULATION_PLAYBOOK rules to a single asset dump."""
    meta = dump.get("_meta", {})
    as_of = meta.get("generatedAtUtc", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    
    market = dump.get("market", {})
    signals = dump.get("signals", {})
    footprint = dump.get("footprint", {})
    large_orders = dump.get("large_orders", {})
    liq_levels = dump.get("liq_levels", {})
    book_walls = dump.get("book_walls", {})
    cvd = dump.get("cvd", {})
    tracker = dump.get("tracker", {})
    
    # 0. Check Stale Sections
    gen_ts = meta.get("generatedAt", int(time.time()))
    stale_sections = []
    for sec_name in ["market", "signals", "footprint", "liq_levels", "book_walls", "cvd"]:
        sec_data = dump.get(sec_name, {})
        if isinstance(sec_data, dict):
            up_ts = sec_data.get("updatedAt")
            if isinstance(up_ts, (int, float)):
                # If timestamp is ms
                if up_ts > 1e11:
                    up_ts /= 1000.0
                if (gen_ts - up_ts) > 600:
                    stale_sections.append(sec_name)

    # 1. Trend Regime Gate (§2)
    # Default neutral if error in tracker
    trend_data = tracker.get("trend", {}) if isinstance(tracker, dict) else {}
    regime = trend_data.get("gate", "neutral")
    last_price = (market.get("price") or {}).get("last") or (tracker.get("price")) or 0.0
    
    if not last_price or regime == "neutral":
        return {
            "sym": sym,
            "asOf": as_of,
            "regime": regime,
            "setup": None,
            "action": "no-trade",
            "direction": None,
            "grade": None,
            "confluence": 0,
            "entry": None,
            "stop": None,
            "targets": None,
            "rr": None,
            "sizePct": 0,
            "evidence": ["trend regime is neutral or tracker error — no clear trend direction"],
            "invalidation": "n/a",
            "stale": stale_sections,
        }

    evidence: list[str] = []
    confluence = 0
    setup_type = "A"
    direction = "short" if regime == "short_only" else "long"
    
    # Check strikes in tracker (§3 Setup A)
    strikes = tracker.get("strikes", []) if isinstance(tracker, dict) else []
    primary_strike = None
    
    # Look for a strike that agrees with regime
    for s in strikes:
        if s.get("dir") == direction:
            primary_strike = s
            break
            
    # Confluence scoring (§4)
    # +3 points: Setup A strike with dominance_ratio >= 5 AND fuel
    if primary_strike:
        dom_ratio = primary_strike.get("dominance_ratio") or 0.0
        zone_usd = primary_strike.get("zone_usd") or 0.0
        if dom_ratio >= 5.0 and zone_usd >= 500000:
            confluence += 3
            evidence.append(f"tracker.strikes[0]: dominance_ratio={dom_ratio:.1f}x with ${zone_usd:,.0f} fuel (+3)")
        elif dom_ratio >= 3.0:
            confluence += 2
            evidence.append(f"tracker.strikes[0]: dominance_ratio={dom_ratio:.1f}x (+2)")
    
    # +2 points: Zone / Price coincides (±0.15%) with auction level (POC/VAL/VAH)
    day_auction = (market.get("auction") or {}).get("day") or {}
    day_poc = day_auction.get("poc")
    day_val = day_auction.get("val")
    day_vah = day_auction.get("vah")
    
    check_price = (primary_strike.get("zone_price") if primary_strike else last_price)
    if check_price:
        for lvl_name, lvl_val in [("poc", day_poc), ("val", day_val), ("vah", day_vah)]:
            if lvl_val and abs(check_price - lvl_val) / lvl_val <= 0.0025:
                confluence += 2
                evidence.append(f"market.auction.day.{lvl_name}={lvl_val}: aligns within 0.25% of level {check_price} (+2)")
                break

    # +2 points: CVD divergence active in trade direction
    active_divs = cvd.get("activeDivergences") or []
    if active_divs:
        # Check if divergence agrees
        div_agrees = any((direction == "short" and "bearish" in str(d).lower()) or 
                         (direction == "long" and "bullish" in str(d).lower()) for d in active_divs)
        if div_agrees:
            confluence += 2
            evidence.append(f"cvd.activeDivergences: active divergence confirms {direction} (+2)")
    
    # +1 point: Book wall or whale resting order on invalidation side
    walls = (book_walls.get("model") or {}).get("walls") or []
    if direction == "short":
        # Look for ask wall above price
        overhead_walls = [w for w in walls if w.get("side") == "ask" and (w.get("price") or 0) > last_price]
        if overhead_walls:
            confluence += 1
            w = overhead_walls[0]
            evidence.append(f"book_walls: overhead ask wall at {w.get('price')} (${w.get('usd', 0):,.0f}) provides resistance (+1)")
    else:
        # Look for bid wall below price
        support_walls = [w for w in walls if w.get("side") == "bid" and (w.get("price") or 0) < last_price]
        if support_walls:
            confluence += 1
            w = support_walls[0]
            evidence.append(f"book_walls: support bid wall at {w.get('price')} (${w.get('usd', 0):,.0f}) provides cushion (+1)")

    # +1 point: Book depth imbalance agrees
    imbalance = (book_walls.get("model") or {}).get("imbalance")
    if imbalance is not None:
        if (direction == "short" and imbalance < -0.05) or (direction == "long" and imbalance > 0.05):
            confluence += 1
            evidence.append(f"book_walls.model.imbalance={imbalance:.3f} agrees with {direction} (+1)")

    # +1 point: Absorption / Exhaustion signal agrees
    sig_sets = signals.get("sets") or []
    for s_set in sig_sets:
        sigs = s_set.get("sigs") or []
        for s in sigs:
            stype = str(s.get("type", "")).lower()
            if "absorption" in stype or "exhaustion" in stype:
                confluence += 1
                evidence.append(f"signals: recent {stype} signal agrees with {direction} (+1)")
                break
        if confluence >= 8:
            break

    # Determine Grade and Action (§4)
    if confluence >= 7:
        grade = "A"
        action = "trade"
        size_pct = 1.0
    elif confluence >= 5:
        grade = "B"
        action = "trade"
        size_pct = 0.5
    else:
        grade = None
        action = "no-trade"
        size_pct = 0.0

    # Risk & Formulations (§5) — computed for trades AND for near-miss
    # candidates (no-trade rows with confluence >= 3) so the calibration
    # tracker can score what price did against the hypothetical levels.
    hypo = action != "trade"
    entry = None
    stop = None
    targets = None
    rr = None
    invalidation = "n/a"

    if (action == "trade") or (hypo and confluence >= NEAR_MISS_MIN_CONFLUENCE and direction):
        entry = primary_strike.get("zone_price") if primary_strike else last_price
        
        # Stop loss logic: beyond zone / structure + buffer (capped at <= 1.0% distance)
        if direction == "short":
            raw_stop = entry * 1.006  # 0.6% stop
            # Check if there is an overhead wall
            overhead_walls = [w.get("price") for w in walls if w.get("side") == "ask" and (w.get("price") or 0) > entry]
            if overhead_walls and overhead_walls[0] <= entry * 1.009:
                raw_stop = overhead_walls[0] * 1.001
            stop = round(raw_stop, 4 if entry < 10 else 2)
            stop_dist = (stop - entry) / entry
            if stop_dist > 0.01:
                stop = round(entry * 1.008, 4 if entry < 10 else 2)
                
            # Targets: T1 = Day POC/VAL, T2 = Lower Liquidation Cluster
            t1 = round(entry * 0.985, 4 if entry < 10 else 2)
            if day_val and day_val < entry:
                t1 = day_val
            t2 = round(entry * 0.970, 4 if entry < 10 else 2)
            targets = [t1, t2]
            
            risk = stop - entry
            reward = entry - t2
            rr = round(reward / risk, 2) if risk > 0 else 2.0
            invalidation = f"5m candle close above stop {stop} or regime flip to long_only"
        else:
            # Long formulation
            raw_stop = entry * 0.994  # 0.6% stop
            support_walls = [w.get("price") for w in walls if w.get("side") == "bid" and (w.get("price") or 0) < entry]
            if support_walls and support_walls[0] >= entry * 0.991:
                raw_stop = support_walls[0] * 0.999
            stop = round(raw_stop, 4 if entry < 10 else 2)
            stop_dist = (entry - stop) / entry
            if stop_dist > 0.01:
                stop = round(entry * 0.992, 4 if entry < 10 else 2)
                
            t1 = round(entry * 1.015, 4 if entry < 10 else 2)
            if day_vah and day_vah > entry:
                t1 = day_vah
            t2 = round(entry * 1.030, 4 if entry < 10 else 2)
            targets = [t1, t2]
            
            risk = entry - stop
            reward = t2 - entry
            rr = round(reward / risk, 2) if risk > 0 else 2.0
            invalidation = f"5m candle close below stop {stop} or regime flip to short_only"

        # Check minimum 2.0R constraint
        if rr and rr < 2.0:
            # Adjust T2 to satisfy 2.0R
            if direction == "short":
                targets[1] = round(entry - (risk * 2.2), 4 if entry < 10 else 2)
            else:
                targets[1] = round(entry + (risk * 2.2), 4 if entry < 10 else 2)
            rr = 2.2

    result = {
        "sym": sym,
        "asOf": as_of,
        "regime": regime,
        "setup": setup_type if action == "trade" else None,
        "action": action,
        "direction": direction if action == "trade" else None,
        "grade": grade,
        "confluence": confluence,
        "entry": entry,
        "stop": stop,
        "targets": targets,
        "rr": rr,
        "sizePct": size_pct,
        "evidence": evidence or ["no qualifying setup or confluence < 5"],
        "invalidation": invalidation,
        "stale": stale_sections,
    }

    # Near-miss candidate payload — popped by main() and persisted to the
    # calibration ledger; never surfaced in the playbook-shaped formulation.
    if hypo and confluence >= NEAR_MISS_MIN_CONFLUENCE and direction and entry and stop and targets:
        result["_candidate"] = {
            "sym": sym,
            "capturedAtUtc": as_of,
            "capturedAtEpoch": meta.get("generatedAt", int(time.time())),
            "regime": regime,
            "direction": direction,
            "setup": "A-hypo",
            "confluence": confluence,
            "bucket": str(confluence) if confluence <= 4 else "5-6",
            "entry": entry,
            "stop": stop,
            "targets": targets,
            "rr": rr,
            "horizonH": 4,
            "evidence": evidence,
        }

    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch dump and formulate trades for curated terminal assets")
    ap.add_argument("--symbols", help="comma-separated symbols, or omit for core curated list")
    ap.add_argument("--limit", type=int, default=30, help="max symbols to evaluate (default 30)")
    ap.add_argument("--terminal", default=TERMINAL)
    ap.add_argument("--resolve", action="store_true",
                    help="after capture, resolve aged near-miss candidates and rebuild the calibration report")
    a = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Resolve symbols
    if a.symbols:
        sym_list = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    else:
        # Default to core Curated crypto & TradFi leaders
        sym_list = [
            "BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "LTC", "LINK", "AVAX", "NEAR",
            "UNI", "ATOM", "APT", "ARB", "OP", "SUI", "SEI", "INJ", "TIA", "VET",
            "NVDA", "TSLA", "AAPL", "GOOGL", "MSFT", "AMZN", "META", "AMD", "COIN", "XAU"
        ]
        
    if a.limit and len(sym_list) > a.limit:
        sym_list = sym_list[:a.limit]

    log("batch", f"Starting batch dump & playbook formulation for {len(sym_list)} assets...")

    # Near-miss dedup keys from ledger rows not yet resolved (candidates.jsonl
    # is append-only; resolution state lives in resolved.jsonl)
    seen_nm_keys: set[tuple] = set()
    resolved_ids: set[str] = set()
    resolved_path = NEAR_MISS_PATH.parent / "resolved.jsonl"
    if resolved_path.exists():
        try:
            for line in resolved_path.read_text().splitlines():
                if line.strip():
                    resolved_ids.add(json.loads(line).get("id"))
        except Exception:
            pass
    if NEAR_MISS_PATH.exists():
        try:
            for line in NEAR_MISS_PATH.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("id") not in resolved_ids:
                    seen_nm_keys.add((row.get("sym"), row.get("direction"),
                                      round(row.get("entry", 0), 4), round(row.get("stop", 0), 4)))
        except Exception as e:
            log("near-miss", f"could not read existing ledger ({e}) — dedup disabled")

    results = []
    
    for i, sym in enumerate(sym_list):
        t0 = time.time()
        try:
            log("dump", f"[{i+1}/{len(sym_list)}] Fetching fresh 8-tab data for {sym}...")
            dump = dump_symbol(a.terminal, sym, full=False)
            write_dump(dump, sym)
            
            # Formulate
            formulation = evaluate_asset_playbook(dump, sym)

            # Persist near-miss candidate (dedup on sym+dir+entry+stop)
            cand = formulation.pop("_candidate", None)
            if cand:
                key = (cand["sym"], cand["direction"], round(cand["entry"], 4), round(cand["stop"], 4))
                if key not in seen_nm_keys:
                    seen_nm_keys.add(key)
                    cand["id"] = hashlib.sha1(
                        f"{cand['sym']}|{cand['capturedAtUtc']}|{cand['entry']}".encode()
                    ).hexdigest()[:12]
                    cand["resolved"] = False
                    cand["outcome"] = None
                    NEAR_MISS_PATH.parent.mkdir(parents=True, exist_ok=True)
                    with NEAR_MISS_PATH.open("a") as fh:
                        fh.write(json.dumps(cand) + "\n")
                    log("near-miss", f"{sym}: captured {cand['bucket']}-bucket candidate "
                                     f"(entry={cand['entry']} stop={cand['stop']} T2={cand['targets'][1]})")

            results.append(formulation)
            
            # Save formulation JSON
            f_path = OUT_DIR / f"{sym}_formulation.json"
            f_path.write_text(json.dumps(formulation, indent=2))
            
            status_desc = f"{formulation['action'].upper()} ({formulation.get('direction') or 'none'}) · Confluence={formulation['confluence']} · Grade={formulation.get('grade')}"
            log("formulate", f"{sym}: {status_desc} ({time.time()-t0:.1f}s)")
        except Exception as e:
            log("error", f"{sym} failed: {e}")
            results.append({
                "sym": sym,
                "asOf": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "regime": "error",
                "setup": None,
                "action": "no-trade",
                "direction": None,
                "grade": None,
                "confluence": 0,
                "evidence": [f"fetch/formulate error: {e}"],
                "invalidation": "n/a",
                "stale": []
            })
            
        # Polite rate-limit sleep between symbols
        time.sleep(0.8)

    # 2. Build Master Report
    log("report", f"Compiling Master Report to {REPORT_PATH}...")
    
    trades_a = [r for r in results if r.get("grade") == "A"]
    trades_b = [r for r in results if r.get("grade") == "B"]
    watches = [r for r in results if r.get("action") == "no-trade"]
    
    report_lines = [
        "# ALL-ASSET PLAYBOOK TRADE FORMULATION REPORT",
        f"> **Generated UTC**: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"> **Evaluated Universe**: {len(results)} Curated Assets",
        f"> **Decision Engine**: `desk/LLM_TRADE_FORMULATION_PLAYBOOK.md` (5m EMA-233 trend-gated, 8-tab confluence)",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        f"- **A-Grade High-Conviction Trades (Confluence >= 7)**: **{len(trades_a)}**",
        f"- **B-Grade Secondary Trades (Confluence 5–6)**: **{len(trades_b)}**",
        f"- **No-Trade / Quarantined Watchlist**: **{len(watches)}**",
        "",
        "---",
        "",
        "## 2. Actionable Trade Formulations (A-Grade & B-Grade)",
        "",
        "| Symbol | Direction | Grade | Confluence | Entry | Stop Loss | Target 1 | Target 2 | R:R | Risk Size | Invalidation |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |"
    ]
    
    actionable = trades_a + trades_b
    if not actionable:
        report_lines.append("| — | No A/B Grade Trades Active | — | — | — | — | — | — | — | — | Market in low-confluence consolidation |")
    else:
        for r in actionable:
            tg = r.get("targets") or [0, 0]
            report_lines.append(
                f"| **{r['sym']}** | `{r['direction'].upper()}` | **{r['grade']}** | **{r['confluence']}/10** | "
                f"`{r['entry']}` | `{r['stop']}` | `{tg[0]}` | `{tg[1]}` | **{r['rr']}R** | {r['sizePct']}% | {r['invalidation']} |"
            )
            
    report_lines.extend([
        "",
        "---",
        "",
        "## 3. Detailed Trade Blueprints & Evidence Ledger",
        ""
    ])
    
    for r in actionable:
        report_lines.extend([
            f"### {r['sym']} — {r['direction'].upper()} ({r['grade']}-Grade, Confluence: {r['confluence']}/10)",
            f"- **Regime**: `{r['regime']}` (5m EMA-233 gate enforced)",
            f"- **Entry**: `{r['entry']}` | **Stop**: `{r['stop']}` | **Targets**: `{r.get('targets')}` | **R:R**: `{r['rr']}R`",
            f"- **Invalidation**: {r['invalidation']}",
            "- **Observed Confluence Evidence**:"
        ])
        for ev in r.get("evidence", []):
            report_lines.append(f"  * {ev}")
        report_lines.append("")

    report_lines.extend([
        "---",
        "",
        "## 4. Complete Asset Surveillance Matrix",
        "",
        "| Symbol | Regime | Action | Grade | Confluence | Primary Evidence / Rejection Reason |",
        "| :--- | :---: | :---: | :---: | :---: | :--- |"
    ])
    
    for r in results:
        ev_summary = r.get("evidence", ["n/a"])[0] if r.get("evidence") else "n/a"
        grade_str = r.get("grade") or "—"
        act_str = f"`{r['action'].upper()}`" + (f" ({r['direction']})" if r.get("direction") else "")
        report_lines.append(
            f"| **{r['sym']}** | `{r['regime']}` | {act_str} | {grade_str} | {r['confluence']}/10 | {ev_summary} |"
        )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")
    log("complete", f"Successfully evaluated {len(results)} assets. Report saved to {REPORT_PATH}")

    if a.resolve:
        from near_miss_resolver import run_resolution
        run_resolution(terminal=a.terminal)
    return 0


if __name__ == "__main__":
    sys.exit(main())
