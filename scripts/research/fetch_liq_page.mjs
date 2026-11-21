#!/usr/bin/env node
/**
 * Fetch the live Coinglass LiquidationHeatMap/XAU?model=2 page, download its
 * JS chunks, and mine them for the model->endpoint/params wiring (which of
 * v2/v5/v6/aggregate each model uses, symbol format, interval/limit per
 * timeframe). Saves chunks to scripts/research/liq-page/ and prints findings.
 */
import fs from "fs";
import path from "path";

const OUT = "/home/z/my-project/scripts/research/liq-page";
fs.mkdirSync(OUT, { recursive: true });

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";
const H = { "user-agent": UA, accept: "text/html,*/*", "accept-language": "en-US,en;q=0.9" };

async function get(url, binary = false) {
  const res = await fetch(url, { headers: H, signal: AbortSignal.timeout(20000) });
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return binary ? Buffer.from(await res.arrayBuffer()) : res.text();
}

// 1) the page HTML for model 2 (and model 3 for comparison)
for (const model of ["1", "2", "3"]) {
  const url = `https://www.coinglass.com/LiquidationHeatMap/XAU?model=${model}`;
  try {
    const html = await get(url);
    const f = path.join(OUT, `page-model${model}.html`);
    fs.writeFileSync(f, html);
    console.log(`saved ${f} (${html.length} bytes)`);
  } catch (e) {
    console.log(`FAIL model=${model}: ${e.message}`);
  }
}

// 2) collect chunk URLs from all saved HTMLs
const chunks = new Set();
for (const f of fs.readdirSync(OUT).filter(x => x.endsWith(".html"))) {
  const html = fs.readFileSync(path.join(OUT, f), "utf8");
  for (const m of html.matchAll(/\/_next\/static\/chunks\/[^"'\s<>]+\.js/g)) chunks.add(m[0]);
  // also direct static app paths
  for (const m of html.matchAll(/\/_next\/static\/[^"'\s<>]+\.js/g)) chunks.add(m[0]);
}
console.log(`\nchunk urls found: ${chunks.size}`);

// 3) download them all (they're the page's actual code)
let n = 0;
for (const u of chunks) {
  const name = u.split("/").pop();
  const dest = path.join(OUT, name);
  if (fs.existsSync(dest)) continue;
  try {
    const buf = await get("https://www.coinglass.com" + u, true);
    fs.writeFileSync(dest, buf);
    n++;
  } catch (e) {
    console.log(`  chunk fail ${name}: ${e.message}`);
  }
}
console.log(`downloaded ${n} chunks`);

// 4) mine every chunk for liqHeatMap wiring
const files = fs.readdirSync(OUT).filter(f => f.endsWith(".js"));
console.log(`\nmining ${files.length} chunks...`);
const pats = [
  /liqHeatMap/g,
  /\bmodel\b/g,
];
for (const f of files) {
  const src = fs.readFileSync(path.join(OUT, f), "utf8");
  if (!/liqHeatMap/.test(src)) continue;
  console.log(`\n######## ${f} (${src.length} bytes) has liqHeatMap`);
  // show each liqHeatMap mention with wide context
  const seen = new Set();
  for (const m of src.matchAll(/liqHeatMap/g)) {
    const c = src.slice(Math.max(0, m.index - 300), m.index + 340).replace(/\n/g, " ");
    if (seen.has(c)) continue;
    seen.add(c);
    console.log("  >>", c.slice(0, 600));
  }
}
// 5) model param handling in any chunk mentioning model + query/searchParams
for (const f of files) {
  const src = fs.readFileSync(path.join(OUT, f), "utf8");
  if (!/model/.test(src) || !/liqHeatMap|LiquidationHeatMap/i.test(src)) continue;
  const seen = new Set();
  for (const m of src.matchAll(/model[=:][^,;)\n]{0,120}/g)) {
    const c = m[0];
    if (seen.has(c)) continue;
    seen.add(c);
    if (/query|search|params|model["']?\s*[=:]/i.test(c)) console.log(`[model] ${f}: ${c.slice(0, 160)}`);
  }
}
