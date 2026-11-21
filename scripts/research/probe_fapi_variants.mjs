#!/usr/bin/env node
/** fapi access variations — find what makes the browser's fapi liqHeatMap
 * call work (page uses fapi for ALL liqHeatMap calls; we get 50001). */
import crypto from "crypto";
import zlib from "zlib";

const STATIC_KEY = Buffer.from("1f68efd73f8d4921acc0dead41dd39bc", "utf8");
const TOTP_SECRET_B32 = "I65VU7K5ZQL7WB4E";

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

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

async function attempt(label, url, headers) {
  try {
    const res = await fetch(url, { headers, signal: AbortSignal.timeout(15000) });
    const text = (await res.text()).slice(0, 150);
    let code = "?";
    try { code = JSON.parse(text)?.code ?? "(no-code)"; } catch {}
    console.log(`${String(res.status).padEnd(4)} code=${String(code).padEnd(8)} ${label}`);
  } catch (e) {
    console.log(`ERR  ${String(e.cause?.code ?? e.message).slice(0, 50).padEnd(8)} ${label}`);
  }
  await new Promise(r => setTimeout(r, 400));
}

const token = makeObeToken();
const base = "https://fapi.coinglass.com/api/index/v2/liqHeatMap";
const q = (extra = "") => `?merge=true&symbol=Binance_BTCUSDT&interval=5&limit=288&data=${encodeURIComponent(token)}${extra}`;

// 1. our current shape
await attempt("fapi v2 as-is", base + q(), {
  obe: token, encryption: "true", "cache-ts-v2": String(Date.now()),
  "user-agent": UA, origin: "https://www.coinglass.com", referer: "https://www.coinglass.com/",
});
// 2. minimal browser-like (no encryption/cache headers)
await attempt("fapi v2 minimal", base + q(), {
  "user-agent": UA, accept: "*/*", origin: "https://www.coinglass.com", referer: "https://www.coinglass.com/LiquidationHeatMap",
});
// 3. token ONLY as data param, no obe header
await attempt("fapi v2 data-only", base + q(), {
  "user-agent": UA, accept: "application/json, text/plain, */*", referer: "https://www.coinglass.com/",
});
// 4. with sec-fetch / sec-ch headers (full browser fingerprint)
await attempt("fapi v2 full-browser-headers", base + q(), {
  "user-agent": UA, accept: "*/*", "accept-language": "en-US,en;q=0.9",
  "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
  "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
  "sec-fetch-dest": "empty", "sec-fetch-mode": "cors", "sec-fetch-site": "same-site",
  origin: "https://www.coinglass.com", referer: "https://www.coinglass.com/",
});
// 5. encrypted=1 / encryption header variants
await attempt("fapi v2 encrypted=1 param", base + q("&encrypted=1"), {
  obe: token, encryption: "1", "cache-ts-v2": String(Date.now()), "user-agent": UA,
  origin: "https://www.coinglass.com", referer: "https://www.coinglass.com/",
});
// 6. also try www.coinglass.com as a same-origin proxy path
await attempt("www host same path", "https://www.coinglass.com/api/index/v2/liqHeatMap" + q(), {
  obe: token, encryption: "true", "cache-ts-v2": String(Date.now()), "user-agent": UA,
  origin: "https://www.coinglass.com", referer: "https://www.coinglass.com/",
});
// 7. capi v5 BTC (known-good sanity)
await attempt("capi v5 sanity", "https://capi.coinglass.com/api/index/v5/liqHeatMap" + q(), {
  obe: token, encryption: "true", "cache-ts-v2": String(Date.now()), "user-agent": UA,
  origin: "https://www.coinglass.com", referer: "https://www.coinglass.com/",
});
// 8. capi v6 / v4-agg (do they exist on capi?)
await attempt("capi v6", "https://capi.coinglass.com/api/index/v6/liqHeatMap" + q("&cp=false&range=24h"), {
  obe: token, encryption: "true", "cache-ts-v2": String(Date.now()), "user-agent": UA,
  origin: "https://www.coinglass.com", referer: "https://www.coinglass.com/",
});
await attempt("capi v4 aggregate", "https://capi.coinglass.com/api/index/v4/aggregate/liqHeatMap" + q().replace("symbol=Binance_BTCUSDT", "symbol=BTC"), {
  obe: token, encryption: "true", "cache-ts-v2": String(Date.now()), "user-agent": UA,
  origin: "https://www.coinglass.com", referer: "https://www.coinglass.com/",
});
