import urllib.request, json, sys, os
from concurrent.futures import ThreadPoolExecutor

symbols = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX"]

def get_json(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return {}

def process_sym(sym):
    mkt = get_json(f"http://127.0.0.1:3000/api/cg/market?sym={sym}")
    liq = get_json(f"http://127.0.0.1:3000/api/cg/liqlevels?sym={sym}&range=3d")
    walls = get_json(f"http://127.0.0.1:3000/api/cg/bookwalls?sym={sym}")

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
    h1_13 = ema.get("h1", {}).get("ema13")
    h1_89 = ema.get("h1", {}).get("ema89")
    h4_13 = ema.get("h4", {}).get("ema13")
    h4_89 = ema.get("h4", {}).get("ema89")
    
    rsi = mkt.get("rsi", {})
    m15_rsi = rsi.get("m15", 50)
    h1_rsi = rsi.get("h1", 50)
    h4_rsi = rsi.get("h4", 50)
    
    stats = liq.get("stats", {})
    above = stats.get("keyLevels", {}).get("above", [])
    below = stats.get("keyLevels", {}).get("below", [])
    shorts_vol = stats.get("totals", {}).get("shorts", 0)
    longs_vol = stats.get("totals", {}).get("longs", 0)
    lsr = round(shorts_vol / longs_vol, 2) if longs_vol > 0 else 0
    
    model_walls = walls.get("model", {}).get("walls", [])
    ask_walls = [w for w in model_walls if w.get("side") == "a" and w.get("price") >= last][:2]
    bid_walls = [w for w in model_walls if w.get("side") == "b" and w.get("price") <= last][:2]
    imbalance = walls.get("model", {}).get("imbalance", 0)

    # HTF Trend determination:
    # If 4h or 1h EMA 13 < 89 and price < day VAH -> BEAR trend pullback
    htf_bias = "BEAR" if (h4_13 and h4_89 and h4_13 < h4_89) or (h1_13 and h1_89 and h1_13 < h1_89) else "BULL"
    
    # ITCLS Formulations
    overhead_shelf = above[0] if above else None
    support_floor = below[0] if below else None

    # Calculate Setup Geometry
    if htf_bias == "BEAR":
        # Short setup: enter at overhead short liquidation shelf
        entry = overhead_shelf.get("price") if overhead_shelf else round(vah * 1.005, 4)
        sec_shelf = above[1] if len(above) > 1 else overhead_shelf
        sl_price = round((sec_shelf.get("price") if sec_shelf else entry) * 1.0035, 4 if last < 10 else 2)
        tp1_price = round(poc, 4 if last < 10 else 2)
        tp2_price = round(support_floor.get("price") if support_floor else val * 0.985, 4 if last < 10 else 2)
        risk_dist = abs(sl_price - entry)
        reward_dist = abs(entry - tp2_price)
        r_mult = round(reward_dist / risk_dist, 2) if risk_dist > 0 else 0
        ev = round(0.60 * r_mult - 0.40 * 1.0 - 0.05, 2)
        archetype = "S0_ITCLS_SHORT"
    else:
        # Long setup: enter at support long liquidation floor
        entry = support_floor.get("price") if support_floor else round(val * 0.995, 4)
        sec_floor = below[1] if len(below) > 1 else support_floor
        sl_price = round((sec_floor.get("price") if sec_floor else entry) * 0.9965, 4 if last < 10 else 2)
        tp1_price = round(poc, 4 if last < 10 else 2)
        tp2_price = round(overhead_shelf.get("price") if overhead_shelf else vah * 1.015, 4 if last < 10 else 2)
        risk_dist = abs(entry - sl_price)
        reward_dist = abs(tp2_price - entry)
        r_mult = round(reward_dist / risk_dist, 2) if risk_dist > 0 else 0
        ev = round(0.60 * r_mult - 0.40 * 1.0 - 0.05, 2)
        archetype = "S0_ITCLS_LONG"

    return {
        "symbol": sym,
        "last": last,
        "chg24h": round(chg, 2),
        "val": val,
        "poc": poc,
        "vah": vah,
        "vwap": vwap,
        "zScore": z_score,
        "htf_bias": htf_bias,
        "h1_rsi": round(h1_rsi, 1),
        "h4_rsi": round(h4_rsi, 1),
        "lsr": lsr,
        "shorts_vol": round(shorts_vol, 0),
        "longs_vol": round(longs_vol, 0),
        "overhead_shelf": overhead_shelf,
        "support_floor": support_floor,
        "ask_walls": ask_walls,
        "bid_walls": bid_walls,
        "imbalance": imbalance,
        "archetype": archetype,
        "entry": entry,
        "sl": sl_price,
        "tp1": tp1_price,
        "tp2": tp2_price,
        "r_mult": r_mult,
        "ev": ev
    }

with ThreadPoolExecutor(max_workers=4) as executor:
    audits = list(executor.map(process_sym, symbols))

os.makedirs("data", exist_ok=True)
with open("data/crypto_formulation_r838.json", "w") as f:
    json.dump(audits, f, indent=2)

print(f"Audited {len(audits)} crypto perps successfully!")
for a in audits:
    print(f"{a['symbol']:5} | Last: {a['last']:8} | Bias: {a['htf_bias']:4} | LSR: {a['lsr']:4.1f} | Entry: {a['entry']} | SL: {a['sl']} | TP2: {a['tp2']} | R: {a['r_mult']:4.2f}R | EV: {a['ev']:4.2f}R")
