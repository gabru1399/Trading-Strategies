/**
 * Coinglass Liquidation-HeatMap colour schemes — exact port of the live
 * page's stop lists (mined from %5Bsymbol%5D-e61edde946656ec4.js, 2026-11-22).
 * Shared by the table grid (and any future lens renderers).
 *
 * Single-ramp schemes paint every cell from one LUT; two-tone schemes
 * (Rose/Mint, Amber/Azure, Violet/Lime) paint above-price rows with the
 * "above" ramp and below-price rows with the mirrored "below" ramp — the
 * page's long/short split at the current price.
 */

export type Stop = [number, number, number]; // rgb

const hex = (h: string): Stop => {
  const v = h.replace("#", "");
  const n = parseInt(v.length === 3 ? v.split("").map((c) => c + c).join("") : v, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

const mix = (a: Stop, b: Stop, t: number): Stop => [
  Math.round(a[0] + (b[0] - a[0]) * t),
  Math.round(a[1] + (b[1] - a[1]) * t),
  Math.round(a[2] + (b[2] - a[2]) * t),
];

/** build a 256-entry LUT: floor colour at 0, then the stops evenly spaced */
const lut = (floor: string, stops: string[]): Stop[] => {
  const cols = stops.map(hex);
  const out: Stop[] = new Array(256);
  for (let i = 0; i < 256; i++) {
    const t = i / 255;
    if (t === 0) {
      out[i] = hex(floor ?? stops[0]);
      continue;
    }
    const x = t * (cols.length - 1);
    const i0 = Math.min(cols.length - 2, Math.floor(x));
    out[i] = mix(cols[i0], cols[i0 + 1], x - i0);
  }
  return out;
};

export interface ColorScheme {
  label: string;
  /** ramp for rows above the current price (short liquidations) */
  above: Stop[];
  /** ramp for rows below the current price (long liquidations); two-tone only */
  below?: Stop[];
}

export const COLORSCHEMES: Record<string, ColorScheme> = {
  viridis: {
    label: "Viridis",
    above: lut("#440053", ["#3e1c62", "#363872", "#2f5381", "#297090", "#24888a", "#1fa084", "#3bb66d", "#6bc94e", "#afd929", "#f2e805"]),
  },
  deep: {
    label: "Deep Blue",
    above: lut("#000031", ["#0000f4", "#0066f4", "#15ffea", "#ffb700"]),
  },
  magma: {
    label: "Magma",
    above: lut("#06020d", ["#190831", "#2f1055", "#4c1a69", "#772d6d", "#9f3e71", "#bd4e71", "#ce5b6c", "#e16968", "#ea927f", "#f1c4a0", "#faf1be"]),
  },
  ocean: {
    label: "Ocean",
    above: lut("#0b1d4d", ["#0b1d4d", "#13348f", "#1b5fc4", "#2491de", "#39c3e6", "#9df0f5", "#ffffff"]),
  },
  spectrum: {
    label: "Spectrum",
    above: lut("#1b3a99", ["#1b3a99", "#1e7fd4", "#17b1a4", "#3dc24c", "#d2e01c", "#ffb000", "#ff6a00", "#e5322d"]),
  },
  roseMint: {
    label: "Rose / Mint",
    above: lut("#202127", ["#48254c", "#8e4696", "#d96be4", "#f9dcff"]),
    below: lut("#202127", ["#174844", "#168e84", "#4bcac0", "#c6f4ed"]),
  },
  amberAzure: {
    label: "Amber / Azure",
    above: lut("#1c2029", ["#593723", "#ad6038", "#efaa52", "#ffe3a2"]),
    below: lut("#1c2029", ["#193f6a", "#246cae", "#54b3ee", "#d1efff"]),
  },
};

export const COLORSCHEME_IDS = Object.keys(COLORSCHEMES);

/** rgb → css string */
export const css = (s: Stop, a = 1): string => `rgba(${s[0]},${s[1]},${s[2]},${a})`;

/**
 * Cell colour for a heat value.
 * intensity = (usd / max)^gamma (page "Heat" lens: γ = 0.7); two-tone
 * schemes pick the ramp by side of the current price.
 */
export function heatColor(
  scheme: ColorScheme,
  usd: number,
  max: number,
  price: number,
  lastPrice: number,
  gamma = 0.7
): string {
  const t = max > 0 ? Math.min(1, Math.pow(usd / max, gamma)) : 0;
  const rows = price < lastPrice && scheme.below ? scheme.below : scheme.above;
  return css(rows[Math.min(255, Math.round(t * 255))]);
}

/** legend gradient css for a scheme */
export function legendCss(colors: string): string {
  const scheme = COLORSCHEMES[colors] ?? COLORSCHEMES.viridis;
  const stops = scheme.above;
  const pick = [0, 0.35, 0.65, 1].map((t) => css(stops[Math.min(255, Math.round(t * 255))]));
  return pick.join(", ");
}

/** compact USD, Coinglass style ($1.23B / $4.5M / $890K) */
export function fmtUsd(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}
