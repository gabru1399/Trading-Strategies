import urllib.request, json, sys
from concurrent.futures import ThreadPoolExecutor

symbols = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "LTC", "SUI", "NEAR"]

def fetch_symbol(sym):
    url_mkt = f"http://127.0.0.1:3000/api/cg/market?sym={sym}"
    url_liq = f"http://127.0.0.1:3000/api/cg/liqlevels?sym={sym}&range=3d"
    url_walls = f"http://127.0.0.1:3000/api/cg/bookwalls?sym={sym}"
    
    row = {"symbol": sym}
    try:
        req = urllib.request.Request(url_mkt, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            mkt = json.loads(resp.read().decode())
            p = mkt.get("price", {})
            row["last"] = p.get("last")
            row["chg24h"] = p.get("chgDayPct")
            auc = mkt.get("auction", {}).get("day", {})
            row["val_day"] = auc.get("val")
            row["poc_day"] = auc.get("poc")
            row["vah_day"] = auc.get("vah")
            vwap = mkt.get("vwap", {})
            row["vwap"] = vwap.get("vwap")
            row["zScore"] = vwap.get("zScore")
            ema = mkt.get("ema", {})
            row["h4_ema13"] = ema.get("h4", {}).get("ema13")
            row["h4_ema89"] = ema.get("h4", {}).get("ema89")
            row["h4_trend"] = "BEAR" if row["h4_ema13"] and row["h4_ema89"] and row["h4_ema13"] < row["h4_ema89"] else "BULL"
            rsi = mkt.get("rsi", {})
            row["m15_rsi"] = rsi.get("m15")
            row["h1_rsi"] = rsi.get("h1")
            row["h4_rsi"] = rsi.get("h4")
    except Exception as e:
        row["mkt_error"] = str(e)

    try:
        req = urllib.request.Request(url_liq, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            liq = json.loads(resp.read().decode())
            row["liq_above"] = liq.get("keyLevels", {}).get("above", [])[:2]
            row["liq_below"] = liq.get("keyLevels", {}).get("below", [])[:2]
            stats = liq.get("stats", {})
            longs = stats.get("totalLongVol", 0) or 0
            shorts = stats.get("totalShortVol", 0) or 0
            row["lsr"] = round(shorts / longs, 2) if longs > 0 else 0
            row["liq_longs"] = longs
            row["liq_shorts"] = shorts
    except Exception as e:
        row["liq_error"] = str(e)

    try:
        req = urllib.request.Request(url_walls, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            walls = json.loads(resp.read().decode())
            row["bid_walls"] = walls.get("walls", {}).get("bids", [])[:1]
            row["ask_walls"] = walls.get("walls", {}).get("asks", [])[:1]
            row["imbalance"] = walls.get("depth", {}).get("imbalancePct")
    except Exception as e:
        row["walls_error"] = str(e)

    return row

with ThreadPoolExecutor(max_workers=6) as executor:
    results = list(executor.map(fetch_symbol, symbols))

print(json.dumps(results, indent=2))
sys.stdout.flush()
