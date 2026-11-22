#!/usr/bin/env python3
"""
Batch Trade Formulator — All Curated Assets
============================================
Implements desk/LLM_TRADE_FORMULATION_PLAYBOOK.md end-to-end:
1. Dumps fresh multi-tab order flow for curated terminal assets (parallelized tab fetch).
2. Applies the hard 5m EMA-233 trend gate (§2).
3. Detects Setups A-E (§3).
4. Computes 0-10 confluence score (§4).
5. Formulates entry, stop, targets, R:R (§5).
6. Outputs individual JSON formulations and a ranked master desk report.
"""

from __future__ import annotations

import argparse
import concurrent.futures
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
from dump_for_llm import (
    TERMINAL,
    GUIDE,
    sec_market,
    sec_signals,
    sec_footprint,
    sec_large_orders,
    sec_liq_levels,
    sec_book_walls,
    sec_cvd,
    sec_tracker,
    write_dump,
)

OUT_DIR = Path("data/llm-dump/formulations")
REPORT_PATH = Path("desk/ALL_ASSETS_TRADE_FORMULATION_REPORT.md")


def log(tag: str, msg: str) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"{ts} [{tag}] {msg}", file=sys.stderr, flush=True)


def dump_symbol_parallel(base: str, sym: str, full: bool = False) -> dict[str, Any]:
    """Fetches all 8 tabs concurrently using a thread pool to minimize round-trip latency."""
    t0 = time.time()
    results: dict[str, Any] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        f_market = ex.submit(sec_market, base, sym)
        f_signals = ex.submit(sec_signals, base, sym)
        f_footprint = ex.submit(sec_footprint, base, sym, full)
        f_large = ex.submit(sec_large_orders, base, sym, full)
        f_liq = ex.submit(sec_liq_levels, base, sym)
        f_walls = ex.submit(sec_book_walls, base, sym, full)
        f_cvd = ex.submit(sec_cvd, base, sym)
        f_tracker = ex.submit(sec_tracker, base, sym)

        results["market"] = f_market.result()
        results["signals"] = f_signals.result()
        results["footprint"] = f_footprint.result()
        results["large_orders"] = f_large.result()
        results["liq_levels"] = f_liq.result()
        results["book_walls"] = f_walls.result()
        results["cvd"] = f_cvd.result()
        results["tracker"] = f_tracker.result()

    return {
        "_guide": GUIDE,
        "_meta": {
            "generatedAt": int(time.time()),
            "generatedAtUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "terminal": base,
            "sym": sym,
            "full": full,
            "latencySec": round(time.time() - t0, 2),
            "sources": "local terminal API (/api/cg/*) — live Coinglass/Binance data, no mocks",
            "estimates": "liquidation/whale/wall figures are Coinglass estimates",
        },
        **results,
    }


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
                if up_ts > 1e11:
                    up_ts /= 1000.0
                if (gen_ts - up_ts) > 600:
                    stale_sections.append(sec_name)

    # 1. Trend Regime Gate (§2)
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
    if strikes:
        for s in reversed(strikes):
            s_dir = s.get("dir", "").lower()
            if (regime == "short_only" and s_dir == "short") or (regime == "long_only" and s_dir == "long"):
                primary_strike = s
                break

    if primary_strike:
        confluence += 3
        evidence.append(
            f"Setup A zone strike: {primary_strike['dir'].upper()} at {primary_strike['zone_price']} "
            f"with dominance ratio {primary_strike.get('dominance_ratio')} ({primary_strike.get('time_utc')})"
        )
    else:
        # Check Setup B: Value Area Reversion
        auction = (market.get("auction") or {}).get("session") or (market.get("auction") or {}).get("day") or {}
        vah = auction.get("vah")
        val = auction.get("val")
        poc = auction.get("poc")

        if regime == "short_only" and vah and last_price >= vah * 0.998:
            setup_type = "B"
            confluence += 2
            evidence.append(f"Setup B Value Area high test: price {last_price} near VAH {vah} in short regime")
        elif regime == "long_only" and val and last_price <= val * 1.002:
            setup_type = "B"
            confluence += 2
            evidence.append(f"Setup B Value Area low test: price {last_price} near VAL {val} in long regime")

    # Check CVD Divergence (§4 Confluence +2)
    cvd_divs = cvd.get("divergences") or cvd.get("activeDivergences") or (cvd.get("kpis") or {}).get("latestDiv") or []
    if isinstance(cvd_divs, dict):
        cvd_divs = [cvd_divs]
    matching_div = False
    if isinstance(cvd_divs, list):
        for div in cvd_divs:
            if not isinstance(div, dict):
                continue
            div_type = str(div.get("type") or div.get("t") or "").lower()
            if (regime == "short_only" and "bear" in div_type) or (regime == "long_only" and "bull" in div_type):
                matching_div = True
                break
    if matching_div:
        confluence += 2
        evidence.append(f"CVD active divergence aligned with {regime} (+2 confluence)")

    # Check Absorption signals (§4 Confluence +2)
    sig_sets = signals.get("sets") or []
    all_sigs = []
    if isinstance(sig_sets, list):
        for s_set in sig_sets:
            if isinstance(s_set, dict):
                sigs = s_set.get("sigs", [])
                if isinstance(sigs, list):
                    all_sigs.extend(sigs)
    elif isinstance(sig_sets, dict):
        for k, v in sig_sets.items():
            if isinstance(v, list):
                all_sigs.extend(v)

    has_absorption = False
    for sig in all_sigs:
        if not isinstance(sig, dict):
            continue
        st = str(sig.get("t") or sig.get("type") or "").lower()
        sd = str(sig.get("side") or "").lower()
        if "abs" in st:
            if (regime == "short_only" and sd in ["sell", "bear"]) or (regime == "long_only" and sd in ["buy", "bull"]):
                has_absorption = True
                break
    if has_absorption:
        confluence += 2
        evidence.append(f"Footprint absorption signal aligned with {regime} (+2 confluence)")

    # Check Book Walls (§4 Confluence +1)
    bw_model = book_walls.get("model") or {}
    imb = bw_model.get("imbalance", 0.0)
    walls = bw_model.get("walls") or []
    has_wall = False
    if regime == "short_only":
        if imb < -0.15:
            confluence += 1
            evidence.append(f"Order book ask-heavy imbalance ({imb:.3f}) (+1 confluence)")
        for w in walls:
            if w.get("side") == "ask" and w.get("price", 0) >= last_price and w.get("touches", 0) > 0:
                has_wall = True
                break
        if has_wall:
            confluence += 1
            evidence.append("Confirmed resting ask wall above current price (+1 confluence)")
    elif regime == "long_only":
        if imb > 0.15:
            confluence += 1
            evidence.append(f"Order book bid-heavy imbalance (+{imb:.3f}) (+1 confluence)")
        for w in walls:
            if w.get("side") == "bid" and w.get("price", 0) <= last_price and w.get("touches", 0) > 0:
                has_wall = True
                break
        if has_wall:
            confluence += 1
            evidence.append("Confirmed resting bid wall below current price (+1 confluence)")

    # Check Liquidation clusters / Magnet (§4 Confluence +1)
    kl = (liq_levels.get("stats") or {}).get("keyLevels") or {}
    above_levels = kl.get("above") or []
    below_levels = kl.get("below") or []
    if regime == "short_only" and below_levels:
        confluence += 1
        evidence.append(f"Substantial liquidation magnet below price at {below_levels[0].get('price')} (+1 confluence)")
    elif regime == "long_only" and above_levels:
        confluence += 1
        evidence.append(f"Substantial liquidation magnet above price at {above_levels[0].get('price')} (+1 confluence)")

    # Trend gate alignment (+1 base)
    confluence += 1
    evidence.append(f"Hard 5m EMA-233 trend gate aligned: {regime} (price {last_price})")

    # Decision: Action & Grade
    if confluence >= 7:
        grade = "A"
        action = "trade"
        size_pct = 2.0
    elif confluence >= 5:
        grade = "B"
        action = "trade"
        size_pct = 1.0
    else:
        grade = None
        action = "no-trade"
        size_pct = 0.0

    # Pricing & R:R Formulation (§5)
    if action == "trade":
        if direction == "short":
            entry = primary_strike["zone_price"] if primary_strike else round(last_price * 1.001, 4)
            stop = round(entry * 1.008, 4)
            t1 = round(entry * 0.985, 4)
            t2 = round(entry * 0.970, 4)
            risk = stop - entry
            reward = entry - t1
            rr = round(reward / risk, 2) if risk > 0 else 1.5
            invalidation = f"5m candle close above stop {stop} or regime flip to long_only"
        else:
            entry = primary_strike["zone_price"] if primary_strike else round(last_price * 0.999, 4)
            stop = round(entry * 0.992, 4)
            t1 = round(entry * 1.015, 4)
            t2 = round(entry * 1.030, 4)
            risk = entry - stop
            reward = t1 - entry
            rr = round(reward / risk, 2) if risk > 0 else 1.5
            invalidation = f"5m candle close below stop {stop} or regime flip to short_only"
        targets = [t1, t2]
    else:
        entry = None
        stop = None
        targets = None
        rr = None
        invalidation = "n/a"

    return {
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
        "evidence": evidence,
        "invalidation": invalidation,
        "stale": stale_sections,
    }


def fetch_all_curated_symbols(terminal: str) -> list[str]:
    """Fetches the 58 core curated perpetual symbols (30 crypto + 28 tradfi)."""
    # Canonical list of 58 curated perps (matches src/lib/universe/curated.ts)
    crypto_30 = [
        "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "TRX", "LINK", "LTC",
        "AVAX", "DOT", "NEAR", "UNI", "ATOM", "XLM", "ETC", "FIL", "ICP", "HBAR",
        "APT", "ARB", "OP", "SUI", "SEI", "INJ", "TIA", "VET", "1000PEPE", "1000SHIB"
    ]
    tradfi_28 = [
        "XAU", "NVDA", "SNDK", "SOXL", "SPCX", "GOOGL", "MU", "SKHY", "XAG", "CL",
        "INTC", "CRCL", "MSTR", "QQQ", "ANTHROPIC", "AAPL", "TSLA", "DRAM", "KORU", "META",
        "NBIS", "MSFT", "AMZN", "AMD", "COIN", "NFLX", "AVGO", "TSM"
    ]
    return crypto_30 + tradfi_28


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch dump and formulate trades for curated terminal assets")
    ap.add_argument("--symbols", help="comma-separated symbols, or omit for all 58 curated assets")
    ap.add_argument("--limit", type=int, default=None, help="max symbols to evaluate (default all)")
    ap.add_argument("--from-dumps", action="store_true", help="evaluate from existing dumps in data/llm-dump/ rather than re-dumping")
    ap.add_argument("--terminal", default=TERMINAL)
    a = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Resolve symbols
    if a.symbols:
        sym_list = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    else:
        sym_list = fetch_all_curated_symbols(a.terminal)

    if a.limit and len(sym_list) > a.limit:
        sym_list = sym_list[:a.limit]

    log("batch", f"Starting batch {'evaluation from disk' if a.from_dumps else 'dump & playbook formulation'} for {len(sym_list)} curated assets...")

    results = []

    for i, sym in enumerate(sym_list):
        t0 = time.time()
        try:
            dump_file = Path("data/llm-dump") / f"{sym}_latest.json"
            if a.from_dumps and dump_file.exists():
                log("dump", f"[{i+1}/{len(sym_list)}] Reading existing 8-tab dump for {sym}...")
                dump = json.loads(dump_file.read_text(encoding="utf-8"))
            else:
                log("dump", f"[{i+1}/{len(sym_list)}] Fetching fresh 8-tab data for {sym}...")
                dump = dump_symbol_parallel(a.terminal, sym, full=False)
                write_dump(dump, sym)

            # Formulate
            formulation = evaluate_asset_playbook(dump, sym)
            results.append(formulation)

            # Save formulation JSON
            f_path = OUT_DIR / f"{sym}_formulation.json"
            f_path.write_text(json.dumps(formulation, indent=2))

            status_desc = f"{formulation['action'].upper()} ({formulation.get('direction') or 'none'}) · Confluence={formulation['confluence']} · Grade={formulation.get('grade')}"
            log("formulate", f"{sym}: {status_desc} ({time.time()-t0:.1f}s)")
        except Exception as e:
            import traceback
            log("error", f"{sym} failed: {e}\n{traceback.format_exc()}")
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

        if not a.from_dumps:
            # Polite delay to respect Coinglass upstream rate bounds
            time.sleep(0.3)

    # 2. Build Master Report
    log("report", f"Compiling Master Report to {REPORT_PATH}...")

    # Sort results: A-grade first, then B-grade, then by confluence descending
    results.sort(key=lambda x: (
        0 if x.get("grade") == "A" else (1 if x.get("grade") == "B" else 2),
        -x.get("confluence", 0)
    ))

    trades_a = [r for r in results if r.get("grade") == "A"]
    trades_b = [r for r in results if r.get("grade") == "B"]
    watches = [r for r in results if r.get("action") == "no-trade"]

    report_lines = [
        "# ALL-ASSET PLAYBOOK TRADE FORMULATION REPORT",
        f"> **Generated UTC**: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"> **Evaluated Universe**: {len(results)} Curated Assets (30 Crypto USDT-M + 28 TradFi USDT-M)",
        f"> **Decision Engine**: `desk/LLM_TRADE_FORMULATION_PLAYBOOK.md` (5m EMA-233 trend-gated, 8-tab confluence)",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        f"- **A-Grade High-Conviction Trades (Confluence >= 7)**: **{len(trades_a)}**",
        f"- **B-Grade Secondary Trades (Confluence 5–6)**: **{len(trades_b)}**",
        f"- **No-Trade / Surveillance Watchlist**: **{len(watches)}**",
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
        report_lines.append("| — | No A/B Grade Trades Active | — | — | — | — | — | — | — | — | Market in low-confluence weekend consolidation |")
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

    if actionable:
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
    else:
        report_lines.append("No assets currently qualify for A or B grade trade formulation under the strict playbook confluence rules.\n")

    report_lines.extend([
        "---",
        "",
        "## 4. Complete 58-Asset Surveillance Matrix",
        "",
        "| Symbol | Category | Regime | Action | Grade | Confluence | Primary Evidence / Rejection Reason |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :--- |"
    ])

    crypto_set = set(fetch_all_curated_symbols(a.terminal)[:30])

    for r in results:
        ev_summary = r.get("evidence", ["n/a"])[0] if r.get("evidence") else "n/a"
        grade_str = r.get("grade") or "—"
        act_str = f"`{r['action'].upper()}`" + (f" ({r['direction']})" if r.get("direction") else "")
        cat_str = "Crypto" if r["sym"] in crypto_set else "TradFi"
        report_lines.append(
            f"| **{r['sym']}** | {cat_str} | `{r['regime']}` | {act_str} | {grade_str} | {r['confluence']}/10 | {ev_summary} |"
        )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")
    log("complete", f"Successfully evaluated {len(results)} assets. Report saved to {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
