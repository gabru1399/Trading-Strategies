#!/usr/bin/env python3
"""Extract the g (range->interval/limit) and x (model-3 range alias) maps and
the liqHeatmap baseURL from the live LiquidationHeatMap chunk."""
import re

f = "/home/z/my-project/scripts/research/liq-page/%5Bsymbol%5D-e61edde946656ec4.js"
src = open(f, encoding="utf-8", errors="replace").read()

# find the region around the G/Q definitions — g and x are defined nearby
m = re.search(r"let G=\{1:\[", src)
print("=== region after G definition (2500 chars):")
print(src[m.start():m.start()+2500].replace("\n", " "))

print("\n\n=== x= map candidates (model-3 range aliases):")
for mm in re.finditer(r"\bx\s*=\s*\{[^}]{5,400}\}", src):
    c = mm.group(0)
    if any(k in c for k in ("24h", "72h", "7d", "30d", "12h")):
        print(c[:500])

print("\n=== liqHeatmap baseURL:")
for mm in re.finditer(r"liqHeatmap[\"']?\s*[:=]\s*[\"'][^\"']+[\"']", src):
    print(mm.group(0))
# search other chunks for the base config too
import glob
for f2 in glob.glob("/home/z/my-project/scripts/research/liq-page/*.js"):
    s2 = open(f2, encoding="utf-8", errors="replace").read()
    for mm in re.finditer(r"liqHeatmap\s*[:=]\s*[\"'](https?://[^\"']+|/[^\"']*)[\"']", s2):
        print(f"{f2.split('/')[-1][:44]}: {mm.group(0)[:120]}")
