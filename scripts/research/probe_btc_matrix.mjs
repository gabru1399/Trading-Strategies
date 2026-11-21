#!/usr/bin/env node
/** BTC v2 liqHeatMap (interval, limit) matrix probe — find the valid
 * combinations the page's 24H/48H/3D/7D/30D selectors map to. */
import crypto from "crypto";
import zlib from "zlib";

const CAPI = "https://capi.coinglass.com";
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

async function probe(interval, limit) {
  const q = new URLSearchParams({
    merge: "true", symbol: "Binance_BTCUSDT",
    interval: String(interval), limit: String(limit), data: makeObeToken(),
  });
  const url = `${CAPI}/api/index/v2/liqHeatMap?${q}`;
  const cacheTs = String(Date.now());
  const res = await fetch(url, {
    headers: {
      obe: makeObeToken(), encryption: "true", "cache-ts-v2": cacheTs,
      "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
      origin: "https://www.coinglass.com", referer: "https://www.coinglass.com/",
    },
    signal: AbortSignal.timeout(15000),
  });
  const raw = Buffer.from(await res.arrayBuffer());
  const timeHeader = res.headers.get("time") ?? undefined;
  const v = res.headers.get("v") ?? "0";
  const userB64 = res.headers.get("user") ?? undefined;
  let parsed = null;
  try {
    const j = JSON.parse(raw.toString("utf8"));
    if (j && typeof j.data === "string" && userB64) {
      const keyA = deriveKeyA(v, cacheTs, timeHeader, url);
      const keyB = stripQuotes(tryInflate(aesDec(Buffer.from(userB64, "base64"), keyA)).toString("utf8"));
      const payload = stripQuotes(tryInflate(aesDec(Buffer.from(j.data, "base64"), Buffer.from(keyB, "utf8"))).toString("utf8"));
      parsed = JSON.parse(payload);
    } else parsed = j;
  } catch {}
  const code = parsed?.code ?? "0";
  const data = parsed?.data;
  let span = "";
  if (data?.liq?.length) {
    const ts = data.liq.map(r => r.t).filter(Boolean);
    if (ts.length >= 2) {
      const mins = (ts[ts.length - 1] - ts[0]) / 60000 + interval;
      span = `window≈${(mins / 60).toFixed(1)}h bars=${ts.length}`;
    }
  }
  console.log(`interval=${String(interval).padStart(5)} limit=${String(limit).padStart(4)} -> code=${String(code).padEnd(6)} ${span}`);
  return code === "0" || code === 0;
}

// matrix: intervals the endpoint might accept × window-appropriate limits
const combos = [
  [5, 288], [5, 576], [5, 864], [5, 2016],
  [10, 288], [15, 288], [15, 192],
  [30, 96], [30, 144], [30, 288], [30, 336], [30, 672],
  [60, 72], [60, 168], [60, 288], [60, 720],
  [120, 144], [240, 72], [240, 180], [360, 120], [720, 60], [1440, 30], [1440, 60],
];
for (const [i, l] of combos) {
  try { await probe(i, l); } catch (e) { console.log(`interval=${i} limit=${l} -> ERR ${e.message}`); }
  await new Promise(r => setTimeout(r, 350));
}
