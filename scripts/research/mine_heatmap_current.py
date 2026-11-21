#!/usr/bin/env python3
"""Mine the CURRENT heatmap [symbol] bundle (Nov 20) + today's page HTML for
the model->endpoint mapping, timeframe options, and fetch params."""
import re

b = open("/home/z/my-project/scripts/cg-js/heatmap__%5Bsymbol%5D-12b2919219442646.js", encoding="utf-8", errors="replace").read()
h = open("/home/z/my-project/scripts/cg-js/heatmap-page.html", encoding="utf-8", errors="replace").read()
print(f"bundle {len(b)} chars, html {len(h)} chars")

def ctx(src, pat, w=170, limit=8, label=""):
    print(f"\n=== {label or pat}")
    seen, n = set(), 0
    for m in re.finditer(pat, src):
        c = src[max(0, m.start()-w):m.end()+w].replace("\n", " ")
        if c in seen: continue
        seen.add(c); print("  ", c[:2*w]); n += 1
        if n >= limit: break
    if n == 0: print("   (none)")

# bundle: model handling
ctx(b, r"model", w=140, limit=10, label="bundle 'model'")
# bundle: timeframe->interval/limit map (the 288/576 style literals)
ctx(b, r"\b288\b", w=150, limit=4, label="bundle 288")
ctx(b, r"\b576\b", w=150, limit=4, label="bundle 576")
ctx(b, r"\b2016\b", w=150, limit=4, label="bundle 2016")
# bundle: timeframe labels as strings
ctx(b, r"[\"'](24h|48h|12h|4h|3d|7d|30d)[\"']", w=140, limit=8, label="bundle tf labels (lowercase)")
ctx(b, r"[\"'](24H|48H|12H|4H|3D|7D|30D)[\"']", w=140, limit=8, label="bundle tf labels (upper)")
# bundle: interval literals
ctx(b, r"interval\s*:\s*[\"']?\d", w=150, limit=6, label="bundle interval")
# html: model buttons + timeframe options in DOM
ctx(h, r"[Mm]odel[\"' ]*[:=]?[\"' ]*[0-9]", w=160, limit=10, label="html model")
ctx(h, r">(24H|48H|12H|4H|3D|7D|30D|1M|3M)<", w=120, limit=10, label="html tf options")
# html: query-state defaults
ctx(h, r"model=2|model=3|model=1", w=120, limit=6, label="html model query")
