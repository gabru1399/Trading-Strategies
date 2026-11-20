"""C:\\Users\\SIGMA\\Documents\\Trading-Strategies\\HFT\\core\\orderbook.py
High-speed in-memory Level 2 orderbook model with microstructure analytics.
Calculates mid-price, basis point spread, depth imbalance, and volume-weighted micro-price.
"""

from typing import Dict, List, Tuple, Optional
import numpy as np


class L2OrderBook:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bids: List[Tuple[float, float]] = []  # sorted descending: [(price, size), ...]
        self.asks: List[Tuple[float, float]] = []  # sorted ascending: [(price, size), ...]
        self.timestamp: float = 0.0

    def update_from_snapshot(self, bids: List[Any], asks: List[Any], timestamp: float = 0.0):
        """Update full L2 depth from REST or WS snapshot."""
        parsed_bids = []
        for b in bids:
            if isinstance(b, dict):
                parsed_bids.append((float(b.get("price", 0)), float(b.get("size", 0))))
            elif isinstance(b, (list, tuple)) and len(b) >= 2:
                parsed_bids.append((float(b[0]), float(b[1])))

        parsed_asks = []
        for a in asks:
            if isinstance(a, dict):
                parsed_asks.append((float(a.get("price", 0)), float(a.get("size", 0))))
            elif isinstance(a, (list, tuple)) and len(a) >= 2:
                parsed_asks.append((float(a[0]), float(a[1])))

        parsed_bids = [(p, s) for p, s in parsed_bids if s > 0]
        parsed_asks = [(p, s) for p, s in parsed_asks if s > 0]
        
        # Sort bids descending, asks ascending
        self.bids = sorted(parsed_bids, key=lambda x: x[0], reverse=True)
        self.asks = sorted(parsed_asks, key=lambda x: x[0])
        self.timestamp = timestamp

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0][0] if self.asks else None

    @property
    def best_bid_size(self) -> float:
        return self.bids[0][1] if self.bids else 0.0

    @property
    def best_ask_size(self) -> float:
        return self.asks[0][1] if self.asks else 0.0

    @property
    def mid_price(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2.0
        return self.best_bid or self.best_ask

    @property
    def spread(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return max(0.0, self.best_ask - self.best_bid)
        return None

    @property
    def spread_bps(self) -> Optional[float]:
        mid = self.mid_price
        sp = self.spread
        if mid and sp is not None and mid > 0:
            return (sp / mid) * 10000.0
        return None

    @property
    def micro_price(self) -> Optional[float]:
        """Volume-Weighted Mid-Price (Stoikov micro-price)."""
        if not (self.best_bid and self.best_ask):
            return self.mid_price
        qb = self.best_bid_size
        qa = self.best_ask_size
        if qb + qa == 0:
            return self.mid_price
        # Micro-price leans toward the thinner side
        return (qb * self.best_ask + qa * self.best_bid) / (qb + qa)

    def depth_imbalance(self, levels: int = 5) -> float:
        """Top-K level order book imbalance in range [-1.0, +1.0].
        Positive indicates heavy buy depth; negative indicates heavy sell depth.
        """
        bid_vol = sum(s for _, s in self.bids[:levels])
        ask_vol = sum(s for _, s in self.asks[:levels])
        total = bid_vol + ask_vol
        if total <= 0:
            return 0.0
        return (bid_vol - ask_vol) / total
