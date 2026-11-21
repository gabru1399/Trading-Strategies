/**
 * Probe 2: is the Hyperliquid 40001 blanket across syms and ranges?
 * Also test the fingerprint/orderflow endpoint with HL to see whether HL
 * data is alive elsewhere (i.e., liq-levels-specific vs venue-wide).
 */
import crypto from "crypto";
import zlib from "zlib";

const CAPI = "https://capi.coinglass.com";
const STATIC_KEY = Buffer.from("1f68efd73f8d4921acc0dead41dd39bc", "utf8");
const TOTP_SECRET_B32 = process.env.CG_TOTP_SECRET_B32 || ""; // redacted — set env var (was hardcoded in sandbox copy)
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
      obe: makeObeToken(),
      encryption: "true",
      "cache-ts-v2": cacheTs,
      "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      accept: "application/json, text/plain, */*",
      origin: "https://www.coinglass.com",
      referer: "https://www.coinglass.com/",
    },
  });
  const bodyText = await res.text();
  const headers = {};
  res.headers.forEach((val, k) => { headers[k] = val; });
  const body = JSON.parse(bodyText);
  if (body.code !== "0" && body.code !== 0) {
    return { code: String(body.code), msg: body.msg, data: null };
  }
  if (typeof body.data !== "string") return { code: "0", msg: "ok", data: body.data };
  try {
    const userBlob = headers["user"] ?? "";
    const v = String(headers["v"] ?? "0");
    const keyA = deriveKeyA(v, cacheTs, headers["time"] ?? null, path);
    const keyBRaw = stripQuotes(tryInflate(aesDec(Buffer.from(userBlob, "base64"), keyA)).toString("utf8"));
    const payloadRaw = stripQuotes(tryInflate(aesDec(Buffer.from(body.data, "base64"), Buffer.from(keyBRaw, "utf8"))).toString("utf8"));
    return { code: "0", msg: "ok", data: JSON.parse(payloadRaw) };
  } catch (err) {
    return { code: "decrypt-error", msg: String(err), data: null };
  }
}

console.log("== HL blanket probe " + new Date().toISOString() + " ==");

// 1) liq-levels HL across syms + ranges
const hlTests = [
  ["BTC", "Hyperliquid_BTC-USD", "3d"],
  ["BTC", "Hyperliquid_BTC-USD", "7d"],
  ["ETH", "Hyperliquid_ETH-USD", "3d"],
  ["SOL", "Hyperliquid_SOL-USD", "3d"],
];
for (const [sym, key, range] of hlTests) {
  const q = new URLSearchParams({ symbol: key, limit: "1000", range });
  const r = await cgGet("/api/liquidationLevels/v2?" + q);
  const dataRows = Array.isArray(r.data?.data) ? r.data.data.length : null;
  console.log(`liq ${sym.padEnd(4)} ${range}  code=${r.code}  msg=${String(r.msg).slice(0, 55)}  rows=${dataRows}`);
}

// 2) control: Binance still fine on same endpoint?
{
  const q = new URLSearchParams({ symbol: "Binance_BTCUSDT", limit: "1000", range: "3d" });
  const r = await cgGet("/api/liquidationLevels/v2?" + q);
  const dataRows = Array.isArray(r.data?.data) ? r.data.data.length : null;
  console.log(`liq BTC  3d  [Binance control]  code=${r.code}  rows=${dataRows}`);
}

// 3) HL on orderflow/fingerprint endpoint (is the venue alive elsewhere?)
{
  const q = new URLSearchParams({ symbol: "Hyperliquid_BTC-USD", interval: "1h" });
  const r = await cgGet("/api/orderflow/v2/aggregated?" + new URLSearchParams({ symbol: "BTC", interval: "15m" }));
  console.log(`orderflow agg BTC (all venues)  code=${r.code}  venues=${r.data?.data ? "present" : JSON.stringify(r.data)?.slice(0, 60)}`);
}
