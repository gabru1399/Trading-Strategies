/**
 * Live probe: which liq-levels venues return usable data for BTC?
 * Self-contained: inlines the capi.coinglass.com crypto layer from
 * src/lib/cg/crypto.ts (obe header + response decrypt) so it runs under
 * plain node with no app imports.
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

function aesDec(buf, key16) {
  const d = crypto.createDecipheriv("aes-128-ecb", key16, null);
  d.setAutoPadding(true);
  return Buffer.concat([d.update(buf), d.final()]);
}

function decryptCgResponse(path, resp) {
  const userB64 = resp.headers["user"];
  const v = String(resp.headers["v"] ?? "0");
  const body = JSON.parse(resp.bodyText);
  if (body.code !== "0" && body.code !== 0) return { code: body.code, msg: body.msg, data: null };
  if (typeof body.data === "object" && body.data !== null && !Array.isArray(body.data)) return body;
  const keyA = v === "0" ? Buffer.from(path.slice(0, 16), "utf8") : Buffer.from(KEY_A_CONSTS[v] ?? path.slice(0, 16), "hex");
  const keyBraw = zlib.inflateSync(aesDec(Buffer.from(userB64, "base64"), keyA)).toString("utf8").replace(/"/g, "");
  const keyB = Buffer.from(keyBraw.length === 32 ? keyBraw : keyBraw.padEnd(32, "0"), "utf8").subarray(0, 16);
  const payload = zlib.inflateSync(aesDec(Buffer.from(body.data, "base64"), keyB)).toString("utf8").replace(/"(\w+)":/g, '"$1":');
  return { code: "0", msg: "success", data: JSON.parse(payload) };
}

async function cgGet(path) {
  const res = await fetch(CAPI + path, {
    headers: {
      obe: makeObeToken(),
      encryption: "true",
      "cache-ts-v2": String(Date.now()),
      "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      accept: "application/json, text/plain, */*",
      origin: "https://www.coinglass.com",
      referer: "https://www.coinglass.com/",
    },
  });
  const bodyText = await res.text();
  const headers = {};
  res.headers.forEach((val, k) => { headers[k] = val; });
  return decryptCgResponse(path, { status: res.status, headers, bodyText });
}

function unwrapPayload(value) {
  for (let depth = 0; depth < 3; depth++) {
    if (!value || typeof value !== "object") return null;
    const payload = value;
    if (Array.isArray(payload.prices) && Array.isArray(payload.data)) {
      const valid = payload.prices.length >= 10 && payload.prices.every((row) =>
        Array.isArray(row) && [0, 2, 3, 4].every((i) => Number.isFinite(Number(row[i])) && Number(row[i]) > 0)
        && Number(row[2]) >= Number(row[3])
      );
      return valid ? payload : null;
    }
    value = payload.data;
  }
  return null;
}

const venues = [
  { name: "Binance", key: "Binance_BTCUSDT" },
  { name: "OKX", key: "OKX_BTC-USDT-SWAP" },
  { name: "Bybit", key: "Bybit_BTCUSDT" },
  { name: "Bitget", key: "Bitget_BTCUSDT_UMCBL" },
  { name: "Hyperliquid", key: "Hyperliquid_BTC-USD" },
];

console.log("== BTC liq-levels venue probe " + new Date().toISOString() + " ==");
for (const v of venues) {
  const query = new URLSearchParams({ symbol: v.key, limit: "4000", range: "3d" });
  try {
    const data = await cgGet("/api/liquidationLevels/v2?" + query);
    const payload = unwrapPayload(data);
    if (payload) {
      console.log(`${v.name.padEnd(13)} OK        rows=${payload.data.length} prices=${payload.prices.length}`);
    } else {
      console.log(`${v.name.padEnd(13)} UNUSABLE  code=${data?.code} msg=${String(data?.msg).slice(0, 60)} payloadShape=${JSON.stringify(data?.data)?.slice(0, 80)}`);
    }
  } catch (err) {
    console.log(`${v.name.padEnd(13)} ERROR     ${String(err).slice(0, 140)}`);
  }
}
