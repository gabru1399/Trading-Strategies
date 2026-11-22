"use client";

import { useMemo, useState } from "react";
import { usePolling } from "./use-cg-data";
import StopmapCanvas from "./charts/stopmap-canvas";
import { assetOf } from "@/lib/cg/assets";

/**
 * Stops (liquidation heatmap) — the CURRENT Coinglass /LiquidationHeatMap
 * page (Model 1/2/3 tabs, Pair/Coin toggle, 12h..2y ranges):
 *  - Model 1 = the classic leverage-exposure grid (default, what the
 *    operator asked to add for pullback entries along the trend)
 *  - Coin mode = ALL venues aggregated under the plain symbol (default)
 *  - Pair mode = the Binance execution venue only
 * Key-liquidation-levels and Market-overview panels follow the page's exact
 * math (last-column local maxima; verified 1:1 against the live page).
 * The legacy 24h/5m BTC view remains as the "24h" range of the same grid.
 */

const RANGES = ["12h", "24h", "48h", "3d", "7d", "14d", "30d", "90d", "180d", "1y", "2y"] as const;
const MODELS = ["1", "2", "3"] as const;

interface Model1Response {
  ok: boolean;
  supported?: boolean;
  reason?: string;
  error?: string;
  sym: string;
  symbol?: string;
  instrument?: string;
  window?: { interval: string; bars: number; from: number; to: number };
  source?: string;
  stale?: boolean;
  model?: {
    model: string;
    mode: "coin" | "pair";
    range: string;
    symbol?: string;
    keyLevels: {
      above: { price: number; usd: number }[];
      below: { price: number; usd: number }[];
    };
    overview: {
      lastPrice: number;
      longs: number;
      shorts: number;
      total: number;
      largestLevel: number;
      priceStep: number;
      columnMinutes: number;
      chgPct24h: number | null;
    };
    yAxis: number[];
    columns: { ts: number; cells: [number, number][] }[];
    profile: number[];
    lastColumn: number[];
    candles: { ts: number; o: number; h: number; l: number; c: number }[];
    liqRows: number;
    cumulative: { price: number; below: number; above: number }[];
  };
  // legacy BTC/rolling shape (stopmap fallback) — rendered by the old path
  lastPrice?: number;
  clusters?: {
    below: { price: number; usd: number; distPct: number; strength: number }[];
    above: { price: number; usd: number; distPct: number; strength: number }[];
  };
  totals?: { below: number; above: number; all: number; rows: number };
  bands?: { a: number; b: number; below: number; above: number }[];
  grid?: { ts: number; cells: [number, number][] }[];
  y?: number[];
}

function fmtB(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return n.toFixed(0);
}

export default function StopmapSection({ sym = "BTC" }: { sym?: string }) {
  const [model, setModel] = useState<(typeof MODELS)[number]>("1");
  const [mode, setMode] = useState<"coin" | "pair">("coin");
  const [range, setRange] = useState<string>("3d");

  const q = usePolling<Model1Response>(
    `/api/cg/stopmap?sym=${sym}&model=${model}&mode=${mode}&range=${range}`,
    30_000
  );
  // defense-in-depth: never render a model that belongs to another symbol
  const m = q.data && q.data.sym === sym ? q.data.model : undefined;
  const isModel1Shape = Boolean(m?.keyLevels && m?.overview);
  const decs = assetOf(sym)?.priceDecs ?? 2;
  const fmtP = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: decs, maximumFractionDigits: decs });
  const px = m?.overview?.lastPrice;

  // strongest cluster either side for the magnet card
  const magnet = useMemo(() => {
    if (!m?.keyLevels) return null;
    const all = [...m.keyLevels.above, ...m.keyLevels.below].sort((a, b) => b.usd - a.usd);
    return all[0] ?? null;
  }, [m]);

  if (!m || !isModel1Shape) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-1 rounded-lg border border-neutral-800 bg-neutral-900/60 p-4 text-center text-sm text-neutral-400">
        <div>{q.loading ? `Loading Model ${model} ${range} heatmap…` : q.error ? `Stops data error: ${q.error}` : q.data?.reason || q.data?.error || "No data"}</div>
        <div className="text-xs text-neutral-500">
          {(q.data?.source ?? "").startsWith("coinglass:") ? "" : "Coin-mode heatmaps need CG_SESSION (see scripts/research/cg_login.mjs); BTC pair 24h works anonymously."}
        </div>
      </div>
    );
  }

  const ov = m.overview;
  const lvl = (price: number, usd: number, side: "above" | "below") => {
    const distPct = px ? ((price - px) / px) * 100 : 0;
    const strength = ov.largestLevel > 0 ? (usd / ov.largestLevel) * 100 : 0;
    return (
      <tr key={`${side}-${price}`} className="border-t border-neutral-800/40">
        <td className="py-1 font-mono text-neutral-200">{fmtP(price)}</td>
        <td className={`py-1 text-right font-mono ${side === "above" ? "text-red-400/80" : "text-emerald-400/80"}`}>
          {side === "above" ? "+" : ""}{distPct.toFixed(2)}%
        </td>
        <td className="py-1 text-right font-mono text-neutral-300">${fmtB(usd)}</td>
        <td className="py-1 pl-2">
          <div className="h-2 w-full overflow-hidden rounded bg-neutral-800">
            <div className={`h-full ${side === "above" ? "bg-red-500/80" : "bg-emerald-500/80"}`} style={{ width: `${strength}%` }} />
          </div>
        </td>
      </tr>
    );
  };

  return (
    <div className="flex flex-col gap-3">
      {/* controls — the live page's selector row */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex overflow-hidden rounded-md border border-neutral-800 text-xs">
          {MODELS.map((v) => (
            <button
              key={v}
              onClick={() => setModel(v)}
              className={`px-2.5 py-1 ${model === v ? "bg-neutral-100 font-medium text-neutral-900" : "bg-neutral-900 text-neutral-400 hover:text-neutral-200"}`}
            >
              Model {v}
            </button>
          ))}
        </div>
        <div className="flex overflow-hidden rounded-md border border-neutral-800 text-xs">
          {(["coin", "pair"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setMode(v)}
              className={`px-2.5 py-1 capitalize ${mode === v ? "bg-neutral-100 font-medium text-neutral-900" : "bg-neutral-900 text-neutral-400 hover:text-neutral-200"}`}
            >
              {v}
            </button>
          ))}
        </div>
        <select
          value={range}
          onChange={(e) => setRange(e.target.value)}
          className="rounded-md border border-neutral-800 bg-neutral-900 px-2 py-1 text-xs text-neutral-300"
        >
          {RANGES.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
        <span className="text-[10px] text-neutral-500">
          {q.data?.stale ? "stale" : q.data?.source?.includes("session") ? "live · session" : "live"} · {ov.columnMinutes}m columns · step {ov.priceStep.toFixed(2)}
        </span>
      </div>

      {/* market overview — the live page's right panel */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
        <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">Last price</div>
          <div className="mt-0.5 font-mono text-sm font-semibold text-neutral-100">{fmtP(ov.lastPrice)}</div>
          <div className="text-[10px] text-neutral-500">{ov.chgPct24h === null ? "" : `${ov.chgPct24h >= 0 ? "+" : ""}${ov.chgPct24h.toFixed(2)}% 24h`}</div>
        </div>
        <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">Open liq levels</div>
          <div className="mt-0.5 font-mono text-sm font-semibold text-neutral-100">${fmtB(ov.total)}</div>
          <div className="text-[10px] text-neutral-500">currently resting exposure</div>
        </div>
        <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">Longs below</div>
          <div className="mt-0.5 font-mono text-sm font-semibold text-emerald-400">${fmtB(ov.longs)}</div>
          <div className="text-[10px] text-neutral-500">{ov.total > 0 ? `${Math.round((ov.longs / ov.total) * 100)}%` : "—"}</div>
        </div>
        <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">Shorts above</div>
          <div className="mt-0.5 font-mono text-sm font-semibold text-red-400">${fmtB(ov.shorts)}</div>
          <div className="text-[10px] text-neutral-500">{ov.total > 0 ? `${Math.round((ov.shorts / ov.total) * 100)}%` : "—"}</div>
        </div>
        <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">Largest single level</div>
          <div className="mt-0.5 font-mono text-sm font-semibold text-neutral-100">${fmtB(ov.largestLevel)}</div>
          <div className="text-[10px] text-neutral-500">{fmtB(m.liqRows)} heat cells</div>
        </div>
        <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">Sweep magnet</div>
          <div className="mt-0.5 font-mono text-sm font-semibold text-neutral-100">{magnet ? fmtP(magnet.price) : "—"}</div>
          <div className="text-[10px] text-neutral-500">{magnet ? `$${fmtB(magnet.usd)} cluster` : ""}</div>
        </div>
      </div>

      <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-2">
        <StopmapCanvas
          model={{
            candles: m.candles,
            y: m.yAxis,
            grid: m.columns,
            profile: m.profile,
            lastPrice: ov.lastPrice,
            clusters: {
              below: m.keyLevels.below.map((k) => ({
                price: k.price,
                usd: k.usd,
                distPct: px ? ((k.price - px) / px) * 100 : 0,
              })),
              above: m.keyLevels.above.map((k) => ({
                price: k.price,
                usd: k.usd,
                distPct: px ? ((k.price - px) / px) * 100 : 0,
              })),
            },
          }}
          height={380}
          priceDecs={decs}
        />
      </div>

      {/* key liquidation levels — the live page's right panel */}
      <div className="grid gap-3 xl:grid-cols-2">
        <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-3">
          <h3 className="mb-2 text-sm font-semibold text-neutral-100">
            🔴 Above — short liquidations <span className="text-[11px] font-normal text-neutral-500">pullback resistance / squeeze fuel</span>
          </h3>
          <table className="w-full text-[11px]">
            <thead className="text-neutral-500">
              <tr>
                <th className="py-1 text-left font-medium">Price</th>
                <th className="py-1 text-right font-medium">From price</th>
                <th className="py-1 text-right font-medium">Liq size</th>
                <th className="py-1 pl-2 text-left font-medium">Strength</th>
              </tr>
            </thead>
            <tbody>
              {m.keyLevels.above.map((k) => lvl(k.price, k.usd, "above"))}
              {!m.keyLevels.above.length && (
                <tr><td colSpan={4} className="py-4 text-center text-neutral-600">No clusters above.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-3">
          <h3 className="mb-2 text-sm font-semibold text-neutral-100">
            🟢 Below — long liquidations <span className="text-[11px] font-normal text-neutral-500">pullback magnets along the trend</span>
          </h3>
          <table className="w-full text-[11px]">
            <thead className="text-neutral-500">
              <tr>
                <th className="py-1 text-left font-medium">Price</th>
                <th className="py-1 text-right font-medium">From price</th>
                <th className="py-1 text-right font-medium">Liq size</th>
                <th className="py-1 pl-2 text-left font-medium">Strength</th>
              </tr>
            </thead>
            <tbody>
              {m.keyLevels.below.map((k) => lvl(k.price, k.usd, "below"))}
              {!m.keyLevels.below.length && (
                <tr><td colSpan={4} className="py-4 text-center text-neutral-600">No clusters below.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-lg border border-neutral-800 bg-neutral-900/40 px-3 py-2 text-[10px] leading-relaxed text-neutral-500">
        Coinglass Model {m.model} estimates ({m.mode} mode · {m.range} window · {q.data?.instrument ?? m.symbol}): leveraged positions
        that would be force-closed at each price — exchanges do not publish individual liquidation prices. Strong clusters are
        liquidity magnets that <em>attract</em> sweeps; for pullback entries along the trend, watch the below-price magnets in an
        uptrend (and above-price in a downtrend) as the zones price is drawn toward. Read together with the Levels tab
        (position-open cohorts) and Book Walls (resting depth).
      </div>
    </div>
  );
}
