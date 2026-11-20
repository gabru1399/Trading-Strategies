"""C:\\Users\\SIGMA\\Documents\\Trading-Strategies\\HFT\\models\\model2_binance_lead_lag.py
Model 2: Cross-Venue Lead-Lag Latency Arbitrage & Sniping Model.
Exploits the 200ms–600ms pricing latency between Binance Futures (global leader)
and Delta Exchange India (local follower).
"""

import time
from typing import Dict, Any, Optional, List
import numpy as np


class BinanceDeltaLeadLagModel:
    def __init__(
        self,
        symbol: str,
        lookback_seconds: float = 3.0,
        shock_threshold_bps: float = 12.0,  # Jump threshold on Binance in bps (e.g. 12 bps in <3s)
        taker_fee_bps: float = 5.0,         # Delta India taker fee (0.05% = 5 bps)
        min_net_edge_bps: float = 6.0,      # Minimum net edge required after fees
    ):
        self.symbol = symbol
        self.lookback_seconds = lookback_seconds
        self.shock_threshold_bps = shock_threshold_bps
        self.taker_fee_bps = taker_fee_bps
        self.min_net_edge_bps = min_net_edge_bps
        
        # Ring buffer for Binance tick history: [(timestamp, price), ...]
        self.binance_history: List[Tuple[float, float]] = []

    def update_binance_price(self, price: float, timestamp: Optional[float] = None):
        ts = timestamp or time.time()
        self.binance_history.append((ts, price))
        # Trim history older than lookback
        cutoff = ts - (self.lookback_seconds * 2.0)
        self.binance_history = [(t, p) for t, p in self.binance_history if t >= cutoff]

    def evaluate_lead_lag_opportunity(
        self,
        delta_best_bid: float,
        delta_best_ask: float,
        delta_timestamp: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Evaluates whether a high-momentum shock on Binance has created an unpriced
        stale-quote mispricing on Delta Exchange India.
        """
        now = delta_timestamp or time.time()
        if len(self.binance_history) < 2:
            return None

        current_binance_price = self.binance_history[-1][1]
        
        # Find the oldest Binance price within the lookback window
        window_start_time = now - self.lookback_seconds
        past_ticks = [p for t, p in self.binance_history if t <= window_start_time]
        if not past_ticks:
            past_binance_price = self.binance_history[0][1]
        else:
            past_binance_price = past_ticks[-1]

        if past_binance_price <= 0:
            return None

        # 1. Compute Binance Price Velocity Shock in basis points
        binance_return_bps = ((current_binance_price - past_binance_price) / past_binance_price) * 10000.0

        # 2. Check for Bullish Momentum Lead-Lag Mispricing
        # Binance has surged UP by > shock_threshold_bps, but Delta Ask is still below Binance Price!
        if binance_return_bps >= self.shock_threshold_bps:
            gross_edge_bps = ((current_binance_price - delta_best_ask) / delta_best_ask) * 10000.0
            net_edge_bps = gross_edge_bps - self.taker_fee_bps
            if net_edge_bps >= self.min_net_edge_bps:
                return {
                    "signal": "SNIPE_BUY",
                    "symbol": self.symbol,
                    "binance_velocity_bps": binance_return_bps,
                    "current_binance_price": current_binance_price,
                    "delta_best_ask": delta_best_ask,
                    "gross_edge_bps": gross_edge_bps,
                    "net_edge_bps": net_edge_bps,
                    "action_price": delta_best_ask,
                    "side": "buy",
                    "reason": f"Binance surged +{binance_return_bps:.1f} bps; Delta ask ({delta_best_ask}) is stale by {gross_edge_bps:.1f} bps.",
                    "timestamp": now,
                }

        # 3. Check for Bearish Momentum Lead-Lag Mispricing
        # Binance has dumped DOWN by > shock_threshold_bps, but Delta Bid is still above Binance Price!
        elif binance_return_bps <= -self.shock_threshold_bps:
            gross_edge_bps = ((delta_best_bid - current_binance_price) / current_binance_price) * 10000.0
            net_edge_bps = gross_edge_bps - self.taker_fee_bps
            if net_edge_bps >= self.min_net_edge_bps:
                return {
                    "signal": "SNIPE_SELL",
                    "symbol": self.symbol,
                    "binance_velocity_bps": binance_return_bps,
                    "current_binance_price": current_binance_price,
                    "delta_best_bid": delta_best_bid,
                    "gross_edge_bps": gross_edge_bps,
                    "net_edge_bps": net_edge_bps,
                    "action_price": delta_best_bid,
                    "side": "sell",
                    "reason": f"Binance dumped {binance_return_bps:.1f} bps; Delta bid ({delta_best_bid}) is stale by {gross_edge_bps:.1f} bps.",
                    "timestamp": now,
                }

        return None
