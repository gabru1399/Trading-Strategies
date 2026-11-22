#!/usr/bin/env node
/**
 * probe_anon_surface.mjs — map which symbols serve Model 1 anonymously.
 * Pair mode (v2) + coin mode (aggregate), 24h window, one hit per cell,
 * 1.8 s spacing. BTC control first/last.
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
const H = {
  "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  accept: "*/*", "accept-language": "en-US,en;q=0.9",
  origin: "https://www.coinglass.com", referer: "https://www.coinglass.com/",
};
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function hit(label, path, params) {
  const url = new URL(path, FAPI);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, String(v));
  url.searchParams.set("data", makeObeToken());
  try {
    const res = await fetch(url, { headers: H, signal: AbortSignal.timeout(20000) });
    const j = await res.json().catch(() => null);
    const code = j?.code ?? "?";
    const d = j?.data;
    let extra = "";
    if (d && typeof d === "object" && Array.isArray(d.liq)) extra = `liq[${d.liq.length}]`;
    console.log(`${String(code).padEnd(7)} ${label.padEnd(34)} ${extra}`);
    return String(code);
  } catch (e) {
    console.log(`ERR     ${label.padEnd(34)} ${String(e.message).slice(0, 40)}`);
    return "ERR";
  }
}

const syms = ["BTC", "ETH", "SOL", "XRP", "DOGE", "XAU", "XAG", "NVDA", "CL"];
const out = {};
for (const s of syms) {
  const pair = await hit(`${s} pair m1 24h`, "/api/index/v2/liqHeatMap", { merge: true, symbol: `Binance_${s}USDT`, interval: 5, limit: 288 });
  await sleep(1800);
  const coin = await hit(`${s} coin m1 24h`, "/api/index/aggregate/liqHeatMap", { merge: true, symbol: s, interval: 5, limit: 288 });
  out[s] = { pair, coin };
  await sleep(1800);
}
console.log("\n=== summary (code 0 = serves anonymously):");
for (const [s, v] of Object.entries(out)) console.log(`  ${s.padEnd(6)} pair:${v.pair.padEnd(6)} coin:${v.coin}`);
