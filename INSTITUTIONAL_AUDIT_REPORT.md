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
