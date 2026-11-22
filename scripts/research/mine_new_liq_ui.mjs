#!/usr/bin/env node
/**
 * mine_new_liq_ui.mjs — fetch the CURRENT Coinglass LiquidationHeatMap page
 * (the new UI from the user's screenshots: Model 1/2/3 tabs, Pair/Coin toggle,
 * 12h..2y ranges) and mine its JS chunks for the liquidation-heatmap API
 * wiring: endpoints, params, model/mode/range maps.
 *
 * Saves everything under scripts/research/liq-new-ui/ (untrusted data — never
 * executed, only text-mined).
 */
import fs from "fs";
import path from "path";

const OUT = "/home/z/my-project/scripts/research/liq-new-ui";
fs.mkdirSync(OUT, { recursive: true });

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";
const H = { "user-agent": UA, accept: "text/html,*/*", "accept-language": "en-US,en;q=0.9" };

async function get(url) {
  const res = await fetch(url, { headers: H, signal: AbortSignal.timeout(25000) });
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.text();
}

// 1) the page HTML (new UI serves at the same URL — no ?model= needed)
const pages = [
  "https://www.coinglass.com/LiquidationHeatMap/XAU",
  "https://www.coinglass.com/LiquidationHeatMap/BTC",
];
const chunkUrls = new Set();
for (const url of pages) {
  try {
    const html = await get(url);
    const name = url.endsWith("/BTC") ? "page-btc.html" : "page-xau.html";
    fs.writeFileSync(path.join(OUT, name), html);
    console.log(`saved ${name} (${html.length} bytes)`);
    for (const m of html.matchAll(/\/_next\/static\/chunks\/[^"'\s<>]+?\.js/g)) chunkUrls.add(m[0]);
    // also build-id manifest references
    for (const m of html.matchAll(/"buildId":"([^"]+)"/g)) console.log("buildId:", m[1]);
  } catch (e) {
    console.log(`FAIL ${url}: ${e.message}`);
  }
}
console.log(`\nchunk urls found in HTML: ${chunkUrls.size}`);

// 2) download chunks (cap 120 — page references shared chunks too)
let n = 0;
for (const u of [...chunkUrls].slice(0, 120)) {
  const full = u.startsWith("http") ? u : `https://www.coinglass.com${u}`;
  const base = path.basename(u.split("?")[0]);
  try {
    const js = await get(full);
    fs.writeFileSync(path.join(OUT, base), js);
    n++;
  } catch (e) {
    console.log(`chunk FAIL ${base}: ${e.message}`);
  }
}
console.log(`downloaded ${n} chunks`);

// 3) mine every chunk for liquidation-heatmap wiring
const findings = { endpoints: new Set(), params: new Set(), maps: [] };
const files = fs.readdirSync(OUT).filter((f) => f.endsWith(".js"));
for (const f of files) {
  const src = fs.readFileSync(path.join(OUT, f), "utf8");
  // any URL-ish path with heat/liq
  for (const m of src.matchAll(/["'`]((?:https?:\/\/[^"'`]+)?\/api\/[^"'`]*?(?:liq|heat)[^"'`]*?)["'`]/gi)) {
    findings.endpoints.add(m[1]);
  }
  for (const m of src.matchAll(/["'`]([^"'`]*liquidity-heatmap[^"'`]*)["'`]/gi)) {
    findings.endpoints.add(m[1]);
  }
  for (const m of src.matchAll(/["'`]([^"'`]*liquidation-heatmap[^"'`]*)["'`]/gi)) {
    findings.endpoints.add(m[1]);
  }
  // model / mode / range wiring
  if (/liqHeatMap|liq-heatmap|liquidationHeatmap/i.test(src)) {
    for (const m of src.matchAll(/["'`](12h|24h|48h|72h|7d|14d|30d|90d|180d|365d|720d)["'`\s:]/g)) {
      findings.params.add(m[1]);
    }
  }
}
console.log("\n=== endpoint-like strings:");
for (const e of [...findings.endpoints].sort()) console.log(" ", e);
console.log("\n=== range literals seen near liqHeatMap code:");
console.log(" ", [...findings.params].sort().join(" "));
