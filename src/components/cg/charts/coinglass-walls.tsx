"use client";

import { useMemo, useState } from "react";
import { COLORSCHEMES, heatColor, legendCss, fmtUsd } from "./heatmap-colormaps";

/**
 * Coinglass "Walls" lens — EXACT port of the live page's buildWalls() +
 * drawWalls() (mined from %5Bsymbol%5D-e61edde946656ec4.js @65684/@66765,
 * 2026-11-22). Same data, same construction:
 *
 *   NORM[c][r] = (usd/max)^0.7, rescaled by the Intensity slider
 *   1. per price row: runs of NORM ≥ 0.3, at least 2 columns long
 *   2. merge runs within ±1 row whose column overlap ≥ 80% of the longer run
 *   3. re-split merged groups on ≥2 empty columns (segments ≥ 2 columns);
 *      wall = {rows rmin..rmax, cols c0..c1, mx = max USD, rpk = peak row,
 *              n = peak NORM, price = lo+(rpk+.5)·bin, score = mx·width}
 *   4. top 24 by score get drawn; thickness tier 3/5/8/11px (capped at 16,
 *      floored by the band's own pixel height); colour = LUT(max(.35, n))
 *      — or red/green short/long split at the current close row in Split mode
 *   5. top 14 get labels "price · size" (11 px vertical dedup); walls
 *      reaching the last column are ACTIVE (not yet swept)
 *   6. faint heat wash behind (α .14), mono candles, dashed current-price
 *      line, Max short/long liquidation callouts on the strongest clusters
 *
 * Rendered as DOM (positioned divs for walls — exact px thickness like the
 * page — plus SVG layers for the wash and candles). Price rows are the RAW
 * bins at fixed height plotH/rows, like the page's fit: XAU 3d ≈ 154 rows
 * over ~560px ≈ 3.6px per bin.
 */

export interface WallsModel {
  yAxis: number[];
  columns: { ts: number; cells: [number, number][] }[];
  candles: { ts: number; o: number; h: number; l: number; c: number }[];
  lastPrice: number;
  priceStep: number;
}

export interface Wall {
  rmin: number;
  rmax: number;
  c0: number;
  c1: number;
  mx: number;
  rpk: number;
  n: number;
  price: number;
  score: number;
}

/** page buildWalls() — verbatim port (see class comment) */
export function buildWalls(
  total: Float64Array,
  cols: number,
  rows: number,
  lo: number,
  bin: number,
  thr: number,
  maxVal: number
): Wall[] {
  // NORM grid: raw = min(1,(v/max)^0.7); NORM = clamp01((raw-thr)/(1-thr))
  const N = new Float32Array(cols * rows);
  for (let k = 0; k < total.length; k++) {
    if (total[k] <= 0) continue;
    const raw = Math.min(1, Math.pow(total[k] / maxVal, 0.7));
    N[k] = raw <= thr ? 0 : Math.min(1, (raw - thr) / (1 - thr));
  }

  // phase 1 — per-row runs of N ≥ 0.3 spanning ≥ 2 columns
  const runs: { r: number; c0: number; c1: number }[] = [];
  for (let r = 0; r < rows; r++) {
    let l = -1;
    for (let s = 0; s <= cols; s++) {
      if (s < cols && N[s * rows + r] >= 0.3) {
        if (l < 0) l = s;
      } else if (l >= 0) {
        if (s - l >= 2) runs.push({ r, c0: l, c1: s - 1 });
        l = -1;
      }
    }
  }

  // phase 2 — merge runs within ±1 row with ≥ 80% column overlap
  runs.sort((a, b) => a.r - b.r || a.c0 - b.c0);
  const groups: { rmin: number; rmax: number; c0: number; c1: number }[] = [];
  for (const e of runs) {
    let t: (typeof groups)[number] | null = null;
    for (const g of groups) {
      if (
        e.r - g.rmax <= 1 &&
        e.r >= g.rmin - 1 &&
        Math.min(e.c1, g.c1) - Math.max(e.c0, g.c0) + 1 >=
          0.8 * Math.max(e.c1 - e.c0 + 1, g.c1 - g.c0 + 1)
      ) {
        t = g;
        break;
      }
    }
    if (t) {
      t.rmin = Math.min(t.rmin, e.r);
      t.rmax = Math.max(t.rmax, e.r);
      t.c0 = Math.min(t.c0, e.c0);
      t.c1 = Math.max(t.c1, e.c1);
    } else {
      groups.push({ rmin: e.r, rmax: e.r, c0: e.c0, c1: e.c1 });
    }
  }

  // phase 3 — re-split on ≥2 empty columns; score = mx × width; top 24
  const walls: Wall[] = [];
  for (const g of groups) {
    let a = -1;
    let empties = 0;
    for (let n = g.c0; n <= g.c1 + 1; n++) {
      let has = false;
      if (n <= g.c1) {
        for (let r = g.rmin; r <= g.rmax && !has; r++) {
          if (N[n * rows + r] >= 0.3) has = true;
        }
      }
      if (has) {
        if (a < 0) a = n;
        empties = 0;
      } else if (a >= 0 && (++empties >= 2 || n > g.c1)) {
        const c = n - empties;
        if (c - a + 1 >= 2) {
          let mx = 0;
          let rpk = g.rmin;
          let npk = 0;
          for (let s = a; s <= c; s++) {
            for (let r = g.rmin; r <= g.rmax; r++) {
              const v = total[s * rows + r];
              if (v > mx) {
                mx = v;
                rpk = r;
              }
              const nn = N[s * rows + r];
              if (nn > npk) npk = nn;
            }
          }
          walls.push({
            rmin: g.rmin,
            rmax: g.rmax,
            c0: a,
            c1: c,
            mx,
            rpk,
            n: npk,
            price: lo + (rpk + 0.5) * bin,
            score: mx * (c - a + 1),
          });
        }
        a = -1;
        empties = 0;
      }
    }
  }
  walls.sort((x, y) => y.score - x.score);
  return walls.slice(0, 24);
}

const pad = (n: number) => String(n).padStart(2, "0");
const fmtClock = (ts: number) => {
  const d = new Date(ts);
  return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
const compact = (n: number): string => fmtUsd(n).replace("$", "");

/** nice axis step covering range in ~n ticks (page's 1/2/5 ladder) */
function niceStep(range: number, n: number): number {
  const raw = range / Math.max(1, n);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  return (norm >= 5 ? 5 : norm >= 2 ? 2 : 1) * mag;
}

/** LUT colour at intensity t (0..1) for a scheme side */
function lutAt(scheme: { above: unknown[]; below?: unknown[] }, t: number, below: boolean): string {
  const rows = (below && scheme.below ? scheme.below : scheme.above) as [number, number, number][];
  const s = rows[Math.min(255, Math.round(Math.max(0, Math.min(1, t)) * 255))];
  return `rgb(${s[0]},${s[1]},${s[2]})`;
}

export default function CoinglassWalls({
  model,
  colors = "viridis",
  intensityMin = 0,
  split = false,
  showCandles = true,
  height = 560,
  priceDecs = 2,
}: {
  model: WallsModel;
  colors?: string;
  intensityMin?: number;
  split?: boolean;
  showCandles?: boolean;
  height?: number;
  priceDecs?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);

  const fmtP = (n: number) =>
    n.toLocaleString("en-US", { minimumFractionDigits: priceDecs, maximumFractionDigits: priceDecs });

  // ---- dense grid + walls (recomputed on model/intensity change, like the page) ----
  const W = useMemo(() => {
    const { yAxis, columns, candles, lastPrice, priceStep: bin } = model;
    const rows = yAxis.length;
    const cols = candles.length;
    if (!rows || !cols) return null;
    const lo = yAxis[0];
    const tsIdx = new Map<number, number>();
    candles.forEach((cd, i) => tsIdx.set(cd.ts, i));

    const total = new Float64Array(cols * rows);
    let maxVal = 0;
    for (const bar of columns) {
      const ci = tsIdx.get(bar.ts);
      if (ci === undefined) continue;
      for (const [yi, usd] of bar.cells) {
        const k = ci * rows + yi;
        total[k] += usd;
        if (total[k] > maxVal) maxVal = total[k];
      }
    }
    if (maxVal <= 0) maxVal = 1;

    const walls = buildWalls(total, cols, rows, lo, bin, intensityMin, maxVal);

    // faint background wash — 24×36 aggregate of the dense grid (page: 1×1
    // raster at α .14; a coarse DOM grid reads the same at a fraction of nodes)
    const WR = Math.min(24, rows);
    const WC = Math.min(36, cols);
    const rowG = new Int32Array(rows);
    const colG = new Int32Array(cols);
    for (let i = 0; i < rows; i++) rowG[i] = Math.min(WR - 1, Math.floor((i * WR) / rows));
    for (let i = 0; i < cols; i++) colG[i] = Math.min(WC - 1, Math.floor((i * WC) / cols));
    const wgrid = new Float64Array(WR * WC);
    for (let c = 0; c < cols; c++) for (let r = 0; r < rows; r++) wgrid[colG[c] * WR + rowG[r]] += total[c * rows + r];

    const t0 = candles[0].ts;
    const t1 = candles[cols - 1].ts;
    const span = Math.max(1, t1 - t0);
    const wash: { x: number; y: number; w: number; h: number; v: number; price: number }[] = [];
    for (let c = 0; c < WC; c++) {
      for (let r = 0; r < WR; r++) {
        const v = wgrid[c * WR + r];
        if (v <= 0) continue;
        const r0 = Math.floor((r * rows) / WR);
        const r1 = Math.min(rows - 1, Math.floor(((r + 1) * rows) / WR) - 1);
        wash.push({
          x: (c * 100) / WC,
          y: (r * 100) / WR,
          w: 100 / WC,
          h: 100 / WR,
          v,
          price: (yAxis[r0] + yAxis[r1]) / 2,
        });
      }
    }

    // close row (page: h = row of the last close — the wall side decision)
    const closeRow = Math.min(rows - 1, Math.max(0, Math.floor((lastPrice - lo) / bin)));
    const rowPx = height / rows;

    // wall draw geometry (page drawWalls: tier vs band height, cap 16)
    const geo = walls.map((w) => {
      const bandPx = (w.rmax - w.rmin + 1) * rowPx;
      const tier = w.n >= 0.85 ? 11 : w.n >= 0.65 ? 8 : w.n >= 0.45 ? 5 : 3;
      const th = Math.max(tier, Math.min(bandPx, 16));
      const midPrice = lo + ((w.rmin + w.rmax + 1) / 2) * bin;
      const x0 = ((candles[w.c0].ts - t0) / span) * 100;
      const x1 = Math.min(100, ((candles[Math.min(w.c1, cols - 1)].ts - t0) / span) * 100 + (100 / cols) * 0.9);
      return {
        w,
        th,
        midPrice,
        x0,
        x1,
        active: w.c1 >= cols - 1,
        side: w.rpk > closeRow ? ("short" as const) : ("long" as const),
      };
    });

    // labels: top 14 by score, 11 px vertical dedup (page)
    const pHi = yAxis[rows - 1] + bin / 2;
    const pLo = yAxis[0] - bin / 2;
    const labelYs: number[] = [];
    const labels = geo.slice(0, 14).filter((g) => {
      const yPx = ((pHi - g.midPrice) / (pHi - pLo)) * height;
      if (labelYs.some((e) => Math.abs(e - yPx) < 11)) return false;
      labelYs.push(yPx);
      return true;
    });

    // max callouts: strongest short wall + strongest long wall
    const maxShort = geo.filter((g) => g.side === "short").reduce<null | (typeof geo)[number]>((m, g) => (!m || g.w.mx > m.w.mx ? g : m), null);
    const maxLong = geo.filter((g) => g.side === "long").reduce<null | (typeof geo)[number]>((m, g) => (!m || g.w.mx > m.w.mx ? g : m), null);

    return { rows, cols, lo, bin, t0, t1, span, maxVal, walls, geo, wash, closeRow, labels, maxShort, maxLong, pLo, pHi };
  }, [model, intensityMin, height]);

  if (!W) return <div className="flex h-40 items-center justify-center text-xs text-neutral-500">No grid data.</div>;

  const scheme = COLORSCHEMES[colors] ?? COLORSCHEMES.viridis;
  const yPct = (p: number) => ((W.pHi - p) / (W.pHi - W.pLo)) * 100;
  const xPct = (ts: number) => ((ts - W.t0) / W.span) * 100;

  // price + time axis ticks
  const step = niceStep(W.pHi - W.pLo, 7);
  const ticks: number[] = [];
  for (let p = Math.ceil(W.pLo / step) * step; p <= W.pHi; p += step) ticks.push(p);
  const tEvery = Math.max(1, Math.ceil(W.cols / 7));

  const hoverGeo = hover !== null ? W.geo[hover] : null;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-col rounded-lg border border-neutral-800 bg-[#0a0e13]">
        <div className="relative w-full" style={{ height }}>
          {/* SVG layer 1: faint heat wash behind the walls (page: α .14) */}
          <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
            <g opacity={0.14}>
              {W.wash.map((c, i) => (
                <rect
                  key={i}
                  x={c.x}
                  y={c.y}
                  width={c.w}
                  height={c.h}
                  fill={heatColor(scheme, c.v, W.maxVal, c.price, model.lastPrice)}
                />
              ))}
            </g>
          </svg>

          {/* walls — positioned divs: exact px thickness, rounded, hover */}
          {W.geo.map((g, i) => {
            // page: es(L.main, max(.35, n)) — LUT at peak NORM, floored at .35
            const bg = split
              ? g.side === "short"
                ? "rgba(225,63,63,0.92)"
                : "rgba(22,142,132,0.92)"
              : lutAt(scheme, Math.max(0.35, g.w.n), g.midPrice < model.lastPrice && scheme.below !== undefined);
            return (
              <div
                key={i}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                className={`absolute cursor-crosshair transition-[filter] ${hover === i ? "brightness-125" : ""}`}
                style={{
                  left: `${g.x0}%`,
                  width: `${Math.max(0.3, g.x1 - g.x0)}%`,
                  top: `calc(${yPct(g.midPrice)}% - ${g.th / 2}px)`,
                  height: `${g.th}px`,
                  background: bg,
                  borderRadius: Math.min(3, g.th / 2),
                  opacity: 0.92,
                  boxShadow: hover === i ? "0 0 0 1px rgba(255,255,255,0.55)" : "0 0 0 1px rgba(10,14,19,0.7)",
                }}
                title={`${fmtP(g.w.price)} · ${compact(g.w.mx)} · ${g.active ? "active" : "swept"}`}
              />
            );
          })}

          {/* SVG layer 2: mono candles (page walls lens) */}
          {showCandles && (
            <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden>
              {model.candles.map((cd, i) => {
                const x = xPct(cd.ts) * 10 + (100 / W.cols) * 5;
                const up = cd.c >= cd.o;
                const col = up ? "#e8eaed" : "#8a93a0";
                const yH = yPct(cd.h) * 10;
                const yL = yPct(cd.l) * 10;
                const yO = yPct(cd.o) * 10;
                const yC = yPct(cd.c) * 10;
                const bw = Math.max(6, (100 / W.cols) * 6);
                return (
                  <g key={i} stroke={col} fill={col} opacity={0.85}>
                    <line x1={x} y1={yH} x2={x} y2={yL} strokeWidth={1} vectorEffect="non-scaling-stroke" />
                    <rect x={x - bw / 2} y={Math.min(yO, yC)} width={bw} height={Math.max(8, Math.abs(yC - yO))} />
                  </g>
                );
              })}
            </svg>
          )}

          {/* dashed current-price line */}
          <div className="pointer-events-none absolute left-0 right-0 border-t border-dashed border-white/50" style={{ top: `${yPct(model.lastPrice)}%` }} />

          {/* max callouts (page: dashed line + chip on the strongest clusters) */}
          {W.maxShort && (
            <div className="pointer-events-none absolute left-0 right-0 border-t border-dashed border-red-400/60" style={{ top: `${yPct(W.maxShort.w.price)}%` }}>
              <span className="absolute left-1 -top-2.5 rounded bg-red-500/20 px-1 text-[9px] font-medium text-red-300">
                Max short liquidation · {compact(W.maxShort.w.mx)} ›
              </span>
            </div>
          )}
          {W.maxLong && (
            <div className="pointer-events-none absolute left-0 right-0 border-t border-dashed border-amber-300/60" style={{ top: `${yPct(W.maxLong.w.price)}%` }}>
              <span className="absolute left-1 -top-2.5 rounded bg-amber-400/15 px-1 text-[9px] font-medium text-amber-200">
                Max long liquidation · {compact(W.maxLong.w.mx)} ›
              </span>
            </div>
          )}

          {/* price axis labels (right gutter) */}
          {ticks.map((p) => (
            <span
              key={p}
              className="pointer-events-none absolute right-1 -translate-y-1/2 font-mono text-[9px] text-neutral-500"
              style={{ top: `${yPct(p)}%` }}
            >
              {fmtP(p)}
            </span>
          ))}

          {/* current price pill */}
          <span
            className="pointer-events-none absolute right-1 z-10 -translate-y-1/2 rounded bg-neutral-50 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-neutral-900"
            style={{ top: `${yPct(model.lastPrice)}%` }}
          >
            {fmtP(model.lastPrice)}
          </span>

          {/* wall labels — top 14: active walls in the right gutter, swept at their right end */}
          {W.labels.map((g, i) => {
            const y = yPct(g.midPrice);
            const txt = `${fmtP(g.w.price)} · ${compact(g.w.mx)}`;
            if (g.active) {
              return (
                <span
                  key={i}
                  className="pointer-events-none absolute z-10 -translate-y-1/2 whitespace-nowrap rounded border border-neutral-600 bg-neutral-950/90 px-1 font-mono text-[9px] text-neutral-200"
                  style={{ top: `${y}%`, right: "64px" }}
                >
                  {txt}
                </span>
              );
            }
            return (
              <span
                key={i}
                className="pointer-events-none absolute z-10 whitespace-nowrap rounded border border-neutral-700 bg-neutral-950/85 px-1 font-mono text-[9px] text-neutral-300"
                style={{ top: `${y}%`, left: `${g.x1}%`, transform: "translate(-100%, -50%)" }}
              >
                {txt}
              </span>
            );
          })}
        </div>

        {/* time axis */}
        <div className="relative h-5 border-t border-neutral-800/60">
          {model.candles.map((cd, i) =>
            i % tEvery === 0 ? (
              <span
                key={i}
                className="absolute top-0.5 -translate-x-1/2 whitespace-nowrap font-mono text-[8px] text-neutral-500"
                style={{ left: `${xPct(cd.ts)}%` }}
              >
                {fmtClock(cd.ts)}
              </span>
            ) : null
          )}
        </div>
      </div>

      {/* legend + hover info bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-[9px] text-neutral-500">
        <div className="flex items-center gap-1.5">
          <span>≥ {Math.round(intensityMin * 100)}%</span>
          <span className="inline-block h-2 w-24 rounded-sm" style={{ background: `linear-gradient(to right, ${legendCss(colors)})` }} />
          <span>100% · {compact(W.maxVal)} per cell</span>
          <span className="text-neutral-600">· 1 price row = {(height / W.rows).toFixed(1)}px fixed</span>
        </div>
        <div className="font-mono">
          {hoverGeo ? (
            <>
              <span className="text-neutral-400">{fmtClock(model.candles[hoverGeo.w.c0].ts)}</span>
              <span className="text-neutral-600"> → </span>
              <span className="text-neutral-400">
                {hoverGeo.active ? "active (not swept)" : fmtClock(model.candles[Math.min(hoverGeo.w.c1, W.cols - 1)].ts)}
              </span>
              <span className="text-neutral-600"> · </span>
              <span className={hoverGeo.side === "short" ? "text-red-400" : "text-emerald-400"}>
                {hoverGeo.side === "short" ? "shorts" : "longs"} {fmtP(hoverGeo.w.price)}
              </span>
              <span className="text-neutral-600"> · </span>
              <span className="text-neutral-200">{fmtUsd(hoverGeo.w.mx)}</span>
              <span className="text-neutral-600"> · peak {Math.round(hoverGeo.w.n * 100)}% · {hoverGeo.w.c1 - hoverGeo.w.c0 + 1} cols</span>
            </>
          ) : (
            <span className="text-neutral-600">
              {W.walls.length} walls of top-24 · hover a wall — formed → swept, price, size, peak
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
