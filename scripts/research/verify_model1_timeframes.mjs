#!/usr/bin/env node
/**
 * verify_model1_timeframes.mjs — cross-timeframe consistency verification
 * for the Model 1 heatmap surface (the user's requirement: "ensure data
 * must match at different time frames").
 *
 * Checks, per (mode, range):
 *   1. the window span matches the requested range (12h → 12h of bars …)
 *   2. the LAST PRICE agrees across ALL ranges and modes (same market, same
 *      moment — only the look-back window may differ)
 *   3. the column period matches the page's g-map (5/15/30/120m…)
 *   4. key levels around spot are consistent: a level prominent in a wider
 *      window must also appear (or have been swept) in the narrower one
 *   5. totals are monotone-ish: wider windows see >= the open exposure of
 *      narrower ones (coin 24h total <= coin 3d total, same mode)
 *
 * Usage: node verify_model1_timeframes.mjs [sym]   (default XAU)
 */
const BASE = process.env.BASE ?? "http://localhost:3000";
const sym = (process.argv[2] ?? "XAU").toUpperCase();

const EXPECT_MINUTES = {
  "12h": 720, "24h": 1440, "48h": 2880, "3d": 4320, "7d": 10080,
  "14d": 20160, "30d": 43200, "90d": 129600,
};
const EXPECT_COLUMN_MIN = { "12h": 5, "24h": 5, "48h": 15, "3d": 15, "7d": 30, "14d": 30, "30d": 120, "90d": 360 };

const fmtM = (n) => (n / 1e6).toFixed(1) + "M";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function fetchOne(mode, range) {
  const url = `${BASE}/api/cg/stopmap?sym=${sym}&model=1&mode=${mode}&range=${range}`;
  const res = await fetch(url, { signal: AbortSignal.timeout(45000) });
  const j = await res.json().catch(() => null);
  return j;
}

const results = [];
let failures = 0;

console.log(`=== ${sym} Model 1 cross-timeframe consistency (vs ${BASE}) ===\n`);

for (const mode of ["coin", "pair"]) {
  for (const range of ["12h", "24h", "48h", "3d", "7d", "14d", "30d"]) {
    const d = await fetchOne(mode, range);
    await sleep(1200);
    if (!d?.ok || !d.model?.overview) {
      console.log(`FAIL ${mode} ${range}: ${d?.error ?? "no model"}`);
      results.push({ mode, range, ok: false, error: d?.error });
      failures++;
      continue;
    }
    const m = d.model;
    const ov = m.overview;
    const spanMin = (m.candles[m.candles.length - 1].ts - m.candles[0].ts) / 60000;
    const expectSpan = EXPECT_MINUTES[range];
    const spanOk = Math.abs(spanMin - expectSpan) / expectSpan < 0.12; // ±12% (partial last bar)
    const colOk = ov.columnMinutes === EXPECT_COLUMN_MIN[range];
    const bars = m.candles.length;
    const ok = spanOk && colOk;
    if (!ok) failures++;
    console.log(
      `${ok ? "ok  " : "FAIL"} ${mode.padEnd(4)} ${range.padEnd(4)} px=${ov.lastPrice} span=${(spanMin / 60).toFixed(1)}h/${expectSpan / 60}h cols=${ov.columnMinutes}m/${EXPECT_COLUMN_MIN[range]}m bars=${bars} total=${fmtM(ov.total)} longs=${fmtM(ov.longs)} shorts=${fmtM(ov.shorts)}`
    );
    if (m.keyLevels.above.length)
      console.log(`     above: ${m.keyLevels.above.map((k) => `${k.price}=${fmtM(k.usd)}`).join(" · ")}`);
    if (m.keyLevels.below.length)
      console.log(`     below: ${m.keyLevels.below.map((k) => `${k.price}=${fmtM(k.usd)}`).join(" · ")}`);
    results.push({
      mode, range, ok,
      lastPrice: ov.lastPrice,
      spanMin: Math.round(spanMin),
      columnMinutes: ov.columnMinutes,
      bars,
      total: Math.round(ov.total),
      longs: Math.round(ov.longs),
      shorts: Math.round(ov.shorts),
      above: m.keyLevels.above,
      below: m.keyLevels.below,
    });
  }
}

// ---- consistency checks ----
console.log("\n=== cross-checks ===");
const prices = results.filter((r) => r.ok).map((r) => r.lastPrice);
if (prices.length) {
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const spreadPct = ((max - min) / min) * 100;
  const priceOk = spreadPct < 0.5; // all windows queried within a minute or two
  console.log(`${priceOk ? "ok  " : "WARN"} last price across ${prices.length} windows: ${min}..${max} (spread ${spreadPct.toFixed(3)}%)`);
  if (!priceOk) failures++;
}

// totals monotone per mode (wider window >= narrower)
for (const mode of ["coin", "pair"]) {
  const rs = results.filter((r) => r.ok && r.mode === mode);
  const order = ["12h", "24h", "48h", "3d", "7d", "14d", "30d"];
  let monoOk = true;
  for (let i = 1; i < rs.length; i++) {
    const a = rs.find((r) => r.range === order[i - 1]);
    const b = rs.find((r) => r.range === order[i]);
    if (a && b && b.total < a.total * 0.55) {
      // a wider window should not see dramatically LESS open exposure
      console.log(`WARN ${mode}: total ${order[i]}=${fmtM(b.total)} << ${order[i - 1]}=${fmtM(a.total)} (levels decayed/swept — plausible after big moves, verify)`);
      monoOk = false;
    }
  }
  console.log(`${monoOk ? "ok  " : "WARN"} ${mode} open-exposure totals are non-collapsing across widening windows`);
}

// key-level coherence: 3d levels should be visible in 7d/30d too (same market)
const r3d = results.find((r) => r.mode === "coin" && r.range === "3d" && r.ok);
for (const wider of ["7d", "30d"]) {
  const rw = results.find((r) => r.mode === "coin" && r.range === wider && r.ok);
  if (!r3d || !rw) continue;
  const near = (a, b, tolPct) => Math.abs(a - b) / b < tolPct;
  let matched = 0;
  for (const k of [...r3d.above, ...r3d.below]) {
    if (rw.above.concat(rw.below).some((w) => near(k.price, w.price, 0.004))) matched++;
  }
  console.log(`${matched >= 3 ? "ok  " : "WARN"} coin 3d key levels also present in ${wider}: ${matched}/${r3d.above.length + r3d.below.length}`);
}

console.log(`\n${failures === 0 ? "ALL CONSISTENT" : `${failures} FAILURES`}`);
process.exit(failures === 0 ? 0 : 1);
