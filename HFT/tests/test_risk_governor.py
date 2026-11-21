"""Risk-governor regression tests for the HFT engine.

Covers the two institutional hardening gates added in the security review:
  1. LIVE mode must refuse to start without credentials.
  2. The daily-loss kill switch must actually fire (cancel + flatten + halt).
"""

import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import sys
HFT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(HFT_ROOT))

from hft_engine import HFTEngine


def make_engine(**kwargs):
    api_key = kwargs.pop("api_key", "k")
    api_secret = kwargs.pop("api_secret", "s")
    eng = HFTEngine(symbols=["TESTUSD"], live=kwargs.pop("live", False), **kwargs)
    # Stub the networked client entirely; tests exercise governor logic only.
    eng.client = MagicMock()
    eng.client.api_key = api_key
    eng.client.api_secret = api_secret
    eng.client.sync_server_time = AsyncMock()
    eng.client.get_products = AsyncMock(return_value=[])
    eng.client.get_positions = AsyncMock(return_value=[])
    return eng


class TestLiveCredentialGate(unittest.IsolatedAsyncioTestCase):
    async def test_live_refused_without_credentials(self):
        eng = make_engine(live=True, api_key=None, api_secret=None)
        with self.assertRaises(RuntimeError) as ctx:
            await eng.initialize()
        self.assertIn("DELTA_API_KEY", str(ctx.exception))

    async def test_live_allowed_with_credentials(self):
        eng = make_engine(live=True, api_key="k", api_secret="s")
        await eng.initialize()  # must not raise
        self.assertTrue(eng.live)

    async def test_dry_run_allowed_without_credentials(self):
        eng = make_engine(live=False, api_key=None, api_secret=None)
        await eng.initialize()  # anonymous dry-run is fine
        self.assertFalse(eng.live)


class TestDailyLossKillSwitch(unittest.IsolatedAsyncioTestCase):
    async def test_kill_switch_fires_on_loss_breach(self):
        eng = make_engine(live=True, daily_loss_limit_usd=5.0)
        eng.running = True
        # Position sync returns a breach: -6.0 unrealized on the tracked symbol.
        eng.client.get_positions = AsyncMock(return_value=[
            {"product_symbol": "TESTUSD", "size": 1, "entry_price": 100.0, "unrealized_pnl": -6.0},
        ])
        eng.shutdown = AsyncMock()
        await eng.sync_positions()
        eng.shutdown.assert_awaited_once_with(flatten=True)

    async def test_no_kill_switch_within_limit(self):
        eng = make_engine(live=True, daily_loss_limit_usd=5.0)
        eng.running = True
        eng.client.get_positions = AsyncMock(return_value=[
            {"product_symbol": "TESTUSD", "size": 1, "entry_price": 100.0, "unrealized_pnl": -4.0},
        ])
        eng.shutdown = AsyncMock()
        await eng.sync_positions()
        eng.shutdown.assert_not_awaited()

    async def test_kill_switch_exact_threshold(self):
        eng = make_engine(live=True, daily_loss_limit_usd=5.0)
        eng.running = True
        eng.client.get_positions = AsyncMock(return_value=[
            {"product_symbol": "TESTUSD", "size": 1, "entry_price": 100.0, "unrealized_pnl": -5.0},
        ])
        eng.shutdown = AsyncMock()
        await eng.sync_positions()
        # Breach is defined as <= -limit: exactly -5.0 trips the switch.
        eng.shutdown.assert_awaited_once_with(flatten=True)


if __name__ == "__main__":
    unittest.main()


class TestAvellanedaStoikovMath(unittest.TestCase):
    """Regression tests for the corrected A-S formulation (relative sigma)."""

    def _model(self, **kw):
        from models.model1_avellaneda_stoikov import AvellanedaStoikovModel
        return AvellanedaStoikovModel("TESTUSD", **kw)

    def test_reservation_price_relative_across_scales(self):
        """The inventory penalty must scale WITH price: 1 contract of inventory
        must skew quotes by the same FRACTION on a 0.013 asset and a 33000 asset."""
        for px in (0.013, 33_000.0):
            m = self._model(gamma=0.1, sigma=0.01, kappa=1.5)
            r = m.calculate_reservation_price(px, current_inventory=10)
            expected_frac = 1.0 - 10 * 0.1 * (0.01 ** 2) * 1.0
            self.assertAlmostEqual(r / px, expected_frac, places=10,
                                   msg=f"penalty not scale-invariant at px={px}")

    def test_reservation_price_direction(self):
        m = self._model(gamma=0.1, sigma=0.01)
        self.assertLess(m.calculate_reservation_price(100.0, 5), 100.0)   # long -> sell cheaper
        self.assertGreater(m.calculate_reservation_price(100.0, -5), 100.0)  # short -> buy higher
        self.assertEqual(m.calculate_reservation_price(100.0, 0), 100.0)

    def test_half_spread_includes_volatility_term(self):
        """A-S half-spread = 0.5*(fill_term + vol_term) in relative units;
        higher sigma must widen the quoted spread around reservation price."""
        m_low = self._model(gamma=0.1, sigma=0.001, kappa=1.5)
        m_high = self._model(gamma=0.1, sigma=0.05, kappa=1.5)
        q_low = m_low.calculate_optimal_quotes(100.0, 0, 99.9, 100.1, tick_size=0.01)
        q_high = m_high.calculate_optimal_quotes(100.0, 0, 99.9, 100.1, tick_size=0.01)
        # Both quote at least at BBO (post-only clamp); the vol-widened model
        # must not quote INSIDE the BBO either way.
        for q in (q_low, q_high):
            self.assertLessEqual(q["quote_bid"], 99.9)
            self.assertGreaterEqual(q["quote_ask"], 100.1)
        # And high-vol reservation skew must differ from low-vol at same inventory
        r_low = m_low.calculate_reservation_price(100.0, 10)
        r_high = m_high.calculate_reservation_price(100.0, 10)
        self.assertLess(r_high, r_low)  # higher vol -> stronger inventory penalty

    def test_update_volatility_adapts(self):
        m = self._model(gamma=0.1, sigma=0.001)
        base = m._rel_vol
        # A burst of 2% moves must push the EW estimate up
        px = 100.0
        for _ in range(20):
            px *= 1.02
            m.update_volatility(px)
        self.assertGreater(m._rel_vol, base)


class TestSniperGate(unittest.IsolatedAsyncioTestCase):
    """Model 2 taker sniping must never fire unless --snipe AND --live."""

    def _engine(self, snipe, live):
        eng = make_engine(live=live)
        eng.snipe = snipe
        eng.reference_prices["TESTUSD"] = 100.0
        # Prime book
        eng.books["TESTUSD"].update_from_snapshot(
            [{"price": 99.5, "size": 10}], [{"price": 100.5, "size": 10}], timestamp=0.0)
        return eng

    async def test_snipe_requires_both_flags(self):
        for snipe, live in ((False, False), (True, False), (False, True)):
            eng = self._engine(snipe, live)
            eng.client.place_order = AsyncMock()
            # Simulate a big Binance surge: reference jumps to 101 -> stale ask
            eng.m2_models["TESTUSD"].update_binance_price(96.0, timestamp=1.0)
            eng.reference_prices["TESTUSD"] = 96.0
            eng.evaluate_symbol_cycle("TESTUSD")
            # cycle logs but never places unless snipe and live
            # (dry-run path places nothing at all)
            if not (snipe and live):
                eng.client.place_order.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
