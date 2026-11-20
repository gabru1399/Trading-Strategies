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
