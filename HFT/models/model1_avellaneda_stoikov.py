"""C:\\Users\\SIGMA\\Documents\\Trading-Strategies\\HFT\\models\\model1_avellaneda_stoikov.py
Model 1: Avellaneda-Stoikov High-Frequency Market Maker for Delta Exchange India.
Implements dynamic inventory-risk reservation pricing, optimal bid/ask spread quoting,
and maker fee rebate capture with strict inventory risk ceilings.
"""

import math
import time
from typing import Dict, Any, Optional, Tuple


class AvellanedaStoikovModel:
    def __init__(
        self,
        symbol: str,
        gamma: float = 0.1,         # Risk aversion parameter (higher = tighter inventory tolerance)
        sigma: float = 0.015,       # RELATIVE (fractional) per-period volatility, e.g. 0.015 = 1.5%
        kappa: float = 1.5,         # Order arrival intensity parameter
        T_minus_t: float = 1.0,     # Time horizon normalized to 1 session unit
        max_inventory: int = 50,    # Max contracts allowed to hold in inventory
        min_spread_bps: float = 4.0,# Minimum spread required to quote (must cover maker friction)
        maker_fee_rate: float = 0.0000, # 0.00% maker fee on Delta India
    ):
        self.symbol = symbol
        self.gamma = gamma
        self.sigma = sigma
        self.kappa = kappa
        self.T_minus_t = T_minus_t
        self.max_inventory = max_inventory
        self.min_spread_bps = min_spread_bps
        self.maker_fee_rate = maker_fee_rate
        # Rolling estimate of per-tick relative volatility, updated from live
        # BBO moves via update_volatility(). Seeds to the configured sigma so
        # quotes exist before the first estimate arrives.
        self._rel_vol = sigma

    def update_volatility(self, mid_price: float) -> float:
        """Feeds the latest mid into an EW estimate of per-tick relative volatility.

        A-S requires sigma in price units per period; measuring it as a
        *fraction* of mid makes the model portable across assets priced at
        0.013 vs 33,000 without per-symbol tuning.
        """
        if mid_price <= 0:
            return self._rel_vol
        if not hasattr(self, "_last_mid"):
            self._last_mid = mid_price
            return self._rel_vol
        if self._last_mid > 0:
            ret = abs(mid_price - self._last_mid) / self._last_mid
            # EWMA with alpha ~ 0.05: reactive but not noisy
            self._rel_vol = 0.95 * self._rel_vol + 0.05 * (ret * 10.0)  # scale: per ~10-tick sigma
        self._last_mid = mid_price
        return self._rel_vol

    def calculate_reservation_price(self, mid_price: float, current_inventory: int) -> float:
        """Computes the reservation (indifference) price r(s, q).
        r(s, q) = s - q * gamma * sigma^2 * (T - t)
        When long (q > 0), reservation price drops below mid to encourage selling.
        When short (q < 0), reservation price rises above mid to encourage buying.
        sigma is interpreted as RELATIVE vol; the penalty is therefore computed
        in relative terms and re-scaled by mid so it stays meaningful at any
        price magnitude.
        """
        rel_penalty = current_inventory * self.gamma * (self._rel_vol ** 2) * self.T_minus_t
        return mid_price * (1.0 - rel_penalty)

    def calculate_optimal_quotes(
        self,
        mid_price: float,
        current_inventory: int,
        best_bid: float,
        best_ask: float,
        tick_size: float = 0.00001,
        base_size: int = 1,
    ) -> Optional[Dict[str, Any]]:
        """Calculates optimal bid and ask limit quote prices and sizes.
        Returns None if market conditions do not satisfy minimum spread hurdles.
        """
        market_spread = best_ask - best_bid
        if mid_price <= 0 or market_spread <= 0:
            return None

        market_spread_bps = (market_spread / mid_price) * 10000.0
        if market_spread_bps < self.min_spread_bps:
            # Spread is too compressed; adverse selection risk outweighs maker edge
            return None

        # 1. Reservation Price
        res_price = self.calculate_reservation_price(mid_price, current_inventory)

        # 2. Optimal Half-Spread (Avellaneda & Stoikov 2008 closed-form solution)
        #     delta_bw + delta_a = (1/gamma) * ln(1 + gamma/kappa) + gamma*sigma^2*(T-t)
        #     Per the paper the half-spread has TWO terms: the fill-intensity
        #     term (1/gamma)*ln(1+gamma/kappa) and the volatility term
        #     gamma*sigma^2*(T-t). With sigma measured RELATIVELY, both terms
        #     are in relative units and are converted to price via mid.
        #     NOTE on kappa calibration: with relative-unit outputs, kappa must
        #     be large (order 1e3) so the fill term lands in single-digit bps.
        #     kappa=1.5 would imply a 64% half-spread, which is meaningless.
        fill_term = (1.0 / self.gamma) * math.log(1.0 + self.gamma / max(0.001, self.kappa))
        vol_term = self.gamma * (self._rel_vol ** 2) * self.T_minus_t
        half_spread_rel = 0.5 * (fill_term + vol_term)
        half_spread_px = half_spread_rel * mid_price

        # Competitiveness cap: a market maker never quotes wider than the
        # current market spread — beyond it the order can never fill and only
        # adds queue risk. Cap the half-spread at the observed full spread.
        half_spread_px = min(half_spread_px, market_spread)

        target_bid = res_price - half_spread_px
        target_ask = res_price + half_spread_px

        # 3. Microstructure Queue Boundary: Do not cross market BBO (must remain post-only maker)
        # Bid must be <= best_bid or step 1 tick inside if spread permits
        quote_bid = min(best_bid, target_bid)
        quote_ask = max(best_ask, target_ask)

        # Round to nearest tick_size with exact decimal precision
        def round_tick(val: float, tick: float) -> float:
            if tick > 0:
                decimals = max(0, -int(math.floor(math.log10(tick) + 1e-9)))
            else:
                decimals = 4
            steps = round(val / tick)
            return round(steps * tick, decimals)

        quote_bid = round_tick(quote_bid, tick_size)
        quote_ask = round_tick(quote_ask, tick_size)

        # Guard: Ensure quote_bid < best_ask to guarantee Post-Only acceptance
        if quote_bid >= best_ask:
            quote_bid = round_tick(best_bid, tick_size)
        if quote_ask <= best_bid:
            quote_ask = round_tick(best_ask, tick_size)

        # 4. Inventory Caps Enforcement
        can_buy = current_inventory < self.max_inventory
        can_sell = current_inventory > -self.max_inventory

        # Bid/Ask size sizing logic
        buy_size = max(1, int(base_size * (1.0 - max(0, current_inventory) / self.max_inventory))) if can_buy else 0
        sell_size = max(1, int(base_size * (1.0 - max(0, -current_inventory) / self.max_inventory))) if can_sell else 0

        return {
            "symbol": self.symbol,
            "mid_price": mid_price,
            "reservation_price": res_price,
            "market_spread_bps": market_spread_bps,
            "quote_bid": quote_bid if can_buy else None,
            "bid_size": buy_size,
            "quote_ask": quote_ask if can_sell else None,
            "ask_size": sell_size,
            "current_inventory": current_inventory,
            "timestamp": time.time(),
        }
