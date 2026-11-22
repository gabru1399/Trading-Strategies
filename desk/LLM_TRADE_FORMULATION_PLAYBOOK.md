# LLM TRADE FORMULATION PLAYBOOK

> Audience: a local LLM reading `data/llm-dump/<SYM>_latest.json` produced by
> `scripts/trading/dump_for_llm.py`. This document is the complete decision
> system: how to read the dump, which setups are valid, how to score them,
> where risk goes, and the exact output format required. Follow it literally.
> If the data is missing, ambiguous or stale — say so; never invent values.

---

## 0. Workflow (always this order)

```
1. python3 scripts/trading/dump_for_llm.py --sym <SYM>        # refresh the dump
2. Read data/llm-dump/<SYM>_latest.json fully (start with _guide, _meta)
3. Determine the trend regime (§2) — this is a HARD filter, not advice
4. Enumerate candidate setups (§3) that agree with the regime
5. Score confluence (§4), pick at most ONE primary setup
6. Formulate the order: entry, stop, targets, size (§5)
7. Emit the verdict in the required JSON shape (§6)
```

The dump's `_meta.generatedAtUtc` is the "now" of every decision. Sections
carry their own `updatedAt` (epoch ms). If any section you rely on is more
than ~10 minutes older than `_meta.generatedAt`, downgrade confidence and
say which section was stale.

---

## 1. Data dictionary (what each section is)

| Section | Tab | What it gives you | Key fields |
| --- | --- | --- | --- |
| `market` | Overview | last price, day change/high/low/vol, auction POC/VAH/VAL for session/day/week/month, EMA 13/89/233 on m15/h1/h4/d1, day VWAP ±1σ/2σ/3σ | `market.price.last`, `market.auction.<session>.poc/vah/val`, `market.ema.<tf>.e13/e89/e233`, `market.vwap` |
| `signals` | Footprint | Coinglass-exact Absorption / Divergence / Strong Divergence / Trap / Exhaustion on 15m time, volume and range bars | `signals.sets[].sigs[]`, `signals.counts.bullish/bearish` |
| `footprint` | Footprint | 60× 5m aggregated order-flow bars (Binance+OKX+Bybit+Hyperliquid): OHLC, per-price-row taker buy `b` / sell `s`, grid low `lo`, row height `tick`, per-bar OI | `footprint.bars[].fp.b`, `.fp.s`, `.c`, `.h`, `.l` |
| `large_orders` | Large Orders | resting whale walls + executed large trades per venue | `large_orders.groups[].list[]` |
| `liq_levels` | Liq Levels | liquidation key levels ±4% (clusters 3d/7d/30d, Coinglass **estimates**) | `liq_levels.stats.keyLevels.above[]` (short fuel) / `.below[]` (long fuel), each `{price, usd, lev, strength, distPct}` |
| `book_walls` | Book Walls | multi-venue depth/imbalance now vs 5m ago, confirmed walls with age + touched state, add/fill/pull events | `book_walls.model.depth.bidUsd/askUsd`, `.imbalance`, `.imbalance5mAgo`, `.walls[]`, `.events[]` |
| `cvd` | CVD | 60× 5m perp and spot cumulative volume delta, taker buy share, active divergences | `cvd.perp[]`, `cvd.spot[]`, `cvd.activeDivergences` |
| `tracker` | (scanner) | the 5m EMA-233 trend gate + key-level finished-auction strikes, already trend-filtered | `tracker.trend.gate`, `tracker.strikes[]` |

Footprint grid geometry: row `i` covers prices `lo + i·tick` upward; the
**last** entries of `b`/`s` are the TOP rows (the bar's high). `top3_buy /
top3_sell` in `tracker.strikes[]` are precomputed sums of the last 3 rows.

---

## 2. Trend regime — the hard filter

`tracker.trend.gate` is computed from the 5m chart's own EMA-233 (600-close
seed, evaluated at each strike bar's timestamp):

- `short_only` — price below EMA-233. **Only SHORT setups may be formulated.**
  LONG evidence may be reported as context, never as the trade.
- `long_only` — price above EMA-233. **Only LONG setups.**
- `neutral` — price sitting on the EMA. No trade; wait for separation.

Cross-check with the higher timeframes in `market.ema`:
- The gate comes from m5 EMA-233 (`tracker.trend.ema233`).
- A trade aligned with m5 AND h1 EMA-233 (`market.ema.h1.e233`) is
  higher quality; note disagreement in the verdict instead of overriding.
- EMA-13 vs EMA-89 spacing tells you trend strength: wide and parallel =
  established; intertwining = chop, demand more confluence (§4 threshold +1).

---

## 3. Setups (only these are formulable)

### Setup A — Key-Level Finished Auction (primary)

The house strategy. A liquidation key level was struck AND the auction at
the level finished against the strike.

**Evidence:** an entry in `tracker.strikes[]` (already trend-gated):
- `dir: "short"` — price rallied into a cluster ABOVE (`liq_levels…above`),
  top-3 footprint rows zero/dominated by sells → the rally found sellers.
- `dir: "long"` — price declined into a cluster BELOW (`…below`), top rows
  dominated by buys → the decline found buyers.

**Quality markers:**
- `dominance_ratio ≥ 5` (clean rejection) beats 3–5 (minimum is 3).
- `zone_usd` matters as fuel: ≥ $1M absolute, OR top-tercile among that
  symbol's zones in this dump (row-level USD varies hugely by asset — an
  ARB cluster can print $5M where a BTC row shows $3K; compare within the
  symbol, not across symbols).
- The strike bar is recent (≤ 3 bars old vs the newest `footprint.bars[]`);
  a strike hours old is context, not an entry.
- Bar CLOSE back on the trend side of the zone (short: closed below the
  zone price; long: above) — otherwise the auction may still be running.

### Setup B — Absorption at a level

Aggressor prints volume but price refuses to move.

**Evidence:** recent Absorption signals in `signals.sets[]` whose price is
within ~0.3% of a `liq_levels` key level or a `book_walls` confirmed wall,
direction matching the regime. Absorption INTO resistance (short regime) =
sellers absorbing late longs.

### Setup C — CVD divergence

Price extends, flow doesn't follow.

**Evidence:** `cvd.activeDivergences[]` non-empty, or manually: last 12
`cvd.perp[]` values flat/falling while `footprint` closes make higher
highs (short regime) — or the mirror for longs. Perp-vs-spot split
(`cvd.perp` vs `cvd.spot`) diverging is the stronger form.

### Setup D — Book-wall magnet/fade

A confirmed wall near price acts as a magnet first, barrier second.

**Evidence:** `book_walls.model.walls[]` entry within 0.5% of
`market.price.last` with `age` > 30 min and `touched` true. With the trend
INTO the wall (short regime, wall overhead): fade the first touch WITH the
trend once `events[]` shows fills or the wall thins. Against the trend:
no trade (wall pull risk).

### Setup E — Liquidity sweep + reclaim

A key level gets run through and immediately reclaimed.

**Evidence:** a `footprint` bar whose `h` pierced a `liq_levels…above`
price but `c` closed back below it (short), followed by a bar with
top-rows dominated by sells (Setup A mechanics on the retest). The sweep
bar itself is the trigger's precondition, not the entry.

---

## 4. Confluence scoring

Score the primary setup 0–10:

| +points | Condition (verify in the dump, not from memory) |
| --- | --- |
| +3 | Setup A strike with `dominance_ratio ≥ 5` AND fuel (zone_usd ≥ $1M or top-tercile among that symbol's zones) |
| +2 | Zone coincides (±0.15%) with an auction level (`market.auction.day.poc`/`val`/`vah`) |
| +2 | CVD divergence active in the trade direction (`cvd.activeDivergences`) |
| +1 | Book-wall or whale resting order beyond the zone (invalidation-side protection) |
| +1 | `book_walls.model.imbalance` agrees (short: < −0.05; long: > +0.05) and moved with `imbalance5mAgo` |
| +1 | Absorption/Exhaustion signal (`signals.sets[]`) within 3 bars, direction agrees |

Thresholds: **≥ 7 = A-grade** (full size), **5–6 = B-grade** (half size),
**< 5 = no trade** (report as watch). In EMA chop (§2) require ≥ 8.
Cap: at most one A-grade trade per symbol per direction until it closes.

---

## 5. Risk

- **Entry:** the strike bar's close, or better: limit at the zone price on
  a retest (`zone_price` from the strike). Never chase > 0.25% past it.
- **Stop:** beyond the structure that produced the setup, plus buffer:
  short → above `max(zone_price, strike-bar high)` + 0.5·`tick`·10; long →
  mirror below. If that is further than 1.0% away, the setup is invalid —
  structural stop does not fit.
- **Targets:** first at the nearest same-side `liq_levels` cluster in the
  trade direction (liquidation fuel gets swept); final at the day
  POC/VAH/VAL extreme (`market.auction.day`). Take half at T1.
- **Minimum R:**2 reward-to-risk at T2; skip otherwise.
- **Sizing:** risk ≤ 1% of account per trade (0.5% for B-grade).
  Position = riskUSD / stopDistancePct. Leverage beyond that is not
  formulable from this data.
- **Invalidation:** opposite gate flip, the zone fully traversed with
  closes beyond it, or the wall that protected your stop (`events[]`
  "pull") disappears → exit or flatten immediately.

---

## 6. Required output format

Emit exactly this JSON (plus one short human paragraph if asked):

```json
{
  "sym": "BTC",
  "asOf": "<_meta.generatedAtUtc>",
  "regime": "long_only | short_only | neutral",
  "setup": "A|B|C|D|E",
  "action": "trade | watch | no-trade",
  "direction": "long | short | null",
  "grade": "A | B | null",
  "confluence": <0-10>,
  "entry": <price>,
  "stop": <price>,
  "targets": [<t1>, <t2>],
  "rr": <number>,
  "sizePct": <account % at risk>,
  "evidence": ["<one line per point scored, citing exact field paths>"],
  "invalidation": "<the one thing that kills this trade>",
  "stale": ["<sections older than 10 min, if any>"]
}
```

Rules for the verdict:
- `no-trade` with reasons is a SUCCESSFUL run — do not manufacture a setup.
- Every `evidence` line must cite a real field path from THIS dump
  (e.g. "`tracker.strikes[0].dominance_ratio = 31.4`"). No path, no point.
- Liquidation/whale/wall numbers are Coinglass **estimates** — describe
  them as such in any human-facing sentence.
- All prices from the dump; arithmetic (R multiples, distances) computed,
  never eyeballed. State distances in % of price.

---

## 7. Worked example (BTC snapshot 2026-11-22T12:19Z — a NO-TRADE)

Facts from that dump (all verified in `BTC_latest.json`):
- `tracker.trend.gate = "long_only"` — px 61,380.6 vs m5 EMA-233 59,883.1.
- `tracker.strikes[1]` = LONG · 09:35 UTC · zone 60,094.1 ($2.5K, High lev,
  strength 12.3) · top3 buy/sell 52.05/1.59 → `dominance_ratio = 32.7` ·
  bar close 60,170.2.
- Newest `footprint.bars[]` ts = 12:15 UTC → the strike bar is ~44 bars
  (3.7 h) old — outside the ≤3-bar freshness window.
- `market.auction.day`: POC 59,399.0 / VAH 60,414.6 / VAL 58,818.6 — the
  60,094 zone is 0.53% below VAH, outside the ±0.15% confluence band.
- `cvd.activeDivergences` = none; perp CVD rising with price (no divergence).
- `book_walls.model.imbalance` = −0.165 (ask-heavy, contra the long).
- Newest signal across `signals.sets[]` (vol-bar exhaustion, sell side) is
  ~3.9 h old — nothing within the 3-bar window.

Scoring: +3 (ratio 32.7 ≥ 5; fuel weak — $2.5K is bottom-tercile, but
ratio carries it), +0 (no auction confluence), +0 (no CVD divergence),
+0 (imbalance contra), +0 (no fresh signal) → **3 → below 5 → no-trade,
watch**.

The lesson: a spectacular 32× dominance strike is still untradeable when
it is stale (3.7 h old), unprotected by book imbalance, and unconfirmed
by level confluence. The correct verdict for this dump was:

```json
{
  "sym": "BTC", "asOf": "2026-11-22T12:19:21Z", "regime": "long_only",
  "setup": "A", "action": "no-trade", "direction": null, "grade": null,
  "confluence": 3, "entry": null, "stop": null, "targets": null, "rr": null,
  "sizePct": 0,
  "evidence": [
    "tracker.strikes[1]: dominance_ratio=32.7 but zone_usd=2488.6 (weak fuel)",
    "strike bar 09:35 vs newest footprint bar 12:15 — 44 bars stale (>3)",
    "market.auction.day.vah=60414.6 vs zone 60094.1 — no level confluence",
    "book_walls.model.imbalance=-0.165 ask-heavy, contra long",
    "cvd.activeDivergences empty; newest signal ~3.9h old — no credits"
  ],
  "invalidation": "n/a — no position; re-arm if a fresh strike prints at POC/VAL",
  "stale": []
}
```

`no-trade` with cited evidence is a SUCCESSFUL run. That is the shape of
a complete formulation. When your dump shows less, say less.

---

## 8. Honesty rules (non-negotiable)

1. Quote only numbers present in the dump you read this run.
2. Label Coinglass-derived figures (liq levels, whales, walls, CVD venues)
   as estimates in human-facing text.
3. If two sections disagree (e.g. `market.price.last` vs
   `liq_levels.livePrice`), prefer the newer `updatedAt` and note it.
4. The trend gate overrides every bullishly/bearishly framed signal. A
   "perfect" LONG stack under `short_only` is a NO-TRADE, reported as such.
5. Never present a formulated order as executed — this playbook formulates;
   execution is a separate human/operator decision.
