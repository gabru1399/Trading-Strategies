"""C:\\Users\\SIGMA\\Documents\\Trading-Strategies\\HFT\\research\\live_edge_discovery.py
Live Market Edge Discovery & Quantitative Microstructure Screener.
Connects to live Delta Exchange India and Binance Futures simultaneously.
Measures real-time bid-ask spreads (bps), cross-venue lead-lag basis, and expected value (EV)
across the entire live perpetual universe to identify genuine quantitative market edges.
"""

import asyncio
import json
import time
import urllib.request
from typing import Dict, Any, List, Optional
import numpy as np

import sys
from pathlib import Path
HFT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(HFT_ROOT))

from core.delta_client import DeltaClient
from core.orderbook import L2OrderBook


async def fetch_binance_futures_tickers() -> Dict[str, float]:
    """Fetch all Binance USDT-M Futures live mid-prices via REST API."""
    url = "https://fapi.binance.com/fapi/v1/ticker/bookTicker"
    loop = asyncio.get_event_loop()
    def _get():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    
    try:
        data = await loop.run_in_executor(None, _get)
        prices = {}
        for item in data:
            sym = item.get("symbol", "").upper()
            if sym.endswith("USDT"):
                base = sym.replace("USDT", "")
                bid = float(item.get("bidPrice", 0))
                ask = float(item.get("askPrice", 0))
                if bid > 0 and ask > 0:
                    prices[base] = (bid + ask) / 2.0
        return prices
    except Exception as e:
        print(f"[Warning] Failed to fetch Binance book tickers: {e}")
        return {}


async def run_live_edge_discovery():
    print("=" * 80)
    print("🚀 STARTING LIVE MARKET HFT EDGE DISCOVERY (CITADEL / JANE STREET STANDARDS)")
    print("=" * 80)
    
    client = DeltaClient()
    await client.sync_server_time()
    
    print("\n1. Fetching active perpetuals from Delta Exchange India...")
    tickers = await client.get_tickers()
    perps = [t for t in tickers if t.get("contract_type") == "perpetual_futures"]
    # Filter for active contracts with meaningful liquidity
    active_perps = [t for t in perps if float(t.get("turnover_usd") or 0) > 5000]
    active_perps.sort(key=lambda x: float(x.get("turnover_usd") or 0), reverse=True)
    print(f"   -> Found {len(perps)} total perpetuals, {len(active_perps)} active perpetuals (> $5k turnover).")

    print("\n2. Ingesting global benchmark prices from Binance Futures...")
    binance_prices = await fetch_binance_futures_tickers()
    print(f"   -> Ingested {len(binance_prices)} live Binance Futures markets.")

    print("\n3. Scanning orderbook microstructure, spreads & lead-lag basis across top candidates...")
    results = []

    # Analyze top 25 most active perps
    top_candidates = active_perps[:25]
    for perp in top_candidates:
        sym = perp.get("symbol")
        turnover = float(perp.get("turnover_usd") or 0)
        
        # Derive base coin name (e.g. BTCUSD -> BTC, 1000PEPEUSD -> 1000PEPE)
        base_coin = sym.replace("USD", "").replace("USDT", "")
        
        try:
            book_data = await client.get_l2_orderbook(sym, depth=10)
            raw_buys = book_data.get("buy", [])
            raw_sells = book_data.get("sell", [])
            
            bids = [(float(b["price"]), float(b["size"])) for b in raw_buys if "price" in b and "size" in b]
            asks = [(float(a["price"]), float(a["size"])) for a in raw_sells if "price" in a and "size" in a]

            if not bids or not asks:
                continue

            best_bid = bids[0][0]
            best_ask = asks[0][0]
            bid_size = bids[0][1]
            ask_size = asks[0][1]
            mid_price = (best_bid + best_ask) / 2.0
            spread = best_ask - best_bid
            spread_bps = (spread / mid_price) * 10000.0 if mid_price > 0 else 0.0

            # Depth imbalance (top 5 levels)
            top_bid_vol = sum(s for _, s in bids[:5])
            top_ask_vol = sum(s for _, s in asks[:5])
            imbalance = (top_bid_vol - top_ask_vol) / max(0.001, top_bid_vol + top_ask_vol)

            # Compare with Binance price
            bin_price = binance_prices.get(base_coin)
            basis_bps = None
            if bin_price and bin_price > 0:
                basis_bps = ((mid_price - bin_price) / bin_price) * 10000.0

            # Expected Value Assessment for Model 1 (Passive Market Making):
            # Net Edge = Spread BPS - (2 * Maker Fee Rate = 0 bps) - Adverse Selection Buffer (30% of spread)
            # Maker fee on Delta is 0.00%
            model1_ev_bps = spread_bps * 0.70  # Capture 70% of half-spread after adverse selection

            # Expected Value Assessment for Model 2 (Lead-Lag Sniping):
            # Profitable if |basis_bps| > 8 bps (exceeds taker fee of 5 bps + slippage)
            model2_viable = basis_bps is not None and abs(basis_bps) >= 8.0

            results.append({
                "symbol": sym,
                "base_coin": base_coin,
                "mid_price": mid_price,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread_bps": spread_bps,
                "imbalance": imbalance,
                "turnover_usd": turnover,
                "binance_price": bin_price,
                "basis_bps": basis_bps,
                "model1_ev_bps": model1_ev_bps,
                "model2_viable": model2_viable,
            })
        except Exception as e:
            continue

    await client.close()

    print("\n" + "=" * 105)
    print(f"{'SYMBOL':<10} | {'MID PRICE':<10} | {'SPREAD (bps)':<12} | {'IMBALANCE':<10} | {'BINANCE PX':<11} | {'BASIS (bps)':<11} | {'M1 EDGE':<10} | {'M2 LEAD-LAG'}")
    print("=" * 105)

    # Sort results by Model 1 edge
    results.sort(key=lambda x: x["spread_bps"], reverse=True)

    for r in results:
        bin_str = f"{r['binance_price']:.4f}" if r['binance_price'] else "N/A"
        basis_str = f"{r['basis_bps']:+.1f}" if r['basis_bps'] is not None else "N/A"
        m2_str = "🔥 SNIPE READY" if r['model2_viable'] else "Normal"
        print(f"{r['symbol']:<10} | {r['mid_price']:<10.4f} | {r['spread_bps']:<12.1f} | {r['imbalance']:<+10.2f} | {bin_str:<11} | {basis_str:<11} | {r['model1_ev_bps']:<10.1f} | {m2_str}")

    print("=" * 105)
    
    # Save discovery artifact
    out_file = HFT_ROOT / "research" / "live_edge_discovery_results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✅ Discovery completed! Full telemetry saved to: {out_file}")

    return results


if __name__ == "__main__":
    asyncio.run(run_live_edge_discovery())
