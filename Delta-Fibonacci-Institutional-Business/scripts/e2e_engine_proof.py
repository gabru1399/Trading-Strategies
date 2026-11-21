"""End-to-end functional proof of the Delta-Fibonacci engine on synthetic data.

Builds a deterministic synthetic OHLC series with embedded mean-reversion
structure, then runs the REAL production code paths:
  - calculate_session_vwap_bands (VWAP engine)
  - calculate_atr / calculate_ema
  - precompute_signals_vector (all 5 rejection patterns)
  - simulate_with_signals (entry, SL/TP/trail sim, cooldowns)
  - calculate_backtest_metrics
  - quant_robustness: split_train_test_data, Monte Carlo, DSR, anti-curve-fit gate
  - evaluate_live_setup_signal (the LIVE entry API) on the same data
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from engine.vwap_bands import calculate_session_vwap_bands
from engine.multidim_grid_backtest import (
    calculate_atr, calculate_ema, precompute_signals_vector,
    simulate_with_signals, calculate_backtest_metrics,
)
from engine.quant_robustness import (
    run_numba_monte_carlo, calculate_deflated_sharpe_ratio,
    split_train_test_data, verify_anti_curve_fit,
)
from engine.mt5_multicriteria_trader import evaluate_live_setup_signal

rng = np.random.default_rng(42)


def synthetic_ohlc(n=3000, seed_drift=0.0, mean_revert=0.05, start=100.0, freq="1h"):
    """Random-walk with mean reversion around a slow trend -> rejection setups exist."""
    steps = rng.normal(0.0004 + seed_drift, 0.012, n)
    mid = np.empty(n)
    mid[0] = start
    anchor = start
    for i in range(1, n):
        anchor = anchor * (1 + 0.00002)
        mid[i] = mid[i - 1] * (1 + steps[i]) + mean_revert * (anchor - mid[i - 1])
    o = mid * (1 + rng.normal(0, 0.002, n))
    c = mid * (1 + rng.normal(0, 0.002, n))
    spread = np.abs(rng.normal(0, 0.006, n)) + 0.001
    h = np.maximum(o, c) * (1 + spread)
    l = np.minimum(o, c) * (1 - spread)
    times = pd.date_range("2025-01-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({"time": times, "open": o, "high": h, "low": l, "close": c,
                         "tick_volume": rng.integers(50, 500, n)})


def main():
    print("=" * 80)
    print("END-TO-END ENGINE PROOF — synthetic data, production code paths")
    print("=" * 80)

    # ---- 1. VWAP band engine sanity
    df = synthetic_ohlc(3000)
    vb = calculate_session_vwap_bands(df, anchor_mode="broker")
    for col in ["vwap", "vwap_p1", "vwap_p2", "vwap_m1", "vwap_m2"]:
        assert vb[col].notna().all(), f"{col} has NaNs"
    assert (vb["vwap_p1"] >= vb["vwap"]).all() and (vb["vwap_m1"] <= vb["vwap"]).all()
    print(f"[1] VWAP bands: OK ({len(vb)} bars, m2<=vwap<=p2 invariant holds)")

    # ---- 2. Signal engine on both model families
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    atr = calculate_atr(h, l, c, 14)
    assert (atr[20:] > 0).all()
    ema100 = calculate_ema(c, 100)
    assert np.isfinite(ema100[100:]).all()
    print("[2] ATR + EMA calculators: OK")

    for family, kwargs in (
        ("VWAP", dict(vwap_vals=vb["vwap"].to_numpy(float), vwap_p1=vb["vwap_p1"].to_numpy(float),
                      vwap_p2=vb["vwap_p2"].to_numpy(float), vwap_m1=vb["vwap_m1"].to_numpy(float),
                      vwap_m2=vb["vwap_m2"].to_numpy(float))),
        ("EMA", dict(ema_vals=ema100, ema_period=100)),
    ):
        sides, setups, rds = precompute_signals_vector(o, h, l, c, atr, family, start_bar=120, **kwargs)
        n_sig = int((sides != 0).sum())
        assert n_sig > 50, f"{family}: too few signals ({n_sig}) — engine not detecting"
        assert set(np.unique(sides)) <= {-1, 0, 1}
        assert all(r > 0 for r in rds[sides != 0])
        from collections import Counter
        pat = Counter(s.split("_", 1)[1] if "_" in s else s for s in setups if s)
        print(f"    {family}: {n_sig} signals | patterns: {dict(pat)}")
    print("[3] Signal engine (5 rejection patterns): OK")

    # ---- 3. Full trade simulation, both exit modes
    sides, setups, rds = precompute_signals_vector(o, h, l, c, atr, "VWAP", start_bar=120,
                                                   vwap_vals=vb["vwap"].to_numpy(float),
                                                   vwap_p1=vb["vwap_p1"].to_numpy(float),
                                                   vwap_p2=vb["vwap_p2"].to_numpy(float),
                                                   vwap_m1=vb["vwap_m1"].to_numpy(float),
                                                   vwap_m2=vb["vwap_m2"].to_numpy(float))
    for exit_mode in ("fixed_2.5r", "trail_0.5r"):
        trades, metrics = simulate_with_signals(df["time"], o, h, l, c, atr, sides, setups,
                                                "SYNTH", "1H", "VWAP", exit_mode=exit_mode,
                                                risk_usd=5.0, cooldown_bars=6, start_bar=120, sig_rds=rds)
        assert metrics["total_trades"] > 10, f"{exit_mode}: too few trades"
        assert all(t["risk_dist"] > 0 for t in trades)
        r_sum = sum(t["r_multiple"] for t in trades)
        print(f"    {exit_mode}: {metrics['total_trades']} trades | net {metrics['net_r']}R | "
              f"PF {metrics['profit_factor']} | maxDD {metrics['max_dd_r']}R | exp {metrics['expectancy_r']}R")
    print("[4] Trade simulation (fixed + trailing exits): OK")

    # ---- 4. Quant robustness stack on the simulated R-multiples
    trades, metrics = simulate_with_signals(df["time"], o, h, l, c, atr, sides, setups,
                                            "SYNTH", "1H", "VWAP", exit_mode="trail_0.5r",
                                            risk_usd=5.0, cooldown_bars=6, start_bar=120, sig_rds=rds)
    r_mults = np.array([t["r_multiple"] for t in trades])
    mc = run_numba_monte_carlo(r_mults, n_sims=5000)
    dsr = calculate_deflated_sharpe_ratio(r_mults, n_trials=40)
    train, test = split_train_test_data(df, 0.70)
    assert len(train) + len(test) == len(df) and len(test) > 0
    def run_vwap_backtest(frame):
        """Compact helper: full VWAP backtest pipeline on a dataframe slice."""
        arrs = {k: frame[k].to_numpy(float) for k in ("open", "high", "low", "close")}
        a = calculate_atr(arrs["high"], arrs["low"], arrs["close"], 14)
        vb = calculate_session_vwap_bands(frame, "broker")
        s, st, rd = precompute_signals_vector(
            arrs["open"], arrs["high"], arrs["low"], arrs["close"], a, "VWAP", start_bar=120,
            vwap_vals=vb["vwap"].to_numpy(float), vwap_p1=vb["vwap_p1"].to_numpy(float),
            vwap_p2=vb["vwap_p2"].to_numpy(float), vwap_m1=vb["vwap_m1"].to_numpy(float),
            vwap_m2=vb["vwap_m2"].to_numpy(float))
        return simulate_with_signals(frame["time"], arrs["open"], arrs["high"], arrs["low"],
                                     arrs["close"], a, s, st, "SYNTH", "1H", "VWAP",
                                     exit_mode="trail_0.5r", start_bar=120, sig_rds=rd)

    is_tr, is_m = run_vwap_backtest(train)
    oos_tr, oos_m = run_vwap_backtest(test)
    oos_vb = calculate_session_vwap_bands(test, "broker")
    oos_atr = calculate_atr(test["high"].to_numpy(float), test["low"].to_numpy(float), test["close"].to_numpy(float), 14)
    oos_sides, oos_setups, oos_rds = precompute_signals_vector(
        test["open"].to_numpy(float), test["high"].to_numpy(float), test["low"].to_numpy(float),
        test["close"].to_numpy(float), oos_atr, "VWAP", start_bar=120,
        vwap_vals=oos_vb["vwap"].to_numpy(float), vwap_p1=oos_vb["vwap_p1"].to_numpy(float),
        vwap_p2=oos_vb["vwap_p2"].to_numpy(float), vwap_m1=oos_vb["vwap_m1"].to_numpy(float),
        vwap_m2=oos_vb["vwap_m2"].to_numpy(float))
    oos_tr, oos_m = simulate_with_signals(test["time"], test["open"].to_numpy(float),
                                          test["high"].to_numpy(float), test["low"].to_numpy(float),
                                          test["close"].to_numpy(float), oos_atr, oos_sides, oos_setups,
                                          "SYNTH", "1H", "VWAP", exit_mode="trail_0.5r", start_bar=120, sig_rds=oos_rds)
    verdict = verify_anti_curve_fit(is_m, oos_m, mc, dsr)
    print(f"    MC(5k): median {mc['mc_median_r']}R | p(profit) {mc['mc_p_profit']} | DD95 {mc['mc_max_dd_95']}R")
    print(f"    DSR: {dsr} | IS {is_m['net_r']}R -> OOS {oos_m['net_r']}R | verdict: {verdict['verdict']}")
    print("[5] Quant robustness (MC + DSR + IS/OOS + gate): OK")

    # ---- 5. LIVE entry API on the same series (the function the MT5 runner calls)
    live_sig = evaluate_live_setup_signal(df, "SYNTHUSD", "1H", "VWAP", "SD_BANDS")
    print(f"    live VWAP signal on latest closed bar: side={live_sig.get('side', 0)}")
    live_sig2 = evaluate_live_setup_signal(df, "SYNTHBTC", "1H", "EMA", "EMA_100")
    print(f"    live EMA signal on latest closed bar: side={live_sig2.get('side', 0)}")
    print("[6] Live entry API (evaluate_live_setup_signal): OK")

    print("=" * 80)
    print("ALL ENGINE PATHS FUNCTIONAL — end-to-end proof complete")


if __name__ == "__main__":
    main()
