#!/usr/bin/env python3
"""
LLM Data Dumper — all terminal tabs → one structured JSON
=========================================================

Runs against the local order-flow terminal (Next.js, port 3000) and dumps
EVERY tab the desk watches, via the terminal's own API, into a single
well-structured JSON file a local LLM can read for analysis and trade
formulation:

  market       Overview    — price, auction POC/VAH/VAL (session/day/week/month),
                            EMA 13/89/233 (m15/h1/h4/d1), day VWAP ±σ
  signals      Footprint   — Coinglass-exact Absorption / Divergence / Trap /
                            Exhaustion signals (time + volume + range bars)
  footprint    Footprint   — aggregated 5m order-flow bars: OHLC, per-row
                            taker buy/sell grid, POC, per-bar OI
  large_orders Large Orders— resting whale walls + executed large trades
  liq_levels   Liq Levels  — liquidation key levels ±4%, clusters 3d/7d/30d
  book_walls   Book Walls  — multi-venue depth/imbalance (now vs 5m ago),
                            confirmed walls with age/touched, add/fill/pull
  cvd          CVD         — perp/spot cumulative volume delta, taker share
  tracker      this repo   — EMA-233 trend gate (below → SHORT-only,
                            above → LONG-only) + key-level finished-auction
                            strikes on the 5m footprint

Usage:
  python3 scripts/trading/dump_for_llm.py                          # BTC, one shot
  python3 scripts/trading/dump_for_llm.py --sym SOL                # any symbol
  python3 scripts/trading/dump_for_llm.py --sym "BTC,ETH,SOL"      # one file each
  python3 scripts/trading/dump_for_llm.py --sym BTC --watch 300    # re-dump every 5 min
  python3 scripts/trading/dump_for_llm.py --sym BTC --full         # untrimmed raw

Files land in data/llm-dump/ (gitignored):
  <SYM>_<utc-timestamp>.json   timestamped snapshot
  <SYM>_latest.json            same content, stable name (overwritten)

Every section carries its own `updatedAt` / `source`. Liquidation and
whale figures are Coinglass ESTIMATES (flagged in `_meta`). If a section
fails it becomes {"error": "..."} — the rest of the dump still writes.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from key_level_auction_tracker import EMA_LEN, KLINE_WARMUP, scan_symbol  # noqa: E402

TERMINAL = "http://localhost:3000"
OUT_DIR = Path("data/llm-dump")
REQ_TIMEOUT = 30

FP_BARS = 60          # 5m bars = 5 hours of footprint (default trim)
CVD_BARS = 60
WALL_EVENTS = 20      # book-wall events kept in the trimmed view
LARGE_LIST = 15       # large orders per group in the trimmed view

GUIDE = {
    "purpose": "Live order-flow snapshot for trade formulation. Read _guide, then market (trend/EMAs/VWAP), "
               "then tracker.strikes (zone strikes with finished auctions), then confirm with the micro tabs.",
    "trend_rule": "tracker.trend.gate is the hard filter: short_only → only SHORT setups are valid; "
                  "long_only → only LONG. Counter-trend signals are already suppressed.",
    "best_signals": {
        "zone_strike": "price hit a liquidation key level AND the 5m footprint auction finished against it "
                       "(tracker.strikes[]; dominance_ratio = top-row buy/sell asymmetry, higher = cleaner)",
        "absorption": "high volume, flat result — the aggressor is being absorbed (signals.sets)",
        "cvd_divergence": "price makes a new extreme, CVD does not (cvd.activeDivergences / perp vs spot)",
        "book_wall": "confirmed wall near price with age + touches — magnet then barrier (book_walls.model.walls)",
    },
    "field_notes": {
        "market.auction": "POC = highest-volume price; VAH/VAL = value area bounds, per session",
        "market.ema": "13 = fast trigger, 89 = swing, 233 = regime (the tracker gate uses the 5m 233)",
        "footprint.bars[].fp": "per price-row taker buy 'b' / sell 's' (top rows = the bar's high); "
                               "'lo' = grid low, 'tick' = row height",
        "liq_levels.stats.keyLevels": "above = SHORT liquidations cluster (resistance/fuel for down-move); "
                                      "below = LONG liquidations (support/fuel for up-move). Coinglass estimates.",
        "large_orders": "resting = walls still in the book; executed = large trades already filled",
        "book_walls.model.imbalance": ">0 bid-heavy, <0 ask-heavy; compare with imbalance5mAgo",
    },
    "honesty": "Liquidation/whale/wall figures are Coinglass ESTIMATES, not exchange truth. "
               "Each section has its own updatedAt — prefer the freshest when they disagree.",
}


def log(tag: str, msg: str) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"{ts} [{tag}] {msg}", file=sys.stderr, flush=True)


def http_get(base: str, path: str) -> dict[str, Any]:
    req = urllib.request.Request(f"{base}{path}", headers={"User-Agent": "llm-dump/1.0"})
    with urllib.request.urlopen(req, timeout=REQ_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def section(fn):
    """Wrap a fetcher: failures become {"error": ...} instead of killing the dump."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (urllib.error.URLError, OSError, ValueError, RuntimeError, KeyError) as e:
            return {"error": f"{type(e).__name__}: {e}"}
    return wrapper


@section
def sec_market(base: str, sym: str) -> dict[str, Any]:
    d = http_get(base, f"/api/cg/market?sym={sym}")
    if not d.get("ok"):
        return {"error": d.get("error", "not ok")}
    keep = {k: d.get(k) for k in ("sym", "name", "kind", "source", "priceDecs",
                                  "price", "auction", "ema", "vwap", "funding", "oi", "updatedAt")
            if d.get(k) is not None}
    return keep


@section
def sec_signals(base: str, sym: str) -> dict[str, Any]:
    d = http_get(base, f"/api/cg/signals?sym={sym}")
    if not d.get("ok"):
        return {"error": d.get("error", "not ok")}
    return {k: d.get(k) for k in ("bt", "counts", "thresholds", "sets", "updatedAt") if d.get(k) is not None}


@section
def sec_footprint(base: str, sym: str, full: bool) -> dict[str, Any]:
    # NOTE: no &live=1 here — the live lane caps limit at 12 bars (it exists
    # for the forming bar on the UI page). The plain call serves full history.
    d = http_get(base, f"/api/cg/fp?sym={sym}&itv=m5&limit={FP_BARS}")
    if not d.get("ok"):
        return {"error": d.get("reason") or d.get("error") or "not ok"}
    out = {k: d.get(k) for k in ("sym", "itv", "venues", "missing", "updatedAt") if d.get(k) is not None}
    out["bars"] = d.get("bars") or []
    if not full:
        # trim each bar's grid to the rows that matter for auction reads:
        # bottom 3 + top 6 native rows (opens/closes of the bar's range)
        for b in out["bars"]:
            fp = b.get("fp") or {}
            for k in ("b", "s"):
                rows = fp.get(k)
                if isinstance(rows, list) and len(rows) > 9:
                    fp[k] = rows[:3] + rows[-6:]
    return out


@section
def sec_large_orders(base: str, sym: str, full: bool) -> dict[str, Any]:
    d = http_get(base, f"/api/cg/largeorder?sym={sym}")
    if not d.get("ok"):
        return {"error": d.get("error", "not ok")}
    out = {"groups": d.get("groups") or []}
    if not full:
        for g in out["groups"]:
            lst = g.get("list")
            if isinstance(lst, list):
                g["list"] = lst[:LARGE_LIST]
            g["n_total"] = len(lst) if isinstance(lst, list) else 0
    return out


@section
def sec_liq_levels(base: str, sym: str) -> dict[str, Any]:
    d = http_get(base, f"/api/cg/liqlevels?sym={sym}")
    if not d.get("ok"):
        return {"error": d.get("error", "not ok")}
    return {k: d.get(k) for k in ("range", "venues", "perVenue", "stats", "livePrice",
                                  "stale", "partial", "updatedAt") if d.get(k) is not None}


@section
def sec_book_walls(base: str, sym: str, full: bool) -> dict[str, Any]:
    d = http_get(base, f"/api/cg/bookwalls?sym={sym}&interval=5m")
    if not d.get("ok"):
        return {"error": d.get("error", "not ok")}
    m = dict(d.get("model") or {})
    out = {k: d.get(k) for k in ("sym", "market", "interval", "venues", "minWallUsd", "updatedAt")
           if d.get(k) is not None}
    if not full and m:
        ev = m.get("events")
        if isinstance(ev, list):
            m["events"] = ev[:WALL_EVENTS]
        m.pop("strip", None)     # raw heat grid — huge, low value for the LLM
        m.pop("ladder", None)
        m.pop("snapshots", None)
    out["model"] = m
    return out


@section
def sec_cvd(base: str, sym: str) -> dict[str, Any]:
    d = http_get(base, f"/api/cg/cvd?sym={sym}&itv=5m&limit={CVD_BARS}")
    if not d.get("ok"):
        return {"error": d.get("error", "not ok")}
    out = {k: d.get(k) for k in ("sym", "itv", "mode", "anchor", "instruments", "n",
                                  "activeDivergences", "updatedAt")
           if d.get(k) is not None}
    # candles/perp/spot come back at engine length (300) regardless of the
    # requested limit — keep only the last CVD_BARS rows so the dump stays lean
    for k in ("candles", "perp", "spot"):
        v = d.get(k)
        if isinstance(v, list):
            out[k] = v[-CVD_BARS:]
    return out


@section
def sec_tracker(base: str, sym: str) -> dict[str, Any]:
    r = scan_symbol(base, sym, "m5")
    if not r.ok:
        return {"error": r.error}
    t = r.trend
    assert t is not None
    return {
        "description": f"key-level finished-auction scan, EMA-{EMA_LEN} m5 gate "
                       f"({KLINE_WARMUP} kline closes seed)",
        "ok": True,
        "price": r.price,
        "trend": {
            "tf": t.tf,
            "ema233": t.ema,
            "price": t.price,
            "gate": t.gate,            # short_only | long_only | neutral
            "rule": "price below ema233 → SHORTs only; above → LONGs only",
        },
        "zones_near": r.zones_near,
        "zones_total": r.zones_total,
        "bars_scanned": r.bars,
        "suppressed_by_trend": r.suppressed,
        "strikes": [
            {
                "dir": s.dir,
                "time_utc": time.strftime("%Y-%m-%dT%H:%M", time.gmtime(s.bar_ts)),
                "zone_price": s.zone.price,
                "zone_usd": s.zone.usd,
                "zone_lev": s.zone.lev,
                "zone_strength": s.zone.strength,
                "bar_close": s.bar_close,
                "top3_buy": s.top_buy,
                "top3_sell": s.top_sell,
                "dominant": s.dominant,
                "dominance_ratio": None if s.dominance_ratio == float("inf") else s.dominance_ratio,
                "ema233_at_strike": t.at_ts(s.bar_ts),
                "note": s.note,
            }
            for s in r.strikes
        ],
    }


def dump_symbol(base: str, sym: str, full: bool) -> dict[str, Any]:
    return {
        "_guide": GUIDE,
        "_meta": {
            "generatedAt": int(time.time()),
            "generatedAtUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "terminal": base,
            "sym": sym,
            "full": full,
            "sources": "local terminal API (/api/cg/*) — live Coinglass/Binance data, no mocks",
            "estimates": "liquidation/whale/wall figures are Coinglass estimates",
        },
        "market": sec_market(base, sym),
        "signals": sec_signals(base, sym),
        "footprint": sec_footprint(base, sym, full),
        "large_orders": sec_large_orders(base, sym, full),
        "liq_levels": sec_liq_levels(base, sym),
        "book_walls": sec_book_walls(base, sym, full),
        "cvd": sec_cvd(base, sym),
        "tracker": sec_tracker(base, sym),
    }


def write_dump(doc: dict[str, Any], sym: str) -> list[Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    paths = [OUT_DIR / f"{sym}_{stamp}.json", OUT_DIR / f"{sym}_latest.json"]
    for p in paths:
        p.write_text(json.dumps(doc, indent=1))
    return paths


def run(base: str, syms: list[str], full: bool) -> None:
    for sym in syms:
        sym = sym.strip().upper()
        t0 = time.time()
        doc = dump_symbol(base, sym, full)
        errs = [k for k, v in doc.items() if isinstance(v, dict) and "error" in v]
        paths = write_dump(doc, sym)
        size = paths[0].stat().st_size
        log("dump", f"{sym}: {'OK' if not errs else 'partial (' + ', '.join(errs) + ' ERROR)'} · "
                    f"{size/1024:.0f} KB · {time.time()-t0:.1f}s")
        log("dump", f"  → {paths[0]}")
        log("dump", f"  → {paths[1]} (latest)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Dump all terminal tabs to one structured JSON for LLM analysis")
    ap.add_argument("--sym", default="BTC", help="symbol or comma-separated list (default BTC)")
    ap.add_argument("--watch", type=int, metavar="SECS", help="re-dump every SECS (default one-shot)")
    ap.add_argument("--full", action="store_true", help="no trimming — raw API payloads")
    ap.add_argument("--terminal", default=TERMINAL)
    a = ap.parse_args()
    syms = [s for s in a.sym.split(",") if s.strip()]
    try:
        if a.watch:
            log("boot", f"llm-dump watch · {'/'.join(syms)} · every {a.watch}s · full={a.full}")
            while True:
                run(a.terminal, syms, a.full)
                log("sleep", f"{a.watch}s")
                time.sleep(a.watch)
        else:
            run(a.terminal, syms, a.full)
        return 0
    except KeyboardInterrupt:
        log("exit", "interrupted")
        return 0
    except Exception as e:  # noqa: BLE001 — CLI boundary
        log("fatal", str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
