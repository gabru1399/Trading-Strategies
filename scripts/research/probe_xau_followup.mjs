#!/usr/bin/env node
/** Focused XAU follow-up probe:
 * 1. How does Coinglass represent XAU? (/api/futures/select/coins/tickers)
 * 2. Do /api/index/5/liqMap or /api/index/2/exLiqMap serve XAU?
 * 3. Model-2 single-fetch with interval/limit (per the chunk's real assembly).
 * 4. ETH/SOL coin-mode sanity (is the 40000 XAU-specific or non-BTC-wide?).
 * 5. XAU retry after a long cooldown.
 */
import crypto from "crypto";

const FAPI = "https://fapi.coinglass.com";
const CAPI = "https://capi.coinglass.com";
const STATIC_KEY = Buffer.from("1f68efd73f8d4921acc0dead41dd39bc", "utf8");
const TOTP_SECRET_B32 = "I65VU7K5ZQL7WB4E";

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
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36";

async function plain(base, path, params, label) {
  const url = new URL(path, base);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, String(v));
  try {
    const res = await fetch(url, {
      headers: { "user-agent": UA, accept: "*/*", origin: "https://www.coinglass.com", referer: "https://www.coinglass.com/" },
      signal: AbortSignal.timeout(15000),
    });
    const txt = await res.text();
    let j = null; try { j = JSON.parse(txt); } catch {}
    const code = j?.code ?? "?";
    let extra = "";
    if (j?.data) {
      const d = j.data;
      if (Array.isArray(d)) extra = `arr[${d.length}]`;
      else if (typeof d === "object") extra = `keys=${Object.keys(d).slice(0, 8).join(",")}`;
      else extra = String(d).slice(0, 50);
    }
    console.log(`${String(code).padEnd(7)} ${label.padEnd(52)} ${extra}`);
    return j;
  } catch (e) {
    console.log(`ERR     ${label.padEnd(52)} ${String(e.message).slice(0, 60)}`);
    return null;
  }
}
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const D = () => ({ data: makeObeToken() });

// 1. tickers: how is XAU represented per exchange?
console.log("=== 1. XAU symbol representation ===");
for (const ex of ["Binance", "OKX", "Bybit"]) {
  const j = await plain(CAPI, "/api/futures/select/coins/tickers", { type: "Futures", exName: ex, keyword: "XAU", ...D() }, `tickers Futures ${ex} XAU`);
  const arr = j?.data;
  if (Array.isArray(arr)) for (const t of arr.slice(0, 4)) console.log("   ", JSON.stringify({ sym: t.symbol ?? t.instrumentId, name: t.baseAsset ?? t.name, price: t.price }).slice(0, 140));
  await sleep(900);
}

// 2. extra family endpoints for XAU
console.log("\n=== 2. other family endpoints (XAU + BTC control) ===");
await plain(FAPI, "/api/index/5/liqMap", { symbol: "XAU", ...D() }, "liqMap XAU coin");
await sleep(900);
await plain(FAPI, "/api/index/5/liqMap", { symbol: "Binance_BTCUSDT", ...D() }, "liqMap BTC pair");
await sleep(900);
await plain(FAPI, "/api/index/2/exLiqMap", { symbol: "XAU", ...D() }, "exLiqMap XAU");
await sleep(900);
await plain(FAPI, "/api/index/2/exLiqMap", { symbol: "Binance_BTCUSDT", ...D() }, "exLiqMap BTC");

// 3. model-2 fixed params (interval/limit per g-map) on BTC
console.log("\n=== 3. model 2 (v5/v3-agg) with interval/limit ===");
await sleep(60_000); // long cooldown first
await plain(FAPI, "/api/index/v5/liqHeatMap", { merge: true, symbol: "Binance_BTCUSDT", interval: 5, limit: 288, ...D() }, "v5 BTC pair 24h (5/288)");
await sleep(1500);
await plain(FAPI, "/api/index/v5/liqHeatMap", { merge: true, symbol: "Binance_BTCUSDT", interval: 30, limit: 336, ...D() }, "v5 BTC pair 7d (30/336)");
await sleep(1500);
await plain(FAPI, "/api/index/v5/liqHeatMap", { merge: true, symbol: "Binance_BTCUSDT", interval: "h2", limit: 372, ...D() }, "v5 BTC pair 30d (h2/372)");
await sleep(1500);
await plain(FAPI, "/api/index/v5/liqHeatMap", { merge: true, symbol: "Binance_BTCUSDT", range: "24h", ...D() }, "v5 BTC pair range=24h");
await sleep(1500);

// 4. ETH/SOL coin-mode sanity on the aggregate endpoints
console.log("\n=== 4. non-BTC coin-mode sanity (24h) ===");
for (const sym of ["ETH", "SOL", "XAU", "XAG"]) {
  await plain(FAPI, "/api/index/v3/aggregate/liqHeatMap", { merge: true, symbol: sym, interval: 5, limit: 288, ...D() }, `v3-agg ${sym} coin (5/288)`);
  await sleep(1500);
}

// 5. XAU retry on v6 (model 3) with range
console.log("\n=== 5. XAU v6 retry after cooldown ===");
for (const range of ["24h", "72h", "30d"]) {
  await plain(FAPI, "/api/index/v6/liqHeatMap", { merge: true, symbol: "XAU", range, cp: false, ...D() }, `v6 XAU coin range=${range}`);
  await sleep(1500);
}
await plain(FAPI, "/api/index/v6/liqHeatMap", { merge: true, symbol: "Binance_XAUUSDT", range: "24h", cp: false, ...D() }, "v6 XAU pair range=24h");
