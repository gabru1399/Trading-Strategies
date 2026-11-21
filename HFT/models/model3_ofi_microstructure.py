"""C:\\Users\\SIGMA\\Documents\\Trading-Strategies\\HFT\\models\\model3_ofi_microstructure.py
Model 3: Order Flow Imbalance (OFI) & Microstructure Drift Engine.
Implements the Cont, Kukanov & Stoikov (2014) high-frequency OFI metric to detect
liquidity depletion and predict short-horizon (1s-5s) price impact.
"""

from typing import Dict, Any, Optional, List, Tuple
import numpy as np


class OrderFlowImbalanceModel:
    def __init__(
        self,
        symbol: str,
        ofi_window: int = 15,          # Rolling window of OFI ticks
        zscore_threshold: float = 2.0, # Z-score threshold for directional conviction
    ):
        self.symbol = symbol
        self.ofi_window = ofi_window
        self.zscore_threshold = zscore_threshold

        self.prev_best_bid: Optional[float] = None
        self.prev_best_bid_size: float = 0.0
        self.prev_best_ask: Optional[float] = None
        self.prev_best_ask_size: float = 0.0

        self.ofi_history: List[float] = []

    def update_book(
        self,
        best_bid: float,
        best_bid_size: float,
        best_ask: float,
        best_ask_size: float,
    ) -> Optional[Dict[str, Any]]:
        """Updates the L2 book state, computes instantaneous OFI, and evaluates
        whether order-flow imbalance generates a high-probability drift signal.
        """
        if self.prev_best_bid is None or self.prev_best_ask is None:
            self.prev_best_bid = best_bid
            self.prev_best_bid_size = best_bid_size
            self.prev_best_ask = best_ask
            self.prev_best_ask_size = best_ask_size
            return None

        # 1. Compute Change in Bid Queue (delta_W_b)
        if best_bid > self.prev_best_bid:
            delta_wb = best_bid_size
        elif best_bid == self.prev_best_bid:
            delta_wb = best_bid_size - self.prev_best_bid_size
        else:
            delta_wb = -self.prev_best_bid_size

        # 2. Compute Change in Ask Queue (delta_W_a)
        if best_ask > self.prev_best_ask:
            delta_wa = -self.prev_best_ask_size
        elif best_ask == self.prev_best_ask:
            delta_wa = best_ask_size - self.prev_best_ask_size
        else:
            delta_wa = self.prev_best_ask_size

        # 3. Cont-Kukanov-Stoikov OFI = delta_wb - delta_wa
        current_ofi = delta_wb - delta_wa
        self.ofi_history.append(current_ofi)
        if len(self.ofi_history) > self.ofi_window * 3:
            self.ofi_history = self.ofi_history[-self.ofi_window * 3:]

        # Update cached state
        self.prev_best_bid = best_bid
        self.prev_best_bid_size = best_bid_size
        self.prev_best_ask = best_ask
        self.prev_best_ask_size = best_ask_size

        # 4. Statistical Evaluation: Rolling Mean & Std of OFI
        if len(self.ofi_history) < self.ofi_window:
            return None

        recent_window = self.ofi_history[-self.ofi_window:]
        mean_ofi = float(np.mean(recent_window))
        std_ofi = float(np.std(recent_window))

        if std_ofi <= 1e-6:
            return None

        z_score = mean_ofi / std_ofi

        # Bullish OFI signal: Aggressive accumulation depleting asks
        if z_score >= self.zscore_threshold:
            return {
                "signal": "OFI_BUY",
                "symbol": self.symbol,
                "z_score": z_score,
                "current_ofi": current_ofi,
                "mean_ofi": mean_ofi,
                "suggested_price": best_bid,
                "side": "buy",
                "reason": f"Strong buying pressure: OFI Z-score = +{z_score:.2f} (depleting ask depth).",
            }
        # Bearish OFI signal: Aggressive distribution depleting bids
        elif z_score <= -self.zscore_threshold:
            return {
                "signal": "OFI_SELL",
                "symbol": self.symbol,
                "z_score": z_score,
                "current_ofi": current_ofi,
                "mean_ofi": mean_ofi,
                "suggested_price": best_ask,
                "side": "sell",
                "reason": f"Strong selling pressure: OFI Z-score = {z_score:.2f} (depleting bid depth).",
            }

        return None
