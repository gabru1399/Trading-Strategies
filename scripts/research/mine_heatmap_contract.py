#!/usr/bin/env python3
"""Mine the archived Coinglass frontend bundles for the LiquidationHeatMap
API contract: which endpoint + params the page sends for model=1/2/3 and the
24H/48H/3D/7D/30D timeframes."""
import re, glob, collections

files = glob.glob("/home/z/my-project/scripts/cg-js/heatmap*") + glob.glob("/home/z/my-project/scripts/cg-js/cvd*")
hits = collections.defaultdict(list)

for f in files:
    try:
        src = open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    # endpoint fragments
    for m in re.finditer(r"liqHeatMap", src):
        hits["liqHeatMap"].append((f, src[max(0, m.start()-140):m.end()+220]))
    # model param usage
    for m in re.finditer(r"model[:=]\s*[\"']?[0-9]", src):
        hits["model"].append((f, src[max(0, m.start()-160):m.end()+200]))
    # timeframe selector values
    for m in re.finditer(r"[\"'](24H|48H|3D|7D|30D|12H|4H|1M)[\"']", src):
        hits["tf"].append((f, src[max(0, m.start()-120):m.end()+140]))
    # index/v endpoint builders
    for m in re.finditer(r"/api/index/v[0-9]+/[a-zA-Z]+", src):
        hits["endpoints"].append((f, src[max(0, m.start()-80):m.end()+160]))

def show(key, limit=6):
    print(f"\n########## {key} ({len(hits[key])} raw hits)")
    seen = set()
    n = 0
    for f, ctx in hits[key]:
        c = ctx.replace("\n", " ")
        if c in seen:
            continue
        seen.add(c)
        tag = f.split("/")[-1][:40]
        print(f"--- [{tag}]")
        print(c[:360])
        n += 1
        if n >= limit:
            break

for k in ("liqHeatMap", "model", "tf", "endpoints"):
    show(k)
