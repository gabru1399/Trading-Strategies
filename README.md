# Trading Strategies: Institutional Multi-Venue Quantitative Trading & HFT Platform

Comprehensive algorithmic trading ecosystem integrating institutional microstructure analytics, multi-criteria quantitative execution, and high-frequency market making across **Delta Exchange India** and **MetaTrader 5 (MT5)**.

---

## 🏛️ Architecture Overview

The repository is organized into three specialized quantitative trading engines:

```
Trading-Strategies/
├── CG-Terminal/                           # Real-Time Order Flow & Telemetry Dashboard
│   ├── src/                               # Next.js 15 + React 19 Frontend & API Routes
│   ├── desk/                              # Canonical Master Specification & Desk Daemon
│   ├── scripts/                           # Forensic TradFi & Footprint Tape Readers
│   └── tests/                             # Comprehensive Integration & Round Audits
│
├── Delta-Fibonacci-Institutional-Business/# Multi-Criteria Institutional Swing/Intraday Engine
│   ├── engine/                            # Live Multi-Criteria Runner & Kaizen Bridge
│   ├── audit/                             # Self-Improvement Ledgers & Trade Audits
│   ├── config/                            # Parameter Matrices & Strategy Rulebooks
│   └── tests/                             # Pytest Rigorous Validation Suite
│
└── HFT/                                   # High-Frequency Trading & Market Making Suite
    ├── core/                              # High-Performance REST/WebSocket Clients & L2 Books
    ├── models/                            # Avellaneda-Stoikov, Lead-Lag & OFI Microstructure
    ├── research/                          # Cross-Venue Edge & Spread Discovery Tools
    └── tests/                             # Mathematical Model & Execution Unit Tests
```

---

## 🚀 Engine Modules

### 1. CG-Terminal (`CG-Terminal/`)
- **Microstructure Telemetry**: Live order book walls, Footprint institutional absorption wicks, and cumulative volume delta (CVD).
- **Liquidation Cluster Mapping**: High-resolution stopmap sweep shelves and liquidation cascades.
- **Autonomous Desk Council**: Governed by `desk/CANONICAL_MASTER_SPECIFICATION.md` enforcing the 12-step execution chain, safety gates 1–11, and the 8-voice quantitative council.

### 2. Delta-Fibonacci Institutional Engine (`Delta-Fibonacci-Institutional-Business/`)
- **Multi-Criteria Selection**: Mathematical confluence of Fibonacci golden ratio levels (0.618, 0.786), order block validation, and volume profile value area highs/lows (VAH/VAL).
- **Autonomous Kaizen Self-Improvement**: Test-driven learning ledger (`KaizenAgentBridge`) performing 5-Whys root-cause diagnosis on every trade to eliminate recurring execution errors.
- **Micro-Risk Guardrails**: Hard $10.00 USD risk ceiling per MT5 formulation with automated bracket take-profit and stop-loss placement.

### 3. High-Frequency Trading Suite (`HFT/`)
- **Model 1: Avellaneda-Stoikov Dynamic Market Maker**: Inventory-risk reservation pricing $r(s, q) = s - q\gamma\sigma^2$, dynamic bid/ask skewing, and Post-Only spread capture (0.00% maker fees on Delta India).
- **Model 2: Binance $\to$ Delta Lead-Lag Latency Sniping**: High-speed velocity shock arbitrage exploiting cross-venue latency dislocations exceeding fee hurdles.
- **Model 3: Cont-Kukanov-Stoikov OFI Microstructure Scalper**: Order Flow Imbalance rolling Z-scores predicting 1s–5s price drift to front-run impending queue depletion.

---

## 🛡️ Risk Management & Safety Invariants

- **Zero Unverified Assertions**: All trading formulations and performance metrics are verified against live broker and exchange APIs before reporting.
- **Strict Post-Only Execution**: HFT market making orders strictly enforce Post-Only flags to ensure zero taker fee slippage and maximum maker rebates.
- **Automated Circuit Breakers**: Daily portfolio loss limits and automated inventory time-stops to eliminate drawdown drift.

---

## 📄 License & Attribution

Proprietary quantitative research and algorithmic trading platform maintained by **kbsingh1399**.

---

## 🔒 Security & Reliability (2026-11-20 hardening)

- **Credential hygiene**: exchange API keys are loaded exclusively from the
  environment / gitignored `.env` — never hardcoded. The HFT engine refuses
  `--live` execution without credentials. See [`SECURITY.md`](SECURITY.md) —
  **rotate any key that was ever committed**.
- **Risk governors, enforced**: the HFT daily-loss kill switch now actually
  fires (cancel-all → flatten → halt), covered by regression tests.
- **CI**: `docs/ci-workflow.yml` (ready-to-activate workflow: copy to
  `.github/workflows/ci.yml` and commit — contributor tokens cannot create
  workflow files). Runs both Python suites on every push/PR plus a gitleaks
  secret scan.
- Full findings: [`INSTITUTIONAL_AUDIT_REPORT.md`](INSTITUTIONAL_AUDIT_REPORT.md).

**Test status**: HFT `10 passed` · Delta-Fibonacci `37 passed, 32 skipped`
(Windows-only / optional-dependency guards).
