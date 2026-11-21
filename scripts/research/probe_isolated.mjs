#!/usr/bin/env node
/** Definitive isolation probe — one request per ~30s, no confounds.
 * Answers:
 *   Q0: which venues list XAU (tickers, no heatmap rate impact)?
 *   Q3: is BTC 7d (30/336) anonymously valid on v2, or 24h-only?
 *   Q5: does the batch `ranges=5:288,30:336` format work?
 *   Q1: does ETH coin-mode work on v1-agg (the endpoint BTC works on)?
 *   Q2: does XAU coin-mode work on v1-agg after full cooldown?
 *   Q6: XAU on v4-agg (model-3 coin endpoint) with range param?
 *   Q7: BTC model-2 (v5) sanity at the end.
 */
import crypto from "crypto";

const FAPI = "https://fapi.coinglass.com";
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
      signal: AbortSignal.timeout(20000),
    });
    const txt = await res.text();
    let j = null; try { j = JSON.parse(txt); } catch {}
    const code = j?.code ?? "?";
    let extra = "";
    const d = j?.data;
    if (Array.isArray(d)) {
      extra = `arr[${d.length}]`;
      if (d.length && typeof d[0] === "object" && d[0]) extra += ` first-keys=${Object.keys(d[0]).slice(0, 6).join(",")}`;
    } else if (d && typeof d === "object") {
      extra = `keys=${Object.keys(d).slice(0, 8).join(",")}`;
      if (Array.isArray(d.liq)) extra += ` liq[${d.liq.length}]`;
    }
    console.log(`${String(code).padEnd(6)} ${label.padEnd(56)} ${extra.slice(0, 130)}`);
    return j;
  } catch (e) {
    console.log(`ERR    ${label.padEnd(56)} ${String(e.message).slice(0, 60)}`);
    return null;
  }
}
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const D = () => ({ data: makeObeToken() });

// Q0: venues listing XAU — try several exName values + unfiltered
console.log("=== Q0: XAU venue discovery (tickers) ===");
const j0 = await plain(FAPI, "/api/futures/select/coins/tickers", { type: "Futures", keyword: "XAU", ...D() }, "tickers all-venues XAU");
if (Array.isArray(j0?.data)) for (const t of j0.data.slice(0, 6)) console.log("   ", JSON.stringify(t).slice(0, 200));
await sleep(2000);
for (const ex of ["Hyperliquid", "Gate", "Bitget", "MEXC"]) {
  const j = await plain(FAPI, "/api/futures/select/coins/tickers", { type: "Futures", exName: ex, keyword: "XAU", ...D() }, `tickers ${ex} XAU`);
  if (Array.isArray(j?.data)) for (const t of j.data.slice(0, 3)) console.log("   ", JSON.stringify({ symbol: t.symbol, instrumentId: t.instrumentId, price: t.price, ex: t.exchangeName }).slice(0, 160));
  await sleep(2000);
}

console.log("\n=== Q3: BTC 7d single window on v2 (after 30s cooldown) ===");
await sleep(30_000);
await plain(FAPI, "/api/index/v2/liqHeatMap", { merge: true, symbol: "Binance_BTCUSDT", interval: 30, limit: 336, ...D() }, "v2 BTC pair 7d (30/336)");

console.log("\n=== Q5: batch ranges format ===");
await sleep(30_000);
await plain(FAPI, "/api/index/v2/liqHeatMap", { merge: true, symbol: "Binance_BTCUSDT", ranges: "5:288,30:336", ...D() }, "v2 BTC pair batch 24h+7d");

console.log("\n=== Q1: ETH coin-mode on v1-agg ===");
await sleep(30_000);
await plain(FAPI, "/api/index/aggregate/liqHeatMap", { merge: true, symbol: "ETH", interval: 5, limit: 288, ...D() }, "v1-agg ETH coin (5/288)");

console.log("\n=== Q2: XAU coin-mode on v1-agg ===");
await sleep(30_000);
await plain(FAPI, "/api/index/aggregate/liqHeatMap", { merge: true, symbol: "XAU", interval: 5, limit: 288, ...D() }, "v1-agg XAU coin (5/288)");

console.log("\n=== Q6: XAU on v4-agg (model-3 coin) ===");
await sleep(30_000);
await plain(FAPI, "/api/index/v4/aggregate/liqHeatMap", { merge: true, symbol: "XAU", range: "24h", cp: false, ...D() }, "v4-agg XAU coin range=24h");

console.log("\n=== Q7: BTC v5 sanity (model 2) ===");
await sleep(30_000);
await plain(FAPI, "/api/index/v5/liqHeatMap", { merge: true, symbol: "Binance_BTCUSDT", interval: 5, limit: 288, ...D() }, "v5 BTC pair (5/288)");
