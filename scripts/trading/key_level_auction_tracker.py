#!/usr/bin/env python3
"""
Key-Level + Finished-Auction Tracker — 5m, EMA-233 trend-gated
==============================================================

Operator setup (2026-11-22):

  1. Price STRIKES one of the key liquidation zones built in the Liq Levels
     tab (±4% window, Coinglass estimates).
  2. The 5m footprint prints a FINISHED AUCTION against the strike:
       SHORT — rally into a short zone, top-3 rows zero/dominated by sells
               (buy == 0 or sell >= dominance × buy)
       LONG  — decline into a long zone, top-3 rows dominated by buys
               (sell == 0 or buy >= dominance × sell)
  3. TREND GATE: price BELOW the 233 EMA → SHORTS ONLY. Above → LONGS
     ONLY. Signals against the trend are suppressed and counted in the
     logs, never shown as entries.

The EMA is computed on the same 5m series you trade by default (--ema-tf
m5, seeded from 600 kline closes, evaluated at each strike bar's own
timestamp); --ema-tf m15|h1|h4|d1 uses the terminal's precomputed EMA
snapshot from /api/cg/market applied to all strikes.

Scans EVERY asset that has both footprint and liquidation key levels
(the curated universe, capability-probed at runtime — exotics without a
footprint feed are skipped and reported in the logs).

Usage:
  python3 scripts/trading/key_level_auction_tracker.py --sym BTC --once
  python3 scripts/trading/key_level_auction_tracker.py --sym BTC --watch
  python3 scripts/trading/key_level_auction_tracker.py --scan 30      # one sweep, first 30 curated
  python3 scripts/trading/key_level_auction_tracker.py --watch-all    # every capable asset, forever

  --ema-tf m5|m15|h1|h4|d1   trend timeframe (default m5)
  --dominance 3.0            finished-auction dominance ratio
  --zone-win 4.0             strike window around price (%)
  --interval 120             watch-all sweep cadence (s)
  --terminal http://…        terminal base URL (default localhost:3000)
  --json                     machine-readable events on stdout
  --self-test                offline unit tests

Logs go to stderr (timestamps, sweep summaries, one [STRIKE] block per
new candidate); --json events go to stdout, one JSON object per line.

Liquidation/whale figures are Coinglass ESTIMATES. No finished auction or
no trend alignment → no entry. This scanner never fabricates a signal.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# knobs (defaults; dominance/zone-win are CLI-overridable)
# ---------------------------------------------------------------------------

TERMINAL = "http://localhost:3000"
TOP_ROWS = 3           # native rows at the bar's top examined for the auction
DOMINANCE = 3.0        # sell >= 3x buy (or buy >= 3x sell) = dominated
ZONE_WIN_PCT = 4.0     # only zones within +/- 4% of price are strike targets
SCAN_BARS = 40         # bars of 5m history scanned for strikes
EMA_LEN = 233
KLINE_WARMUP = 600     # 5m closes fetched for the EMA (≈2 days, well-seeded)
POLL_SECS_SINGLE = 20  # --watch (single symbol)
POLL_SECS_ALL = 120    # --watch-all sweep cadence
REQ_TIMEOUT = 25
SYM_GAP = 0.12         # gentle pacing between symbols in a sweep
SEEN_FILE = Path("data/key-level-tracker/seen.json")

CURATED_FALLBACK = [
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "TRX", "LINK", "LTC",
    "AVAX", "DOT", "NEAR", "UNI", "ATOM", "XLM", "ETC", "FIL", "ICP", "HBAR",
    "APT", "ARB", "OP", "SUI", "SEI", "INJ", "TIA", "VET", "1000PEPE", "1000SHIB",
]


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def log(tag: str, msg: str) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"{ts} [{tag}] {msg}", file=sys.stderr, flush=True)


def fmt_qty(x: float) -> str:
    a = abs(x)
    if a >= 1e9:
        return f"{x/1e9:.2f}B"
    if a >= 1e6:
        return f"{x/1e6:.2f}M"
    if a >= 1e3:
        return f"{x/1e3:.1f}K"
    if a >= 100:
        return f"{x:.0f}"
    if a >= 1:
        return f"{x:.2f}"
    if a >= 0.01:
        return f"{x:.4f}"
    return f"{x:.6g}"


def fmt_px(x: float) -> str:
    return f"{x:,.6g}" if x < 1000 else f"{x:,.1f}"


def fmt_ratio(x: float) -> str:
    return "∞" if math.isinf(x) else f"{x:.1f}×"


def http_get(base: str, path: str) -> dict[str, Any]:
    req = urllib.request.Request(f"{base}{path}", headers={"User-Agent": "key-level-tracker/2.0"})
    with urllib.request.urlopen(req, timeout=REQ_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


# ---------------------------------------------------------------------------
# domain
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
            o=float(raw["o"]), h=float(raw["h"]), l=float(raw["l"]), c=float(raw["c"]),
            tick=float(fp["tick"]), lo=float(fp["lo"]),
            b=[float(x) for x in fp["b"]], s=[float(x) for x in fp["s"]],
        )

    def top_rows_split(self, n: int = TOP_ROWS) -> tuple[float, float]:
        buy = sum(self.b[-n:])
        sell = sum(self.s[-n:])
        return buy, sell

    def struck(self, price: float) -> bool:
        return self.h >= price >= self.l


@dataclass
class Zone:
    side: str            # "short" (cluster above price) | "long" (below)
    price: float
    dist_pct: float
    lev: str
    strength: float
    usd: float


@dataclass
class Strike:
    dir: str             # trade direction: "short" | "long"
    zone: Zone
    bar_ts: int
    bar_close: float
    top_buy: float
    top_sell: float
    dominant: str        # "buy" | "sell" | "flat"
    dominance_ratio: float
    note: str


@dataclass
class Trend:
    """EMA-233 gate — price below → shorts only, above → longs only."""

    ema: float
    price: float
    tf: str
    per_bar: bool = False           # True = ema_by_ts valid at each strike ts
    ema_by_ts: dict[int, float] = field(default_factory=dict, repr=False)

    @property
    def gate(self) -> str:
        """'short_only' | 'long_only' | 'neutral'."""
        if self.price < self.ema:
            return "short_only"
        if self.price > self.ema:
            return "long_only"
        return "neutral"

    def at_ts(self, ts: int) -> float:
        """EMA value at a strike bar (per-bar series) or the current value."""
        if not self.per_bar or not self.ema_by_ts:
            return self.ema
        if ts in self.ema_by_ts:
            return self.ema_by_ts[ts]
        keys = sorted(self.ema_by_ts)
        i = bisect.bisect_right(keys, ts) - 1
        return self.ema_by_ts[keys[max(0, i)]]

    def gate_at_ts(self, ts: int, close: float) -> str:
        ema = self.at_ts(ts)
        if close < ema:
            return "short_only"
        if close > ema:
            return "long_only"
        return "neutral"

    def allows(self, s: Strike) -> bool:
        gate = self.gate_at_ts(s.bar_ts, s.bar_close)
        return (s.dir == "short" and gate == "short_only") or (s.dir == "long" and gate == "long_only")


def ema_series(closes: list[float], n: int) -> list[float | None]:
    """Standard EMA seeded with the SMA of the first n closes."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) < n:
        return out
    alpha = 2.0 / (n + 1.0)
    e = sum(closes[:n]) / n
    out[n - 1] = e
    for i in range(n, len(closes)):
        e = alpha * closes[i] + (1.0 - alpha) * e
        out[i] = e
    return out


# ---------------------------------------------------------------------------
# fetchers
# ---------------------------------------------------------------------------


def fetch_zones(base: str, sym: str) -> list[Zone]:
    d = http_get(base, f"/api/cg/liqlevels?sym={sym}")
    if not d.get("ok"):
        raise RuntimeError(f"liqlevels: {d.get('error', 'unknown')}")
    kl = (d.get("stats") or {}).get("keyLevels") or {}
    out: list[Zone] = []
    for side, arr in (("short", kl.get("above") or []), ("long", kl.get("below") or [])):
        for z in arr or []:
            out.append(Zone(side, float(z["price"]), float(z.get("distPct", 0.0)),
                            str(z.get("lev", "?")), float(z.get("strength", 0.0)), float(z.get("usd", 0.0))))
    if not out:
        raise RuntimeError("liqlevels: no key levels in window")
    return out


def fetch_bars(base: str, sym: str, limit: int = SCAN_BARS) -> list[Bar]:
    d = http_get(base, f"/api/cg/fp?sym={sym}&itv=m5&limit={limit}")
    if not d.get("ok"):
        raise RuntimeError(f"footprint: {d.get('reason') or d.get('error') or 'no data'}")
    bars = [b for b in (Bar.from_api(x) for x in d.get("bars") or []) if b]
    if not bars:
        raise RuntimeError("footprint: no bars")
    return bars


def fetch_trend(base: str, sym: str, tf: str, bars: list[Bar]) -> Trend:
    """EMA-233 trend gate.

    m5 (default): exact — EMA computed over 600 kline closes and evaluated
    at each strike bar's own timestamp. Other TFs: the terminal's
    precomputed EMA snapshot from /api/cg/market applied to all strikes.
    """
    if tf != "m5":
        d = http_get(base, f"/api/cg/market?sym={sym}")
        ema = ((d.get("ema") or {}).get(tf) or {}).get("e233")
        price = (d.get("price") or {}).get("last")
        if ema is None or price is None:
            raise RuntimeError(f"market: no {tf} ema233")
        return Trend(ema=float(ema), price=float(price), tf=tf)
    # m5: EMA computed on the lead-venue (Binance) 5m candles — the same
    # series the footprint's OHLC rides. NOTE /api/cg/kline takes the
    # INSTRUMENT key (`symbol=Binance_XAUUSDT`), not `sym=` — passing sym
    # silently returns BTC candles, so the response symbol is verified.
    inst = f"Binance_{sym}USDT"
    d = http_get(base, f"/api/cg/kline?symbol={inst}&interval=m5&limit={KLINE_WARMUP}")
    got = str(d.get("symbol") or "")
    if got.replace("Binance_", "") != f"{sym}USDT":
        raise RuntimeError(f"kline: asked {inst}, got {got} — refusing (wrong-series guard)")
    rows = d.get("rows") or []
    closes = [float(r[4]) for r in rows]
    ts_list = [int(r[0]) for r in rows]
    emas = ema_series(closes, EMA_LEN)
    if emas[-1] is None:
        raise RuntimeError(f"kline: only {len(closes)} closes — need >= {EMA_LEN} for EMA-{EMA_LEN}")
    by_ts = {ts: e for ts, e in zip(ts_list, emas) if e is not None}
    # current price: prefer the freshest footprint close (live lane)
    price = bars[-1].c if bars else closes[-1]
    return Trend(ema=float(emas[-1]), price=price, tf="m5", per_bar=True, ema_by_ts=by_ts)


def fetch_curated(base: str) -> list[str]:
    d = http_get(base, "/api/cg/assets")
    cur = [a["sym"] for a in d.get("curated") or []]
    return cur or CURATED_FALLBACK


# ---------------------------------------------------------------------------
# strike engine
# ---------------------------------------------------------------------------


def evaluate_strike(bar: Bar, zone: Zone) -> Strike | None:
    """Strike + finished auction (no trend logic here)."""
    if not bar.struck(zone.price):
        return None
    buy, sell = bar.top_rows_split(TOP_ROWS)
    if zone.side == "short":
        finished = buy <= 0.0 or sell >= DOMINANCE * buy
        dominant = "sell" if sell > buy else ("buy" if buy > sell else "flat")
        ratio = (sell / buy) if buy > 0 else (math.inf if sell > 0 else 0.0)
        note = "rally struck short zone; top rows zero/dominated by sells"
    else:
        finished = sell <= 0.0 or buy >= DOMINANCE * sell
        dominant = "buy" if buy > sell else ("sell" if sell > buy else "flat")
        ratio = (buy / sell) if sell > 0 else (math.inf if buy > 0 else 0.0)
        note = "decline struck long zone; top rows dominated by buys"
    if not finished:
        return None
    return Strike(dir=zone.side, zone=zone, bar_ts=bar.ts, bar_close=bar.c,
                  top_buy=buy, top_sell=sell, dominant=dominant, dominance_ratio=ratio, note=note)


@dataclass
class SymbolResult:
    sym: str
    ok: bool
    price: float | None = None
    trend: Trend | None = None
    zones_near: int = 0
    zones_total: int = 0
    bars: int = 0
    strikes: list[Strike] = field(default_factory=list)
    suppressed: int = 0
    error: str = ""


def scan_symbol(base: str, sym: str, ema_tf: str) -> SymbolResult:
    """Full pipeline for one symbol: zones → bars → strikes → trend gate."""
    res = SymbolResult(sym=sym, ok=False)
    try:
        zones = fetch_zones(base, sym)
        bars = fetch_bars(base, sym)
    except (RuntimeError, urllib.error.URLError, OSError, ValueError) as e:
        res.error = str(e)
        return res
    price_ref = bars[-1].c
    near = [z for z in zones if abs(z.dist_pct) <= ZONE_WIN_PCT]
    try:
        trend = fetch_trend(base, sym, ema_tf, bars)
    except (RuntimeError, urllib.error.URLError, OSError, ValueError) as e:
        res.error = f"trend unavailable: {e}"
        return res

    raw: list[Strike] = []
    for bar in bars:
        for zone in near:
            st = evaluate_strike(bar, zone)
            if st:
                raw.append(st)
    raw.sort(key=lambda s: (s.bar_ts, s.zone.strength), reverse=True)
    allowed = [s for s in raw if trend.allows(s)]
    res.ok = True
    res.price = price_ref
    res.trend = trend
    res.zones_near = len(near)
    res.zones_total = len(zones)
    res.bars = len(bars)
    res.strikes = allowed[:6]
    res.suppressed = len(raw) - len(allowed)
    return res


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


def strike_to_dict(sym: str, s: Strike, trend: Trend) -> dict[str, Any]:
    ema_at = trend.at_ts(s.bar_ts)
    return {
        "event": "zone_strike",
        "sym": sym,
        "dir": s.dir,
        "zone_side": s.zone.side,
        "zone_price": s.zone.price,
        "zone_usd": s.zone.usd,
        "zone_lev": s.zone.lev,
        "zone_strength": s.zone.strength,
        "bar_ts": s.bar_ts,
        "bar_close": s.bar_close,
        "top_buy": s.top_buy,
        "top_sell": s.top_sell,
        "dominant": s.dominant,
        "dominance_ratio": None if math.isinf(s.dominance_ratio) else s.dominance_ratio,
        "ema233_at_strike": ema_at,
        "trend_tf": trend.tf,
        "note": s.note,
    }


def strike_log_line(sym: str, s: Strike, trend: Trend) -> str:
    hhmm = time.strftime("%H:%M", time.gmtime(s.bar_ts))
    ema_at = trend.at_ts(s.bar_ts)
    arrow = "below → shorts only" if s.dir == "short" else "above → longs only"
    return (
        f"[STRIKE] {sym} {s.dir.upper()} · 5m {hhmm} UTC · "
        f"zone {fmt_px(s.zone.price)} (${s.zone.usd/1e6:.1f}M · {s.zone.lev} · str{round(s.zone.strength)}) · "
        f"top{TOP_ROWS} buy {fmt_qty(s.top_buy)} / sell {fmt_qty(s.top_sell)} · "
        f"{s.dominant} {fmt_ratio(s.dominance_ratio)} · bar close {fmt_px(s.bar_close)} · "
        f"ema233[{trend.tf}] {fmt_px(ema_at)} {arrow}"
    )


def symbol_log_line(r: SymbolResult) -> str:
    t = r.trend
    assert t is not None
    gate = {"short_only": "SHORT-only", "long_only": "LONG-only", "neutral": "NEUTRAL"}[t.gate]
    side = "below" if t.price < t.ema else ("above" if t.price > t.ema else "at")
    return (
        f"{r.sym:<10} {fmt_px(r.price or 0):>12}  trend {gate:<10} "
        f"(px {side} ema233[{t.tf}] {fmt_px(t.ema)})  zones {r.zones_near}/{r.zones_total}  "
        f"bars {r.bars}  strikes {len(r.strikes)}"
        + (f"  (+{r.suppressed} suppressed by trend)" if r.suppressed else "")
    )


# ---------------------------------------------------------------------------
# modes
# ---------------------------------------------------------------------------


def run_once(base: str, sym: str, ema_tf: str, as_json: bool) -> SymbolResult:
    r = scan_symbol(base, sym, ema_tf)
    if as_json:
        if not r.ok:
            print(json.dumps({"event": "error", "sym": sym, "error": r.error}))
        else:
            for s in r.strikes:
                print(json.dumps(strike_to_dict(sym, s, r.trend)))
        return r
    if not r.ok:
        log("error", f"{sym}: {r.error}")
        return r
    log("scan", symbol_log_line(r))
    for s in r.strikes:
        log("scan", strike_log_line(sym, s, r.trend))
    if not r.strikes:
        note = "no finished-auction strikes"
        if r.suppressed:
            note += f" ({r.suppressed} found but against the trend — suppressed)"
        log("scan", f"{sym}: {note}")
    return r


def sweep(base: str, syms: list[str], ema_tf: str, as_json: bool, seen: set | None,
          sweep_no: int) -> dict[str, int]:
    """One pass over symbols. Returns {scanned, capable, strikes, suppressed}."""
    t0 = time.time()
    scanned = capable = nstrikes = nsuppressed = 0
    for sym in syms:
        r = scan_symbol(base, sym, ema_tf)
        scanned += 1
        if not r.ok:
            if sweep_no == 0:
                log("discover", f"{sym}: not capable — {r.error}")
            time.sleep(SYM_GAP)
            continue
        capable += 1
        nsuppressed += r.suppressed
        fresh: list[Strike] = []
        for s in r.strikes:
            key = (sym, s.bar_ts, s.zone.price)
            if seen is not None and key in seen:
                continue
            fresh.append(s)
            if seen is not None:
                seen.add(key)
        nstrikes += len(fresh)
        if as_json:
            for s in fresh:
                print(json.dumps(strike_to_dict(sym, s, r.trend)), flush=True)
        elif fresh or r.suppressed:
            log(f"sweep-{sweep_no}", symbol_log_line(r))
            for s in fresh:
                log(f"sweep-{sweep_no}", strike_log_line(sym, s, r.trend))
        time.sleep(SYM_GAP)
    dt = time.time() - t0
    log(f"sweep-{sweep_no}",
        f"done in {dt:.1f}s · {scanned} scanned · {capable} capable · "
        f"{nstrikes} strike{'s' if nstrikes != 1 else ''} · {nsuppressed} suppressed by trend")
    return {"scanned": scanned, "capable": capable, "strikes": nstrikes, "suppressed": nsuppressed}


def run_scan_all(base: str, limit: int | None, ema_tf: str, as_json: bool, watch: bool,
                 interval: int) -> None:
    syms = fetch_curated(base)
    log("boot", f"tracker v2 · ema_tf={ema_tf} · dominance {DOMINANCE}× · top {TOP_ROWS} rows · "
               f"zone window ±{ZONE_WIN_PCT}% · {len(syms)} curated assets")
    if limit:
        syms = syms[:limit]
        log("boot", f"limit: first {limit} of the curated list")
    seen: set | None = set() if watch else None
    if watch:
        cached = load_json(SEEN_FILE, [])
        if isinstance(cached, list):
            seen = {tuple(k) for k in cached}
    sweep_no = 0
    while True:
        if watch and sweep_no > 0:
            log("sleep", f"{interval}s until next sweep")
            time.sleep(interval)
        sweep(base, syms, ema_tf, as_json, seen, sweep_no)
        if watch and seen is not None:
            save_json(SEEN_FILE, sorted(seen)[-5000:])  # bounded persistence
        if not watch:
            return
        sweep_no += 1


# ---------------------------------------------------------------------------
# self-test — offline, no network
# ---------------------------------------------------------------------------


def self_test() -> int:
    t0 = 1_700_000_000
    # 6-row grid, tick 5 → prices 90..120; top-3 rows = indices 3,4,5.
    mk = lambda i, lo, hi, top_b, top_s: Bar(  # noqa: E731
        ts=t0 + i * 300, o=lo, h=hi, l=lo, c=hi, tick=5.0, lo=lo,
        b=[10.0, 10.0, 10.0, 0.0, top_b, 0.0],
        s=[10.0, 10.0, 10.0, 0.0, top_s, 0.0],
    )
    z_short = Zone("short", 105.0, 2.0, "High", 80.0, 1.5e6)
    z_long = Zone("long", 95.0, -2.0, "Mid", 60.0, 9.0e5)

    # 1. finished SHORT strike (sell 9× buy at top)
    sh = evaluate_strike(mk(1, 90.0, 106.0, 1.0, 9.0), z_short)
    assert sh and sh.dir == "short" and sh.dominant == "sell" and sh.dominance_ratio == 9.0

    # 2. unfinished auction rejected
    assert evaluate_strike(mk(2, 90.0, 106.0, 9.0, 1.0), z_short) is None

    # 3. zero-at-top still qualifies (flat 0/0)
    st = evaluate_strike(mk(3, 90.0, 106.0, 0.0, 0.0), z_short)
    assert st and st.dominant == "flat" and st.dominance_ratio == 0.0

    # 4. no reach, no strike
    assert evaluate_strike(mk(4, 90.0, 100.0, 1.0, 9.0), z_short) is None

    # 5. finished LONG strike through the lower zone
    bar = mk(5, 106.0, 110.0, 12.0, 2.0)
    bar.l = 94.0
    lo_ = evaluate_strike(bar, z_long)
    assert lo_ and lo_.dir == "long" and lo_.dominance_ratio == 6.0

    # 6. top_rows_split reads the TOP rows of a tall grid
    tall = Bar(t0, 90, 110, 90, 110, 5.0, 90, [5.0, 5.0, 0.0, 7.0], [5.0, 5.0, 0.0, 1.0])
    assert tall.top_rows_split(3) == (12.0, 6.0)

    # 7. EMA: constant series → EMA equals the constant
    es = ema_series([100.0] * 300, EMA_LEN)
    assert es[-1] is not None and abs(es[-1] - 100.0) < 1e-9

    # 8. EMA: rising series → last EMA below last close
    es = ema_series([100.0 + i for i in range(600)], EMA_LEN)
    assert es[-1] is not None and es[-1] < 599.0

    # 9. TREND GATE — EMA above the zone (downtrend pullback): at strike time
    #     close 106 < ema 110 → short_only → the SHORT passes, the LONG is blocked
    tr = Trend(ema=110.0, price=99.0, tf="m5")
    assert tr.gate == "short_only" and tr.allows(sh) and not tr.allows(lo_)

    # 10. EMA below everything (uptrend): close 110 > ema 90 → longs only
    tr2 = Trend(ema=90.0, price=101.0, tf="m5")
    assert tr2.gate == "long_only" and tr2.allows(lo_) and not tr2.allows(sh)

    # 11. per-bar trend: at strike time the then-EMA was 100 < close 106 →
    #     long_only THEN → the short is suppressed even though the current
    #     gate (price 99 < ema 110) is short_only
    tr3 = Trend(ema=110.0, price=99.0, tf="m5", per_bar=True, ema_by_ts={sh.bar_ts: 100.0})
    assert tr3.gate == "short_only" and tr3.at_ts(sh.bar_ts) == 100.0
    assert not tr3.allows(sh)

    # 12. snapshot fallback: non-m5 tf applies the current EMA to all strikes
    tr4 = Trend(ema=100.0, price=99.0, tf="h1")
    assert tr4.at_ts(0) == 100.0 and tr4.gate_at_ts(sh.bar_ts, sh.bar_close) == "long_only"

    print("self-test: 12/12 passed")
    return 0


# ---------------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------------


def main() -> int:
    global TERMINAL, DOMINANCE, ZONE_WIN_PCT
    ap = argparse.ArgumentParser(description="Key-level + finished-auction tracker (5m, EMA-233 gated)",
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sym", default="BTC", help="symbol for --once/--watch (default BTC)")
    ap.add_argument("--once", action="store_true", help="single scan of --sym")
    ap.add_argument("--watch", action="store_true", help="continuous scan of --sym")
    ap.add_argument("--scan", type=int, nargs="?", const=0, metavar="N",
                    help="one sweep over ALL curated assets (N = first-N limit)")
    ap.add_argument("--watch-all", action="store_true",
                    help="continuous sweep over ALL curated assets")
    ap.add_argument("--ema-tf", choices=["m5", "m15", "h1", "h4", "d1"], default="m5",
                    help="EMA-233 timeframe (default m5 = the chart you trade)")
    ap.add_argument("--dominance", type=float, default=DOMINANCE)
    ap.add_argument("--zone-win", type=float, default=ZONE_WIN_PCT)
    ap.add_argument("--interval", type=int, default=0, help="watch-all sweep cadence in seconds")
    ap.add_argument("--terminal", default=TERMINAL)
    ap.add_argument("--json", action="store_true", help="machine-readable events on stdout")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    TERMINAL = a.terminal
    DOMINANCE = a.dominance
    ZONE_WIN_PCT = a.zone_win

    try:
        if a.self_test:
            return self_test()
        if a.watch_all or a.scan is not None:
            watch = a.watch_all
            interval = a.interval or POLL_SECS_ALL
            run_scan_all(TERMINAL, a.scan or None, a.ema_tf, a.json, watch, interval)
        elif a.watch:
            seen: set = set()
            log("boot", f"tracker v2 · {a.sym} · ema_tf={a.ema_tf} · dominance {a.dominance}× · "
                        f"polling every {POLL_SECS_SINGLE}s")
            while True:
                r = run_once(TERMINAL, a.sym, a.ema_tf, a.json)
                for s in (r.strikes if r.ok else []):
                    key = (a.sym, s.bar_ts, s.zone.price)
                    if key in seen:
                        continue
                    seen.add(key)
                    if not a.json:
                        log("new", strike_log_line(a.sym, s, r.trend))
                time.sleep(POLL_SECS_SINGLE)
        else:
            log("boot", f"tracker v2 · {a.sym} · ema_tf={a.ema_tf} · dominance {a.dominance}×")
            run_once(TERMINAL, a.sym, a.ema_tf, a.json)
        return 0
    except KeyboardInterrupt:
        log("exit", "interrupted")
        return 0
    except Exception as e:  # noqa: BLE001 — CLI boundary
        log("fatal", str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
