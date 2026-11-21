#!/usr/bin/env python3
"""Extract the exact liqHeatMap fetch-param assembly from the live [symbol]
chunk: symbol format, the timeframe param name (values 24h/72h/7d/30d), and
how model 1/2/3 choose between the primary and aggregate endpoint."""
import re

f = "/home/z/my-project/scripts/research/liq-page/%5Bsymbol%5D-e61edde946656ec4.js"
src = open(f, encoding="utf-8", errors="replace").read()
print(f"chunk: {len(src)} bytes")

# 1. where is G (the model->endpoints map) used?
for m in re.finditer(r"G\[", src):
    print("\n=== G[ usage:")
    print(src[max(0, m.start()-400):m.end()+500].replace("\n", " ")[:900])

# 2. where is Q (the tf map) used?
for m in re.finditer(r"Q\[", src):
    print("\n=== Q[ usage:")
    print(src[max(0, m.start()-350):m.end()+400].replace("\n", " ")[:750])

# 3. param objects containing "24h"/"72h" keys or range-ish params
for pat in (r"range\s*:", r"timeType", r"period\s*:", r"merge\s*:"):
    seen = set()
    for m in re.finditer(pat, src):
        c = src[max(0, m.start()-250):m.end()+300].replace("\n", " ")
        if c in seen: continue
        seen.add(c)
        print(f"\n=== {pat}:")
        print(c[:550])

# 4. the fetch functions tu/td/tf/th invocations (minified names from _app)
for name in ("tu(", "td(", "tf(", "th("):
    for m in re.finditer(re.escape(name), src):
        c = src[max(0, m.start()-200):m.end()+350].replace("\n", " ")
        if "{" in c[len(name):len(name)+40] or any(k in c for k in ("symbol", "coin")):
            print(f"\n=== {name} call:")
            print(c[:560])
            break
