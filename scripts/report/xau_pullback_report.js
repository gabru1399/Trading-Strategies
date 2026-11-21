/**
 * XAU Liquidation Pullback-Magnet Report — generated from live data
 * (scripts/research/xau-pullback-levels.json, fetched 2026-11-21).
 * Cover: R1 (Pure Paragraph Left) with IG-1 Ink Gold palette (finance).
 * Font profile A (formal). English document (user's working language).
 */
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, WidthType, BorderStyle, TableLayoutType,
  ShadingType, PageBreak, TableOfContents, NumberFormat, Footer, PageNumber,
  HeightRule,
} = require("docx");
const fs = require("fs");

const DATA = JSON.parse(fs.readFileSync("/home/z/my-project/scripts/research/xau-pullback-levels.json", "utf8"));
const OUT = "/home/z/my-project/download/XAU-Liquidation-Pullback-Magnets.docx";

// ---------- palette (IG-1 Ink Gold) ----------
const P = {
  bg: "1A1A1A", accent: "C9A84C",
  titleColor: "FFFFFF", subtitleColor: "B0B8C0", metaColor: "90989F", footerColor: "687078",
  tableHeaderBg: "C9A84C", tableHeaderText: "1A1A1A", innerLine: "DDD5C0", surface: "F5F2E8",
};
const NB = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const allNoBorders = { top: NB, bottom: NB, left: NB, right: NB, insideHorizontal: NB, insideVertical: NB };

// ---------- helpers ----------
function calcTitleLayout(title, maxWidthTwips, preferredPt = 40, minPt = 24) {
  const charWidth = (pt) => pt * 20;
  const charsPerLine = (pt) => Math.floor(maxWidthTwips / charWidth(pt));
  let titlePt = preferredPt, lines;
  while (titlePt >= minPt) {
    const cpl = charsPerLine(titlePt);
    if (cpl < 2) { titlePt -= 2; continue; }
    lines = splitTitleLines(title, cpl);
    if (lines.length <= 3) break;
    titlePt -= 2;
  }
  if (!lines || lines.length > 3) { lines = splitTitleLines(title, charsPerLine(minPt)); titlePt = minPt; }
  return { titlePt, titleLines: lines };
}
function splitTitleLines(title, charsPerLine) {
  if (title.length <= charsPerLine) return [title];
  const words = title.split(" ");
  const lines = []; let cur = "";
  for (const w of words) {
    if ((cur + " " + w).trim().length > charsPerLine && cur) { lines.push(cur.trim()); cur = w; }
    else cur = (cur + " " + w).trim();
  }
  if (cur) lines.push(cur.trim());
  if (lines.length > 1 && lines[lines.length - 1].length < 8) {
    const last = lines.pop(); lines[lines.length - 1] += " " + last;
  }
  return lines;
}
function calcCoverSpacing(params) {
  const { titleLineCount = 1, titlePt = 36, hasSubtitle = false, hasEnglishLabel = false,
    metaLineCount = 0, fixedHeight = 800, pageHeight = 16838 } = params;
  const SAFETY = 1200;
  const usableHeight = pageHeight - SAFETY;
  const titleHeight = titleLineCount * (titlePt * 23 + 200);
  const subtitleHeight = hasSubtitle ? (12 * 23 + 600) : 0;
  const englishLabelHeight = hasEnglishLabel ? (9 * 23 + 600) : 0;
  const metaHeight = metaLineCount * (10 * 23 + 100);
  const implicitParaHeight = 3 * 300;
  const contentHeight = titleHeight + subtitleHeight + englishLabelHeight + metaHeight + fixedHeight + implicitParaHeight;
  const safeRemaining = Math.max(usableHeight - contentHeight, 400);
  const FOOTER_MIN = 800;
  const rawTop = Math.floor(safeRemaining * 0.45), rawBottom = Math.floor(safeRemaining * 0.45);
  const bottomSpacing = Math.max(rawBottom, FOOTER_MIN);
  const topSpacing = Math.max(rawTop - Math.max(0, FOOTER_MIN - rawBottom), 400);
  return { topSpacing, bottomSpacing };
}

// ---------- cover (R1) ----------
function buildCoverR1(config) {
  const padL = 1200, padR = 800;
  const availableWidth = 11906 - padL - padR - 300;
  const { titlePt, titleLines } = calcTitleLayout(config.title, availableWidth, 40, 24);
  const titleSize = titlePt * 2;
  const spacing = calcCoverSpacing({
    titleLineCount: titleLines.length, titlePt,
    hasSubtitle: !!config.subtitle, hasEnglishLabel: !!config.englishLabel,
    metaLineCount: (config.metaLines || []).length, fixedHeight: 400,
  });
  const accentLeft = { style: BorderStyle.SINGLE, size: 8, color: P.accent, space: 12 };
  const children = [];
  children.push(new Paragraph({ spacing: { before: spacing.topSpacing } }));
  if (config.englishLabel) {
    children.push(new Paragraph({
      indent: { left: padL, right: padR }, spacing: { after: 500 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: P.accent, space: 8 } },
      children: [new TextRun({ text: config.englishLabel.split("").join("  "), size: 18, color: P.accent, font: { ascii: "Calibri", eastAsia: "SimHei" } })],
    }));
  }
  for (let i = 0; i < titleLines.length; i++) {
    children.push(new Paragraph({
      indent: { left: padL },
      spacing: { after: i < titleLines.length - 1 ? 100 : 300, line: Math.ceil(titlePt * 23), lineRule: "atLeast" },
      children: [new TextRun({ text: titleLines[i], size: titleSize, bold: true, color: P.titleColor, font: { eastAsia: "SimHei", ascii: "Arial" } })],
    }));
  }
  if (config.subtitle) {
    children.push(new Paragraph({
      indent: { left: padL }, spacing: { after: 800 },
      children: [new TextRun({ text: config.subtitle, size: 24, color: P.subtitleColor, font: { eastAsia: "Microsoft YaHei", ascii: "Arial" } })],
    }));
  }
  for (const line of (config.metaLines || [])) {
    children.push(new Paragraph({
      indent: { left: padL + 200 }, spacing: { after: 80 },
      border: { left: accentLeft },
      children: [new TextRun({ text: line, size: 24, color: P.metaColor, font: { eastAsia: "Microsoft YaHei", ascii: "Arial" } })],
    }));
  }
  children.push(new Paragraph({ spacing: { before: spacing.bottomSpacing } }));
  children.push(new Paragraph({
    indent: { left: padL, right: padR },
    border: { top: { style: BorderStyle.SINGLE, size: 2, color: P.accent, space: 8 } },
    spacing: { before: 200 },
    children: [
      new TextRun({ text: config.footerLeft || "", size: 16, color: P.footerColor, font: { ascii: "Arial" } }),
      new TextRun({ text: "                                        " }),
      new TextRun({ text: config.footerRight || "", size: 16, color: P.footerColor, font: { ascii: "Arial" } }),
    ],
  }));
  return [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED,
    borders: allNoBorders,
    rows: [new TableRow({
      height: { value: 16838, rule: HeightRule.EXACT },
      children: [new TableCell({
        borders: allNoBorders,
        shading: { type: ShadingType.CLEAR, fill: P.bg, color: "auto" },
        margins: { left: 0, right: 0 },
        verticalAlign: "top",
        children,
      })],
    })],
  })];
}

// ---------- body helpers ----------
const cellMargins = { top: 60, bottom: 60, left: 120, right: 120 };
const thinLine = { style: BorderStyle.SINGLE, size: 4, color: P.innerLine };
const tableBorders = { top: thinLine, bottom: thinLine, left: thinLine, right: thinLine, insideHorizontal: thinLine, insideVertical: thinLine };

function h1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 200, line: 312 }, keepNext: true,
    children: [new TextRun({ text, bold: true, color: "1A1A1A", font: { ascii: "Arial", eastAsia: "SimHei" }, size: 32 })] });
}
function h2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 280, after: 160, line: 312 }, keepNext: true,
    children: [new TextRun({ text, bold: true, color: "3A3A3A", font: { ascii: "Arial", eastAsia: "SimHei" }, size: 26 })] });
}
function body(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 120, line: 312 },
    alignment: AlignmentType.JUSTIFIED,
    children: [new TextRun({ text, size: 22, color: "222222", font: { ascii: "Times New Roman", eastAsia: "SimSun" }, ...opts })] });
}
function bodyRuns(runs) {
  return new Paragraph({
    spacing: { after: 120, line: 312 }, alignment: AlignmentType.JUSTIFIED,
    children: runs.map(r => new TextRun({ size: 22, color: "222222", font: { ascii: "Times New Roman", eastAsia: "SimSun" }, ...r })) });
}
function note(text) {
  return new Paragraph({ spacing: { after: 120, line: 312 }, alignment: AlignmentType.LEFT,
    children: [new TextRun({ text, size: 20, italics: true, color: "666666", font: { ascii: "Times New Roman", eastAsia: "SimSun" } })] });
}
function th(text, w) {
  return new TableCell({
    width: w ? { size: w, type: WidthType.PERCENTAGE } : undefined,
    margins: cellMargins, shading: { type: ShadingType.CLEAR, fill: P.tableHeaderBg, color: "auto" },
    children: [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { line: 276 },
      children: [new TextRun({ text, bold: true, size: 20, color: P.tableHeaderText, font: { ascii: "Arial", eastAsia: "SimHei" } })] })],
  });
}
function td(text, opts = {}) {
  return new TableCell({
    margins: cellMargins,
    shading: opts.fill ? { type: ShadingType.CLEAR, fill: opts.fill, color: "auto" } : undefined,
    children: [new Paragraph({ alignment: opts.align || AlignmentType.CENTER, spacing: { line: 276 },
      children: [new TextRun({ text: String(text), size: 20, bold: !!opts.bold, color: opts.color || "222222", font: { ascii: "Times New Roman", eastAsia: "SimSun" } })] })],
  });
}
function magnetTable(rows, label) {
  const header = new TableRow({ tableHeader: true, cantSplit: true, children: [
    th("Cluster", 16), th("Price (USD)", 16), th("Dist from spot", 15), th("Est. exposure", 16), th("Strength", 12), th("Venues", 25),
  ]});
  const bodyRows = rows.map((r, i) => new TableRow({ cantSplit: true, children: [
    td(r.label || (r.distPct < 0 ? "below spot" : "above spot"), { fill: i % 2 ? P.surface : undefined }),
    td(r.price.toFixed(1), { bold: true, fill: i % 2 ? P.surface : undefined }),
    td((r.distPct < 0 ? "" : "+") + r.distPct.toFixed(2) + "%", { color: r.distPct < 0 ? "1B7A3D" : "B02A2A", fill: i % 2 ? P.surface : undefined }),
    td("$" + (r.usd / 1e6).toFixed(2) + "M", { fill: i % 2 ? P.surface : undefined }),
    td(r.strength, { fill: i % 2 ? P.surface : undefined }),
    td(r.venues.join(" + "), { align: AlignmentType.LEFT, fill: i % 2 ? P.surface : undefined }),
  ]}));
  return [new Paragraph({ keepNext: true, spacing: { before: 160, after: 80 },
    children: [new TextRun({ text: label, bold: true, size: 21, color: "3A3A3A", font: { ascii: "Arial", eastAsia: "SimHei" } })] }),
  new Table({ width: { size: 100, type: WidthType.PERCENTAGE }, layout: TableLayoutType.FIXED, borders: tableBorders, rows: [header, ...bodyRows] })];
}

// ---------- content ----------
const spot = DATA.spot;
const views = DATA.views;
const f = (n) => "$" + (n / 1e6).toFixed(2) + "M";

const doc = new Document({
  styles: { default: { document: { run: { font: { ascii: "Times New Roman", eastAsia: "SimSun" }, size: 22 } } } },
  features: { updateFields: true },
  sections: [
    // ---- cover ----
    {
      properties: { page: { margin: { top: 0, bottom: 0, left: 0, right: 0 } } },
      children: buildCoverR1({
        title: "XAU Liquidation Pullback Magnets",
        subtitle: "Multi-venue liquidation cluster ladder for pullback entries — 24H / 48H / 3D / 7D / 30D",
        englishLabel: "ORDER FLOW DESK RESEARCH",
        metaLines: [
          "Instrument: XAU (Gold) USDT perpetuals",
          "Venues: Binance / OKX / Bybit / Bitget / Gate",
          "Spot at capture: $" + spot.toFixed(1) + " (Binance XAUUSDT)",
          "Data: Coinglass estimates via /api/liquidationLevels/v2",
          "Generated: " + DATA.generatedAt.replace("T", " ").slice(0, 16) + " UTC",
        ],
        footerLeft: "CG Order-Flow Terminal", footerRight: "Trading-Strategies / main",
      }),
    },
    // ---- TOC ----
    {
      properties: { page: { margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
      children: [
        new Paragraph({ spacing: { after: 240 }, children: [new TextRun({ text: "Contents", bold: true, size: 32, color: "1A1A1A", font: { ascii: "Arial", eastAsia: "SimHei" } })] }),
        new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-2" }),
        new Paragraph({ spacing: { before: 120 },
          children: [new TextRun({ text: "Note: right-click the table of contents and choose \u201cUpdate Field\u201d to refresh page numbers.", italics: true, size: 18, color: "888888", font: { ascii: "Times New Roman" } })] }),
        new Paragraph({ children: [new PageBreak()] }),
      ],
    },
    // ---- body ----
    {
      properties: { page: { margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 }, pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } } },
      children: [
        // 1. Executive summary
        h1("1. Executive Summary"),
        bodyRuns([
          { text: "This report maps the estimated liquidation clusters around gold (XAU) across five time windows — 24H, 48H, 3D, 7D and 30D — as pullback-entry reference levels. At capture, XAU spot was " },
          { text: "$" + spot.toFixed(1), bold: true },
          { text: " on the Binance XAUUSDT perpetual. The two dominant 30-day magnets sit at " },
          { text: "$" + views["30D"].below[0].price.toFixed(0) + " (-" + Math.abs(views["30D"].below[0].distPct).toFixed(1) + "%)", bold: true },
          { text: " and " },
          { text: "$" + views["30D"].below[1].price.toFixed(0) + " (-" + Math.abs(views["30D"].below[1].distPct).toFixed(1) + "%)", bold: true },
          { text: " below spot (long-liquidation floors, the dip magnets), with the nearest overhead short-liquidation shelves at " },
          { text: "$" + views["30D"].above[0].price.toFixed(0) + " and $" + views["30D"].above[1].price.toFixed(0), bold: true },
          { text: " (squeeze targets)." },
        ]),
        body("The ladder is remarkably regular: clusters concentrate near round percentage distances from spot (-1%, -2%, -4% below; +1%, +2% above), which is exactly the footprint of leveraged positions opened at recent prices with 25x-100x style leverage. For pullback traders this yields a practical map: buy-side interest defends the -1% and -2% floors (where forced sellers get absorbed), while the +1%/+2% shelves are the natural first targets on a bounce. All figures are Coinglass estimates, not exchange-published data."),

        // 2. Upstream exploration
        h1("2. The Coinglass Liquidation HeatMap Page: Models, Modes and the Anonymous Wall"),
        body("The coinglass.com LiquidationHeatMap page exposes three calculation models and two symbol modes. These were extracted from the live page bundle and verified against the API on 2026-11-21:"),
        new Table({ width: { size: 100, type: WidthType.PERCENTAGE }, layout: TableLayoutType.FIXED, borders: tableBorders, rows: [
          new TableRow({ tableHeader: true, cantSplit: true, children: [th("Model", 14), th("Endpoint (pair mode)", 44), th("Parameters", 42)] }),
          new TableRow({ cantSplit: true, children: [td("Model 1", { bold: true }), td("/api/index/v2/liqHeatMap", { align: AlignmentType.LEFT }), td("interval/limit grid (5-minute bars; 24h = 288 x 5m)", { align: AlignmentType.LEFT })] }),
          new TableRow({ cantSplit: true, children: [td("Model 2", { bold: true, fill: P.surface }), td("/api/index/v5/liqHeatMap", { align: AlignmentType.LEFT, fill: P.surface }), td("interval/limit grid (the page default your screenshot shows)", { align: AlignmentType.LEFT, fill: P.surface })] }),
          new TableRow({ cantSplit: true, children: [td("Model 3", { bold: true }), td("/api/index/v6/liqHeatMap (fapi)", { align: AlignmentType.LEFT }), td("range = 12h ... 2y, cp = false", { align: AlignmentType.LEFT })] }),
        ] }),
        new Paragraph({ spacing: { before: 120, after: 120 }, children: [] }),
        bodyRuns([
          { text: "Pair mode vs coin mode. ", bold: true },
          { text: "Pair mode (e.g. symbol=Binance_BTCUSDT) queries ONE venue's leveraged positions; coin mode (symbol=XAU) calls the aggregate endpoints (/api/index/aggregate, /v3, /v4) and merges EVERY venue's positions for the coin. Coin mode therefore carries more information for pullback work — it is the full cross-venue magnet field rather than one exchange's book — and it is what the page uses for non-BTC symbols. The desk's equivalent is the terminal's multi-venue liquidation-levels ladder (Binance, OKX, Bybit, Bitget, Gate), which is the data source of this report." },
        ]),
        bodyRuns([
          { text: "The anonymous wall. ", bold: true },
          { text: "Live probing (isolated requests, 30-second spacing) showed the anonymous API serves only BTC at the 24-hour window. ETH and XAU in coin mode, and every longer window (48H through 30D), return error 40000 without a logged-in coinglass.com session; the page itself also rejects headless browsers. The models cannot be compared anonymously for XAU — so this report builds the honest equivalent: per-venue liquidation levels across five exchanges, aggregated the same way the terminal's stopmap route does for non-BTC perps." },
        ]),

        // 3. Method
        h1("3. Data and Method"),
        body("Source: Coinglass /api/liquidationLevels/v2 per venue (Binance_XAUUSDT, OKX_XAU-USDT-SWAP, Bybit_XAUUSDT, Bitget_XAUUSDT_UMCBL, Gate_XAU_USDT) at ranges 3d, 7d and 30d. The endpoint returns a time series of estimated level snapshots {beginDate, price, size, tier h1/h2/h3, side}; the currently-open levels are the rows at the newest snapshot, and persistence is measured by how many consecutive snapshots a level has been resting. The 24H and 48H views are derived from the 3-day payload by beginDate cutoff. Open levels are clustered within 0.3% of price and summed across venues; strength is each cluster's exposure relative to the strongest cluster in its window. Exposure in USD is size x price (upstream size is per-unit notional for metals). All liquidation figures are Coinglass estimates."),

        // 4. The ladder
        h1("4. The XAU Magnet Ladder (24H to 30D)"),
        ...magnetTable(views["24H"].below.slice(0, 4), "4.1  24H window — magnets below spot (long-liquidation floors)"),
        ...magnetTable(views["24H"].above.slice(0, 4), "4.2  24H window — magnets above spot (short-liquidation shelves)"),
        ...magnetTable(views["48H"].below.slice(0, 4), "4.3  48H window — magnets below spot"),
        ...magnetTable(views["48H"].above.slice(0, 4), "4.4  48H window — magnets above spot"),
        ...magnetTable(views["3D"].below.slice(0, 4), "4.5  3D window — magnets below spot"),
        ...magnetTable(views["3D"].above.slice(0, 4), "4.6  3D window — magnets above spot"),
        ...magnetTable(views["7D"].below.slice(0, 4), "4.7  7D window — magnets below spot"),
        ...magnetTable(views["7D"].above.slice(0, 4), "4.8  7D window — magnets above spot"),
        ...magnetTable(views["30D"].below.slice(0, 5), "4.9  30D window — magnets below spot (the primary pullback floors)"),
        ...magnetTable(views["30D"].above.slice(0, 5), "4.10  30D window — magnets above spot (the squeeze targets)"),
        note("Table fields: cluster price = midpoint of the aggregated level band; distance = percent from spot at capture; exposure = estimated USD notional of resting liquidation orders (Coinglass estimate); strength = 100 = strongest cluster in that window; venues = exchanges whose levels contribute to the cluster."),

        // 5. Reading
        h1("5. How to Read the Ladder for Pullback Entries"),
        bodyRuns([
          { text: "The short window (24H/48H) shows the freshest leverage: the " },
          { text: "$" + views["24H"].below[1].price.toFixed(0) + " and $" + views["24H"].below[0].price.toFixed(0), bold: true },
          { text: " floors have accumulated the newest long positions whose stops sit just below — a dip into them that holds (absorption, not continuation) is the classic pullback entry, with the " },
          { text: "$" + views["24H"].above[1].price.toFixed(0), bold: true },
          { text: " shelf the first squeeze target on the recovery." },
        ]),
        bodyRuns([
          { text: "The 30-day window carries the heaviest exposure — " },
          { text: f(views["30D"].totals.below) + " below spot vs " + f(views["30D"].totals.above) + " above", bold: true },
          { text: " in tracked clusters — concentrated in the " },
          { text: "$" + views["30D"].below[0].price.toFixed(0) + " / $" + views["30D"].below[1].price.toFixed(0), bold: true },
          { text: " floors. The asymmetry (roughly 5:1 below vs above in the top clusters) is itself informative: the leveraged crowd is long gold at recent highs, which both fuels sharp dips (their stops) and caps upside (their take-profits) until the floors are swept. A 30D floor that breaks and closes below flips from magnet to acceleration zone — the -4% cluster at $" + views["30D"].below[2].price.toFixed(0) + " is the next standing floor in that scenario." },
        ]),
        body("Desk rules of thumb (consistent with the canonical ITCLS archetype): enter pullbacks AT or inside a magnet, never in front of it; place stops beyond the cluster in the cold zone between magnets (for XAU now: a long at the -1% floor carries its cold zone toward -3.9%, between the -2% and -4% clusters); first targets at the opposing +1%/+2% shelves; treat a 4H close beyond a major floor as invalidation, not as a deeper-entry signal. These levels move with price — the ladder should be re-pulled whenever spot migrates more than ~0.5% from capture."),

        // 6. Machine access
        h1("6. Machine Access from the Terminal"),
        body("The full ladder is reproducible from the terminal at any time: GET /api/cg/liqlevels?sym=XAU&range=3d|7d|30d returns the multi-venue aggregate with key levels, totals and per-venue breakdown; GET /api/cg/stopmap?sym=XAU serves the rolling 24h construction over the same archives. The MCP tool liquidation_levels { sym: XAU } exposes the same data to the desk agent, and analyze_setup { sym: XAU } bundles it with market, footprint and book-wall context. The upstream LiquidationHeatMap contract (three models, pair vs coin mode, the anonymous BTC-only-24h limitation) is documented in the stopmap route source and in scripts/research/xau-pullback-levels.json, which also carries the complete probe record behind this report."),

        // 7. Caveats
        h1("7. Caveats and Honesty Notes"),
        body("Liquidation levels are Coinglass model estimates, not exchange-published data; they are derived from open interest, funding and price history and can be wrong in both size and location. The aggregate mixes five venues with different margin currencies and leverage conventions; the USD notional is an approximation (size x price). Windows overlap by construction (the 3D view contains the 24H view; the 30D contains all). The anonymous-wall findings are a snapshot of access behaviour on 2026-11-21 and may change. This report is research output for the pullback workflow — it is not a trade recommendation, and every entry must still pass the canonical desk gates."),
      ],
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.mkdirSync("/home/z/my-project/download", { recursive: true });
  fs.writeFileSync(OUT, buf);
  console.log("wrote", OUT, buf.length, "bytes");
});
