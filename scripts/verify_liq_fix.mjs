/**
 * Verification: simulate the FIXED liqlevels route loadSnapshot for BTC 3d
 * using the real fetchLiqVenuePayload ladder from liq-model.ts, against the
 * live capi.coinglass.com API. Expect: 5/5 venues, Hyperliquid via 7d
 * fallback, partial=false.
 */
import crypto from "crypto";
import zlib from "zlib";

const CAPI = "https://capi.coinglass.com";
const STATIC_KEY = Buffer.from("1f68efd73f8d4921acc0dead41dd39bc", "utf8");
const TOTP_SECRET_B32 = "I65VU7K5ZQL7WB4E";
const KEY_A_CONSTS = { "55": "170b070da9654622", "66": "d6537d845a964081", "77": "863f08689c97435b" };

function base32Decode(s) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = 0, value = 0;
  const out = [];
  for (const ch of s.toUpperCase().replace(/=+$/, "")) {
    const idx = alphabet.indexOf(ch);
    if (idx === -1) continue;
    value = (value << 5) | idx;
    bits += 5;
    if (bits >= 8) { out.push((value >>> (bits - 8)) & 0xff); bits -= 8; }
  }
  return Buffer.from(out);
}
function totp(secretB32, t) {
  const key = base32Decode(secretB32);
  const counter = Buffer.alloc(8);
  counter.writeUInt32BE(Math.floor(t / 30), 4);
  const digest = crypto.createHmac("sha1", key).update(counter).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  return String((digest.readUInt32BE(offset) & 0x7fffffff) % 1000000).padStart(6, "0");
}
function makeObeToken(nowMs) {
  const secs = Math.floor((nowMs ?? Date.now()) / 1000);
  const plain = Buffer.from(`${secs},${totp(TOTP_SECRET_B32, secs)}`, "utf8");
  const cipher = crypto.createCipheriv("aes-256-ecb", STATIC_KEY, null);
  return Buffer.concat([cipher.update(plain), cipher.final()]).toString("base64");
}
function aesDec(buf, key) {
  const algo = key.length === 16 ? "aes-128-ecb" : key.length === 24 ? "aes-192-ecb" : "aes-256-ecb";
  const d = crypto.createDecipheriv(algo, key, null);
  d.setAutoPadding(true);
  return Buffer.concat([d.update(buf), d.final()]);
}
function tryInflate(buf) {
  for (const fn of [zlib.inflateSync, zlib.inflateRawSync, zlib.gunzipSync]) {
    try { return fn(buf); } catch { /* next */ }
  }
  return buf;
}
function stripQuotes(s) {
  let out = s;
  if (out.startsWith('"')) out = out.slice(1);
  if (out.endsWith('"')) out = out.slice(0, -1);
  return out;
}
function mangleUrl(url) {
  const idx = url.indexOf("/api");
  if (idx === -1) return url;
  const q = url.indexOf("?");
  return q === -1 ? url.slice(idx) : url.slice(idx, q);
}
function deriveKeyA(v, cacheTs, timeHeader, url) {
  let src;
  if (v === "0") src = cacheTs;
  else if (v === "2") src = timeHeader ?? "";
  else if (v === "1") src = mangleUrl(url);
  else src = KEY_A_CONSTS[v] ?? "";
  return Buffer.from(Buffer.from(src, "utf8").toString("base64").slice(0, 16), "utf8");
}
async function cgGet(path) {
  const cacheTs = String(Date.now());
  const res = await fetch(CAPI + path, {
    headers: {
      obe: makeObeToken(), encryption: "true", "cache-ts-v2": cacheTs,
      "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      accept: "application/json, text/plain, */*", origin: "https://www.coinglass.com", referer: "https://www.coinglass.com/",
    },
  });
  const bodyText = await res.text();
  const headers = {};
  res.headers.forEach((val, k) => { headers[k] = val; });
  const body = JSON.parse(bodyText);
  if (body.code !== "0" && body.code !== 0) {
    throw new Error(`upstream code ${body.code}: ${body.msg ?? "unknown"}`);
  }
  if (typeof body.data !== "string") return body.data;
  const userBlob = headers["user"] ?? "";
  const v = String(headers["v"] ?? "0");
  const keyA = deriveKeyA(v, cacheTs, headers["time"] ?? null, path);
  const keyBRaw = stripQuotes(tryInflate(aesDec(Buffer.from(userBlob, "base64"), keyA)).toString("utf8"));
  const payloadRaw = stripQuotes(tryInflate(aesDec(Buffer.from(body.data, "base64"), Buffer.from(keyBRaw, "utf8"))).toString("utf8"));
  return JSON.parse(payloadRaw);
}

// === port of the NEW fetchLiqVenuePayload (liq-model.ts) ===
function isUsableLiqPayload(val) {
  if (!val || typeof val !== "object") return false;
  const p = val;
  if (!Array.isArray(p.prices) || !Array.isArray(p.data)) return false;
  return p.prices.length >= 10 && p.prices.every((row) =>
    Array.isArray(row) && [0, 2, 3, 4].every((i) => Number.isFinite(Number(row[i])) && Number(row[i]) > 0)
    && Number(row[2]) >= Number(row[3])
  );
}
function unwrapLiqPayload(val) {
  for (let depth = 0; depth < 3; depth++) {
    if (isUsableLiqPayload(val)) return val;
    if (!val || typeof val !== "object") return null;
    val = val.data;
  }
  return null;
}
const LIQ_RANGE_ORDER = ["3d", "7d", "30d"];
async function fetchLiqVenuePayload(cgGetFn, venueKey, range, limit) {
  const ladder = [range, ...LIQ_RANGE_ORDER.filter((r) => r !== range)];
  let lastNoData = false;
  for (const r of ladder) {
    const query = new URLSearchParams({ symbol: venueKey, limit: String(limit), range: r });
    let val;
    try {
      val = await cgGetFn("/api/liquidationLevels/v2?" + query, 30_000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (/\b(40001|405)\b/.test(msg)) { lastNoData = true; continue; }
      throw err;
    }
    const payload = unwrapLiqPayload(val);
    if (payload) return { payload, rangeUsed: r };
    lastNoData = true;
  }
  throw new Error(lastNoData
    ? `no usable liquidation snapshot for ${venueKey} in ranges ${ladder.join(",")}`
    : `liquidation fetch failed for ${venueKey}`);
}

// === run the fixed loadSnapshot venue loop for BTC 3d ===
const venues = [
  { name: "Binance", key: "Binance_BTCUSDT" },
  { name: "OKX", key: "OKX_BTC-USDT-SWAP" },
  { name: "Bybit", key: "Bybit_BTCUSDT" },
  { name: "Bitget", key: "Bitget_BTCUSDT_UMCBL" },
  { name: "Hyperliquid", key: "Hyperliquid_BTC-USD" },
];
console.log("== FIXED route simulation · BTC · range=3d · " + new Date().toISOString());
const results = await Promise.allSettled(venues.map(async (venue, i) => {
  if (i > 0) await new Promise((r) => setTimeout(r, i * 50));
  const { payload, rangeUsed } = await fetchLiqVenuePayload(cgGet, venue.key, "3d", 4000);
  return { name: venue.name, rows: payload.data.length, rangeUsed };
}));
let ok = 0;
const rangeFallback = {};
for (const r of results) {
  if (r.status === "fulfilled") {
    ok++;
    const flag = r.value.rangeUsed === "3d" ? "" : `  ← LADDER RECOVERY (served ${r.value.rangeUsed})`;
    if (r.value.rangeUsed !== "3d") rangeFallback[r.value.name] = r.value.rangeUsed;
    console.log(`${r.value.name.padEnd(13)} OK    rows=${r.value.rows}  range=${r.value.rangeUsed}${flag}`);
  } else {
    console.log(`ERROR          ${String(r.reason).slice(0, 100)}`);
  }
}
console.log(`\nRESULT: ${ok}/${venues.length} venues · partial=${ok < venues.length}` +
  (Object.keys(rangeFallback).length ? ` · rangeFallback=${JSON.stringify(rangeFallback)}` : ""));
console.log(ok === venues.length
  ? "✅ PASS — aggregate is complete; UI would show 'live' with an honest 7D-fallback note instead of 'partial coverage'"
  : "⚠ partial remains — check the ERROR lines above");
