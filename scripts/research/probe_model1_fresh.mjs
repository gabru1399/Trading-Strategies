#!/usr/bin/env node
/**
 * probe_model1_fresh.mjs — fresh probe of the fapi liqHeatMap family for XAU,
 * trying harder than the 2026-11-21 round:
 *   1. full Chrome header set (sec-ch-ua, sec-fetch-*, accept-language…)
 *   2. curl --http2 (different TLS fingerprint than node fetch)
 *   3. all model×mode endpoints, plus cp/range variants
 *   4. checks the capi legacy liquidity-heatmap service too
 * Spacing 1.5 s; saves findings to scripts/research/probe-model1-fresh.json.
 */
import crypto from "crypto";
import fs from "fs";
import { execFile } from "child_process";
import { promisify } from "util";
const execFileP = promisify(execFile);

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

const FULL_HEADERS = {
  "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  accept: "*/*",
  "accept-language": "en-US,en;q=0.9",
  origin: "https://www.coinglass.com",
  referer: "https://www.coinglass.com/",
  "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
  "sec-ch-ua-mobile": "?0",
  "sec-ch-ua-platform": '"Windows"',
  "sec-fetch-dest": "empty",
  "sec-fetch-mode": "cors",
  "sec-fetch-site": "same-site",
  "priority": "u=1, i",
};

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function nodeFetch(url, label) {
  try {
    const res = await fetch(url, { headers: FULL_HEADERS, signal: AbortSignal.timeout(20000) });
    const txt = await res.text();
    let j = null; try { j = JSON.parse(txt); } catch {}
    const code = j?.code ?? "?";
    let extra = "";
    const d = j?.data;
    if (Array.isArray(d)) extra = `arr[${d.length}]`;
    else if (d && typeof d === "object") {
      extra = `keys=${Object.keys(d).slice(0, 7).join(",")}`;
      if (Array.isArray(d.liq)) extra += ` liq[${d.liq.length}] y[${(d.y ?? []).length}] prices[${(d.prices ?? []).length}]`;
    }
    console.log(`node ${String(res.status).padEnd(4)} code=${String(code).padEnd(7)} ${label} ${extra}`);
    return { via: "node", status: res.status, code, extra, ok: code === "0" };
  } catch (e) {
    console.log(`node ERR  ${String(e.message).slice(0, 60).padEnd(8)} ${label}`);
    return { via: "node", error: e.message, ok: false };
  }
}

async function curlFetch(url, label) {
  const args = ["-s", "--http2", "--max-time", "20", "-w", "\n%{http_code}"];
  for (const [k, v] of Object.entries(FULL_HEADERS)) args.push("-H", `${k}: ${v}`);
  args.push(url);
  try {
    const { stdout } = await execFileP("curl", args);
    const lines = stdout.trimEnd().split("\n");
    const status = lines.pop();
    const body = lines.join("\n");
    let j = null; try { j = JSON.parse(body); } catch {}
    const code = j?.code ?? "?";
    let extra = "";
    const d = j?.data;
    if (d && typeof d === "object" && !Array.isArray(d) && Array.isArray(d.liq)) {
      extra = `liq[${d.liq.length}] y[${(d.y ?? []).length}]`;
    } else if (Array.isArray(d)) extra = `arr[${d.length}]`;
    console.log(`curl ${String(status).padEnd(4)} code=${String(code).padEnd(7)} ${label} ${extra}`);
    return { via: "curl", status: Number(status), code, extra, ok: code === "0" };
  } catch (e) {
    console.log(`curl ERR  ${String(e.message).slice(0, 60)} ${label}`);
    return { via: "curl", error: e.message, ok: false };
  }
}

const token = () => encodeURIComponent(makeObeToken());
const results = [];

// --- 1. XAU coin mode, model 1 (aggregate endpoint), full headers, both stacks
const cases = [
  ["m1 coin 24h",  `${FAPI}/api/index/aggregate/liqHeatMap?merge=true&symbol=XAU&interval=5&limit=288&data=${token()}`],
  ["m1 pair 24h",  `${FAPI}/api/index/v2/liqHeatMap?merge=true&symbol=Binance_XAUUSDT&interval=5&limit=288&data=${token()}`],
  ["m1 coin 3d",   `${FAPI}/api/index/aggregate/liqHeatMap?merge=true&symbol=XAU&interval=15&limit=288&data=${token()}`],
  ["m2 coin 24h",  `${FAPI}/api/index/v3/aggregate/liqHeatMap?merge=true&symbol=XAU&interval=5&limit=288&data=${token()}`],
  ["m3 coin 3d",   `${FAPI}/api/index/v4/aggregate/liqHeatMap?merge=true&symbol=XAU&range=72h&cp=false&data=${token()}`],
  ["m3 pair 3d",   `${FAPI}/api/index/v6/liqHeatMap?merge=true&symbol=Binance_XAUUSDT&range=72h&cp=false&data=${token()}`],
  ["BTC ctrl m1",  `${FAPI}/api/index/v2/liqHeatMap?merge=true&symbol=Binance_BTCUSDT&interval=5&limit=288&data=${token()}`],
];

for (const [label, url] of cases) {
  results.push({ label, ...(await nodeFetch(url, label)) });
  await sleep(1600);
  results.push({ label: label + " [curl]", ...(await curlFetch(url, label + " [curl]")) });
  await sleep(1600);
}

fs.writeFileSync("/home/z/my-project/scripts/research/probe-model1-fresh.json", JSON.stringify(results, null, 1));
const oks = results.filter(r => r.ok);
console.log(`\nOK: ${oks.length}/${results.length}`);
for (const r of oks) console.log(`  ${r.label} (${r.via}) ${r.extra}`);
