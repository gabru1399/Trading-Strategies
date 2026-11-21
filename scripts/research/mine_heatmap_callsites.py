#!/usr/bin/env python3
"""Find the LiquidationHeatMap page's fetch call-sites: which endpoint each
model (1/2/3) hits, the symbol format, and the timeframe->interval/limit map."""
import re

src = open("/home/z/my-project/scripts/cg-js/heatmap-page.pretty.js", encoding="utf-8", errors="replace").read()
print(f"page pretty js: {len(src)} chars")

# 1. timeframe-bar literals 288/576/2016 and 24H-style labels
print("\n=== limit-ish literals:")
for n in ("288", "576", "864", "2016", "8640"):
    for m in re.finditer(rf"[^0-9]{n}[^0-9]", src):
        c = src[max(0, m.start()-100):m.end()+120].replace("\n", " ")
        print(f"[{n}] {c[:240]}")
        break  # first hit per literal is enough to locate, more below

print("\n=== all 288 hits:")
for m in re.finditer(r"\b288\b", src):
    print("   ", src[max(0, m.start()-90):m.end()+110].replace("\n", " ")[:220])

# 2. model param handling in query assembly
print("\n=== model in params:")
for m in re.finditer(r"model", src):
    c = src[max(0, m.start()-130):m.end()+160].replace("\n", " ")
    if any(k in c for k in ("params", "query", "url", "=")) and "navicon" not in c:
        print("   ", c[:280])

# 3. endpoint function names used in page (v5/v6/aggregate imports)
print("\n=== endpoint mentions:")
for pat in ("v5/liqHeatMap", "v6/liqHeatMap", "aggregate/liqHeatMap", "liqMap", "exLiqMap"):
    for m in re.finditer(re.escape(pat), src):
        print(f"[{pat}]", src[max(0, m.start()-140):m.end()+180].replace("\n", " ")[:300])

# 4. symbol formatting for the heatmap fetch
print("\n=== symbol formatting:")
for m in re.finditer(r"symbol\s*[:=][^,\n]{0,80}", src):
    c = m.group(0)
    if any(k in c for k in ("Binance", "exName", "coin", "CUR")):
        print("   ", c[:120])
