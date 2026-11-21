#!/usr/bin/env node
/**
 * XAU liquidation-heatmap upstream probe (user request 2026-11-21):
 * explore coinglass.com/LiquidationHeatMap/XAU?model=2 at models 1/2/3 and
 * timeframes 24H/48H/3D/7D/30D.
 *
 * The Coinglass frontend (mined from scripts/cg-js/__app bundle) exposes a
 * family of liqHeatMap endpoints:
 *   /api/index/v2/liqHeatMap                 (capi — the one our stopmap uses, model 1)
 *   /api/index/v5/liqHeatMap                 (capi — candidate model 2)
 *   https://fapi.coinglass.com/api/index/v6/liqHeatMap        (candidate model 3)
 *   https://fapi.coinglass.com/api/index/v4/aggregate/liqHeatMap (aggregate)
 *   /api/index/aggregate/liqHeatMap + /api/index/v3/aggregate/liqHeatMap
 *
 * This probe answers, with live calls: which endpoint/params serve XAU
 * anonymously, and what timeframe (interval x limit) each selector maps to.
 * BTC is probed as control. Output: scripts/research/probe-xau-heatmap.json
 */
import crypto from "crypto";
import zlib from "zlib";
import fs from "fs";

const CAPI = "https://capi.coinglass.com";
const FAPI = "https://fapi.coinglass.com";
const STATIC_KEY = Buffer.from("1f68efd73f8d4921acc0dead41dd39bc", "utf8");
const TOTP_SECRET_B32 = process.env.CG_TOTP_SECRET_B32 || "I65VU7K5ZQL7WB4E"; // sandbox-local value; redacted upstream
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
function totp(secretB32, t) {
  const key = base32Decode(secretB32);
  const counter = Buffer.alloc(8); counter.writeUInt32BE(Math.floor(t / 30), 4);
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
  const d = crypto.createDecipheriv(algo, key, null); d.setAutoPadding(true);
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

/** One authenticated GET. Returns { status, code, msg, shape } where shape is
 * a compact structural digest (never the full payload). */
async function cgGet(base, path, params) {
  const url = new URL(path, base);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, String(v));
  const cacheTs = String(Date.now());
  let res, raw;
  try {
    res = await fetch(url, {
      headers: {
        obe: makeObeToken(),
        encryption: "true",
        "cache-ts-v2": cacheTs,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        accept: "*/*",
        "accept-language": "en-US,en;q=0.9",
        origin: "https://www.coinglass.com",
        referer: "https://www.coinglass.com/",
      },
      signal: AbortSignal.timeout(15000),
    });
    raw = Buffer.from(await res.arrayBuffer());
  } catch (e) {
    return { status: 0, code: "net", msg: String(e).slice(0, 120), shape: null };
  }
  const timeHeader = res.headers.get("time") ?? undefined;
  const v = res.headers.get("v") ?? "0";
  const userB64 = res.headers.get("user") ?? undefined;
  let bodyText = raw.toString("utf8");
  let parsed = null;
  try {
    const j = JSON.parse(bodyText);
    if (j && typeof j.data === "string" && userB64) {
      const keyA = deriveKeyA(v, cacheTs, timeHeader, url.toString());
      const keyB = stripQuotes(tryInflate(aesDec(Buffer.from(userB64, "base64"), keyA)).toString("utf8"));
      const payload = stripQuotes(tryInflate(aesDec(Buffer.from(j.data, "base64"), Buffer.from(keyB, "utf8"))).toString("utf8"));
      parsed = JSON.parse(payload);
    } else {
      parsed = j;
    }
  } catch { parsed = null; }
  const code = parsed?.code ?? parsed?.success ?? "?";
  const msg = parsed?.msg ?? parsed?.message ?? "";
  const shape = digest(parsed?.data ?? parsed);
  return { status: res.status, code: String(code), msg: String(msg).slice(0, 140), shape };
}

/** Compact structural digest of the response data. */
function digest(d) {
  if (d == null) return null;
  if (Array.isArray(d)) {
    return { t: "array", n: d.length, first: digest(d[0]) };
  }
  if (typeof d === "object") {
    const keys = Object.keys(d);
    const o = { t: "object", keys: keys.slice(0, 14) };
    for (const k of keys.slice(0, 4)) {
      const v = d[k];
      if (Array.isArray(v)) o[k] = `arr[${v.length}]` + (v.length && typeof v[0] === "object" ? `{${Object.keys(v[0]).slice(0, 6).join(",")}}` : "");
      else if (typeof v === "number" || typeof v === "string") o[k] = String(v).slice(0, 40);
      else if (v && typeof v === "object") o[k] = `{${Object.keys(v).slice(0, 8).join(",")}}`;
    }
    return o;
  }
  return { t: typeof d, v: String(d).slice(0, 60) };
}

// ---------- probe matrix ----------
const TFS = [
  { tf: "24H", interval: 5, limit: 288 },
  { tf: "48H", interval: 5, limit: 576 },
  { tf: "3D",  interval: 15, limit: 288 },
  { tf: "7D",  interval: 30, limit: 336 },
  { tf: "30D", interval: 1440, limit: 30 },
  { tf: "30D-alt", interval: 240, limit: 180 },
];
const SYMFORMATS = {
  refSymbol: (s) => ({ symbol: `Binance_${s}USDT` }),
  plain: (s) => ({ symbol: s }),
  coin: (s) => ({ coin: s }),
};
const ENDPOINTS = [
  { name: "v2 (model 1, our stopmap)", base: CAPI, path: "/api/index/v2/liqHeatMap", sym: "refSymbol", extra: { merge: "true" } },
  { name: "v5 (candidate model 2)", base: CAPI, path: "/api/index/v5/liqHeatMap", sym: "refSymbol", extra: {} },
  { name: "v6 (candidate model 3)", base: FAPI, path: "/api/index/v6/liqHeatMap", sym: "refSymbol", extra: {} },
  { name: "v4 aggregate", base: FAPI, path: "/api/index/v4/aggregate/liqHeatMap", sym: "coin", extra: { exchanges: "Binance,OKX,Bybit", market: "futures" } },
  { name: "aggregate (v1)", base: CAPI, path: "/api/index/aggregate/liqHeatMap", sym: "coin", extra: { exchanges: "Binance,OKX,Bybit", market: "futures" } },
  { name: "aggregate (v3)", base: CAPI, path: "/api/index/v3/aggregate/liqHeatMap", sym: "coin", extra: { exchanges: "Binance,OKX,Bybit", market: "futures" } },
];

const results = [];
async function probe(sym, tfRow, ep) {
  const params = { ...SYMFORMATS[ep.sym](sym), interval: tfRow.interval, limit: tfRow.limit, ...ep.extra, data: makeObeToken() };
  const r = await cgGet(ep.base, ep.path, params);
  results.push({ sym, tf: tfRow.tf, interval: tfRow.interval, limit: tfRow.limit, endpoint: ep.name, path: ep.path, ...r });
  const ok = r.code === "0" || (r.status === 200 && r.shape);
  console.log(`${ok ? "OK " : "-- "} ${sym} ${tfRow.tf.padEnd(7)} ${ep.name.padEnd(30)} status=${r.status} code=${r.code} ${r.msg ? "msg=" + r.msg : ""} ${ok ? "shape=" + JSON.stringify(r.shape).slice(0, 220) : ""}`);
  return ok;
}

// 1) endpoint discovery pass: BTC + XAU at 24H on every endpoint/symformat
console.log("=== PASS 1: endpoint discovery (24H) ===");
for (const ep of ENDPOINTS) {
  await probe("BTC", TFS[0], ep);
  await probe("XAU", TFS[0], ep);
  // try plain symbol format too when the primary failed
  const last = results[results.length - 1];
  if (last.code !== "0") {
    await probe("XAU", TFS[0], { ...ep, sym: ep.sym === "coin" ? "refSymbol" : "coin" });
  }
}

// 2) for every endpoint that served XAU, sweep the timeframes
console.log("\n=== PASS 2: XAU timeframe sweep on working endpoints ===");
const working = [...new Set(results.filter(r => r.sym === "XAU" && (r.code === "0")).map(r => r.endpoint))];
if (working.length === 0) {
  console.log("(no endpoint served XAU — the anonymous wall is symbol-wide, not timeframe-specific)");
} else {
  for (const w of working) {
    const ep = ENDPOINTS.find(e => e.name === w);
    for (const tf of TFS.slice(1)) await probe("XAU", tf, ep);
  }
}

// 3) BTC full timeframe sweep on v2 (control, documents the tf->interval/limit map)
console.log("\n=== PASS 3: BTC v2 timeframe sweep (control) ===");
for (const tf of TFS) await probe("BTC", tf, ENDPOINTS[0]);

fs.writeFileSync("/home/z/my-project/scripts/research/probe-xau-heatmap.json", JSON.stringify(results, null, 1));
console.log(`\nwrote ${results.length} probe rows to scripts/research/probe-xau-heatmap.json`);
