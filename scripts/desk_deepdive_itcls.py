#!/usr/bin/env python3
"""
desk_deepdive_itcls.py — Full D1-D16 evidence for ITCLS screen candidates.
Correct field mappings (live-verified 2026-11-21):
  signals: sets[].sigs[] {t, side, p, ts} (t: abs|div|sdiv|trap|exh)
  cvd: candles[], perp, spot, delta, divergences[]
  bookwalls: model.depth{bidUsd,askUsd}, model.walls[{side:a|b,price,usd,ageMs,touched}],
             model.imbalance, model.imbalance5mAgo, model.events[]
  largeorder: groups[] (per venue)
  funding: aggregate{...}, series[]
"""
import json
import time
import urllib.request

BASE_URL = "http://localhost:3000"
CANDS = ["XAU", "SOL", "LINK", "ATOM", "HBAR", "XRP"]
OUT = "/home/z/my-project/data/desk-deepdive-itcls.json"


def fetch(endpoint, timeout=30):
    req = urllib.request.Request(f"{BASE_URL}{endpoint}",
                                 headers={"User-Agent": "CG-Terminal-DeepDive/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status == 200:
                return json.loads(r.read().decode())
    except Exception:
        return None
    return None


def _lv(bl):
    if not bl:
        return None
    return {"price": bl[0]["price"], "str": bl[0]["strength"],
            "usd": bl[0].get("usd"), "distPct": bl[0]["distPct"],
            "lev": bl[0].get("lev")}


def fmt_ts(ts):
    return time.strftime("%m-%d %H:%M", time.gmtime(ts / 1000 if ts > 1e11 else ts))


def deepdive(sym):
    print(f"\n{'='*78}\nDEEP DIVE · {sym}\n{'='*78}")
    ev = {"sym": sym}

    # --- D2/D3/D4/D5: market snapshot (already screened, re-pull for freshness)
    mkt = fetch(f"/api/cg/market?sym={sym}")
    if not mkt or not mkt.get("price"):
        print("  market unavailable — skip")
        return None
    ev["price"] = mkt["price"]["last"]
    ev["vwap"] = mkt["vwap"]["vwap"]
    ev["sd1"] = mkt["vwap"]["bands"]["sd1"]
    ev["auction"] = {k: {kk: vv for kk, vv in v.items() if kk in ("poc", "vah", "val")}
                     for k, v in mkt.get("auction", {}).items()}
    ev["ema"] = mkt.get("ema", {})
    ev["rsi"] = mkt.get("rsi", {})
    ev["atr"] = mkt.get("vol", {}).get("atr14H1")
    ev["levels"] = {k: mkt.get("levels", {}).get(k) for k in ("pdh", "pdl", "pwh", "pwl")}
    p, vwap, sd1 = ev["price"], ev["vwap"], ev["sd1"]
    z = (p - vwap) / sd1 if sd1 else 0
    print(f"  price {p:g} · VWAP {vwap:g} · z {z:+.2f}σ · ATR(h1) {ev['atr']:.4g}")
    print(f"  day VA {ev['auction']['day']['val']:.6g} / POC {ev['auction']['day']['poc']:.6g} / "
          f"VAH {ev['auction']['day']['vah']:.6g}")
    e4 = ev["ema"]["h4"]; e1 = ev["ema"]["h1"]; ed = ev["ema"]["d1"]
    print(f"  EMA h4 13/89 {e4['e13']:.6g}/{e4['e89']:.6g} · d1 13/89 {ed['e13']:.6g}/{ed['e89']:.6g}")
    print(f"  RSI m15/h1/h4/d1 {ev['rsi']['m15']:.0f}/{ev['rsi']['h1']:.0f}/{ev['rsi']['h4']:.0f}/{ev['rsi']['d1']:.0f}")

    # --- D11: liq windows
    lw = {}
    for rng in ("3d", "7d", "30d"):
        d = fetch(f"/api/cg/liqlevels?sym={sym}&range={rng}")
        lw[rng] = {"above": _lv((d or {}).get("stats", {}).get("keyLevels", {}).get("above", [])),
                   "below": _lv((d or {}).get("stats", {}).get("keyLevels", {}).get("below", [])),
                   "totals": (d or {}).get("stats", {}).get("totals", {})} if (d and d.get("stats")) else None
        time.sleep(0.4)
    ev["liq_windows"] = lw
    for rng, v in lw.items():
        if v and v["above"]:
            a = v["above"]
            print(f"  liq {rng:>3}: above {a['price']} (str {a['str']:.0f}, ${a['usd']/1e3:.0f}k, {a['distPct']:+.2f}%)"
                  + (f" · below {v['below']['price']} (str {v['below']['str']:.0f})" if v["below"] else ""))
        else:
            print(f"  liq {rng:>3}: unavailable")

    # --- D6/D7: footprint signals (time bars m15)
    sig = fetch(f"/api/cg/signals?sym={sym}&bt=time")
    ev["signals"] = []
    if sig and sig.get("sets"):
        for st in sig["sets"]:
            for s in st.get("sigs", [])[-8:]:
                ev["signals"].append({"t": s.get("t"), "side": s.get("side"), "p": s.get("p"),
                                      "ts": s.get("ts"), "bt": st.get("bt")})
    recent = [f"{s['t']}/{s['side']}@{s['p']:.6g}" for s in ev["signals"][-6:]]
    print(f"  signals: {recent if recent else 'none in window'}")

    # --- D8: CVD h1
    cvd = fetch(f"/api/cg/cvd?sym={sym}&itv=h1&limit=24")
    ev["cvd"] = None
    if cvd and cvd.get("ok"):
        ev["cvd"] = {
            "perp": cvd.get("perp"), "spot": cvd.get("spot"), "total": cvd.get("total"),
            "delta": cvd.get("delta"),
            "takerBuyShare": (cvd.get("kpis") or {}).get("takerBuyShare"),
            "divergences": [{"type": d.get("type"), "ts": d.get("ts"), "hit": d.get("hit")}
                            for d in (cvd.get("divergences") or [])[-3:]],
        }
        c = ev["cvd"]
        print(f"  cvd h1: perp {c['perp'] if c['perp'] is not None else '?'} · spot {c['spot'] if c['spot'] is not None else '?'}"
              f" · divs {c['divergences']}")

    # --- D9: book walls (±2%)
    bw = fetch(f"/api/cg/bookwalls?sym={sym}&band=2&interval=h1&limit=50")
    ev["walls"] = None
    if bw and bw.get("ok") and bw.get("model"):
        m = bw["model"]
        ev["walls"] = {
            "depth": m.get("depth"), "imbalance": m.get("imbalance"),
            "imbalance5mAgo": m.get("imbalance5mAgo"),
            "walls": [{"side": w.get("side"), "price": w.get("price"), "usd": w.get("usd"),
                       "distPct": w.get("distPct"), "ageMs": w.get("ageMs"), "touched": w.get("touched")}
                      for w in (m.get("walls") or [])],
            "events": [{"t": e.get("t"), "type": e.get("type"), "side": e.get("side"),
                        "p": e.get("p"), "usd": e.get("usd")}
                       for e in (m.get("events") or [])[:8]],
        }
        w_ = ev["walls"]
        d_ = w_["depth"] or {}
        print(f"  walls ±2%: bid ${float(d_.get('bidUsd',0))/1e6:.1f}M / ask ${float(d_.get('askUsd',0))/1e6:.1f}M"
              f" · imbalance {w_['imbalance']:+.3f}")
        for wl in sorted(w_["walls"], key=lambda x: -float(x.get("usd", 0) or 0))[:4]:
            side = "ASK" if wl["side"] == "a" else "BID"
            print(f"    {side} wall {wl['price']} ${float(wl['usd'])/1e6:.2f}M ({wl['distPct']:+.2f}%) "
                  f"age {wl['ageMs']/3.6e6:.1f}h touched={wl['touched']}")

    # --- D10: large/whale orders
    lo = fetch(f"/api/cg/largeorder?sym={sym}USDT&hours=24")
    ev["large_orders"] = None
    if lo and lo.get("ok"):
        groups = lo.get("groups", [])
        ev["large_orders"] = {
            "n_groups": len(groups),
            "top": [],
        }
        rows = []
        for g in groups:
            for o in (g.get("orders") or g.get("rows") or [])[:50]:
                rows.append(o)
        # shape-agnostic top resting walls by usd
        def usd_of(o):
            for k in ("usd", "notionalUsd", "amountUsd", "value"):
                if o.get(k) is not None:
                    return float(o[k])
            return 0.0
        rows.sort(key=lambda o: -usd_of(o))
        ev["large_orders"]["top"] = rows[:8]
        if rows:
            print(f"  large orders: {len(rows)} resting rows")
            for o in rows[:4]:
                side = o.get("side", "?")
                print(f"    {side} {o.get('price')} ${usd_of(o)/1e3:.0f}k")
        else:
            print(f"  large orders: groups={len(groups)} but no rows (keys {list(groups[0].keys())[:8] if groups else '-'})")

    # --- D14: funding
    fd = fetch(f"/api/cg/funding?sym={sym}")
    ev["funding"] = None
    if fd and fd.get("ok"):
        agg = fd.get("aggregate") or {}
        ev["funding"] = {
            "rate": agg.get("rate", agg.get("fundingRate")),
            "series_tail": (fd.get("series") or [])[-3:],
        }
        print(f"  funding agg: {json.dumps(agg)[:200]}")

    time.sleep(0.5)
    return ev


results = {}
for c in CANDS:
    e = deepdive(c)
    if e:
        results[c] = e

with open(OUT, "w") as f:
    json.dump(results, f, indent=1)
print(f"\nsaved -> {OUT} ({len(results)} symbols)")
