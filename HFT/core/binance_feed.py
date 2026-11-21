"""C:\\Users\\SIGMA\\Documents\\Trading-Strategies\\HFT\\core\\binance_feed.py
Real-time streaming connector to Binance USDT-M Futures WebSocket feeds.
Used as the global price discovery reference to measure lead-lag latency against Delta Exchange India.
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Callable
import websockets

BINANCE_WS_FUTURES = "wss://fstream.binance.com/ws"


class BinanceFuturesFeed:
    def __init__(self, symbols: List[str]):
        # Convert symbols to lowercase without punctuation (e.g. BTC -> btcusdt)
        self.symbols = [s.lower() if s.lower().endswith("usdt") else f"{s.lower()}usdt" for s in symbols]
        self.prices: Dict[str, float] = {}
        self.bid_asks: Dict[str, Dict[str, float]] = {}
        self.timestamps: Dict[str, float] = {}
        self._running = False
        self._callbacks: List[Callable[[str, float, float], None]] = []

    def on_tick(self, callback: Callable[[str, float, float], None]):
        """Register a callback: callback(symbol, price, timestamp)."""
        self._callbacks.append(callback)

    async def start(self):
        self._running = True
        streams = "/".join([f"{s}@bookTicker" for s in self.symbols])
        url = f"wss://fstream.binance.com/stream?streams={streams}"
        
        while self._running:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                    while self._running:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        payload = data.get("data", {})
                        sym = payload.get("s", "").upper()
                        b_price = float(payload.get("b", 0))
                        a_price = float(payload.get("a", 0))
                        if b_price > 0 and a_price > 0:
                            mid = (b_price + a_price) / 2.0
                            ts = time.time()
                            clean_sym = sym.replace("USDT", "")
                            self.prices[clean_sym] = mid
                            self.bid_asks[clean_sym] = {
                                "bid": b_price,
                                "ask": a_price,
                                "bid_size": float(payload.get("B", 0)),
                                "ask_size": float(payload.get("A", 0)),
                            }
                            self.timestamps[clean_sym] = ts
                            for cb in self._callbacks:
                                cb(clean_sym, mid, ts)
            except Exception as e:
                if self._running:
                    await asyncio.sleep(1.0)

    def stop(self):
        self._running = False
