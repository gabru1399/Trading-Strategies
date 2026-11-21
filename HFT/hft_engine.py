"""C:\\Users\\SIGMA\\Documents\\Trading-Strategies\\HFT\\hft_engine.py
Unified High-Frequency Trading (HFT) Engine for Delta Exchange India.
Orchestrates:
  - Model 1: Avellaneda-Stoikov Dynamic Market Maker (Spread & Maker Rebate Capture)
  - Model 2: Binance -> Delta Lead-Lag Latency Sniping (Cross-Venue Momentum Mispricing)
  - Model 3: Order Flow Imbalance (OFI) Drift Scalper (Queue Depletion Anticipation)

Institutional Safety & Risk Architecture:
  - Micro-Risk Boundary: Max Notional per Symbol <= $5.00 USD (Ceiling $10.00 USD)
  - Strict Post-Only Maker Execution (0.00% maker fee, zero taker fee slippage)
  - Dynamic Cancel-Replace Queue Management
  - Daily Loss Circuit Breaker: Hard kill switch at -$5.00 USD
"""

import argparse
import asyncio
import json
import logging
import math
import os
import signal
import sys
import time
from typing import Dict, Any, List, Optional
from pathlib import Path

# Setup paths
HFT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(HFT_ROOT))

from core.delta_client import DeltaClient
from core.orderbook import L2OrderBook
from core.binance_feed import BinanceFuturesFeed
from models.model1_avellaneda_stoikov import AvellanedaStoikovModel
from models.model2_binance_lead_lag import BinanceDeltaLeadLagModel
from models.model3_ofi_microstructure import OrderFlowImbalanceModel

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("DeltaHFT")


class HFTEngine:
    def __init__(
        self,
        symbols: List[str],
        live: bool = False,
        order_size: int = 1,
        max_notional_per_symbol: float = 5.0,
        daily_loss_limit_usd: float = 5.0,
        quote_refresh_sec: float = 15.0,
        snipe: bool = False,
    ):
        self.symbols = symbols
        self.live = live
        self.snipe = snipe  # Model 2 taker lane: OFF unless explicitly enabled
        self.order_size = order_size
        self.max_notional_per_symbol = max_notional_per_symbol
        self.daily_loss_limit_usd = daily_loss_limit_usd
        self.quote_refresh_sec = quote_refresh_sec

        self.client = DeltaClient()
        self.books: Dict[str, L2OrderBook] = {s: L2OrderBook(s) for s in symbols}
        self.product_specs: Dict[str, Dict[str, Any]] = {}

        # Instantiate Models per Symbol
        # kappa calibrated for RELATIVE-unit A-S outputs: (1/gamma)*ln(1+gamma/kappa)
        # must land in single-digit bps, i.e. kappa ~ O(1e3). See model docstring.
        self.m1_models: Dict[str, AvellanedaStoikovModel] = {
            s: AvellanedaStoikovModel(s, gamma=0.1, sigma=0.002, kappa=2000.0, max_inventory=2, min_spread_bps=4.0)
            for s in symbols
        }
        self.m2_models: Dict[str, BinanceDeltaLeadLagModel] = {
            s: BinanceDeltaLeadLagModel(s, lookback_seconds=3.0, shock_threshold_bps=10.0, taker_fee_bps=5.0, min_net_edge_bps=5.0)
            for s in symbols
        }
        self.m3_models: Dict[str, OrderFlowImbalanceModel] = {
            s: OrderFlowImbalanceModel(s, ofi_window=10, zscore_threshold=2.2)
            for s in symbols
        }

        # Inventory & State Tracking
        self.inventories: Dict[str, int] = {s: 0 for s in symbols}
        self.entry_prices: Dict[str, float] = {s: 0.0 for s in symbols}
        # Binance reference mids for Model 2 lead-lag (symbol -> mid), fed by BinanceFuturesFeed
        self.reference_prices: Dict[str, Optional[float]] = {s: None for s in symbols}
        self.binance_feed: Optional[BinanceFuturesFeed] = None
        # Active orders structure: {symbol: {"buy": {"id": int, "price": float, "ts": float}, "sell": ...}}
        self.active_orders: Dict[str, Dict[str, Optional[Dict[str, Any]]]] = {
            s: {"buy": None, "sell": None} for s in symbols
        }
        self.stats = {
            "quotes_placed": 0,
            "quotes_cancelled": 0,
            "fills_detected": 0,
            "round_turns_completed": 0,
        }
        self.running = False
        self.last_pos_check: float = 0.0
        self.last_dashboard_print: float = 0.0

    async def initialize(self):
        logger.info("=" * 70)
        logger.info("INITIALIZING DELTA EXCHANGE HFT EXECUTION ENGINE")
        logger.info("=" * 70)
        # RISK GATE: refuse live execution without credentials (anonymous clients
        # can still dry-run on public market data). See SECURITY.md.
        if self.live and (not self.client.api_key or not self.client.api_secret):
            raise RuntimeError(
                "LIVE mode refused: DELTA_API_KEY / DELTA_API_SECRET not set. "
                "Export credentials or run in dry-run (default)."
            )
        await self.client.sync_server_time()
        mode_str = "🔥 LIVE ORDER EXECUTION 🔥" if self.live else "🛡️ DRY RUN (PAPER SIMULATION)"
        logger.info(f"Execution Mode: {mode_str}")
        logger.info(f"Symbols: {self.symbols} | Order Size: {self.order_size} contract(s)")
        logger.info(f"Max Notional Risk: ${self.max_notional_per_symbol:.2f} USD | Kill Switch: -${self.daily_loss_limit_usd:.2f} USD")

        # Fetch product specs
        products = await self.client.get_products()
        for p in products:
            sym = p.get("symbol")
            if sym in self.symbols:
                tick_str = str(p.get("tick_size", "0.0001"))
                contract_val = float(p.get("contract_value", 1.0))
                self.product_specs[sym] = {
                    "id": p.get("id"),
                    "symbol": sym,
                    "tick_size": float(tick_str),
                    "tick_size_str": tick_str,
                    "contract_value": contract_val,
                }
                logger.info(f"  [SPEC] {sym} | ID: {p.get('id')} | Tick: {tick_str} | ContractVal: {contract_val}")

        # Start the Binance reference feed for Model 2 lead-lag evaluation.
        # on_tick routes each Binance mid into reference_prices keyed by the
        # Delta symbol (both mapped and raw base). Feed failures degrade to
        # Model-2-silent: the engine keeps market making on Delta book data.
        def _on_ref_tick(base: str, price: float, ts: float):
            for s in self.symbols:
                base_delta = s[:-3] if s.endswith("USD") else s  # BTCUSD -> BTC
                if base_delta == base:
                    self.reference_prices[s] = price
        try:
            self.binance_feed = BinanceFuturesFeed(
                [s[:-3] if s.endswith("USD") else s for s in self.symbols]
            )
            self.binance_feed.on_tick(_on_ref_tick)
            asyncio.create_task(self.binance_feed.start())
            logger.info(f"Binance reference feed subscribing: {[s[:-3] + 'USDT' for s in self.symbols]}")
        except Exception as e:
            logger.warning(f"Binance reference feed unavailable ({e}); Model 2 lead-lag stays silent.")

        # Ingest existing positions
        await self.sync_positions()
        logger.info(f"Starting inventories: {self.inventories}")
        logger.info("HFT Engine Initialized Successfully.\n")

    async def sync_positions(self):
        # Dry-run / anonymous mode: authenticated endpoints would 401 (or worse,
        # raise inside HMAC signing when the secret is None). Position sync is
        # only meaningful when credentials exist; the kill switch likewise
        # only guards real inventory.
        if not (self.client.api_key and self.client.api_secret):
            return
        try:
            positions = await self.client.get_positions()
            for p in positions:
                sym = p.get("product_symbol")
                if sym in self.inventories:
                    new_size = int(float(p.get("size", 0)))
                    old_size = self.inventories[sym]
                    entry_px = float(p.get("entry_price") or 0.0)
                    self.entry_prices[sym] = entry_px
                    if new_size != old_size:
                        self.stats["fills_detected"] += 1
                        logger.info(f"🎯 [FILL DETECTED] {sym} Inventory changed: {old_size} -> {new_size} contracts | EntryPx: {entry_px} | UPnL: {p.get('unrealized_pnl')}")
                        # If inventory crossed zero or returned to zero, a round-turn closed
                        if (old_size > 0 and new_size == 0) or (old_size < 0 and new_size == 0):
                            self.stats["round_turns_completed"] += 1
                            logger.info(f"💰 [SPREAD CAPTURED] Round-turn completed on {sym}! Profit locked in.")
                    self.inventories[sym] = new_size

            # RISK GOVERNOR: enforce the advertised daily-loss kill switch.
            # Every position sync re-checks aggregate unrealized PnL; breaching
            # the limit halts quoting, cancels all resting orders and flattens
            # inventory so the engine can never drift past its risk mandate.
            total_upnl = sum(
                float(p.get("unrealized_pnl") or 0.0)
                for p in positions
                if p.get("product_symbol") in self.inventories
            )
            if total_upnl <= -abs(self.daily_loss_limit_usd) and self.running:
                logger.critical(
                    f"🛑 [KILL SWITCH] Aggregate unrealized PnL ${total_upnl:.2f} breached "
                    f"-${abs(self.daily_loss_limit_usd):.2f} limit. Cancelling quotes and flattening."
                )
                await self.shutdown(flatten=True)
        except Exception as e:
            logger.warning(f"Position sync error: {e}")

    async def sync_book(self, symbol: str):
        try:
            data = await self.client.get_l2_orderbook(symbol, depth=10)
            buys = data.get("buy", [])
            sells = data.get("sell", [])
            self.books[symbol].update_from_snapshot(buys, sells, timestamp=time.time())
        except Exception as e:
            logger.debug(f"Book sync error for {symbol}: {e}")

    async def cancel_active_quote(self, symbol: str, side: str):
        active = self.active_orders[symbol].get(side)
        if not active:
            return
        oid = active["id"]
        pid = self.product_specs.get(symbol, {}).get("id")
        try:
            await self.client.cancel_order(oid, product_id=pid, symbol=symbol)
            self.stats["quotes_cancelled"] += 1
            logger.info(f"🗑️ [CANCEL MAKER] {symbol} {side.upper()} order #{oid} (Price: {active['price']}) cancelled")
        except Exception as e:
            logger.debug(f"Cancel order error {symbol} #{oid}: {e}")
        finally:
            self.active_orders[symbol][side] = None

    async def evaluate_symbol_cycle(self, symbol: str):
        book = self.books[symbol]
        if not book.best_bid or not book.best_ask:
            return

        spec = self.product_specs.get(symbol, {})
        tick_size = spec.get("tick_size", 0.0001)
        contract_val = spec.get("contract_value", 1.0)
        mid = book.mid_price
        spread_bps = book.spread_bps
        inv = self.inventories.get(symbol, 0)
        now = time.time()

        # Check notional exposure cap
        contract_notional = mid * contract_val * self.order_size
        if contract_notional > self.max_notional_per_symbol:
            logger.warning(f"Skipping {symbol}: 1 contract notional (${contract_notional:.2f}) exceeds max notional (${self.max_notional_per_symbol:.2f})")
            return

        # ----------------- Check Model 2: Binance Lead-Lag (when reference feed is live) -----------------
        # The Binance reference mid is pushed by the feed callback; evaluate the
        # stale-quote sniper before quoting so a signal can suppress market
        # making on the affected side instead of quoting into dislocated prices.
        ref = self.reference_prices.get(symbol)
        if ref is not None:
            self.m2_models[symbol].update_binance_price(ref, timestamp=now)
            m2_sig = self.m2_models[symbol].evaluate_lead_lag_opportunity(
                delta_best_bid=book.best_bid,
                delta_best_ask=book.best_ask,
                delta_timestamp=now,
            )
            if m2_sig:
                logger.info(
                    f"🎯 [LEAD-LAG {m2_sig['signal']}] {symbol}: velocity {m2_sig['binance_velocity_bps']:+.1f} bps | "
                    f"net edge {m2_sig['net_edge_bps']:.1f} bps | {m2_sig['reason']}"
                )
                self.stats["lead_lag_signals"] = self.stats.get("lead_lag_signals", 0) + 1
                # Sniper lane: executes taker IOCs ONLY when the operator has
                # explicitly opted in via --snipe. Default remains log-only.
                if self.snipe and self.live:
                    try:
                        res = await self.client.place_order(
                            symbol=symbol,
                            size=self.order_size,
                            side=m2_sig["side"],
                            limit_price=m2_sig["action_price"],
                            post_only=False,
                            time_in_force="ioc",
                        )
                        self.stats["snipes_fired"] = self.stats.get("snipes_fired", 0) + 1
                        logger.info(f"🏹 [SNIPE EXECUTED] {symbol} {m2_sig['side'].upper()} @ {m2_sig['action_price']} -> order {res.get('id')}")
                    except Exception as e:
                        logger.error(f"Snipe order failed on {symbol}: {e}")

        # ----------------- Check Model 3: OFI Microstructure -----------------
        ofi_sig = self.m3_models[symbol].update_book(
            best_bid=book.best_bid,
            best_bid_size=book.best_bid_size,
            best_ask=book.best_ask,
            best_ask_size=book.best_ask_size,
        )
        if ofi_sig:
            logger.info(f"⚡ [OFI DRIFT TRIGGER] {symbol}: Z={ofi_sig['ofi_zscore']:.2f} | Imbalance: {ofi_sig['imbalance_ratio']:.2f}")

        # ----------------- Check Model 1: Avellaneda-Stoikov Market Maker -----------------
        # Feed live mid into the EW relative-vol estimate first so reservation
        # price and half-spread adapt to each asset's own noise level.
        self.m1_models[symbol].update_volatility(mid)
        m1_quotes = self.m1_models[symbol].calculate_optimal_quotes(
            mid_price=mid,
            current_inventory=inv,
            best_bid=book.best_bid,
            best_ask=book.best_ask,
            tick_size=tick_size,
            base_size=self.order_size,
        )

        if not m1_quotes:
            return

        q_bid = m1_quotes.get("quote_bid")
        q_ask = m1_quotes.get("quote_ask")
        res_px = m1_quotes.get("reservation_price")

        # Inventory Unwind Profit Protection:
        # If long inventory (inv > 0), ensure ask quote is at least entry_price + tick_size
        if inv > 0 and self.entry_prices.get(symbol, 0.0) > 0:
            min_exit_ask = round(round((self.entry_prices[symbol] + tick_size) / tick_size) * tick_size, 8)
            if q_ask is not None:
                q_ask = max(q_ask, min_exit_ask)
        elif inv < 0 and self.entry_prices.get(symbol, 0.0) > 0:
            max_exit_bid = round(round((self.entry_prices[symbol] - tick_size) / tick_size) * tick_size, 8)
            if q_bid is not None:
                q_bid = min(q_bid, max_exit_bid)

        # ----------------- Live Order Placement & Lifecycle -----------------
        if self.live:
            # 1. Handle BUY Maker Quote
            active_buy = self.active_orders[symbol]["buy"]
            if q_bid is not None and m1_quotes.get("bid_size", 0) > 0:
                needs_replace = False
                if active_buy is None:
                    needs_replace = True
                else:
                    # If price moved away by >= 1 tick or quote is older than refresh window
                    px_diff = abs(active_buy["price"] - q_bid)
                    if px_diff >= tick_size or (now - active_buy["ts"]) > self.quote_refresh_sec:
                        await self.cancel_active_quote(symbol, "buy")
                        needs_replace = True

                if needs_replace:
                    try:
                        res = await self.client.place_order(
                            symbol=symbol,
                            size=self.order_size,
                            side="buy",
                            limit_price=q_bid,
                            post_only=True,
                            time_in_force="gtc",
                        )
                        oid = res.get("id")
                        if oid:
                            self.active_orders[symbol]["buy"] = {"id": oid, "price": q_bid, "ts": now}
                            self.stats["quotes_placed"] += 1
                            logger.info(f"✅ [POST-ONLY BID] {symbol} | Price: {q_bid} (x{self.order_size}) | Order #{oid} | Spread: {spread_bps:.1f} bps")
                    except Exception as e:
                        logger.error(f"Failed to place Post-Only BID on {symbol} @ {q_bid}: {e}")
            elif active_buy is not None:
                # Inventory saturated on long side; cancel resting bid
                await self.cancel_active_quote(symbol, "buy")

            # 2. Handle SELL Maker Quote
            active_sell = self.active_orders[symbol]["sell"]
            if q_ask is not None and m1_quotes.get("ask_size", 0) > 0:
                needs_replace = False
                if active_sell is None:
                    needs_replace = True
                else:
                    px_diff = abs(active_sell["price"] - q_ask)
                    if px_diff >= tick_size or (now - active_sell["ts"]) > self.quote_refresh_sec:
                        await self.cancel_active_quote(symbol, "sell")
                        needs_replace = True

                if needs_replace:
                    try:
                        res = await self.client.place_order(
                            symbol=symbol,
                            size=self.order_size,
                            side="sell",
                            limit_price=q_ask,
                            post_only=True,
                            time_in_force="gtc",
                        )
                        oid = res.get("id")
                        if oid:
                            self.active_orders[symbol]["sell"] = {"id": oid, "price": q_ask, "ts": now}
                            self.stats["quotes_placed"] += 1
                            logger.info(f"✅ [POST-ONLY ASK] {symbol} | Price: {q_ask} (x{self.order_size}) | Order #{oid} | Spread: {spread_bps:.1f} bps")
                    except Exception as e:
                        logger.error(f"Failed to place Post-Only ASK on {symbol} @ {q_ask}: {e}")
            elif active_sell is not None:
                # Inventory saturated on short side; cancel resting ask
                await self.cancel_active_quote(symbol, "sell")
        else:
            # Paper mode log
            logger.info(f"📊 [PROPOSAL] {symbol} | Mid: {mid:.5f} | ResPx: {res_px:.5f} | Bid: {q_bid} | Ask: {q_ask} | Spread: {spread_bps:.1f} bps | Inv: {inv}")

    async def print_dashboard(self):
        logger.info("-" * 75)
        logger.info(f"📈 [HFT DASHBOARD] Quotes Placed: {self.stats['quotes_placed']} | Cancelled: {self.stats['quotes_cancelled']} | Fills: {self.stats['fills_detected']} | Round-Turns: {self.stats['round_turns_completed']}")
        for sym in self.symbols:
            inv = self.inventories.get(sym, 0)
            b = self.active_orders[sym]["buy"]
            a = self.active_orders[sym]["sell"]
            b_str = f"#{b['id']} @ {b['price']}" if b else "None"
            a_str = f"#{a['id']} @ {a['price']}" if a else "None"
            logger.info(f"   {sym:10s} | Inv: {inv:2d} | Resting Bid: {b_str:20s} | Resting Ask: {a_str:20s}")
        logger.info("-" * 75)

    async def run_loop(self, poll_interval_ms: int = 500):
        self.running = True
        logger.info(f"Starting High-Frequency surveillance loop ({poll_interval_ms}ms cycle)...")

        while self.running:
            t0 = time.time()
            now = time.time()

            # 1. Periodic Position Sync (every 2.5s)
            if now - self.last_pos_check >= 2.5:
                await self.sync_positions()
                self.last_pos_check = now

            # 2. Cycle each symbol
            for sym in self.symbols:
                await self.sync_book(sym)
                await self.evaluate_symbol_cycle(sym)

            # 3. Print Dashboard (every 6.0s)
            if now - self.last_dashboard_print >= 6.0:
                await self.print_dashboard()
                self.last_dashboard_print = now

            elapsed_ms = (time.time() - t0) * 1000.0
            sleep_time = max(0.05, (poll_interval_ms - elapsed_ms) / 1000.0)
            await asyncio.sleep(sleep_time)

    async def shutdown(self, flatten: bool = False):
        logger.info("\n" + "=" * 70)
        logger.info("GRACEFULLY SHUTTING DOWN HFT EXECUTION ENGINE")
        logger.info("=" * 70)
        self.running = False
        if self.binance_feed is not None:
            self.binance_feed.stop()
        if self.live:
            logger.info("Cancelling all resting maker orders placed by engine...")
            for s in self.symbols:
                await self.cancel_active_quote(s, "buy")
                await self.cancel_active_quote(s, "sell")
            if flatten:
                # Kill-switch path: flatten any residual inventory at market so
                # the engine can never keep drifting past the loss limit.
                logger.warning("🛑 [KILL SWITCH] Flattening residual inventory at market...")
                for s in self.symbols:
                    if self.inventories.get(s, 0) != 0:
                        side = "sell" if self.inventories[s] > 0 else "buy"
                        try:
                            await self.client.place_order(
                                symbol=s,
                                size=abs(self.inventories[s]),
                                side=side,
                                limit_price=self.books[s].best_ask if side == "buy" else self.books[s].best_bid,
                                post_only=False,  # taker: immediate flatten
                                time_in_force="ioc",
                            )
                            logger.warning(f"   Flattened {s}: {side} {abs(self.inventories[s])} contracts")
                        except Exception as e:
                            logger.error(f"   Flatten FAILED for {s}: {e} — MANUAL INTERVENTION REQUIRED")
        await self.client.close()
        logger.info(f"Final Statistics: {self.stats}")
        logger.info("HFT Engine Shutdown Complete.")


def parse_args():
    parser = argparse.ArgumentParser(description="Delta Exchange India High-Frequency Trading Engine")
    parser.add_argument("--symbols", nargs="+", default=["RAREUSD", "PIPPINUSD"], help="Target perpetual symbols")
    parser.add_argument("--live", action="store_true", help="Execute real live orders (default: Dry Run)")
    parser.add_argument("--snipe", action="store_true", help="Enable Model 2 lead-lag taker sniping (requires --live)")
    parser.add_argument("--size", type=int, default=1, help="Contract order size per quote")
    parser.add_argument("--max-notional", type=float, default=5.0, help="Max notional risk per symbol in USD")
    parser.add_argument("--interval-ms", type=int, default=500, help="Polling cycle interval in milliseconds")
    parser.add_argument("--duration-sec", type=int, default=0, help="Run duration in seconds (0 = continuous)")
    return parser.parse_args()


async def main():
    args = parse_args()
    if args.snipe and not args.live:
        parser.error("--snipe requires --live (sniping is a taker strategy and cannot run in dry-run)")

    engine = HFTEngine(
        symbols=args.symbols,
        live=args.live,
        order_size=args.size,
        max_notional_per_symbol=args.max_notional,
        snipe=args.snipe,
    )
    await engine.initialize()

    if args.duration_sec > 0:
        async def stop_after():
            await asyncio.sleep(args.duration_sec)
            await engine.shutdown()

        await asyncio.gather(
            engine.run_loop(poll_interval_ms=args.interval_ms),
            stop_after(),
        )
    else:
        try:
            await engine.run_loop(poll_interval_ms=args.interval_ms)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await engine.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
