#!/usr/bin/env node
/**
 * probe_session_matrix.mjs — full model × mode × range matrix for XAU with
 * the logged-in session, verifying payload numbers against the user's
 * screenshots (2026-11-22 12:44): pair 3d → 3621=11.6M short cluster,
 * 3510=14.6M long; coin 3d → 3614=13.6M / 3510=18.3M; spot ≈ 3,550.
 *
 * Usage: CG_SESSION=<token> node probe_session_matrix.mjs
 */
import crypto from "crypto";
import fs from "fs";

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

const SESSION = process.env.CG_SESSION ?? fs.readFileSync("/tmp/cg_session_token.txt", "utf8").trim();
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const MODELS = {
  1: { pair: "/api/index/v2/liqHeatMap", coin: "/api/index/aggregate/liqHeatMap" },
  2: { pair: "/api/index/v5/liqHeatMap", coin: "/api/index/v3/aggregate/liqHeatMap" },
  3: { pair: "/api/index/v6/liqHeatMap", coin: "/api/index/v4/aggregate/liqHeatMap" },
};
const G_MAP = {
  "12h": { interval: 5, limit: 144 },
  "24h": { interval: 5, limit: 288 },
  "48h": { interval: 15, limit: 192 },
  "3d": { interval: 15, limit: 288 },
  "7d": { interval: 30, limit: 336 },
  "14d": { interval: 30, limit: 672 },
  "30d": { interval: "h2", limit: 372 },
  "90d": { interval: "h6", limit: 360 },
  "180d": { interval: "h12", limit: 360 },
  "1y": { interval: "h24", limit: 360 },
  "2y": { interval: "d1", limit: 720 },
};
const X_MAP = { "12h": "12h", "24h": "24h", "48h": "48h", "3d": "72h", "7d": "7d", "14d": "14d", "30d": "30d", "90d": "90d", "180d": "180d", "1y": "365d", "2y": "720d" };

/** page's ec() port: grid + key levels from the LAST column (ep). */
function pageModel(d) {
  if (!d || !Array.isArray(d.prices) || !Array.isArray(d.y) || !Array.isArray(d.liq)) return null;
  const prices = d.prices.filter(r => Array.isArray(r) && r.length >= 5 && Number.isFinite(+r[0]));
  const a = prices.length, i = d.y.length;
  if (!a || i < 2) return null;
  // y ascending sort + rank (page does this for lookup; we need row order)
  const yAsc = d.y.map((p, idx) => [+p, idx]).sort((p, q) => p[0] - q[0]);
  const rank = new Int32Array(i);
  yAsc.forEach(([, orig], r) => (rank[orig] = r));
  const yAxis = yAsc.map(([p]) => p);
  const bin = (yAxis[i - 1] - yAxis[0]) / (i - 1) || 1;
  const close = prices.map(r => +r[4]);
  // page layout: total[col * rows + row]
  const total = new Float64Array(a * i);
  const longs = new Float64Array(a * i);
  const shorts = new Float64Array(a * i);
  for (const [b, yi, usd] of d.liq) {
    const c = 0 | b, r = rank[0 | yi], v = +usd;
    if (c < 0 || c >= a || r < 0 || r >= i || !(v > 0)) continue;
    const k = c * i + r;
    total[k] += v;
    if (yAxis[r] > close[c]) shorts[k] += v; else longs[k] += v;
  }
  const last = close[a - 1];
  // ep(): key levels from LAST column, local maxima >= 12% of column max, 4 per side
  const off = (a - 1) * i;
  let colMax = 0;
  for (let r = 0; r < i; r++) colMax = Math.max(colMax, total[off + r]);
  const peaks = [];
  for (let r = 1; r < i - 1; r++) {
    const v = total[off + r];
    if (v >= total[off + r - 1] && v > total[off + r + 1] && v > 0.12 * colMax) peaks.push({ price: yAxis[r], value: v });
  }
  peaks.sort((p, q) => q.value - p.value);
  const up = [], down = [];
  for (const p of peaks) {
    const side = p.price > last ? up : down;
    if (side.length >= 4 || side.some(q => Math.abs(q.price - p.price) < 3 * bin)) continue;
    side.push(p);
  }
  up.sort((p, q) => p.price - q.price);
  down.sort((p, q) => q.price - p.price);
  // ed(): market overview — last column longs/shorts totals
  let longsSum = 0, shortsSum = 0;
  for (let r = 0; r < i; r++) { longsSum += longs[off + r]; shortsSum += shorts[off + r]; }
  return { last, colMax, up, down, longs: longsSum, shorts: shortsSum, bin, dt: d.prices?.length ? (prices[1] ? Math.round((+prices[1][0] - +prices[0][0]) / 60000) || 5 : 5) : 5, rows: i, cols: a, liqRows: d.liq.length };
}
const fmtM = (n) => (n / 1e6).toFixed(1) + "M";

async function run(sym, mode, model, tf) {
  const path = MODELS[model][mode];
  const symbol = mode === "coin" ? sym : `Binance_${sym}USDT`;
  const params = new URLSearchParams({ merge: "true", symbol });
  if (model === 3) { params.set("range", X_MAP[tf]); params.set("cp", "false"); }
  else { const g = G_MAP[tf]; params.set("interval", String(g.interval)); params.set("limit", String(g.limit)); }
  params.set("data", makeObeToken());
  const url = `${FAPI}${path}?${params.toString()}`;
  try {
    const res = await fetch(url, {
      headers: { "user-agent": UA, accept: "*/*", "accept-language": "en-US,en;q=0.9", origin: "https://www.coinglass.com", referer: "https://www.coinglass.com/", obe: SESSION },
      signal: AbortSignal.timeout(30000),
    });
    const j = await res.json().catch(() => null);
    const row = { sym, mode, model, tf, ok: false };
    const d = j?.data;
    const m = pageModel(Array.isArray(d) ? d[0] : d);
    if (j?.code === "0" && m) {
      row.ok = true;
      row.analysis = {
        last: m.last, longs: Math.round(m.longs), shorts: Math.round(m.shorts),
        total: Math.round(m.longs + m.shorts),
        up: m.up.map(p => ({ price: +p.price.toFixed(1), usd: Math.round(p.value) })),
        down: m.down.map(p => ({ price: +p.price.toFixed(1), usd: Math.round(p.value) })),
        grid: `${m.cols}x${m.rows}`, liq: m.liqRows,
      };
      console.log(`OK  ${sym} m${model} ${mode.padEnd(4)} ${tf.padEnd(4)} px=${m.last} total=${fmtM(m.longs + m.shorts)} longs(below)=${fmtM(m.longs)} shorts(above)=${fmtM(m.shorts)}`);
      for (const p of m.down.slice(0, 3)) console.log(`      BELOW ${p.price}  ${fmtM(p.value)}`);
      for (const p of m.up.slice(0, 3)) console.log(`      ABOVE ${p.price}  ${fmtM(p.value)}`);
    } else {
      row.code = j?.code ?? "?"; row.msg = String(j?.msg ?? "").slice(0, 80);
      console.log(`--  ${sym} m${model} ${mode.padEnd(4)} ${tf.padEnd(4)} code=${row.code} ${row.msg}`);
    }
    return row;
  } catch (e) {
    console.log(`ERR ${sym} m${model} ${mode} ${tf}: ${String(e.message).slice(0, 60)}`);
    return { sym, mode, model, tf, ok: false, error: e.message };
  }
}

const results = [];
// XAU Model 1 across ALL ranges (the user's ask: data must match at different timeframes)
for (const tf of ["12h", "24h", "48h", "3d", "7d", "14d", "30d", "90d", "180d", "1y", "2y"]) {
  results.push(await run("XAU", "coin", 1, tf));
  await sleep(1700);
}
for (const tf of ["24h", "3d", "7d", "30d"]) {
  results.push(await run("XAU", "pair", 1, tf));
  await sleep(1700);
}
// models 2/3 spot checks (coin mode)
for (const model of [2, 3]) {
  for (const tf of ["24h", "3d", "30d"]) {
    results.push(await run("XAU", "coin", model, tf));
    await sleep(1700);
  }
}
fs.writeFileSync("/home/z/my-project/scripts/research/session-matrix-xau.json", JSON.stringify(results, null, 1));
const ok = results.filter(r => r.ok);
console.log(`\nOK: ${ok.length}/${results.length}`);
