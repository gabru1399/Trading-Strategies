#!/usr/bin/env python3
"""Extract the heatmap fetch call-sites with arguments from the current
[symbol] bundle: params objects, model handling, timeframe mapping."""
import re

b = open("/home/z/my-project/scripts/cg-js/heatmap__%5Bsymbol%5D-12b2919219442646.js", encoding="utf-8", errors="replace").read()

def ctx(pat, w=200, limit=8, label=""):
    print(f"\n=== {label or pat}")
    seen, n = set(), 0
    for m in re.finditer(pat, b):
        c = b[max(0, m.start()-w):m.end()+w].replace("\n", " ")
        if c in seen: continue
        seen.add(c); print("  ", c); n += 1
        if n >= limit: break
    if n == 0: print("   (none)")

# the endpoint function invocations with argument context
ctx(r"tw\(", w=90, limit=3, label="v5 calls tw()")
ctx(r"t_\(", w=90, limit=3, label="v6 calls t_()")
ctx(r"tS\(", w=90, limit=3, label="v4-agg calls tS()")
ctx(r"tk\(", w=90, limit=3, label="liqMap5 calls tk()")
# query model param usage
ctx(r"query\.model|searchParams|model\s*===|model\s*==", w=160, limit=6, label="model handling")
# interval + limit + symbol assembly
ctx(r"interval", w=130, limit=8, label="interval assembly")
ctx(r"limit", w=110, limit=8, label="limit assembly")
ctx(r"Binance_|exName|refSymbol", w=130, limit=6, label="symbol format")
