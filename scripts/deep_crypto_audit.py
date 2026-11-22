import urllib.request, json, sys, math

symbols = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "LTC", "SUI", "NEAR"]

def get_json(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {}

def audit_symbol(sym):
    mkt = get_json(f"http://127.0.0.1:3000/api/cg/market?sym={sym}")
    liq_3d = get_json(f"http://127.0.0.1:3000/api/cg/liqlevels?sym={sym}&range=3d")
    liq_7d = get_json(f"http://127.0.0.1:3000/api/cg/liqlevels?sym={sym}&range=7d")
    walls = get_json(f"http://127.0.0.1:3000/api/cg/bookwalls?sym={sym}")
    signals = get_json(f"http://127.0.0.1:3000/api/cg/signals?sym={sym}")
    cvd = get_json(f"http://127.0.0.1:3000/api/cg/cvd?sym={sym}")

    p = mkt.get("price", {})
    last = p.get("last", 0)
    chg = p.get("chgDayPct", 0)
    
    auc = mkt.get("auction", {}).get("day", {})
    val = auc.get("val", 0)
    poc = auc.get("poc", 0)
    vah = auc.get("vah", 0)
    
    vwap_data = mkt.get("vwap", {})
    vwap = vwap_data.get("vwap", 0)
    z_score = vwap_data.get("zScore", 0)
    
    ema = mkt.get("ema", {})
    m15_13 = ema.get("m15", {}).get("ema13")
    m15_89 = ema.get("m15", {}).get("ema89")
    h1_13 = ema.get("h1", {}).get("ema13")
    h1_89 = ema.get("h1", {}).get("ema89")
    h4_13 = ema.get("h4", {}).get("ema13")
    h4_89 = ema.get("h4", {}).get("ema89")
    
    rsi = mkt.get("rsi", {})
    m15_rsi = rsi.get("m15", 50)
    h1_rsi = rsi.get("h1", 50)
    h4_rsi = rsi.get("h4", 50)
    
    stats_3d = liq_3d.get("stats", {})
    above_3d = stats_3d.get("keyLevels", {}).get("above", [])
    below_3d = stats_3d.get("keyLevels", {}).get("below", [])
    shorts_vol = stats_3d.get("totals", {}).get("shorts", 0)
    longs_vol = stats_3d.get("totals", {}).get("longs", 0)
    lsr = round(shorts_vol / longs_vol, 2) if longs_vol > 0 else 0
    
    stats_7d = liq_7d.get("stats", {})
    above_7d = stats_7d.get("keyLevels", {}).get("above", [])
    below_7d = stats_7d.get("keyLevels", {}).get("below", [])
    
    # Book walls
    model_walls = walls.get("model", {}).get("walls", [])
    ask_walls = [w for w in model_walls if w.get("side") == "a" and w.get("price") >= last][:3]
    bid_walls = [w for w in model_walls if w.get("side") == "b" and w.get("price") <= last][:3]
    imbalance = walls.get("model", {}).get("imbalance", 0)
    
    # Signals
    sigs = signals.get("signals", []) if isinstance(signals, dict) else []
    
    # CVD
    spot_cvd = cvd.get("spotCvd", 0)
    perp_cvd = cvd.get("perpCvd", 0)

    # Determine Macro & Micro Regime
    # H4 Trend
    htf_bias = "BEAR" if (h4_13 and h4_89 and h4_13 < h4_89) or (h1_13 and h1_89 and h1_13 < h1_89) else "BULL"
    
    # Check ITCLS Pullback Setup
    # Downtrend Pullback: price bounced from below VWAP towards or above VWAP/Day VAH into overhead short liquidation shelf
    pullback_detected = False
    archetype = "S0_ITCLS"
    entry = None
    sl = None
    tp1 = None
    tp2 = None
    r_mult = 0.0
    ev = 0.0

    if htf_bias == "BEAR":
        # Target overhead short liquidation shelf
        overhead_shelf = above_3d[0] if above_3d else None
        if overhead_shelf:
            shelf_p = overhead_shelf.get("price")
            dist = overhead_shelf.get("distPct", 0)
            # Entry at peak shelf
            entry = shelf_p
            # Stop beyond secondary shelf + 0.20% cold zone
            sec_shelf = above_3d[1] if len(above_3d) > 1 else overhead_shelf
            sl = round(sec_shelf.get("price") * 1.0025, 2 if entry > 10 else 4)
            # TP1 at Day POC
            tp1 = round(poc, 2 if entry > 10 else 4)
            # TP2 at Primary lower long liquidation cluster
            lower_pool = below_3d[0] if below_3d else None
            tp2 = round(lower_pool.get("price") if lower_pool else val * 0.98, 2 if entry > 10 else 4)
            
            risk_dist = abs(sl - entry)
            reward_dist = abs(entry - tp2)
            r_mult = round(reward_dist / risk_dist, 2) if risk_dist > 0 else 0
            ev = round(0.60 * r_mult - 0.40 * 1.0 - 0.05, 2)
            pullback_detected = True
    else:
        # Bullish trend pullback into lower long liquidation floor
        floor_shelf = below_3d[0] if below_3d else None
        if floor_shelf:
            floor_p = floor_shelf.get("price")
            entry = floor_p
            sec_floor = below_3d[1] if len(below_3d) > 1 else floor_shelf
            sl = round(sec_floor.get("price") * 0.9975, 2 if entry > 10 else 4)
            tp1 = round(poc, 2 if entry > 10 else 4)
            upper_pool = above_3d[0] if above_3d else None
            tp2 = round(upper_pool.get("price") if upper_pool else vah * 1.02, 2 if entry > 10 else 4)
            risk_dist = abs(entry - sl)
            reward_dist = abs(tp2 - entry)
            r_mult = round(reward_dist / risk_dist, 2) if risk_dist > 0 else 0
            ev = round(0.60 * r_mult - 0.40 * 1.0 - 0.05, 2)
            pullback_detected = True

    return {
        "sym": sym,
        "last": last,
        "chg24h": chg,
        "val": val,
        "poc": poc,
        "vah": vah,
        "vwap": vwap,
        "zScore": z_score,
        "h1_ema13": h1_13,
        "h1_ema89": h1_89,
        "h4_ema13": h4_13,
        "h4_ema89": h4_89,
        "htf_bias": htf_bias,
        "m15_rsi": m15_rsi,
        "h1_rsi": h1_rsi,
        "h4_rsi": h4_rsi,
        "lsr": lsr,
        "shorts_vol": shorts_vol,
        "longs_vol": longs_vol,
        "above_3d": above_3d[:2],
        "below_3d": below_3d[:2],
        "ask_walls": ask_walls[:2],
        "bid_walls": bid_walls[:2],
        "imbalance": imbalance,
        "pullback_detected": pullback_detected,
        "archetype": archetype,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "r_mult": r_mult,
        "ev": ev
    }

from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=6) as executor:
    audits = list(executor.map(audit_symbol, symbols))

print(json.dumps(audits, indent=2))
