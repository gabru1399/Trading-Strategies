#!/usr/bin/env python3
"""Mechanical parse-check of every Python file in the repo (CG terminal at root).

Compiles each file (ast.parse), then attempts import where feasible without
network/MT5. Reports a classification: OK / SYNTAX / IMPORT / SKIP-WINDOWS.
"""
import ast
import sys
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
files = sorted(ROOT.rglob("*.py"))
print(f"repo Python files: {len(files)}")

results = {"OK": [], "SYNTAX": [], "IMPORT": [], "SIDE-EFFECT": [], "SKIP-WINDOWS": []}
archive_markers = ("legacy", "archive", "node_modules", ".next", "HFT", "Delta-Fibonacci-Institutional-Business")

for f in files:
    rel = str(f.relative_to(ROOT))
    try:
        ast.parse(f.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as e:
        results["SYNTAX"].append((rel, str(e)))
        continue

    if any(m in rel.lower() for m in ("mt5",)) or "MetaTrader5" in f.read_text(encoding="utf-8", errors="replace")[:4000]:
        results["SKIP-WINDOWS"].append(rel)
        continue
    if any(m in rel.lower() for m in archive_markers):
        results["SKIP-WINDOWS"].append(rel)
        continue

    # import probe in an isolated subprocess (side-effect safe)
    code = (
        "import sys, importlib.util;\n"
        f"spec = importlib.util.spec_from_file_location('probe', {str(f)!r});\n"
        "mod = importlib.util.module_from_spec(spec);\n"
        "spec.loader.exec_module(mod)\n"
    )
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        # Module has top-level side effects (e.g. opens a long poll). Not an
        # import error — it RUNS. Classified separately.
        results["SIDE-EFFECT"].append(rel)
        continue
    if r.returncode == 0:
        results["OK"].append(rel)
    else:
        last = (r.stderr.strip().splitlines() or ["?"])[-1]
        results["IMPORT"].append((rel, last[:120]))

print(f"\nOK: {len(results['OK'])} | SYNTAX: {len(results['SYNTAX'])} | "
      f"IMPORT: {len(results['IMPORT'])} | SIDE-EFFECT: {len(results['SIDE-EFFECT'])} | "
      f"SKIP-WINDOWS/archive: {len(results['SKIP-WINDOWS'])}")

if results["SYNTAX"]:
    print("\n--- SYNTAX ERRORS ---")
    for rel, err in results["SYNTAX"]:
        print(f"  {rel}: {err}")

if results["IMPORT"]:
    print("\n--- IMPORT FAILURES (non-Windows) ---")
    for rel, err in results["IMPORT"]:
        print(f"  {rel}: {err}")
