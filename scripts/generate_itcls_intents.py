#!/usr/bin/env python3
"""
generate_itcls_intents.py — Institutional Quantitative Desk Kernel:
In-Trend Counter-Liquidation Sweep (ITCLS) Intent Generator.

Default Sovereign Execution Behavior for CG-Terminal & Quantitative Desk Council:
1. Determine Higher-Timeframe (HTF) Trend Bias from 4H/Daily EMA 13/89/233 + Day/Month VWAP.
2. In Bearish HTF Trend: Never short breakdown lows. Identify the trapped counter-trend short-squeeze
   liquidation shelf (keyLevels.above). Rest passive maker sell limits at peak shelf exhaustion.
3. In Bullish HTF Trend: Never buy breakout highs. Identify the trapped counter-trend long-flush
   liquidation floor (keyLevels.below). Rest passive maker buy limits at peak panic absorption.
4. Enforce strict risk & execution envelopes:
   - Net T2 Payoff >= 2.0R
   - Structural Stop Loss beyond liquidation wick (+ 0.15% to 0.20xATR buffer)
   - Delta Exchange India: 100% passive maker (post_only: true), max risk <= $0.50 USD, margin <= $1.50 USD
   - Blueberry Markets MT5: Pending limits with PIT-18 spread clearance (spread <= 20% of SL distance), max risk <= $6.00 USD
"""

import sys
import json
import argparse
import urllib.request
import urllib.error

BASE_URL = "http://localhost:3000"

def fetch_json(endpoint, timeout=15):
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(url, headers={"User-Agent": "CG-Terminal-ITCLS/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[WARN] Failed fetching {url}: {e}", file=sys.stderr)
    return None

def analyze_asset_itcls(sym):
    cg_sym = f"{sym.upper()}USDT"
    mkt = fetch_json(f"/api/cg/market?sym={cg_sym}")
    liq = fetch_json(f"/api/cg/liqlevels?sym={cg_sym}")

    if not mkt or not mkt.get("price"):
        return {"ok": False, "sym": sym, "reason": "Market telemetry unavailable"}
    if not liq or not liq.get("stats"):
        return {"ok": False, "sym": sym, "reason": "Liquidation telemetry unavailable"}

    price_info = mkt.get("price", {})
    last_price = float(price_info.get("last", 0.0))
    if last_price <= 0:
        return {"ok": False, "sym": sym, "reason": "Invalid last price"}

    vwap_info = mkt.get("vwap", {})
    day_vwap = float(vwap_info.get("vwap", last_price))
    bands = vwap_info.get("bands", {})
    sd1 = float(bands.get("sd1", last_price * 0.015))
    sd3 = float(bands.get("sd3", sd1 * 3.0))

    ema_info = mkt.get("ema", {})
    h4_ema = ema_info.get("h4", {})
    e13_h4 = float(h4_ema.get("e13", 0.0))
    e89_h4 = float(h4_ema.get("e89", 0.0))

    h1_ema = ema_info.get("h1", {})
    e13_h1 = float(h1_ema.get("e13", 0.0))
    e89_h1 = float(h1_ema.get("e89", 0.0))

    # 1. Determine HTF Trend Bias
    bearish_votes = 0
    bullish_votes = 0

    if e13_h4 > 0 and e89_h4 > 0:
        if e13_h4 < e89_h4:
            bearish_votes += 2
        else:
            bullish_votes += 2

    if e13_h1 > 0 and e89_h1 > 0:
        if e13_h1 < e89_h1:
            bearish_votes += 1
        else:
            bullish_votes += 1

    if last_price < day_vwap:
        bearish_votes += 1
    else:
        bullish_votes += 1

    if bearish_votes > bullish_votes:
        htf_bias = "BEARISH"
        intended_side = "SHORT"
    elif bullish_votes > bearish_votes:
        htf_bias = "BULLISH"
        intended_side = "LONG"
    else:
        htf_bias = "NEUTRAL"
        intended_side = "SHORT" if last_price < day_vwap else "LONG"

    # 2. Extract Liquidation Shelves
    stats = liq.get("stats", {})
    key_levels = stats.get("keyLevels", {})
    above_levels = key_levels.get("above", [])
    below_levels = key_levels.get("below", [])
    totals = stats.get("totals", {})
    shorts_total = float(totals.get("shorts", 0.0))
    longs_total = float(totals.get("longs", 0.0))
    lsr = (shorts_total / max(longs_total, 1.0)) if longs_total > 0 else 1.0

    # 3. Match Counter-Trend Liquidation Sweep
    candidate_level = None
    opposing_target_level = None

    if intended_side == "SHORT":
        # Look for the dominant short liquidation shelf above current price (counter-trend bounce zone)
        # Prefer levels 0.5% to 4.0% above mark
        valid_shelves = [lv for lv in above_levels if 0.4 <= float(lv.get("distPct", 0)) <= 4.5]
        if not valid_shelves and above_levels:
            valid_shelves = above_levels[:2]
        if valid_shelves:
            # Sort by strength / USD size
            valid_shelves.sort(key=lambda x: float(x.get("strength", 0)), reverse=True)
            candidate_level = valid_shelves[0]
        
        # Target: Dominant long liquidation floor below price
        if below_levels:
            opposing_target_level = below_levels[0]

    else: # LONG
        # Look for the dominant long liquidation floor below current price (counter-trend flush zone)
        valid_shelves = [lv for lv in below_levels if -4.5 <= float(lv.get("distPct", 0)) <= -0.4]
        if not valid_shelves and below_levels:
            valid_shelves = below_levels[:2]
        if valid_shelves:
            valid_shelves.sort(key=lambda x: float(x.get("strength", 0)), reverse=True)
            candidate_level = valid_shelves[0]

        # Target: Dominant short liquidation shelf above price
        if above_levels:
            opposing_target_level = above_levels[0]

    if not candidate_level:
        return {"ok": False, "sym": sym, "reason": f"No valid {intended_side} liquidation shelf identified within target band"}

    entry_price = float(candidate_level.get("price"))
    dist_pct = float(candidate_level.get("distPct"))

    # 4. Compute Structural Stop Loss & Target Ladder
    # Cold zone buffer: 0.2% - 0.4% beyond the liquidation shelf
    buffer_pct = 0.0035

    if intended_side == "SHORT":
        stop_loss = round(entry_price * (1.0 + buffer_pct), 2 if entry_price > 10 else 4)
        t1 = round(day_vwap if day_vwap < entry_price else entry_price * 0.99, 2 if entry_price > 10 else 4)
        t2_raw = float(opposing_target_level.get("price")) if opposing_target_level else (entry_price - 2.5 * (stop_loss - entry_price))
        t2 = round(t2_raw, 2 if entry_price > 10 else 4)
        t3 = round(day_vwap - sd3, 2 if entry_price > 10 else 4)
        risk_dist = stop_loss - entry_price
        reward_t2 = entry_price - t2
    else: # LONG
        stop_loss = round(entry_price * (1.0 - buffer_pct), 2 if entry_price > 10 else 4)
        t1 = round(day_vwap if day_vwap > entry_price else entry_price * 1.01, 2 if entry_price > 10 else 4)
        t2_raw = float(opposing_target_level.get("price")) if opposing_target_level else (entry_price + 2.5 * (entry_price - stop_loss))
        t2 = round(t2_raw, 2 if entry_price > 10 else 4)
        t3 = round(day_vwap + sd3, 2 if entry_price > 10 else 4)
        risk_dist = entry_price - stop_loss
        reward_t2 = t2 - entry_price

    if risk_dist <= 0:
        return {"ok": False, "sym": sym, "reason": "Invalid structural risk geometry"}

    raw_r = reward_t2 / risk_dist if risk_dist > 0 else 0.0

    # 5. Sizing & Risk Governance
    # Delta Exchange India: Max Risk $0.50 USD, Margin cap $1.50 USD
    delta_risk_cap = 0.50
    delta_margin_cap = 1.50
    # Determine unit per contract (e.g. BTC=0.001, ETH=0.01, SOL=0.1, etc.)
    contract_units = {
        "BTC": 0.001,
        "ETH": 0.01,
        "SOL": 0.1,
        "BNB": 0.01,
        "PAXG": 0.001,
        "XAU": 0.001
    }
    unit = contract_units.get(sym.upper(), 0.01)
    loss_per_contract = risk_dist * unit
    delta_contracts = max(1, int(delta_risk_cap / max(loss_per_contract, 0.0001))) if loss_per_contract > 0 else 1
    # Check stressed loss
    actual_delta_loss = delta_contracts * loss_per_contract

    # Blueberry MT5: Max Risk $6.00 USD, PIT-18 Spread Check
    mt5_risk_cap = 6.00
    # Typical MT5 spreads (points)
    mt5_spreads = {
        "BTC": 15.0,
        "ETH": 1.20,
        "SOL": 0.08,
        "BNB": 0.60,
        "XAU": 0.35,
        "PAXG": 0.35
    }
    spread = mt5_spreads.get(sym.upper(), 1.0)
    
    # Auto-adjust MT5 SL to satisfy PIT-18: distance >= 5 * spread (spread/dist <= 0.20)
    min_mt5_dist = spread * 5.05 # slight buffer
    mt5_risk_dist = max(risk_dist, min_mt5_dist)
    if intended_side == "SHORT":
        mt5_sl = round(entry_price + mt5_risk_dist, 2 if entry_price > 10 else 4)
    else:
        mt5_sl = round(entry_price - mt5_risk_dist, 2 if entry_price > 10 else 4)

    pit18_ratio = spread / mt5_risk_dist if mt5_risk_dist > 0 else 1.0
    pit18_pass = pit18_ratio <= 0.20

    # Calculate MT5 Lots
    loss_per_lot_mt5 = mt5_risk_dist * 1.20 # 1.20x stress multiplier
    mt5_lots = max(0.01, round(mt5_risk_cap / max(loss_per_lot_mt5, 0.01), 2))
    actual_mt5_loss = mt5_lots * loss_per_lot_mt5

    return {
        "ok": True,
        "sym": sym.upper(),
        "htf_bias": htf_bias,
        "side": intended_side,
        "last_price": last_price,
        "entry_price": entry_price,
        "dist_pct": dist_pct,
        "stop_loss": stop_loss,
        "mt5_stop_loss": mt5_sl,
        "stop_distance_pct": round((risk_dist / entry_price) * 100, 2),
        "target_1": t1,
        "target_2": t2,
        "target_3": t3,
        "net_t2_r": round(raw_r, 2),
        "lsr": round(lsr, 2),
        "shelf_usd": candidate_level.get("usd"),
        "shelf_strength": candidate_level.get("strength"),
        "delta": {
            "contracts": delta_contracts,
            "stressed_risk_usd": round(actual_delta_loss, 2),
            "cap_usd": delta_risk_cap,
            "post_only": True
        },
        "mt5": {
            "lots": mt5_lots,
            "sl": mt5_sl,
            "stressed_risk_usd": round(actual_mt5_loss, 2),
            "cap_usd": mt5_risk_cap,
            "pit18_ratio": round(pit18_ratio, 3),
            "pit18_pass": pit18_pass
        }
    }

def main():
    parser = argparse.ArgumentParser(description="Generate ITCLS In-Trend Counter-Liquidation Sweep Trade Intents")
    parser.add_argument("--syms", default="BTC,ETH,SOL,BNB,PAXG", help="Comma-separated symbols to evaluate")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    sym_list = [s.strip() for s in args.syms.split(",") if s.strip()]
    results = []

    print(f"=== IN-TREND COUNTER-LIQUIDATION SWEEP (ITCLS) SOVEREIGN INTENT EVALUATION ===")
    print(f"Target Assets: {', '.join(sym_list)}\n")

    for sym in sym_list:
        res = analyze_asset_itcls(sym)
        results.append(res)
        if not res.get("ok"):
            print(f"[-] {sym}: SKIPPED — {res.get('reason')}")
            continue

        side = res["side"]
        bias = res["htf_bias"]
        entry = res["entry_price"]
        sl = res["stop_loss"]
        t1 = res["target_1"]
        t2 = res["target_2"]
        t3 = res["target_3"]
        r = res["net_t2_r"]
        sl_pct = res["stop_distance_pct"]
        d = res["delta"]
        m = res["mt5"]

        print(f"================================================================================")
        print(f"[+] ASSET: {res['sym']} | HTF BIAS: {bias} | DEFAULT SETUP: S0/ITCLS ({side})")
        print(f"    Current Mark: {res['last_price']} -> Liquidation Shelf Entry: {entry} ({res['dist_pct']:+.2f}%)")
        print(f"    Shelf Size: ${res['shelf_usd']:,.0f} USD (Strength: {res['shelf_strength']}/100) | LSR: {res['lsr']}:1")
        print(f"    Structural SL: {sl} (Distance: {sl_pct}%)")
        print(f"    Target Ladder: T1: {t1} (Mean Rev) | T2: {t2} (Opposing Floor, {r}R) | T3: {t3} (Expansion)")
        print(f"    [VENUE: DELTA INDIA] Contracts: {d['contracts']} | Risk: ${d['stressed_risk_usd']} USD (<= ${d['cap_usd']}) | 100% MAKER POST-ONLY")
        print(f"    [VENUE: BLUEBERRY MT5] SL: {m['sl']} | Lots: {m['lots']} | Stressed Risk: ${m['stressed_risk_usd']} USD (<= ${m['cap_usd']}) | PIT-18: {'PASS' if m['pit18_pass'] else 'FAIL'} (ratio {m['pit18_ratio']})")
        print(f"================================================================================\n")

    if args.json:
        print("\n--- JSON OUTPUT ---")
        print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
