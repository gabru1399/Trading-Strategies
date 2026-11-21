"""C:\\Users\\SIGMA\\Documents\\Trading-Strategies\\HFT\\tests\\test_hft_models.py
Unit tests for HFT models and microstructure analytics.
"""

import unittest
import numpy as np
import sys
from pathlib import Path

HFT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(HFT_ROOT))

from core.orderbook import L2OrderBook
from models.model1_avellaneda_stoikov import AvellanedaStoikovModel
from models.model2_binance_lead_lag import BinanceDeltaLeadLagModel
from models.model3_ofi_microstructure import OrderFlowImbalanceModel


class TestHFTMicrostructure(unittest.TestCase):
    def test_orderbook_metrics(self):
        book = L2OrderBook("BTCUSD")
        bids = [{"price": "59000.0", "size": "10.0"}, {"price": "58990.0", "size": "5.0"}]
        asks = [{"price": "59010.0", "size": "5.0"}, {"price": "59020.0", "size": "15.0"}]
        book.update_from_snapshot(bids, asks)

        self.assertEqual(book.best_bid, 59000.0)
        self.assertEqual(book.best_ask, 59010.0)
        self.assertEqual(book.mid_price, 59005.0)
        self.assertEqual(book.spread, 10.0)
        
        # Spread in bps: (10.0 / 59005.0) * 10000 = 1.6947 bps
        self.assertAlmostEqual(book.spread_bps, 1.69477, places=3)

        # Micro-price: weighted towards thinner side (asks=5 vs bids=10, so price leans to ask)
        # (10 * 59010 + 5 * 59000) / 15 = 59006.6667
        self.assertAlmostEqual(book.micro_price, 59006.6667, places=3)

        # Imbalance: (15 - 20) / 35 = -0.142857
        self.assertAlmostEqual(book.depth_imbalance(2), -0.142857, places=4)

    def test_avellaneda_stoikov_pricing(self):
        model = AvellanedaStoikovModel(
            symbol="RAREUSD",
            gamma=0.1,
            sigma=0.02,
            kappa=1.5,
            max_inventory=50,
            min_spread_bps=5.0,
        )

        mid = 0.0130
        # 1. Flat inventory (q=0): reservation price == mid
        res_flat = model.calculate_reservation_price(mid, current_inventory=0)
        self.assertEqual(res_flat, mid)

        # 2. Long inventory (q=+20): reservation price should be LOWER than mid
        res_long = model.calculate_reservation_price(mid, current_inventory=20)
        self.assertLess(res_long, mid)

        # 3. Short inventory (q=-20): reservation price should be HIGHER than mid
        res_short = model.calculate_reservation_price(mid, current_inventory=-20)
        self.assertGreater(res_short, mid)

        # 4. Optimal quotes generation
        quotes = model.calculate_optimal_quotes(
            mid_price=0.0130,
            current_inventory=10,
            best_bid=0.0128,
            best_ask=0.0132,
            tick_size=0.0001,
        )
        self.assertIsNotNone(quotes)
        self.assertIn("quote_bid", quotes)
        self.assertIn("quote_ask", quotes)
        self.assertLessEqual(quotes["quote_bid"], 0.0128)
        self.assertGreaterEqual(quotes["quote_ask"], 0.0132)

    def test_binance_lead_lag_sniping(self):
        model = BinanceDeltaLeadLagModel(
            symbol="BTCUSD",
            lookback_seconds=2.0,
            shock_threshold_bps=10.0,
            taker_fee_bps=5.0,
            min_net_edge_bps=5.0,
        )

        t0 = 1000.0
        # Normal ticks
        model.update_binance_price(59000.0, timestamp=t0)
        # Surge on Binance: 59000 -> 59120 (+20.3 bps in 1 second)
        model.update_binance_price(59120.0, timestamp=t0 + 1.0)

        # Delta ask is lagging at 59010.0 (stale resting orders)
        signal = model.evaluate_lead_lag_opportunity(
            delta_best_bid=59000.0,
            delta_best_ask=59010.0,
            delta_timestamp=t0 + 1.0,
        )

        self.assertIsNotNone(signal)
        self.assertEqual(signal["signal"], "SNIPE_BUY")
        self.assertEqual(signal["side"], "buy")
        self.assertGreater(signal["net_edge_bps"], 5.0)

    def test_order_flow_imbalance(self):
        model = OrderFlowImbalanceModel(symbol="DOGEUSD", ofi_window=5, zscore_threshold=1.5)

        # Initial book
        model.update_book(best_bid=0.0540, best_bid_size=100.0, best_ask=0.0542, best_ask_size=100.0)

        # Aggressive buy queue accumulation: bids continuously increase in price and size
        sig = None
        for i in range(1, 8):
            sig = model.update_book(
                best_bid=0.0540 + (i * 0.0001),
                best_bid_size=100.0 + (i * 50.0),
                best_ask=0.0550,
                best_ask_size=50.0,
            )

        self.assertIsNotNone(sig)
        self.assertEqual(sig["signal"], "OFI_BUY")
        self.assertGreater(sig["z_score"], 1.5)


if __name__ == "__main__":
    unittest.main()
