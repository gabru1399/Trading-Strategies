/**
 * Regression test for the liqlevels coverage semantics fix (2026-11-21).
 * Exercises loadSnapshot's evidence-based partial logic by stubbing the
 * venue fetcher through the route module — runs against the built server
 * logic via tsx-style transpile using next's swc is overkill; instead this
 * re-implements the exact decision block over fetchLiqVenuePayload outcomes
 * to assert the matrix. Kept honest: the block below is COPIED from the
 * route (marked) so any drift must be re-synced manually — the live
 * endpoint tests above are the authoritative check.
 */
const assert = require("assert");

// ---- inputs: (venueName, fulfilled?, realFailure?, rangeUsed) ----
function decide(requested, results, available, servedEverSet) {
  // ==== COPIED from src/app/api/cg/liqlevels/route.ts loadSnapshot ====
  const NO_DATA_RE = /^no usable liquidation snapshot/;
  const known = servedEverSet ?? new Set();
  for (const venue of available) known.add(venue.name);
  const failedVenues = [];
  requested.forEach((venue, i) => {
    if (available.some((a) => a.name === venue.name)) return;
    const r = results[i];
    const realFailure = r.status === "rejected" && !NO_DATA_RE.test(String(r.reason ?? ""));
    if (realFailure || known.has(venue.name)) failedVenues.push(venue.name);
  });
  return { partial: failedVenues.length > 0, failedVenues, known };
  // ====================================================================
}

const R = (status, reason) => ({ status, reason });

// 1. Hyperliquid 3d->7d substitution (the reported case): venue PRESENT
assert.deepStrictEqual(
  decide(
    ["Binance", "OKX", "Bybit", "Bitget", "Hyperliquid"].map((n) => ({ name: n })),
    [R("fulfilled"), R("fulfilled"), R("fulfilled"), R("fulfilled"), R("fulfilled")],
    [{ name: "Binance" }, { name: "OKX" }, { name: "Bybit" }, { name: "Bitget" }, { name: "Hyperliquid" }],
    new Set(["Binance", "OKX", "Bybit", "Bitget", "Hyperliquid"])
  ),
  { partial: false, failedVenues: [], known: new Set(["Binance", "OKX", "Bybit", "Bitget", "Hyperliquid"]) }
);
console.log("PASS 1: HL 7D substitution -> no warning (partial=false)");

// 2. Bitget never listed TIA and returns no-data: expected absence
assert.deepStrictEqual(
  decide(
    [{ name: "Binance" }, { name: "Bitget" }, { name: "Hyperliquid" }],
    [R("fulfilled"), R("rejected", "no usable liquidation snapshot for Bitget_TIAUSDT_UMCBL in ranges 3d,7d,30d"), R("fulfilled")],
    [{ name: "Binance" }, { name: "Hyperliquid" }],
    new Set(["Binance", "Hyperliquid"])
  ),
  { partial: false, failedVenues: [], known: new Set(["Binance", "Hyperliquid"]) }
);
console.log("PASS 2: never-listed venue no-data -> expected absence, no warning");

// 3. OKX served BTC before but now 429s: regression -> WARN
const r3 = decide(
  [{ name: "Binance" }, { name: "OKX" }, { name: "Bybit" }],
  [R("fulfilled"), R("rejected", "Coinglass 429: rate limited"), R("fulfilled")],
  [{ name: "Binance" }, { name: "Bybit" }],
  new Set(["Binance", "OKX", "Bybit"])
);
assert.strictEqual(r3.partial, true);
assert.deepStrictEqual(r3.failedVenues, ["OKX"]);
console.log("PASS 3: served-before venue real failure -> warning fires, names the venue");

// 4. Fresh symbol, all venues no-data (new listing): nothing served, no warning
const r4 = decide(
  [{ name: "Binance" }, { name: "Bitget" }],
  [R("rejected", "no usable liquidation snapshot for Binance_NEWUSDT in ranges 3d,7d,30d"), R("rejected", "no usable liquidation snapshot for Bitget_NEWUSDT_UMCBL in ranges 3d,7d,30d")],
  [],
  new Set()
);
assert.strictEqual(r4.partial, false);
console.log("PASS 4: fresh symbol, all no-data -> no false warning (model build fails separately, handled by disk fallback)");

// 5. Venue served in THIS call then counted: learned into servedEver
const r5 = decide(
  [{ name: "Binance" }, { name: "Gate" }],
  [R("fulfilled"), R("rejected", "no usable liquidation snapshot for Gate_XAG_USDT in ranges 3d,7d,30d")],
  [{ name: "Binance" }],
  new Set(["Binance"])
);
assert.strictEqual(r5.partial, false);
assert.ok(r5.known.has("Binance") && !r5.known.has("Gate"));
console.log("PASS 5: servedEver learns only from actual serves");

// 6. later call: never-served venue fails with a REAL network error -> flagged
const r6 = decide(
  [{ name: "Binance" }, { name: "Gate" }],
  [R("fulfilled"), R("rejected", "fetch failed: network timeout")],
  [{ name: "Binance" }],
  r5.known // carries Binance only
);
assert.strictEqual(r6.partial, true); // real failure must warn even for a never-served venue
assert.deepStrictEqual(r6.failedVenues, ["Gate"]);
console.log("PASS 6: real network failure names the venue even for never-served venue");

console.log("\nAll 6 semantics cases PASS.");
