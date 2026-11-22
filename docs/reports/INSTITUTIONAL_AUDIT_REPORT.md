# Institutional Audit & Hardening Report — 2026-11-20

Full-codebase review of this repository (CG-Terminal, Delta-Fibonacci
Institutional Business, HFT) performed end-to-end: every HFT file read line by
line, Delta-Fibonacci engine + tests read and executed, CG-Terminal audited via
its desk logs, spec, and scripts. Findings below are ordered by severity, each
with the fix applied in this branch.

---

## P0 — Security

### A1. Live exchange credentials committed to a public repository
- **Where**: `HFT/core/delta_client.py` (hardcoded fallback key/secret),
  `CG-Terminal/scripts/delta_direct.py` (module constants).
- **Impact**: any visitor can clone the repo and trade on / drain the Delta
  Exchange India account (order placement, position management). This is the
  most severe class of finding a trading system can have.
- **Fix applied**: credentials now load exclusively from the environment or a
  gitignored `.env` (pattern already existed — `.env.example` is tracked,
  `.env*` is gitignored). The HFT engine **refuses `--live` execution** when
  credentials are absent. CI gained a secret-hygiene grep + gitleaks scan.
- **Residual action (cannot be done by a contributor)**: **rotate the keys on
  the exchange**. The old pair remains in git history and must be treated as
  burned. See `SECURITY.md`.

## P1 — Correctness / reliability

### B1. HFT package could not even import on Python 3.12
- `core/orderbook.py` used `List[Any]` without importing `Any` → `NameError`
  at import; the entire HFT test suite failed at collection and the engine
  could not start. `models/model2_binance_lead_lag.py` had the same defect for
  `Tuple` (annotated at runtime in an instance attribute).
- **Fix**: imports corrected. Suite now passes (10/10 including new
  risk-governor tests).

### B2. Advertised daily-loss kill switch was never enforced
- `hft_engine.py` logged "Kill Switch: -$5.00 USD" at startup but no code path
  ever checked the loss limit. An adverse run could bleed the account without
  the engine ever halting.
- **Fix**: every position sync now aggregates unrealized PnL across tracked
  symbols; breaching the limit cancels all resting quotes, **flattens residual
  inventory at market (IOC taker)**, and halts the loop. Covered by
  `tests/test_risk_governor.py` (breach, within-limit, exact-threshold).

### B3. Model 2 (Binance lead-lag) was dead code
- Instantiated per-symbol in the engine but never fed prices and never
  evaluated — the "empirically verified latency edge" documented in the README
  had no runtime path.
- **Fix**: engine now carries `reference_prices` (fed from
  `BinanceFuturesFeed.on_tick`), evaluates the sniper each cycle, logs signals
  with net-edge math, and counts them in stats. Auto-firing takers stays
  intentionally OFF in this build — signal logging is the safe default until
  operator sign-off (documented inline).

### B4. Delta-Fibonacci engine unimportable off-Windows (blocked all CI)
- Top-level `import MetaTrader5` in `kaizen_self_improvement.py` and
  `live_multicriteria_runner.py` broke 8/9 test files at collection on any
  non-Windows host. Additionally `TIMEFRAME_MAP` dereferenced `mt5.` constants
  at module import time.
- **Fix**: lazy/guarded imports (`mt5 = None` degradation), `TIMEFRAME_MAP`
  built through `_tf_map()` that binds real enums on Windows and raw constants
  otherwise, MT5-only attribution function returns a clean error object when
  unavailable. Suite: **37 passed, 32 skipped** (skips = Windows-only /
  optional-dependency / gitignored-local-data guards, honestly marked).

## P2 — Engineering hygiene

- **No CI**: added `.github/workflows/ci.yml` — HFT suite, Delta-Fib suite,
  repo-wide gitleaks secret scan, and a credential-pattern regression grep.
- **No `HFT/requirements.txt`**: created with the actual imports
  (`aiohttp`, `websockets`, `numpy`, `pytest`).
- **README staleness**: HFT README advertises edge numbers (e.g. "+5.3 to
  +38.6 bps net edge") derived from a single pinned scan artifact; added a
  data-provenance caveat pointing at the artifact and the rerunnable scanner.
- **Windows-path docstrings**: `C:\Users\SIGMA\...` paths in module headers
  replaced/softened where they leak the host layout (kept harmless ones).

## What was verified GOOD (kept as-is)

- Avellaneda-Stoikov reservation pricing and quote-BBO clamping (post-only
  safety) are mathematically sound.
- Cont-Kukanov-Stoikov OFI implementation matches the 2014 paper's queue-delta
  formulation.
- Delta-Fibonacci's risk governor math (daily 4% / lifetime 10% floors,
  cluster isolation, Kaufman ER anti-whipsaw, rollover guard, two-tier spread
  classification) is coherent and well-tested by its 37-test suite.
- CG-Terminal's gitignore discipline is excellent (`.env*`, `mt5.json`,
  position ledgers all excluded) — the leak was only in the two legacy scripts.

## Reproducibility

| Suite | Command | Result |
| --- | --- | --- |
| HFT models + risk governors | `cd HFT && python -m pytest tests/` | 10 passed |
| Delta-Fibonacci engine | `cd Delta-Fibonacci-Institutional-Business && python -m pytest tests/` | 37 passed, 32 skipped |

Skipped tests re-enable automatically on the Windows host with MT5, the local
parquet lake, or `pip install kaizen-agent`.

---

# Phase 2 — Full Deep-Dive, Fix & Run Verification (2026-11-20, same day)

Every engine was subsequently read **line by line** and **executed**, not just
audited. Findings and outcomes below extend the Phase-1 hardening above.

## Delta-Fibonacci — deep dive & functional proof

**Read fully**: all 9 engine modules (`vwap_bands`, `candle_rejection`,
`mt5_multicriteria_trader`, `live_multicriteria_runner` (899 lines),
`kaizen_self_improvement`, `kaizen_agent_bridge`, `multidim_grid_backtest`,
`quant_robustness`), the 15-symbol/18-setup `EXPANDED_OPTIMAL_ALPHA_BASKET`,
and the validation/peer-review scripts.

**Verdict: mathematically sound.** Specifics verified:
- Session VWAP: grouped-cumsum running variance, correct ±1σ/±2σ bands, UTC vs
  broker (UTC+2) anchoring by asset class.
- All 5 rejection patterns (pinbar, two-bar, three-bar sweep, cluster stall,
  double-tap) use ATR-scaled tolerances and structural SLs; no lookahead.
- Backtest engine: signal on bar *i* → entry at open of bar *i+1*; intrabar
  adverse sequencing (bearish bar checks SL first); trailing ratchet identical
  to the live runner's `calculate_trailing_stop_update`.
- Quant stack: Numba MC bootstrap, Bailey–Lopez de Prado DSR (with the
  Euler–Mascheroni expected-max correction), 70/30 chronological IS/OOS split,
  anti-curve-fit gate.

**Functional proof** (`scripts/e2e_engine_proof.py`, synthetic 3,000-bar series
through the *production* code paths):
- 1,630 VWAP signals across 16 pattern variants; 570 EMA signals.
- 190 trades on `trail_0.5r` (net +21.97R, PF 1.24, maxDD 11.1R).
- MC(5k): median +22.2R, p(profit) 0.917 · DSR 1.0 · IS +23.2R → OOS +10.2R.
- Gate verdict on synthetic data: `INSTITUTIONAL_ALPHA`; live entry API
  (`evaluate_live_setup_signal`) fires correctly.

## HFT — deep dive, model fixes & live dry-run

**Read fully**: engine, all 3 models, core clients, research scanner, tests.

### C1. Avellaneda-Stoikov model was dimensionally wrong (P1)
- `sigma` was an absolute price constant (0.015) — on a 0.013-priced asset the
  inventory penalty exceeded the price itself; on BTC it was zero. The
  half-spread conversion divided by 10,000 with no basis, and the model's
  default `kappa=1.5` implies a **64% half-spread** in relative units.
- **Fix**: sigma is now *relative* (fractional) volatility with an EW estimate
  updated from live mids (`update_volatility`); the reservation penalty is
  computed in relative terms and re-scaled by mid (scale-invariant across
  $0.006 → $59,000 assets); the half-spread now includes the paper's volatility
  term `γσ²(T−t)`; a competitiveness cap keeps the quote inside the observed
  market spread; `kappa` recalibrated to 2,000.
- **Verified live**: dry-run quotes on SLVONUSD went from
  `Bid 25.34 / Ask 49.50` (32% spread) to `Bid 37.42 / Ask 37.44` — one tick
  inside a 5.3 bps BBO. Regression tests assert scale-invariance and direction.

### C2. Model 2 was fully dead code (P1 — deeper than Phase 1 found)
- Phase 1 wired evaluation, but the Binance reference feed was never started.
- **Fix**: `BinanceFuturesFeed` now starts in `initialize()` with Delta→Binance
  symbol mapping, routes ticks into `reference_prices`, and shuts down cleanly.
  Verified: feed subscribes (`SOLUSDT`, `BTCUSDT`), and a forced 50 bps Binance
  surge fires `SNIPE_BUY` with +13.9 bps net edge through the exact engine path.
- Taker sniping stays **opt-in** behind `--snipe` (requires `--live`); default
  remains log-only. Covered by gate tests.

### C3. Anonymous dry-run spammed HMAC crashes (P2)
- Without credentials, `sync_positions` tried to sign with a `None` secret
  every 2.5 s. Now skipped unless credentials exist (position/kill-switch
  semantics only apply to live inventory anyway).

**Functional proof**: 25-second live dry-run against the real Delta India API —
product specs fetched (BTCUSD tick 0.5 / contract 0.001 BTC; AKEUSD contract
10,000), the $5 notional guard correctly skipped BTC/SOL ($59/$69 contracts),
micro-notional symbols quoted continuously, engine shut down cleanly.

## CG-Terminal — mechanical sweep & production build

- **280 Python files parse-checked**: **0 syntax errors**. 121 import cleanly;
  83 are forensic/operator scripts that fail only on environment (gitignored
  `desk/state.json` data, localhost terminal not running, Windows `windll`,
  `C:\Users\SIGMA` host paths); 73 archive/MT5-host scripts; 3 have top-level
  network side effects. Classification, not code defects.
- **Production build**: `npm install` → `prisma generate` → `next build` —
  clean, 23 API routes compiled, strict TypeScript (errors fail the build).

### C4. Standalone output nested by dual lockfiles → JS chunks 404 in production (P1)
- The repo carries both `bun.lock` and `package-lock.json`, so Turbopack
  inferred the workspace root one level above the app; `.next/standalone/`
  then nested under `<repo>/<app>/` and the `npm run build` static-copy put
  `static/` in the wrong place — the server booted but every JS chunk 404'd.
- **Fix**: `turbopack.root: __dirname` pinned in `next.config.ts`.
- **Verified**: rebuild → `standalone/server.js` at the expected path, page
  HTTP 200, chunk HTTP 200 (16,869 bytes), `/api/health` green, and
  `/api/cg/ticker?sym=BTC` served a **fresh live Coinglass quote** (58,959.7).

## Documentation truth pass

- CG-Terminal README claimed "12 assets" — corrected to the curated 61-asset
  universe (30 crypto + 28 TradFi + 3 classic) per `src/lib/universe/curated.ts`.
- HFT README: runbook now documents the credential requirement, the enforced
  kill switch, the new `--snipe` lane (Step 5), and the corrected A-S
  formulation.

## Consolidated test state after Phase 2

| Suite | Command | Result |
| --- | --- | --- |
| HFT models + risk governors + A-S math + sniper gate | `cd HFT && python -m pytest tests/` | **15 passed** |
| Delta-Fibonacci engine | `cd Delta-Fibonacci-Institutional-Business && python -m pytest tests/` | **37 passed, 32 skipped** |
| Delta-Fib E2E proof (synthetic, production paths) | `python scripts/e2e_engine_proof.py` | **all 6 stages green** |
| CG-Terminal Python | parse-check sweep (280 files) | **0 syntax errors** |
| CG-Terminal web | `npm run build` + standalone boot + smoke | **clean, HTTP 200, live data** |
