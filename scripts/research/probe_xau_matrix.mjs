#!/usr/bin/env node
/**
 * XAU liquidation heatmap — corrected full matrix probe.
 *
 * Live-page contract (mined from LiquidationHeatMap [symbol] chunk, 2026-11-21):
 *   G = {1: ["/api/index/v2/liqHeatMap", "/api/index/aggregate/liqHeatMap"],
 *        2: ["/api/index/v5/liqHeatMap", "/api/index/v3/aggregate/liqHeatMap"],
 *        3: ["/api/index/v6/liqHeatMap", "/api/index/v4/aggregate/liqHeatMap"]}
 *   mode "coin"  -> aggregate endpoint, symbol = plain coin (e.g. XAU)
 *   mode "pair"  -> primary endpoint,   symbol = exchange pair
 *   model 3 params: { range: "12h|24h|48h|72h|7d|14d|30d|90d|180d|365d|720d", cp: false }
 *   model 1/2 params: model1 -> interval/limit (5/288 for 24h); model2 -> range 24h|72h|7d|30d
 *   baseURL: https://fapi.coinglass.com  (page routes ALL liqHeatMap calls through fapi)
 *   params always include merge:true, symbol, data:<obe-token>
 *
 * This probe runs the full model × timeframe × mode matrix for XAU (and BTC
 * control), parses the payload, and prints per-window cluster analysis:
 * strongest liquidation levels above and below spot = the pullback magnets.
 */
import crypto from "crypto";
import zlib from "zlib";
import fs from "fs";

const FAPI = "https://fapi.coinglass.com";
const STATIC_KEY = Buffer.from("1f68efd73f8d4921acc0dead41dd39bc", "utf8");
const TOTP_SECRET_B32 = "I65VU7K5ZQL7WB4E";
const KEY_A_CONSTS = { "55": "170b070da9654622", "66": "d6537d845a964081", "77": "863f08689c97435b" };

function base32Decode(s) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = 0, value = 0; const out = [];
  for (const ch of s.toUpperCase().replace(/=+$/, "")) {
    const idx = alphabet.indexOf(ch); if (idx === -1) continue;
    value = (value << 5) | idx; bits += 5;
    if (bits >= 8) { out.push((value >>> (bits - 8)) & 0xff); bits -= 8; }
  }
  return Buffer.from(out);
}
function totp(t) {
  const key = base32Decode(TOTP_SECRET_B32);
  const counter = Buffer.alloc(8); counter.writeUInt32BE(Math.floor(t / 30), 4);
  const d = crypto.createHmac("sha1", key).update(counter).digest();
  const off = d[d.length - 1] & 0x0f;
  return String((d.readUInt32BE(off) & 0x7fffffff) % 1000000).padStart(6, "0");
}
function makeObeToken() {
  const secs = Math.floor(Date.now() / 1000);
  const cipher = crypto.createCipheriv("aes-256-ecb", STATIC_KEY, null);
  return Buffer.concat([cipher.update(Buffer.from(`${secs},${totp(secs)}`, "utf8")), cipher.final()]).toString("base64");
}
function aesDec(buf, key) {
  const algo = key.length === 16 ? "aes-128-ecb" : key.length === 24 ? "aes-192-ecb" : "aes-256-ecb";
  const d = crypto.createDecipheriv(algo, key, null); d.setAutoPadding(true);
  return Buffer.concat([d.update(buf), d.final()]);
}
function tryInflate(buf) {
  for (const fn of [zlib.inflateSync, zlib.inflateRawSync, zlib.gunzipSync]) {
    try { return fn(buf); } catch {}
  }
  return buf;
}
function stripQuotes(s) { return s.startsWith('"') ? s.slice(1) : s.endsWith('"') ? s.slice(0, -1) : s; }
function mangleUrl(url) {
  const idx = url.indexOf("/api"); if (idx === -1) return url;
  const q = url.indexOf("?");
  return q === -1 ? url.slice(idx) : url.slice(idx, q);
}
function deriveKeyA(v, cacheTs, timeHeader, url) {
  let src = v === "0" ? cacheTs : v === "2" ? (timeHeader ?? "") : v === "1" ? mangleUrl(url) : (KEY_A_CONSTS[v] ?? "");
  return Buffer.from(Buffer.from(src, "utf8").toString("base64").slice(0, 16), "utf8");
}

async function cgFetch(base, path, params) {
  const url = new URL(path, base);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, String(v));
  // fapi serves liqHeatMap only with PLAIN requests: sending `encryption:true`
  // + `cache-ts-v2` pushes it onto the encrypted-response path, which 50001s
  // for these endpoints (live-verified 2026-11-21). The `data` token param is
  // still required — it authenticates the request.
  const res = await fetch(url, {
    headers: {
      "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
      accept: "*/*",
      origin: "https://www.coinglass.com",
      referer: "https://www.coinglass.com/",
    },
    signal: AbortSignal.timeout(20000),
  });
  const raw = Buffer.from(await res.arrayBuffer());
  let parsed = null;
  try { parsed = JSON.parse(raw.toString("utf8")); } catch {}
  return parsed; // null on transport/parse failure
}

// ---------- cluster analysis (mirrors our buildStopModel logic) ----------
function analyze(data) {
  if (!data || !Array.isArray(data.y) || !Array.isArray(data.liq)) return null;
  const y = data.y, liq = data.liq, prices = data.prices ?? [];
  const lastPrice = prices.length ? Number(prices[prices.length - 1][4]) : null;
  // profile: window-total USD per y level
  const profile = new Array(y.length).fill(0);
  for (const [, yi, usd] of liq) if (usd > 0 && yi >= 0 && yi < y.length) profile[yi] += usd;
  const maxUsd = Math.max(...profile, 0);
  // clusters: adjacent y levels merged
  const clusters = [];
  let cur = null;
  for (let i = 0; i < y.length; i++) {
    if (profile[i] > 0) {
      if (!cur) cur = { lo: y[i], hi: y[i], usd: 0 };
      cur.hi = y[i]; cur.usd += profile[i];
    } else if (cur) { clusters.push(cur); cur = null; }
  }
  if (cur) clusters.push(cur);
  const above = [], below = [];
  for (const c of clusters) {
    if (lastPrice == null) break;
    const mid = (c.lo + c.hi) / 2;
    const distPct = ((mid - lastPrice) / lastPrice) * 100;
    const entry = { price: +mid.toFixed(2), usd: c.usd, distPct: +distPct.toFixed(2), strength: +(100 * c.usd / (maxUsd || 1)).toFixed(1) };
    if (distPct >= 0) above.push(entry); else below.push(entry);
  }
  above.sort((a, b) => b.usd - a.usd); below.sort((a, b) => b.usd - a.usd);
  const totAbove = above.reduce((s, c) => s + c.usd, 0);
  const totBelow = below.reduce((s, c) => s + c.usd, 0);
  return { lastPrice, rangeLow: data.rangeLow, rangeHigh: data.rangeHigh, updateTime: data.updateTime, maxUsd, totAbove, totBelow, above, below };
}

// ---------- matrix ----------
const MODELS = [
  { model: 1, pair: "/api/index/v2/liqHeatMap", coin: "/api/index/aggregate/liqHeatMap" },
  { model: 2, pair: "/api/index/v5/liqHeatMap", coin: "/api/index/v3/aggregate/liqHeatMap" },
  { model: 3, pair: "/api/index/v6/liqHeatMap", coin: "/api/index/v4/aggregate/liqHeatMap" },
];
// mined from the live page chunk: g = range -> {interval, limit}
const G_MAP = {
  "12h": { interval: 5, limit: 144 },
  "24h": { interval: 5, limit: 288 },
  "48h": { interval: 15, limit: 192 },
  "3d": { interval: 15, limit: 288 },
  "7d": { interval: 30, limit: 336 },
  "14d": { interval: 30, limit: 672 },
  "30d": { interval: "h2", limit: 372 },
  "90d": { interval: "h6", limit: 360 },
  "180d": { interval: "h12", limit: 360 },
  "1y": { interval: "h24", limit: 360 },
  "2y": { interval: "d1", limit: 720 },
};
// mined from the live page chunk: x = model-3 range aliases
const X_MAP = { "12h": "12h", "24h": "24h", "48h": "48h", "3d": "72h", "7d": "7d", "14d": "14d", "30d": "30d", "90d": "90d", "180d": "180d", "1y": "365d", "2y": "720d" };
// mined: model-2 batch uses Q aliases {24h,3d->72h,7d,30d}; single-fetch may accept both — try range first
const Q_MAP = { "24h": "24h", "3d": "72h", "7d": "7d", "30d": "30d", "12h": "24h", "48h": "72h", "14d": "7d", "90d": "30d" };

const TFS = ["24h", "48h", "3d", "7d", "30d"];

const results = [];
async function run(sym, mode, model, tf) {
  const M = MODELS.find(m => m.model === model);
  const path = mode === "coin" ? M.coin : M.pair;
  const symbol = mode === "coin" ? sym : `Binance_${sym}USDT`;
  let params;
  if (model === 3) params = { merge: true, symbol, range: X_MAP[tf], cp: false, data: makeObeToken() };
  else if (model === 2) params = { merge: true, symbol, range: Q_MAP[tf], data: makeObeToken() };
  else { const g = G_MAP[tf]; params = { merge: true, symbol, interval: g.interval, limit: g.limit, data: makeObeToken() }; }
  const parsed = await cgFetch(FAPI, path, params);
  const row = { sym, mode, model, tf, path, params: { interval: params.interval, limit: params.limit, range: params.range }, ok: false };
  const data = parsed?.data ?? parsed;
  const a = analyze(Array.isArray(data) ? data[0] : data);
  if (parsed && parsed.code === "0" && a) {
    row.ok = true; row.analysis = {
      lastPrice: a.lastPrice, totAbove: a.totAbove, totBelow: a.totBelow,
      top: { above: a.above.slice(0, 5), below: a.below.slice(0, 5) },
    };
  } else {
    row.code = parsed?.code ?? (parsed ? "?" : "net/parse-fail");
    row.msg = parsed?.msg ?? "";
  }
  results.push(row);
  if (row.ok) {
    const an = row.analysis;
    console.log(`OK  ${sym} m${model} ${mode.padEnd(4)} ${tf.padEnd(4)} px=${an.lastPrice} below=$${fmt(an.totBelow)} above=$${fmt(an.totAbove)}`);
    for (const c of an.top.below.slice(0, 3)) console.log(`      magnet BELOW  $${c.price} (${c.distPct}%)  $${fmt(c.usd)}  str ${c.strength}`);
    for (const c of an.top.above.slice(0, 3)) console.log(`      magnet ABOVE  $${c.price} (+${c.distPct}%)  $${fmt(c.usd)}  str ${c.strength}`);
  } else {
    console.log(`--  ${sym} m${model} ${mode.padEnd(4)} ${tf.padEnd(4)} code=${row.code} ${row.msg}`);
  }
  return row.ok;
}
function fmt(n) { return (n / 1e6).toFixed(2) + "M"; }

// XAU: full matrix, slow (1.2s spacing to stay clear of the rate limiter)
console.log("=== XAU full matrix ===");
for (const model of [1, 2, 3]) {
  for (const tf of TFS) {
    await run("XAU", "coin", model, tf);
    await new Promise(r => setTimeout(r, 1200));
  }
}
// XAU pair-mode spot checks
console.log("\n=== XAU pair-mode spot checks ===");
for (const model of [1, 2, 3]) {
  await run("XAU", "pair", model, "24h");
  await new Promise(r => setTimeout(r, 1200));
}
// BTC control (should work everywhere)
console.log("\n=== BTC control ===");
for (const model of [1, 2, 3]) {
  await run("BTC", "pair", model, "24h");
  await new Promise(r => setTimeout(r, 1200));
  await run("BTC", "coin", model, "24h");
  await new Promise(r => setTimeout(r, 1200));
  await run("BTC", "coin", model, "30d");
  await new Promise(r => setTimeout(r, 1200));
}

fs.writeFileSync("/home/z/my-project/scripts/research/probe-xau-heatmap-full.json", JSON.stringify(results, null, 1));
const okXau = results.filter(r => r.sym === "XAU" && r.ok);
console.log(`\nXAU working combos: ${okXau.length}`);
for (const r of okXau) console.log(`  m${r.model} ${r.mode} ${r.tf}`);

