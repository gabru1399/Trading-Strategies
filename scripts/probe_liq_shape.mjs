/**
 * Probe 3: inspect the raw level field shape of /api/liquidationLevels/v2
 * (does each level carry x/endX bar indices, beginDate/endDate epochs, or
 * both?) — needed to map 7d-fallback levels onto a 3d lead timeline safely.
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
  if (body.code !== "0" && body.code !== 0) return { code: String(body.code), msg: body.msg, data: null };
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

// unwrap { prices, data } at depth 0-3 (same as the route)
function unwrapPayload(value) {
  for (let depth = 0; depth < 3; depth++) {
    if (!value || typeof value !== "object") return null;
    const payload = value;
    if (Array.isArray(payload.prices) && Array.isArray(payload.data)) return payload;
    value = payload.data;
  }
  return null;
}

for (const [label, key, range] of [
  ["Binance BTC 3d", "Binance_BTCUSDT", "3d"],
  ["HL BTC 7d", "Hyperliquid_BTC-USD", "7d"],
]) {
  const q = new URLSearchParams({ symbol: key, limit: "500", range });
  const r = await cgGet("/api/liquidationLevels/v2?" + q);
  const p = unwrapPayload(r.data);
  if (!p) { console.log(`${label}: no payload code=${r.code} msg=${r.msg}`); continue; }
  console.log(`== ${label}: prices=${p.prices.length} bars, data=${p.data.length} levels`);
  console.log(`   prices[0]=${JSON.stringify(p.prices[0])}  prices[-1]=${JSON.stringify(p.prices[p.prices.length - 1])}`);
  for (const lv of p.data.slice(0, 3)) {
    console.log(`   level keys: ${Object.keys(lv).join(",")}`);
    console.log(`   sample: ${JSON.stringify(lv).slice(0, 200)}`);
  }
}
