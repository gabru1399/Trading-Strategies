#!/usr/bin/env python3
"""
Key-Level + Finished-Auction Tracker — 5m
==========================================

Operator setup (2026-11-22): enter when price STRIKES one of the key
liquidation zones built in the Liq Levels tab AND the 5m footprint shows a
FINISHED AUCTION against the strike:

  SHORT: price rallies into a key SHORT zone (liquidation cluster above
         price) and the auction finishes with ZERO AT TOP — the top rows of
         the striking 5m bar print sells ≈ 0 / buys exhausted (buy == 0 or
         sell >= ratio x buy in the top-N native rows). The rally ran out of
         buyers into the zone where shorts (forced liquidations of shorts…
         actually: the zone is where SHORT positions get liquidated, i.e.
         buy-side fuel) — fade it.

  LONG: price declines into a key LONG zone and the top rows show buys
        overwhelming (buy >= ratio x sell). The decline died — buy it.

Everything is driven by the terminal's own API (no third-party calls, no
mock data): /api/cg/liqlevels for the zones, /api/cg/fp?itv=m5 for the 5m
aggregated footprint (Binance+OKX+Bybit+Hyperliquid — the Coinglass
aggregated method). Liquidation/whale figures are Coinglass ESTIMATES.

Usage:
  python3 scripts/trading/key_level_auction_tracker.py --sym BTC --once
  python3 scripts/trading/key_level_auction_tracker.py --sym BTC --watch
  python3 scripts/trading/key_level_auction_tracker.py --sym BTC --scan 61  # all curated
  python3 scripts/trading/key_level_auction_tracker.py --self-test

Output: JSON lines on stdout (one event per line) + human summary to stderr.
Exit code 0 always (a scanner, not a gate); use --json for machine parsing.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Any

TERMINAL = "http://localhost:3000"
TOP_ROWS = 3          # native rows at the bar's top examined for the auction
DOMINANCE = 3.0       # sell >= 3x buy (or buy >= 3x sell) = dominated
ZONE_WIN_PCT = 4.0    # only zones within +/- 4% of price are strike targets
SCAN_BARS = 40        # bars of 5m history scanned for strikes
POLL_SECS = 20        # --watch cadence (5m bars; 20s is plenty responsive)
REQ_TIMEOUT = 25


# ---------------------------------------------------------------------------
# data plumbing (stdlib only — no requests dependency)
# ---------------------------------------------------------------------------

def http_get(path: str) -> dict[str, Any]:
    url = f"{TERMINAL}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "key-level-tracker/1.0"})
    with urllib.request.urlopen(req, timeout=REQ_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_zones(sym: str) -> list[dict[str, Any]]:
    """Key liquidation levels from the Liq Levels tab (Coinglass estimates)."""
    d = http_get(f"/api/cg/liqlevels?sym={sym}")
    if not d.get("ok"):
        raise RuntimeError(f"liqlevels failed for {sym}: {d.get('error', 'unknown')}")
    kl = (d.get("stats") or {}).get("keyLevels") or {}
    out: list[dict[str, Any]] = []
    for side, arr in (("short", kl.get("above") or []), ("long", kl.get("below") or [])):
        for z in arr or []:
            out.append(
                {
                    "side": side,          # side of the LIQUIDATIONS at that price
                    "price": float(z["price"]),
                    "distPct": float(z.get("distPct", 0.0)),
                    "lev": z.get("lev", "?"),
                    "strength": float(z.get("strength", 0.0)),
                    "usd": float(z.get("usd", 0.0)),
                }
            )
    return out


def fetch_fp_5m(sym: str, limit: int = SCAN_BARS) -> dict[str, Any]:
    """5m aggregated footprint bars (same pipeline the Footprint tab renders)."""
    return http_get(f"/api/cg/fp?sym={sym}&itv=m5&limit={limit}")


# ---------------------------------------------------------------------------
# finished-auction logic — mirrors footprint-tool.tsx zoneStrikes 1:1
# ---------------------------------------------------------------------------

@dataclass
class Bar:
    ts: int
    o: float
    h: float
    l: float
    c: float
    tick: float
    lo: float
    b: list[float]
    s: list[float]

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Bar | None":
        fp = raw.get("fp")
        if not fp or not fp.get("b"):
            return None
        return cls(
            ts=int(raw["ts"]),
            o=float(raw["o"]),
            h=float(raw["h"]),
            l=float(raw["l"]),
            c=float(raw["c"]),
            tick=float(fp["tick"]),
            lo=float(fp["lo"]),
            b=[float(x) for x in fp["b"]],
            s=[float(x) for x in fp["s"]],
        )

    def top_rows_split(self, n: int = TOP_ROWS) -> tuple[float, float]:
        """Buy/sell volume of the topmost n native rows (highest prices)."""
        buy = sum(self.b[len(self.b) - n:] if len(self.b) >= n else self.b)
        sell = sum(self.s[len(self.s) - n:] if len(self.s) >= n else self.s)
        return buy, sell

    def struck(self, price: float) -> bool:
        """Did this bar's range trade through the zone price?"""
        return self.h >= price >= self.l


@dataclass
class Strike:
    dir: str                   # "short" | "long" — the trade direction
    zone_side: str             # "short" (above) | "long" (below)
    zone_price: float
    zone_usd: float
    zone_lev: str
    zone_strength: float
    bar_ts: int
    bar_close: float
    top_buy: float
    top_sell: float
    dominant: str              # "buy" | "sell" | "flat"
    dominance_ratio: float     # dominant/other (inf when other == 0)
    finished_auction: bool = True
    note: str = ""


def evaluate_strike(bar: Bar, zone: dict[str, Any]) -> Strike | None:
    """Return a Strike if bar touched the zone AND the auction finished."""
    if not bar.struck(zone["price"]):
        return None
    buy, sell = bar.top_rows_split(TOP_ROWS)
    dom_ratio: float
    if zone["side"] == "short":
        # SHORT setup: auction finished against the rally — zero/dominated
        # buys at the top (sellers absorbed everything up there)
        finished = buy <= 0.0 or sell >= DOMINANCE * buy
        dominant = "sell" if sell > buy else ("buy" if buy > sell else "flat")
        dom_ratio = (sell / buy) if buy > 0 else (math.inf if sell > 0 else 0.0)
        note = "rally struck short zone, top rows zero/dominated by sells"
    else:
        # LONG setup: decline died — buys dominate the top rows
        finished = sell <= 0.0 or buy >= DOMINANCE * sell
        dominant = "buy" if buy > sell else ("sell" if sell > buy else "flat")
        dom_ratio = (buy / sell) if sell > 0 else (math.inf if buy > 0 else 0.0)
        note = "decline struck long zone, top rows dominated by buys"
    if not finished:
        return None
    return Strike(
        dir=zone["side"],
        zone_side=zone["side"],
        zone_price=zone["price"],
        zone_usd=zone["usd"],
        zone_lev=zone["lev"],
        zone_strength=zone["strength"],
        bar_ts=bar.ts,
        bar_close=bar.c,
        top_buy=buy,
        top_sell=sell,
        dominant=dominant,
        dominance_ratio=dom_ratio,
        note=note,
    )


def scan_symbol(sym: str) -> dict[str, Any]:
    zones = fetch_zones(sym)
    fp = fetch_fp_5m(sym)
    if not fp.get("ok"):
        return {"sym": sym, "ok": False, "error": fp.get("error", "no data")}
    bars = [b for b in (Bar.from_api(x) for x in fp.get("bars") or []) if b]
    live = fp.get("updatedAt")
    price_ref = fp["bars"][-1]["c"] if fp.get("bars") else None
    near = [z for z in zones if price_ref and abs(z["distPct"]) <= ZONE_WIN_PCT]
    strikes: list[Strike] = []
    for bar in bars:
        for zone in near:
            st = evaluate_strike(bar, zone)
            if st:
                strikes.append(st)
    strikes.sort(key=lambda s: (s.bar_ts, s.zone_strength), reverse=True)
    return {
        "sym": sym,
        "ok": True,
        "price": price_ref,
        "updatedAt": live,
        "zones_total": len(zones),
        "zones_near": len(near),
        "bars_scanned": len(bars),
        "strikes": [asdict(s) for s in strikes[:6]],
    }


# ---------------------------------------------------------------------------
# self-test — synthetic bars/zones, no network
# ---------------------------------------------------------------------------

def self_test() -> int:
    t0 = 1_700_000_000
    # 6-row grid, tick 5 → prices 90..120; top-3 rows = indices 3,4,5.
    # mk(i, lo, hi, top_b, top_s): top-3 buy = top_b, top-3 sell = top_s.
    mk = lambda i, lo, hi, top_b, top_s: Bar(  # noqa: E731
        ts=t0 + i * 300, o=lo, h=hi, l=lo, c=hi,
        tick=5.0, lo=lo,
        b=[10.0, 10.0, 10.0, 0.0, top_b, 0.0],
        s=[10.0, 10.0, 10.0, 0.0, top_s, 0.0],
    )
    zone_short = {"side": "short", "price": 105.0, "distPct": 2.0, "lev": "High", "strength": 80.0, "usd": 1.5e6}
    zone_long = {"side": "long", "price": 95.0, "distPct": -2.0, "lev": "Mid", "strength": 60.0, "usd": 9.0e5}

    # 1. rally into short zone, top rows: buy 1, sell 9 → 9x dominated → SHORT
    bar = mk(1, 90.0, 106.0, 1.0, 9.0)
    st = evaluate_strike(bar, zone_short)
    assert st is not None and st.dir == "short", "expected finished SHORT strike"
    assert st.dominant == "sell" and st.dominance_ratio == 9.0

    # 2. rally into short zone, top rows buy 9 sell 1 → auction NOT finished
    bar = mk(2, 90.0, 106.0, 9.0, 1.0)
    assert evaluate_strike(bar, zone_short) is None, "must reject unfinished auction"

    # 3. buy == 0 at top → zero-at-top → SHORT even with sell == 0
    bar = mk(3, 90.0, 106.0, 0.0, 0.0)
    st = evaluate_strike(bar, zone_short)
    assert st is not None and st.dominance_ratio == 0.0 and st.dominant == "flat"

    # 4. bar does NOT reach the zone → no strike
    bar = mk(4, 90.0, 100.0, 1.0, 9.0)
    assert evaluate_strike(bar, zone_short) is None

    # 5. decline into long zone, top rows buy 12 sell 2 → 6x → LONG
    bar = mk(5, 106.0, 110.0, 12.0, 2.0)
    bar.l = 94.0  # bar spans down through the long zone
    st = evaluate_strike(bar, zone_long)
    assert st is not None and st.dir == "long" and st.dominance_ratio == 6.0

    # 6. top_rows_split reads the TOP (highest price) rows — explicit tall grid
    tall = Bar(ts=t0, o=90, h=110, l=90, c=110, tick=5.0, lo=90,
               b=[5.0, 5.0, 0.0, 7.0], s=[5.0, 5.0, 0.0, 1.0])
    tb, ts_ = tall.top_rows_split(3)
    assert (tb, ts_) == (5.0 + 0.0 + 7.0, 5.0 + 0.0 + 1.0), (tb, ts_)

    print("self-test: 6/6 passed")
    return 0


# ---------------------------------------------------------------------------
# modes
# ---------------------------------------------------------------------------

def run_once(sym: str, as_json: bool) -> dict[str, Any]:
    res = scan_symbol(sym)
    if as_json:
        print(json.dumps(res))
    else:
        if not res.get("ok"):
            print(f"[{sym}] ERROR: {res.get('error')}", file=sys.stderr)
            return res
        print(f"[{sym}] price={res['price']} zones(near/total)={res['zones_near']}/{res['zones_total']} bars={res['bars_scanned']}")
        for s in res["strikes"]:
            ratio = "inf" if math.isinf(s["dominance_ratio"]) else f"{s['dominance_ratio']:.1f}x"
            print(
                f"  {time.strftime('%H:%M', time.gmtime(s['bar_ts']))}  {s['dir'].upper():5} zone "
                f"{s['zone_price']} (${s['zone_usd']/1e6:.1f}M {s['zone_lev']} str{round(s['zone_strength'])}) "
                f"top{TOP_ROWS} buy {s['top_buy']:.4g} / sell {s['top_sell']:.4g}  {s['dominant']} {ratio}"
            )
        if not res["strikes"]:
            print("  no finished-auction strikes in the scanned window")
    return res


def run_watch(sym: str) -> None:
    seen: set[tuple[int, float]] = set()
    print(f"[watch] {sym} — polling every {POLL_SECS}s, Ctrl-C to stop", file=sys.stderr)
    while True:
        try:
            res = scan_symbol(sym)
            for s in res.get("strikes") or []:
                key = (s["bar_ts"], s["zone_price"])
                if key in seen:
                    continue
                seen.add(key)
                print(json.dumps({"event": "zone_strike", "sym": sym, **s}))
                sys.stdout.flush()
        except (urllib.error.URLError, RuntimeError, OSError) as e:
            print(json.dumps({"event": "error", "sym": sym, "error": str(e)}))
            sys.stdout.flush()
        time.sleep(POLL_SECS)


def run_scan(limit: int) -> None:
    try:
        cur = http_get("/api/cg/symbols")  # may not exist; fall back below
        syms = [s for s in (cur.get("symbols") or [])][:limit]
    except Exception:
        syms = []
    if not syms:
        syms = [
            "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "TRX", "LINK", "LTC",
            "AVAX", "DOT", "NEAR", "UNI", "ATOM", "XLM", "ETC", "FIL", "ICP", "HBAR",
            "APT", "ARB", "OP", "SUI", "SEI", "INJ", "TIA", "VET", "1000PEPE", "1000SHIB",
        ][:limit]
    hits = 0
    for sym in syms:
        try:
            res = run_once(sym, as_json=False)
            hits += len(res.get("strikes") or []) if res.get("ok") else 0
        except Exception as e:
            print(f"[{sym}] error: {e}", file=sys.stderr)
    print(f"[scan] {len(syms)} symbols, {hits} strikes", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sym", default="BTC")
    ap.add_argument("--once", action="store_true", help="single scan (default)")
    ap.add_argument("--watch", action="store_true", help="poll and emit new strikes as JSON lines")
    ap.add_argument("--scan", type=int, metavar="N", help="scan N curated symbols")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    try:
        if a.self_test:
            return self_test()
        if a.scan:
            run_scan(a.scan)
        elif a.watch:
            run_watch(a.sym)
        else:
            run_once(a.sym, a.json)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"fatal: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
