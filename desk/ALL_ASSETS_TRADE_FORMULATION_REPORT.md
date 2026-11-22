# ALL-ASSET PLAYBOOK TRADE FORMULATION REPORT
> **Generated UTC**: 2026-11-22T14:00:07Z
> **Evaluated Universe**: 58 Curated Assets (30 Crypto USDT-M + 28 TradFi USDT-M)
> **Decision Engine**: `desk/LLM_TRADE_FORMULATION_PLAYBOOK.md` (5m EMA-233 trend-gated, 8-tab confluence)

---

## 1. Executive Summary
- **A-Grade High-Conviction Trades (Confluence >= 7)**: **0**
- **B-Grade Secondary Trades (Confluence 5–6)**: **1**
- **No-Trade / Surveillance Watchlist**: **57**

---

## 2. Actionable Trade Formulations (A-Grade & B-Grade)

| Symbol | Direction | Grade | Confluence | Entry | Stop Loss | Target 1 | Target 2 | R:R | Risk Size | Invalidation |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **COIN** | `LONG` | **B** | **5/10** | `105.78` | `104.9338` | `107.3667` | `108.9534` | **1.88R** | 1.0% | 5m candle close below stop 104.9338 or regime flip to short_only |

---

## 3. Detailed Trade Blueprints & Evidence Ledger

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
| **COIN** | TradFi | `long_only` | `TRADE` (long) | B | 5/10 | Setup A zone strike: LONG at 105.78 with dominance ratio 4.681455190771961 (2026-11-22T12:45) |
| **BTC** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **ETH** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **BNB** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **SOL** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **XRP** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **ADA** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **DOGE** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **TRX** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **LINK** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **LTC** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **AVAX** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **DOT** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **NEAR** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **UNI** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **ATOM** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **XLM** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **ETC** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **FIL** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **ICP** | Crypto | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **HBAR** | Crypto | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **APT** | Crypto | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **ARB** | Crypto | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **OP** | Crypto | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **SUI** | Crypto | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **SEI** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **INJ** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **TIA** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **VET** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **1000PEPE** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **1000SHIB** | Crypto | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **XAU** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **NVDA** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **SNDK** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **SOXL** | TradFi | `neutral` | `NO-TRADE` | — | 0/10 | trend regime is neutral or tracker error — no clear trend direction |
| **SPCX** | TradFi | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **GOOGL** | TradFi | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **MU** | TradFi | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **SKHY** | TradFi | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **XAG** | TradFi | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **CL** | TradFi | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **INTC** | TradFi | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
| **CRCL** | TradFi | `error` | `NO-TRADE` | — | 0/10 | fetch/formulate error: 'list' object has no attribute 'get' |
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