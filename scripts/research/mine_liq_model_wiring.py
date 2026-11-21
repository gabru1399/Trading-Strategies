#!/usr/bin/env python3
"""Mine the Nov-9 liquidation-heatmap chunks for the model->endpoint wiring
and the timeframe->interval/limit mapping."""
import re

files = {
    "sym_nov9": "/home/z/my-project/scripts/cg-js/heatmap__%5Bsymbol%5D-f88d9956c06a091c.js",
    "chunk_1c0": "/home/z/my-project/scripts/cg-js/heatmap__1c0311fb-c74eb105fd098827.js",
    "chunk_898": "/home/z/my-project/scripts/cg-js/heatmap__89831-44ae4262b44f6805.js",
    "app":       "/home/z/my-project/scripts/cg-js/heatmap___app-69142b6832e382a1.js",
}
# find where each endpoint fn (tx=v2, tw=v5, t_=v6, tS=v4agg, tz=agg, tN=v3agg,
# tk=/5/liqMap, tA=/2/exLiqMap) is INVOKED with an object argument, in each file
invokes = {"tx": r"tx\(\{", "tw": r"tw\(\{", "t_": r"t_\(\{", "tS": r"tS\(\{",
           "tz": r"tz\(\{", "tN": r"tN\(\{", "tk": r"tk\(\{", "tA": r"tA\(\{"}

for name, f in files.items():
    src = open(f, encoding="utf-8", errors="replace").read()
    print(f"\n############ {name} ({len(src)} chars)")
    for fn, pat in invokes.items():
        ms = list(re.finditer(pat, src))
        if not ms:
            continue
        for m in ms[:2]:
            # grab the whole object literal (brace matching)
            start = m.start()
            depth, i = 0, start
            while i < len(src) and i - start < 600:
                if src[i] == "{":
                    depth += 1
                elif src[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            obj = src[start:i+1].replace("\n", " ")
            # context before the call (what selects this endpoint)
            pre = src[max(0, start-260):start].replace("\n", " ")
            print(f"\n--- {fn}():")
            print(f"PRE: {pre[-240:]}")
            print(f"CALL: {obj[:420]}")
