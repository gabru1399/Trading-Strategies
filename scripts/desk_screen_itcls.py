#!/usr/bin/env python3
"""
desk_screen_itcls.py — Universe screen for ITCLS (In-Trend Counter-Liquidation
Sweep) pullback setups at liquidation levels, per desk/CANONICAL_MASTER_SPECIFICATION.md.

Doctrine (scripts/generate_itcls_intents.py):
  - HTF bias from H4 EMA13x89 (2 votes) + H1 EMA13x89 (1 vote) + Day VWAP position (1 vote).
  - BULLISH -> LONG at the dominant long-liquidation floor below price (flush zone).
  - BEARISH -> SHORT at the dominant short-liquidation shelf above price (squeeze zone).
  - Passive maker limit at the shelf; stop 0.35% beyond (cold zone); T2 = opposing magnet.

Screen outputs per symbol: bias, shelf, geometry (entry/stop/T1/T2/R), LSR (0-2%
band from stats.bands), Table-7 pre-score (trend 2.0 + vwap regime 1.5 + liq
magnet 1.5 = 5.0 max at screen stage; order-flow/wall/CVD/GEX verified in
deep-dive). Candidates: pre-score >= 3.5 AND net T2 R >= 1.8 AND shelf
strength >= 45.
"""
import json
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "http://localhost:3000"

# Curated 61: 30 crypto + 28 TradFi perps (classic SPX500/UKO/NDX100 have no order-flow tabs)
PERPS = [
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "TRX", "LINK", "LTC",
    "AVAX", "DOT", "NEAR", "UNI", "ATOM", "XLM", "ETC", "FIL", "ICP", "HBAR",
    "APT", "ARB", "OP", "SUI", "SEI", "INJ", "TIA", "VET", "1000PEPE", "1000SHIB",
    "XAU", "NVDA", "SNDK", "SOXL", "SPCX", "GOOGL", "MU", "SKHY", "XAG", "CL",
    "INTC", "CRCL", "MSTR", "QQQ", "ANTHROPIC", "AAPL", "TSLA", "DRAM", "KORU",
    "META", "NBIS", "MSFT", "AMZN", "AMD", "COIN", "NFLX", "AVGO", "TSM",
]


def fetch_json(endpoint, timeout=25):
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(url, headers={"User-Agent": "CG-Terminal-DeskScreen/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return None


def decs(p):
    return 2 if p > 10 else 4


def screen_symbol(sym):
    mkt = fetch_json(f"/api/cg/market?sym={sym}")
    if not mkt or not mkt.get("price"):
        return {"sym": sym, "ok": False, "reason": "market unavailable"}

    price = float(mkt["price"]["last"])
    vwap = float(mkt["vwap"]["vwap"])
    sd1 = float(mkt["vwap"]["bands"]["sd1"])
    ema = mkt.get("ema", {})
    e13_h4 = float(ema.get("h4", {}).get("e13", 0) or 0)
    e89_h4 = float(ema.get("h4", {}).get("e89", 0) or 0)
    e13_h1 = float(ema.get("h1", {}).get("e13", 0) or 0)
    e89_h1 = float(ema.get("h1", {}).get("e89", 0) or 0)
    e13_d1 = float(ema.get("d1", {}).get("e13", 0) or 0)
    e89_d1 = float(ema.get("d1", {}).get("e89", 0) or 0)

    if not (e13_h4 and e89_h4 and price):
        return {"sym": sym, "ok": False, "reason": "ema/price unavailable"}

    # 1. HTF bias votes (ITCLS weighting)
    bear = 0
    bull = 0
    if e13_h4 < e89_h4:
        bear += 2
    else:
        bull += 2
    if e13_h1 and e89_h1:
        if e13_h1 < e89_h1:
            bear += 1
        else:
            bull += 1
    if price < vwap:
        bear += 1
    else:
        bull += 1

    if bear > bull:
        side = "SHORT"
    elif bull > bear:
        side = "LONG"
    else:
        side = "LONG" if price > vwap else "SHORT"

    # 2. Liquidation shelves (3d window — primary actionable window)
    liq = fetch_json(f"/api/cg/liqlevels?sym={sym}&range=3d")
    if not liq or not liq.get("stats"):
        return {"sym": sym, "ok": False, "reason": "liqlevels unavailable", "bias": side}

    kl = liq["stats"].get("keyLevels", {})
    above = kl.get("above", [])   # short-liq squeeze shelf above price
    below = kl.get("below", [])   # long-liq flush floor below price

    if side == "SHORT":
        valid = [lv for lv in above if 0.4 <= float(lv.get("distPct", 0)) <= 4.5]
        valid.sort(key=lambda x: float(x.get("strength", 0)), reverse=True)
        shelf = valid[0] if valid else None
        opposing = below[0] if below else None
    else:
        valid = [lv for lv in below if -4.5 <= float(lv.get("distPct", 0)) <= -0.4]
        valid.sort(key=lambda x: float(x.get("strength", 0)), reverse=True)
        shelf = valid[0] if valid else None
        opposing = above[0] if above else None

    if not shelf:
        return {"sym": sym, "ok": False, "reason": f"no {side} shelf in band", "bias": side}

    entry = float(shelf["price"])
    dist_pct = float(shelf.get("distPct", 0))
    strength = float(shelf.get("strength", 0))
    shelf_usd = float(shelf.get("usd", 0))
    shelf_lev = shelf.get("lev", "?")

    # 3. Geometry (ITCLS envelopes)
    buffer_pct = 0.0035
    if side == "SHORT":
        stop = entry * (1 + buffer_pct)
        t1 = vwap if vwap < entry else entry * 0.99
        t2 = float(opposing["price"]) if opposing else entry - 2.5 * (stop - entry)
        risk = stop - entry
        reward = entry - t2
    else:
        stop = entry * (1 - buffer_pct)
        t1 = vwap if vwap > entry else entry * 1.01
        t2 = float(opposing["price"]) if opposing else entry + 2.5 * (entry - stop)
        risk = entry - stop
        reward = t2 - entry

    if risk <= 0:
        return {"sym": sym, "ok": False, "reason": "invalid geometry", "bias": side}
    r_t2 = reward / risk
    r_t1 = ((t1 - entry) if side == "LONG" else (entry - t1)) / risk

    # 4. LSR within 0-2% band (desk convention: shorts/longs in the near window)
    bands = liq["stats"].get("bands", [])
    up = sum(float(b.get("up", 0)) for b in bands if float(b.get("b", 0)) <= 2)
    down = sum(float(b.get("down", 0)) for b in bands if float(b.get("b", 0)) <= 2)
    lsr_2pct = (up / down) if down > 0 else float("inf")

    # 5. Table-7 pre-score (screen stage: factors 1, 2, 6)
    trend_ok = (side == "LONG" and e13_h4 > e89_h4 and e13_d1 > e89_d1) or \
               (side == "SHORT" and e13_h4 < e89_h4 and e13_d1 < e89_d1)
    z_entry = (entry - vwap) / sd1 if sd1 > 0 else 0
    # Long in discount (entry below VWAP, |z|<=1 at entry) / Short in premium
    vwap_regime_ok = (side == "LONG" and z_entry <= -0.05 and z_entry >= -1.0) or \
                     (side == "SHORT" and z_entry >= 0.05 and z_entry <= 1.0)
    # Liq magnet: skew favors direction + LSR gate
    if side == "LONG":
        skew_favors = down > up * 1.2  # more long-liq below -> flush fuel for our long
    else:
        skew_favors = up > down * 1.2
    lsr_gate_open = lsr_2pct < 2.5

    pre = 0.0
    pre += 2.0 if trend_ok else 0.0
    pre += 1.5 if vwap_regime_ok else 0.0
    pre += 1.5 if (skew_favors and lsr_gate_open) else (0.75 if lsr_gate_open else 0.0)

    # candidacy for deep-dive
    candidate = (pre >= 3.5) and (r_t2 >= 1.8) and (strength >= 45)

    return {
        "sym": sym, "ok": True, "bias": side,
        "price": price, "vwap": vwap, "z_now": round((price - vwap) / sd1, 2) if sd1 else None,
        "trend_h4d1": trend_ok,
        "shelf": {"price": entry, "distPct": dist_pct, "strength": strength,
                  "usd": shelf_usd, "lev": shelf_lev},
        "entry": round(entry, decs(entry)), "stop": round(stop, decs(entry)),
        "t1": round(t1, decs(entry)), "t2": round(t2, decs(entry)),
        "r_t2": round(r_t2, 2), "r_t1": round(r_t1, 2),
        "lsr_2pct": round(lsr_2pct, 2) if lsr_2pct != float("inf") else None,
        "skew_favors": skew_favors,
        "pre_score": round(pre, 2),
        "vwap_regime_ok": vwap_regime_ok,
        "candidate": candidate,
    }


def main():
    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(screen_symbol, s): s for s in PERPS}
        for fut in as_completed(futs):
            results.append(fut.result())

    ok = [r for r in results if r.get("ok")]
    failed = [r for r in results if not r.get("ok")]
    cands = sorted([r for r in ok if r["candidate"]],
                   key=lambda r: (r["pre_score"], r["r_t2"], r["shelf"]["strength"]), reverse=True)
    near = sorted([r for r in ok if not r["candidate"] and r["pre_score"] >= 3.0],
                  key=lambda r: r["pre_score"], reverse=True)

    print(f"Screened {len(results)} perps in {time.time()-t0:.0f}s — ok: {len(ok)}, "
          f"no-data: {len(failed)}, candidates: {len(cands)}\n")

    print(f"{'SYM':<10}{'SIDE':<6}{'PRICE':>10}{'ENTRY':>10}{'STOP':>10}{'T2':>10}"
          f"{'R_T2':>6}{'STR':>6}{'LSR2%':>7}{'PRE':>6}  FLAGS")
    for r in cands:
        flags = []
        if r["trend_h4d1"]: flags.append("trend")
        if r["vwap_regime_ok"]: flags.append("vwap-regime")
        if r["skew_favors"]: flags.append("skew")
        print(f"{r['sym']:<10}{r['bias']:<6}{r['price']:>10g}{r['entry']:>10g}{r['stop']:>10g}"
              f"{r['t2']:>10g}{r['r_t2']:>6.2f}{r['shelf']['strength']:>6.1f}"
              f"{(r['lsr_2pct'] or 0):>7.2f}{r['pre_score']:>6.2f}  {','.join(flags)}")

    print(f"\n--- near-misses (pre >= 3.0): {len(near)}")
    for r in near[:12]:
        print(f"  {r['sym']:<10}{r['bias']:<6}pre {r['pre_score']:.2f} R {r['r_t2']:.2f} "
              f"str {r['shelf']['strength']:.0f} dist {r['shelf']['distPct']:+.2f}%")

    print(f"\n--- no data / no shelf: {len(failed)}")
    for r in failed:
        print(f"  {r['sym']:<10}{r.get('reason','?')}")

    out = {"ts": int(time.time() * 1000), "candidates": cands, "near": near, "failed": failed}
    with open("/home/z/my-project/data/desk-screen-itcls.json", "w") as f:
        json.dump(out, f, indent=1)
    print(f"\nsaved -> data/desk-screen-itcls.json")


if __name__ == "__main__":
    main()
