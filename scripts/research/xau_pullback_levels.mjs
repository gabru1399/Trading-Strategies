#!/usr/bin/env node
/**
 * XAU pullback-magnet report (corrected aggregation).
 *
 * Upstream semantics learned from the live payload (2026-11-21):
 * /api/liquidationLevels/v2 returns a TIME SERIES of estimated liq levels:
 *   { beginDate, level, level2: h1|h2|h3, price, side: 1|2, size, x }
 * snapshotted repeatedly over the window. The CURRENT OPEN levels are the
 * rows at max(beginDate) per venue. Older rows = history (a level that later
 * got hit, or moved). Summing everything double-counts — the first version
 * of this script did that.
 *
 * Views the user asked for (24H / 48H / 3D / 7D / 30D):
 *   - 3d/7d/30d fetched directly (upstream ranges).
 *   - 24H/48H derived from the 3d payload by beginDate cutoff.
 *
 * "Magnet" = currently-open estimated cluster near spot, ranked by size,
 * with persistence (how long a level has been sitting there = distinct
 * snapshot count / window). Liquidation figures are Coinglass ESTIMATES.
 */
import crypto from "crypto";
import zlib from "zlib";
import fs from "fs";

const CAPI = "https://capi.coinglass.com";
const STATIC_KEY = Buffer.from("1f68efd73f8d4921acc0dead41dd39bc", "utf8");
const TOTP_SECRET_B32 = "I65VU7K5ZQL7WB4E";
const KEY_A_CONSTS = { "55": "170b070da9654622", "66": "d6537d845a964081", "77": "863f08689c97435b" };

function base32Decode(s) {
  const a = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = 0, value = 0; const out = [];
  for (const ch of s.toUpperCase().replace(/=+$/, "")) {
    const idx = a.indexOf(ch); if (idx === -1) continue;
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

async function cgGet(path) {
  const url = CAPI + path;
  const cacheTs = String(Date.now());
  const res = await fetch(url, {
    headers: {
      obe: makeObeToken(), encryption: "true", "cache-ts-v2": cacheTs,
      "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
      origin: "https://www.coinglass.com", referer: "https://www.coinglass.com/",
    },
    signal: AbortSignal.timeout(20000),
  });
  const raw = Buffer.from(await res.arrayBuffer());
  const timeHeader = res.headers.get("time") ?? undefined;
  const v = res.headers.get("v") ?? "0";
  const userB64 = res.headers.get("user") ?? undefined;
  const j = JSON.parse(raw.toString("utf8"));
  if (j && typeof j.data === "string" && userB64) {
    const mangled = url.slice(url.indexOf("/api"), url.indexOf("?"));
    const src = v === "0" ? cacheTs : v === "2" ? (timeHeader ?? "") : v === "1" ? mangled : (KEY_A_CONSTS[v] ?? "");
    const keyA = Buffer.from(Buffer.from(src, "utf8").toString("base64").slice(0, 16), "utf8");
    const keyB = stripQuotes(tryInflate(aesDec(Buffer.from(userB64, "base64"), keyA)).toString("utf8"));
    const payload = stripQuotes(tryInflate(aesDec(Buffer.from(j.data, "base64"), Buffer.from(keyB, "utf8"))).toString("utf8"));
    return JSON.parse(payload);
  }
  return j;
}

async function spot() {
  // Binance fapi gets this sandbox IP banned under probing load — use the
  // Coinglass aggregated price instead (same source the liq levels use).
  try {
    const j = await cgGet(`/api/futures/peerAgent/latestPrice?symbol=Binance_XAUUSDT&data=${encodeURIComponent(makeObeToken())}`);
    const p = Number(j?.data?.price ?? j?.data);
    if (Number.isFinite(p) && p > 0) return p;
  } catch {}
  try {
    const j = await cgGet(`/api/ticker/price?symbol=Binance_XAUUSDT&data=${encodeURIComponent(makeObeToken())}`);
    const p = Number(j?.data?.price ?? j?.data);
    if (Number.isFinite(p) && p > 0) return p;
  } catch {}
  // last resort: OKX public ticker (no key, plain JSON)
  const r = await fetch("https://www.okx.com/api/v5/market/ticker?instId=XAU-USDT-SWAP", { signal: AbortSignal.timeout(10000) });
  const j = await r.json();
  const p = Number(j?.data?.[0]?.last);
  if (Number.isFinite(p) && p > 0) return p;
  throw new Error("could not fetch XAU spot from any source");
}

const VENUES = [
  { name: "Binance", key: "Binance_XAUUSDT" },
  { name: "OKX", key: "OKX_XAU-USDT-SWAP" },
  { name: "Bybit", key: "Bybit_XAUUSDT" },
  { name: "Bitget", key: "Bitget_XAUUSDT_UMCBL" },
  { name: "Gate", key: "Gate_XAU_USDT" },
];

function parseRows(j) {
  let val = j?.data ?? j;
  if (val && typeof val === "object" && !Array.isArray(val)) val = val.data ?? val;
  if (!Array.isArray(val)) return [];
  return val.map(r => ({
    t: Number(r.beginDate ?? 0), price: Number(r.price), size: Number(r.size ?? 0),
    side: Number(r.side ?? 0), tier: String(r.level2 ?? ""),
  })).filter(r => r.t > 0 && Number.isFinite(r.price) && r.price > 0);
}

/** Current-open levels + persistence for one venue payload. */
function openLevels(rows, cutoffSec) {
  if (!rows.length) return [];
  const rowsIn = cutoffSec ? rows.filter(r => r.t >= cutoffSec) : rows;
  if (!rowsIn.length) return [];
  const maxT = Math.max(...rowsIn.map(r => r.t));
  const open = rowsIn.filter(r => r.t === maxT);
  // persistence: distinct snapshot timestamps with a level within ±0.15% of the open price
  return open.map(o => {
    const near = rowsIn.filter(r => Math.abs(r.price - o.price) / o.price < 0.0015);
    const snaps = new Set(near.map(r => r.t)).size;
    return { ...o, persistenceSnaps: snaps, windowSnaps: new Set(rowsIn.map(r => r.t)).size };
  });
}

/** Aggregate open levels across venues -> clustered rows above/below spot.
 * Upstream `size` is per-unit notional for metals (hundreds for XAU, not
 * millions): USD exposure = size * price. Our production liq-model sums raw
 * size for ranking (unit-consistent within one symbol) — this report also
 * carries the honest USD notional. */
function aggregate(perVenue, spot) {
  const all = Object.entries(perVenue).flatMap(([vn, lv]) => lv.map(l => ({ ...l, venue: vn })));
  const byPrice = new Map();
  for (const l of all) {
    const k = Math.round(l.price * 10) / 10;
    const cur = byPrice.get(k) ?? { size: 0, usd: 0, venues: new Set(), side: l.side, tiers: new Set(), snaps: 0 };
    cur.size += l.size; cur.usd += l.size * l.price; cur.venues.add(l.venue); cur.tiers.add(l.tier); cur.snaps = Math.max(cur.snaps, l.persistenceSnaps);
    byPrice.set(k, cur);
  }
  const keys = [...byPrice.keys()].sort((a, b) => a - b);
  const clusters = [];
  let cur = null;
  for (const k of keys) {
    if (cur && (k - cur.hi) / cur.hi < 0.003) {
      cur.hi = k; cur.size += byPrice.get(k).size; cur.usd += byPrice.get(k).usd; cur.n += 1;
      cur.venues = new Set([...cur.venues, ...byPrice.get(k).venues]);
      cur.snaps = Math.max(cur.snaps, byPrice.get(k).snaps);
    } else {
      if (cur) clusters.push(cur);
      cur = { lo: k, hi: k, size: byPrice.get(k).size, usd: byPrice.get(k).usd, n: 1, venues: byPrice.get(k).venues, snaps: byPrice.get(k).snaps };
    }
  }
  if (cur) clusters.push(cur);
  const maxUsd = Math.max(...clusters.map(c => c.usd), 1);
  return clusters.map(c => {
    const mid = (c.lo + c.hi) / 2;
    return {
      price: +mid.toFixed(1), lo: c.lo, hi: c.hi, size: c.size, usd: c.usd,
      distPct: +(((mid - spot) / spot) * 100).toFixed(2),
      strength: +(100 * c.usd / maxUsd).toFixed(0),
      venues: [...c.venues], persistenceSnaps: c.snaps,
    };
  });
}

const px = await spot();
console.log(`XAU spot: ${px} (Binance XAUUSDT perp)\n`);

// fetch 3d / 7d / 30d raw rows per venue once
const raw = {}; // range -> venue -> rows
for (const range of ["3d", "7d", "30d"]) {
  raw[range] = {};
  for (const v of VENUES) {
    try {
      const j = await cgGet(`/api/liquidationLevels/v2?symbol=${encodeURIComponent(v.key)}&limit=4000&range=${range}&data=${encodeURIComponent(makeObeToken())}`);
      raw[range][v.name] = parseRows(j);
    } catch (e) {
      raw[range][v.name] = [];
      console.log(`  WARN ${range} ${v.name}: ${String(e.message).slice(0, 60)}`);
    }
    await new Promise(r => setTimeout(r, 700));
  }
  const n = Object.values(raw[range]).reduce((s, r) => s + r.length, 0);
  const lastT = Math.max(...Object.values(raw[range]).flatMap(r => r.map(x => x.t)), 0);
  console.log(`fetched ${range}: ${n} rows, newest snapshot ${new Date(lastT * 1000).toISOString()}`);
}

// build views: 24H/48H from the 3d payload; 3D/7D/30D direct
const now = Math.floor(Date.now() / 1000);
const VIEWS = [
  { label: "24H", range: "3d", cutoff: now - 24 * 3600 },
  { label: "48H", range: "3d", cutoff: now - 48 * 3600 },
  { label: "3D", range: "3d", cutoff: null },
  { label: "7D", range: "7d", cutoff: null },
  { label: "30D", range: "30d", cutoff: null },
];

const report = {
  generatedAt: new Date().toISOString(), spot: px,
  note: "Coinglass ESTIMATES via /api/liquidationLevels/v2 (multi-venue: Binance/OKX/Bybit/Bitget/Gate). Current-open levels at the latest snapshot, clustered within 0.3%. persistenceSnaps = snapshot count the cluster has been sitting (window size varies by view). Liquidation figures are estimates, not exchange-published data.",
  views: {},
};

for (const view of VIEWS) {
  const perVenue = {};
  for (const v of VENUES) perVenue[v.name] = openLevels(raw[view.range][v.name], view.cutoff);
  const rows = aggregate(perVenue, px);
  const below = rows.filter(r => r.distPct < 0).sort((a, b) => b.usd - a.usd);
  const above = rows.filter(r => r.distPct >= 0).sort((a, b) => b.usd - a.usd);
  report.views[view.label] = { below, above, totals: { below: below.reduce((s, r) => s + r.usd, 0), above: above.reduce((s, r) => s + r.usd, 0) } };
  console.log(`\n=== XAU ${view.label} — magnets BELOW spot (long-liq clusters / dip magnets) ===`);
  for (const r of below.slice(0, 6)) console.log(`  $${r.price.toFixed(1).padStart(7)} ${r.distPct.toFixed(2).padStart(7)}%  $${(r.usd / 1e6).toFixed(2)}M  str${String(r.strength).padStart(3)}  snaps${String(r.persistenceSnaps).padStart(4)}  [${r.venues.join("+")}]`);
  console.log(`=== XAU ${view.label} — magnets ABOVE spot (short-liq clusters / squeeze magnets) ===`);
  for (const r of above.slice(0, 6)) console.log(`  $${r.price.toFixed(1).padStart(7)} +${r.distPct.toFixed(2).padStart(6)}%  $${(r.usd / 1e6).toFixed(2)}M  str${String(r.strength).padStart(3)}  snaps${String(r.persistenceSnaps).padStart(4)}  [${r.venues.join("+")}]`);
}

fs.writeFileSync("/home/z/my-project/scripts/research/xau-pullback-levels.json", JSON.stringify(report, null, 1));
console.log("\nwrote scripts/research/xau-pullback-levels.json");
