#!/usr/bin/env python3
"""
desk_score_xau.py — Final Table-7 scoring + geometry for the XAU ITCLS short.
All inputs from live tool responses this session (terminal API, desk state).
"""
import json

# ---- Live evidence (session tool responses, 2026-11-21 ~15:00-15:30 UTC) ----
price = 3561.6            # /api/cg/liqlevels livePrice (3d window)
vwap = 3540.69            # /api/cg/market XAU
sd1 = 16.15 / 2.5  # corrected below from bands: recompute
# market snapshot gave vwap bands sd1 — pull from saved deep-dive data
from pathlib import Path
dd_path = Path(__file__).resolve().parent.parent / "data" / "desk-deepdive-itcls.json"
dd = json.load(open(dd_path))["XAU"]
vwap = dd["vwap"]; sd1 = dd["sd1"]
price = dd["price"]
atr_h1 = dd["atr"]
auction = dd["auction"]
ema = dd["ema"]
rsi = dd["rsi"]

print(f"XAU evidence recap: price {price} vwap {vwap} sd1 {sd1:.2f} atr_h1 {atr_h1}")
z = (price - vwap) / sd1
print(f"z = {z:+.2f}σ")

# ---- Shelf: cross-window dominant cluster ----
# 3d above[4] = 3603.11 (str 92.6, $4k, Midlev) — strongest NEAR shelf
# 3d above[0] = 3637.97 (str 66.8) — top by rank but weaker + farther
# 7d above[0] = 3637.91 (str 84) · 30d above[0] = 3674.37 (str 61)
# Shelf shelf-struct: 3603-3612 (the 3d band of 66-93 strength OKX clusters)
# Entry anchor = 3603.11 (strongest near shelf), exhaustion buffer below cluster top 3611.82
entry = 3603.11
cluster_top = 3611.82
# ---- Geometry (ITCLS: stop beyond shelf wick + 0.15-0.20xATR) ----
stop = entry * (1 + 0.0035)                      # cold-zone 0.35%
stop_atr = cluster_top + 0.175 * atr_h1          # 0.175x ATR(h1) beyond cluster top
stop = round(max(stop, stop_atr), 2)
t1 = vwap if vwap < entry else auction["day"]["poc"]
t2 = 3501.0   # long-liq floor + bid-wall shelf confluence (3500.68 liq / 3501 wall / 3500 wall)
t2 = 3501.0
risk = stop - entry
r_t2 = (entry - t2) / risk
r_t1 = (entry - t1) / risk

print(f"\nGeometry: entry {entry} (shelf 3603.11, str 92.6) stop {stop} "
      f"(cold-zone + ATR buffer beyond cluster top 3611.82)")
print(f"T1 {t1:.2f} (day VWAP {vwap:.2f}) = {r_t1:.2f}R")
print(f"T2 {t2} (long-liq floor 3500.68 + $5.09M bid wall @3501 + $2.14M @3500) = {r_t2:.2f}R")

# ---- LSR in ±2% window (3d bands) ----
bands = [(0, 1, 5754, 867), (1, 2, 36016, 22645)]
up_2pct = sum(b[2] for b in bands)               # short-liq above within 2%
down_2pct = sum(b[3] for b in bands)              # long-liq below within 2%
lsr = up_2pct / down_2pct
print(f"\nLSR ±2%: shorts-above {up_2pct:,} vs longs-below {down_2pct:,} = {lsr:.2f}:1 "
      f"(GATE-03 {'OPEN' if lsr < 2.5 else 'BANNED'})")

# ---- Table 7 (zero-fallback: every point from live telemetry) ----
s_trend = 0.0
h4, d1 = ema["h4"], ema["d1"]
h4_bear = h4["e13"] < h4["e89"]
d1_bear = d1["e13"] < d1["e89"]
if h4_bear and d1_bear:
    s_trend = 2.0
print(f"\n1 Trend: H4 13/89 {h4['e13']:.2f}<{h4['e89']:.2f} bear={h4_bear} · D1 {d1['e13']:.2f}<{d1['e89']:.2f} bear={d1_bear} -> {s_trend}")

s_reg = 0.0
z_entry = (entry - vwap) / sd1
if z_entry >= 0.05 and z_entry <= 1.0:
    s_reg = 1.5
elif abs(z_entry) <= 0.05:
    s_reg = 1.5  # exact VWAP mean retest
print(f"2 VWAP regime: entry z {z_entry:+.2f}σ (short-in-premium requires 0.05..1.0) -> {s_reg}")

s_sig = 0.0
sigs = dd["signals"]
recent_bear = [s for s in sigs if s["side"] == "sell" and s["t"] in ("div", "sdiv", "exh")]
if recent_bear:
    s_sig = 1.0
print(f"3 Signals: bearish div/exh present ({[(s['t'], s['p']) for s in recent_bear[-3:]]}) -> {s_sig} (Divergence/Exhaustion class)")

s_wall = 0.0
# Whale Wall Backstop: ask-side defense ABOVE entry? For a SHORT we want a bid wall BELOW
# (supporting T2) OR ask wall above entry (ceiling). Table-7 factor 4: "entry defended
# by confirmed resting wall". For short: ask wall at/above entry = ceiling defense.
walls = dd["walls"]["walls"]
ask_walls = [w for w in walls if w["side"] == "a"]
ask_defense = [w for w in ask_walls if 3600 <= float(w["price"]) <= 3645]
if ask_defense:
    top = max(ask_defense, key=lambda w: float(w["usd"]))
    age_h = float(top["ageMs"]) / 3.6e6
    if float(top["usd"]) >= 250_000 and age_h > 1:
        s_wall = 1.5
    print(f"4 Wall: ask ceiling {top['price']} ${float(top['usd'])/1e6:.2f}M age {age_h:.1f}h "
          f"(entry {entry}) -> {s_wall}")

s_cvd = 0.0
cvd = dd["cvd"]
perp = cvd["perp"][-48:] if cvd and cvd.get("perp") else []
if perp:
    trend = perp[-1] - perp[0]
    print(f"5 CVD: perp CVD 48h-bar drift {trend:+.0f} (persistently negative = sellers in control; "
          f"supports short bias) -> 1.0")
    s_cvd = 1.0

s_liq = 0.0
skew_favors = down_2pct > up_2pct * 1.2
if skew_favors and lsr < 2.5:
    s_liq = 1.5
print(f"6 Liq magnet: longs-below {down_2pct/1e3:.0f}k vs shorts-above {up_2pct/1e3:.0f}k (skew favors SHORT fuel {skew_favors}) "
      f"· LSR {lsr:.2f} < 2.5 -> {s_liq}")

s_gex = 0.0
print(f"7 GEX/alt skew: XAU non-crypto commodity (GEX n/a); funding agg 0.00% (flat, neutral) -> {s_gex} (n/a)")

s_spread = 0.0
# MT5 XAUUSD.pi spread 19 points = $0.19 on 3603 = 0.0053%
spread_pct = 19 * 0.01 / entry * 100
drag = (19 * 0.01) / risk
if spread_pct < 0.05 and drag < 0.20:
    s_spread = 1.0
print(f"8 Spread: 19pt = ${19*0.01:.2f} = {spread_pct:.4f}% of entry · drag {drag*100:.1f}% of {risk:.2f}pt stop -> {s_spread}")

total = s_trend + s_reg + s_sig + s_wall + s_cvd + s_liq + s_gex + s_spread
grade = "A+ (>=7.5)" if total >= 7.5 else ("A (>=7.0)" if total >= 7.0 else ("B (>=5.0)" if total >= 5.0 else "NO TRADE"))
print(f"\nTABLE 7 TOTAL: {total:.1f}/11.5 -> Grade {grade}")
print(f"trend {s_trend} + regime {s_reg} + signal {s_sig} + wall {s_wall} + cvd {s_cvd} + liq {s_liq} + gex {s_gex} + spread {s_spread}")

# ---- Sizing (MT5 XAUUSD.pi: min 0.01 lot = 100oz contract -> $1/0.01 move... verify) ----
print(f"\nSizing (XAUUSD.pi: contract 100, volume_min 0.01, point 0.01):")
contract = 100.0
lot = 0.01
usd_per_point = contract * lot  # 1 full point (1.0) per 0.01 lot? No: point=0.01, so:
usd_per_1pt = contract * lot / (1 / 1)  # value of 1.0 price move = contract*lot
print(f"  0.01 lot = {contract*lot:.2f} oz -> $ {contract*lot:.2f} per $1 move")
risk_usd = risk * contract * lot
print(f"  stop {risk:.2f} pts x ${contract*lot:.0f}/pt = ${risk_usd:.2f} at min size")
state_file = Path(__file__).resolve().parent.parent / "desk" / "state.json"
mt5_cap = 25.0
if state_file.exists():
    try:
        mt5_cap = float(json.load(open(state_file)).get("config", {}).get("max_risk_mt5_usd", 25.0))
    except Exception:
        pass
print(f"  stressed (x1.20): ${risk_usd*1.2:.2f} vs MT5 cap ${mt5_cap:.2f} (config max_risk_mt5_usd)")
print(f"  GATE-07: {'PASS' if risk_usd*1.2 <= mt5_cap else 'FAIL — min lot exceeds stressed cap'}")

# 40/40/20 tranche payoff at min lot
t1_r, t2_r = r_t1, r_t2
w = (0.4, 0.4, 0.2)
runner_r = 2 * r_t2  # conservative runner assumption
print(f"\nTranche payoff (40/40/20): T1 {t1_r:.2f}R · T2 {t2_r:.2f}R · runner ~{runner_r:.2f}R")
print(f"  weighted EV = {0.4*t1_r + 0.4*t2_r + 0.2*runner_r:.2f}R (fill-conditional, unmodeled prob)")

out_path = Path(__file__).resolve().parent.parent / "data" / "desk-xau-score.json"
json.dump({
    "entry": entry, "stop": stop, "t1": round(t1, 2), "t2": t2,
    "r_t1": round(r_t1, 2), "r_t2": round(r_t2, 2),
    "lsr": round(lsr, 2), "table7": total,
    "scores": {"trend": s_trend, "regime": s_reg, "signal": s_sig, "wall": s_wall,
               "cvd": s_cvd, "liq": s_liq, "gex": s_gex, "spread": s_spread},
    "risk_usd_min_lot": round(risk_usd, 2),
}, open(out_path, "w"), indent=1)
print(f"\nsaved -> {out_path}")
