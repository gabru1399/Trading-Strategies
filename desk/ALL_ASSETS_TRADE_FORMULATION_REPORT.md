# ALL-ASSET PLAYBOOK TRADE FORMULATION REPORT
> **Generated UTC**: 2026-11-22T14:03:26Z
> **Evaluated Universe**: 58 Curated Assets (30 Crypto USDT-M + 28 TradFi USDT-M)
> **Decision Engine**: `desk/LLM_TRADE_FORMULATION_PLAYBOOK.md` (5m EMA-233 trend-gated, 8-tab confluence)

---

## 1. Executive Summary
- **A-Grade High-Conviction Trades (Confluence >= 7)**: **1**
- **B-Grade Secondary Trades (Confluence 5–6)**: **4**
- **No-Trade / Surveillance Watchlist**: **53**

---

## 2. Actionable Trade Formulations (A-Grade & B-Grade)

| Symbol | Direction | Grade | Confluence | Entry | Stop Loss | Target 1 | Target 2 | R:R | Risk Size | Invalidation |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **CL** | `LONG` | **A** | **7/10** | `83.8461` | `83.1753` | `85.1038` | `86.3615` | **1.87R** | 2.0% | 5m candle close below stop 83.1753 or regime flip to short_only |
| **XLM** | `LONG` | **B** | **6/10** | `0.1281` | `0.1271` | `0.13` | `0.1319` | **1.9R** | 1.0% | 5m candle close below stop 0.1271 or regime flip to short_only |
| **TIA** | `LONG` | **B** | **6/10** | `0.3339` | `0.3312` | `0.3389` | `0.3439` | **1.85R** | 1.0% | 5m candle close below stop 0.3312 or regime flip to short_only |
| **GOOGL** | `LONG` | **B** | **6/10** | `274.9448` | `272.7452` | `279.069` | `283.1931` | **1.87R** | 1.0% | 5m candle close below stop 272.7452 or regime flip to short_only |
| **COIN** | `LONG` | **B** | **5/10** | `105.78` | `104.9338` | `107.3667` | `108.9534` | **1.88R** | 1.0% | 5m candle close below stop 104.9338 or regime flip to short_only |

---

## 3. Detailed Trade Blueprints & Evidence Ledger

### CL — LONG (A-Grade, Confluence: 7/10)
- **Regime**: `long_only` (5m EMA-233 gate enforced)
- **Entry**: `83.8461` | **Stop**: `83.1753` | **Targets**: `[85.1038, 86.3615]` | **R:R**: `1.87R`
- **Invalidation**: 5m candle close below stop 83.1753 or regime flip to short_only
- **Observed Confluence Evidence**:
  * Setup B Value Area low test: price 83.93 near VAL 83.80708333333334 in long regime
  * Footprint absorption signal aligned with long_only (+2 confluence)
  * Order book bid-heavy imbalance (+0.203) (+1 confluence)
  * Substantial liquidation magnet above price at 86.641 (+1 confluence)
  * Hard 5m EMA-233 trend gate aligned: long_only (price 83.93)

### XLM — LONG (B-Grade, Confluence: 6/10)
- **Regime**: `long_only` (5m EMA-233 gate enforced)
- **Entry**: `0.1281` | **Stop**: `0.1271` | **Targets**: `[0.13, 0.1319]` | **R:R**: `1.9R`
- **Invalidation**: 5m candle close below stop 0.1271 or regime flip to short_only
- **Observed Confluence Evidence**:
  * Setup B Value Area low test: price 0.12822 near VAL 0.12799625 in long regime
  * Footprint absorption signal aligned with long_only (+2 confluence)
  * Substantial liquidation magnet above price at 0.1333 (+1 confluence)
  * Hard 5m EMA-233 trend gate aligned: long_only (price 0.12822)

### TIA — LONG (B-Grade, Confluence: 6/10)
- **Regime**: `long_only` (5m EMA-233 gate enforced)
- **Entry**: `0.3339` | **Stop**: `0.3312` | **Targets**: `[0.3389, 0.3439]` | **R:R**: `1.85R`
- **Invalidation**: 5m candle close below stop 0.3312 or regime flip to short_only
- **Observed Confluence Evidence**:
  * Setup B Value Area low test: price 0.3342 near VAL 0.334625 in long regime
  * Footprint absorption signal aligned with long_only (+2 confluence)
  * Substantial liquidation magnet above price at 0.3473 (+1 confluence)
  * Hard 5m EMA-233 trend gate aligned: long_only (price 0.3342)

### GOOGL — LONG (B-Grade, Confluence: 6/10)
- **Regime**: `long_only` (5m EMA-233 gate enforced)
- **Entry**: `274.9448` | **Stop**: `272.7452` | **Targets**: `[279.069, 283.1931]` | **R:R**: `1.87R`
- **Invalidation**: 5m candle close below stop 272.7452 or regime flip to short_only
- **Observed Confluence Evidence**:
  * Setup B Value Area low test: price 275.22 near VAL 274.68675 in long regime
  * Footprint absorption signal aligned with long_only (+2 confluence)
  * Substantial liquidation magnet above price at 284.81 (+1 confluence)
  * Hard 5m EMA-233 trend gate aligned: long_only (price 275.22)

### COIN — LONG (B-Grade, Confluence: 5/10)
- **Regime**: `long_only` (5m EMA-233 gate enforced)
- **Entry**: `105.78` | **Stop**: `104.9338` | **Targets**: `[107.3667, 108.9534]` | **R:R**: `1.88R`
- **Invalidation**: 5m candle close below stop 104.9338 or regime flip to short_only
- **Observed Confluence Evidence**:
  * Setup A zone strike: LONG at 105.78 with dominance ratio 4.681455190771961 (2026-11-22T12:45)
  * Substantial liquidation magnet above price at 109.99 (+1 confluence)
  * Hard 5m EMA-233 trend gate aligned: long_only (price 105.89)

---

## 4. Complete 58-Asset Surveillance Matrix

| Symbol | Category | Regime | Action | Grade | Confluence | Primary Evidence / Rejection Reason |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **CL** | TradFi | `long_only` | `TRADE` (long) | A | 7/10 | Setup B Value Area low test: price 83.93 near VAL 83.80708333333334 in long regime |
| **XLM** | Crypto | `long_only` | `TRADE` (long) | B | 6/10 | Setup B Value Area low test: price 0.12822 near VAL 0.12799625 in long regime |
| **TIA** | Crypto | `long_only` | `TRADE` (long) | B | 6/10 | Setup B Value Area low test: price 0.3342 near VAL 0.334625 in long regime |
| **GOOGL** | TradFi | `long_only` | `TRADE` (long) | B | 6/10 | Setup B Value Area low test: price 275.22 near VAL 274.68675 in long regime |
| **COIN** | TradFi | `long_only` | `TRADE` (long) | B | 5/10 | Setup A zone strike: LONG at 105.78 with dominance ratio 4.681455190771961 (2026-11-22T12:45) |
| **BTC** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **ETH** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **BNB** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **SOL** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **XRP** | Crypto | `short_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with short_only (+2 confluence) |
| **ADA** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **DOGE** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **TRX** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **LINK** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **LTC** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **AVAX** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **DOT** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **NEAR** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **UNI** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **ATOM** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **ETC** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **FIL** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **SEI** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **INJ** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **VET** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **1000PEPE** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **1000SHIB** | Crypto | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **SPCX** | TradFi | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **MU** | TradFi | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **SKHY** | TradFi | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **XAG** | TradFi | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **INTC** | TradFi | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **CRCL** | TradFi | `long_only` | `NO-TRADE` | — | 4/10 | Footprint absorption signal aligned with long_only (+2 confluence) |
| **ICP** | Crypto | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **HBAR** | Crypto | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **APT** | Crypto | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **ARB** | Crypto | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **OP** | Crypto | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **SUI** | Crypto | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **XAU** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **NVDA** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **SNDK** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **SOXL** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **MSTR** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **QQQ** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **ANTHROPIC** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **AAPL** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **TSLA** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **DRAM** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **KORU** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **META** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **NBIS** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **MSFT** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **AMZN** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **AMD** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **NFLX** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **AVGO** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **TSM** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |