"use client";

import { useMemo, useState } from "react";
import { COLORSCHEMES, heatColor, legendCss, fmtUsd } from "./heatmap-colormaps";

/**
 * Coinglass-style Liquidation-HeatMap rendered as a real DOM table —
 * rows = price levels, columns = time buckets, cell background = heat colour
 * (the page's exact colormaps, γ=0.7 like its "Heat" lens).
 *
 * The raw Model-1 grid can be 154 rows × 284 columns, so a Detail control
 * aggregates neighbouring price bins / time columns (summing their USD — a
 * merged wall reads brighter, exactly like zooming the page out):
 *
 *   low  · ~24 price rows × ~36 time cols  — cell values printable
 *   mid  · ~48 × ~72                       (default)
 *   high · ~96 × ~144
 *   full · every bin × every column
 *
 * Extras carried over from the page: key-level rows get a price·$size chip,
 * the current-price row is flagged, the candle-close path is a dot trail,
 * the right edge shows each row's time-summed total, and hovering a cell
 * prints time · price · size · share in the info bar below.
 */

export interface HeatmapTableModel {
  yAxis: number[];
  columns: { ts: number; cells: [number, number][] }[];
  candles: { ts: number; o: number; h: number; l: number; c: number }[];
  keyLevels: { above: { price: number; usd: number }[]; below: { price: number; usd: number }[] };
  lastPrice: number;
  priceStep: number;
  columnMinutes: number;
  updateTime: number;
}

export type DetailLevel = "low" | "mid" | "high" | "full";

const DETAIL_PRESET: Record<DetailLevel, { rows: number; cols: number; cellW: number; cellH: number }> = {
  low: { rows: 24, cols: 36, cellW: 16, cellH: 18 },
  mid: { rows: 48, cols: 72, cellW: 9, cellH: 10 },
  high: { rows: 96, cols: 144, cellW: 5, cellH: 6 },
  full: { rows: Infinity, cols: Infinity, cellW: 3, cellH: 4 },
};

const pad = (n: number) => String(n).padStart(2, "0");
const fmtClock = (ts: number) => {
  const d = new Date(ts);
  return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

/** partition [0..n) into `k` near-equal consecutive groups; returns group index per item */
function groupOf(n: number, k: number): Int32Array {
  const out = new Int32Array(n);
  const g = Math.max(1, Math.min(k, n));
  for (let i = 0; i < n; i++) out[i] = Math.min(g - 1, Math.floor((i * g) / n));
  return out;
}

export default function CoinglassHeatmapTable({
  model,
  colors = "viridis",
  intensityMin = 0,
  detail = "mid",
  showCandles = true,
  showValues = false,
  priceDecs = 2,
}: {
  model: HeatmapTableModel;
  colors?: string;
  intensityMin?: number;
  detail?: DetailLevel;
  showCandles?: boolean;
  showValues?: boolean;
  priceDecs?: number;
}) {
  const [hover, setHover] = useState<{ r: number; c: number } | null>(null);

  // ---- aggregation (useMemo: grid rebuilds only when model/detail change) ----
  const agg = useMemo(() => {
    const { yAxis, columns, candles, keyLevels, lastPrice } = model;
    const preset = DETAIL_PRESET[detail];
    const nR = yAxis.length;

    // candle ts → index (columns carry the ts of their candle)
    const tsIdx = new Map<number, number>();
    candles.forEach((cd, i) => tsIdx.set(cd.ts, i));

    const rowG = groupOf(nR, preset.rows);
    const nCol = candles.length;
    const colG = groupOf(nCol, preset.cols);
    const nRowG = Math.max(1, Math.min(preset.rows, nR));
    const nColG = Math.max(1, Math.min(preset.cols, nCol));

    const grid: number[][] = Array.from({ length: nRowG }, () => new Array<number>(nColG).fill(0));
    const rowLo = new Array<number>(nRowG).fill(Infinity);
    const rowHi = new Array<number>(nRowG).fill(-Infinity);
    for (let i = 0; i < nR; i++) {
      const g = rowG[i];
      rowLo[g] = Math.min(rowLo[g], yAxis[i] - model.priceStep / 2);
      rowHi[g] = Math.max(rowHi[g], yAxis[i] + model.priceStep / 2);
    }

    for (const bar of columns) {
      const ci = tsIdx.get(bar.ts);
      if (ci === undefined) continue;
      const cg = colG[ci];
      for (const [yi, usd] of bar.cells) {
        grid[rowG[yi]][cg] += usd;
      }
    }

    // per-column totals + max over aggregated cells (rescaled per detail,
    // like the page re-normalising contrast when you zoom out)
    const colTotals = new Array<number>(nColG).fill(0);
    let max = 0;
    for (let r = 0; r < nRowG; r++) {
      for (let c = 0; c < nColG; c++) {
        const v = grid[r][c];
        colTotals[c] += v;
        if (v > max) max = v;
      }
    }

    // row time-summed totals (right column) + row max for its own tint
    const rowTotals = grid.map((row) => row.reduce((a, b) => a + b, 0));
    const rowMax = Math.max(1, ...rowTotals);

    // key levels → strongest key falling inside each row band
    const keyByRow = new Map<number, { price: number; usd: number; side: "above" | "below" }>();
    for (const side of ["above", "below"] as const) {
      for (const k of keyLevels[side]) {
        for (let r = 0; r < nRowG; r++) {
          if (k.price >= rowLo[r] && k.price <= rowHi[r]) {
            const prev = keyByRow.get(r);
            if (!prev || k.usd > prev.usd) keyByRow.set(r, { ...k, side });
            break;
          }
        }
      }
    }

    // current-price row + candle-close row trail
    const lastRow = rowG[Math.min(nR - 1, Math.max(0, Math.round((lastPrice - yAxis[0]) / model.priceStep)))];
    const closeRow: number[] = new Array(nColG).fill(-1);
    for (let ci = 0; ci < nCol; ci++) {
      const c = candles[ci].c;
      let best = 0;
      let bd = Infinity;
      for (let i = 0; i < nR; i++) {
        const d = Math.abs(yAxis[i] - c);
        if (d < bd) {
          bd = d;
          best = i;
        }
      }
      closeRow[colG[ci]] = rowG[best];
    }

    // display rows top (highest price) → bottom
    const rowsDesc = Array.from({ length: nRowG }, (_, i) => nRowG - 1 - i);

    return {
      grid, rowLo, rowHi, colTotals, max, rowTotals, rowMax, keyByRow, lastRow, closeRow,
      rowsDesc, nRowG, nColG,
      colLabel: (cg: number) => {
        // label from the first candle in that column group
        const first = candles.findIndex((_, i) => colG[i] === cg);
        return first >= 0 ? candles[first].ts : candles[0].ts;
      },
      colSpanOf: (cg: number) => candles.reduce((a, _, i) => a + (colG[i] === cg ? 1 : 0), 0),
    };
  }, [model, detail]);

  const scheme = COLORSCHEMES[colors] ?? COLORSCHEMES.viridis;
  const preset = DETAIL_PRESET[detail];
  const threshold = intensityMin * agg.max;
  const fmtP = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: priceDecs, maximumFractionDigits: priceDecs });

  // label every k-th column so the header stays readable
  const labelEvery = Math.max(1, Math.ceil(agg.nColG / 10));
  const hoverCell = (() => {
    if (!hover) return null;
    const v = agg.grid[hover.r]?.[hover.c] ?? 0;
    const lo = agg.rowLo[hover.r];
    const hi = agg.rowHi[hover.r];
    const price = (lo + hi) / 2;
    const ts = agg.colLabel(hover.c);
    return {
      v,
      price,
      lo,
      hi,
      ts,
      share: agg.max > 0 ? (v / agg.max) * 100 : 0,
      side: price > model.lastPrice ? ("above" as const) : ("below" as const),
      colTotal: agg.colTotals[hover.c],
    };
  })();

  const totalCells = agg.nRowG * agg.nColG;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="max-h-[540px] overflow-auto rounded-lg border border-neutral-800 bg-[#0a0e13]">
        <table
          className="border-separate border-spacing-0 font-mono text-[9px] leading-none"
          style={{ borderCollapse: "separate" }}
          onMouseMove={(e) => {
            const td = (e.target as HTMLElement).closest("td[data-r]");
            if (!td) return;
            const r = Number(td.getAttribute("data-r"));
            const c = Number(td.getAttribute("data-c"));
            if (Number.isFinite(r) && Number.isFinite(c)) setHover({ r, c });
          }}
          onMouseLeave={() => setHover(null)}
        >
          <thead className="sticky top-0 z-20">
            <tr>
              <th className="sticky left-0 z-30 min-w-[86px] border-b border-r border-neutral-800 bg-neutral-900 px-1.5 py-1 text-left text-[9px] font-normal text-neutral-500">
                price ▾
              </th>
              {Array.from({ length: agg.nColG }, (_, c) => (
                <th
                  key={c}
                  className="border-b border-neutral-800/60 bg-neutral-900 px-0 py-1 text-center font-normal text-neutral-500"
                  style={{ minWidth: preset.cellW, height: 14 }}
                >
                  {c % labelEvery === 0 ? (
                    <span className="whitespace-nowrap text-[8px]">{fmtClock(agg.colLabel(c)).slice(detail === "low" ? 0 : 6)}</span>
                  ) : (
                    ""
                  )}
                </th>
              ))}
              <th className="sticky right-0 z-30 min-w-[54px] border-b border-l border-neutral-800 bg-neutral-900 px-1 py-1 text-right text-[8px] font-normal text-neutral-500">
                Σ row
              </th>
            </tr>
          </thead>
          <tbody>
            {agg.rowsDesc.map((r) => {
              const key = agg.keyByRow.get(r);
              const isLast = r === agg.lastRow;
              return (
                <tr key={r}>
                  <th
                    className={`sticky left-0 z-10 border-b border-r border-neutral-800/60 bg-neutral-900 px-1.5 text-left font-normal ${
                      isLast ? "text-neutral-50" : key ? "text-neutral-200" : "text-neutral-500"
                    }`}
                    style={{ height: preset.cellH }}
                  >
                    <span className="flex items-center gap-1 whitespace-nowrap">
                      {isLast && <span className="text-amber-300">▸</span>}
                      {fmtP((agg.rowLo[r] + agg.rowHi[r]) / 2)}
                      {key && (
                        <span
                          className={`rounded px-1 text-[8px] ${
                            key.side === "above" ? "bg-red-500/20 text-red-300" : "bg-emerald-500/20 text-emerald-300"
                          }`}
                        >
                          {fmtUsd(key.usd)}
                        </span>
                      )}
                    </span>
                  </th>
                  {Array.from({ length: agg.nColG }, (_, c) => {
                    const v = agg.grid[r][c];
                    const bg =
                      v >= threshold && v > 0
                        ? heatColor(scheme, v, agg.max, (agg.rowLo[r] + agg.rowHi[r]) / 2, model.lastPrice)
                        : undefined;
                    const isClose = showCandles && agg.closeRow[c] === r;
                    const printVal = showValues && detail === "low" && v >= threshold && v > 0;
                    return (
                      <td
                        key={c}
                        data-r={r}
                        data-c={c}
                        title={`${fmtClock(agg.colLabel(c))} · ${fmtP((agg.rowLo[r] + agg.rowHi[r]) / 2)} · ${fmtUsd(v)}`}
                        className={`border-b border-neutral-900/40 p-0 text-center ${hover && hover.r === r && hover.c === c ? "outline outline-1 outline-neutral-300" : ""}`}
                        style={{ background: bg, minWidth: preset.cellW, maxWidth: preset.cellW, height: preset.cellH }}
                      >
                        {printVal ? (
                          <span className="text-[7px] text-black/70">{v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${Math.round(v / 1e3)}K` : ""}</span>
                        ) : isClose ? (
                          <span className="text-white drop-shadow">•</span>
                        ) : (
                          ""
                        )}
                      </td>
                    );
                  })}
                  <th
                    className="sticky right-0 z-10 border-b border-l border-neutral-800/60 px-1 text-right font-normal text-neutral-300"
                    style={{
                      height: preset.cellH,
                      background: agg.rowTotals[r] > 0 ? heatColor(scheme, agg.rowTotals[r], agg.rowMax, (agg.rowLo[r] + agg.rowHi[r]) / 2, model.lastPrice) : undefined,
                    }}
                    title={`time-summed ${fmtUsd(agg.rowTotals[r])}`}
                  >
                    <span className="whitespace-nowrap text-[8px]">{agg.rowTotals[r] > 0 ? fmtUsd(agg.rowTotals[r]).replace("$", "") : ""}</span>
                  </th>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* legend + hover info bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-[9px] text-neutral-500">
        <div className="flex items-center gap-1.5">
          <span>≥ {Math.round(intensityMin * 100)}%</span>
          <span className="inline-block h-2 w-24 rounded-sm" style={{ background: `linear-gradient(to right, ${legendCss(colors)})` }} />
          <span>100% · {fmtUsd(agg.max)} per cell</span>
        </div>
        <div className="font-mono">
          {hoverCell ? (
            <>
              <span className="text-neutral-400">{fmtClock(hoverCell.ts)}</span>
              <span className="text-neutral-600"> · </span>
              <span className={hoverCell.side === "above" ? "text-red-400" : "text-emerald-400"}>
                {hoverCell.side === "above" ? "shorts" : "longs"} {fmtP(hoverCell.lo)}–{fmtP(hoverCell.hi)}
              </span>
              <span className="text-neutral-600"> · </span>
              <span className="text-neutral-200">{fmtUsd(hoverCell.v)}</span>
              <span className="text-neutral-600"> · {hoverCell.share.toFixed(1)}% of max · col Σ {fmtUsd(hoverCell.colTotal)}</span>
            </>
          ) : (
            <span className="text-neutral-600">
              hover a cell — {agg.nRowG} price rows × {agg.nColG} time cols ({totalCells.toLocaleString()} cells)
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
