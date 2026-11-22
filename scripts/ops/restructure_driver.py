#!/usr/bin/env python3
"""
Institutional restructure driver — 2026-11-22.

Moves the flat scripts/ sprawl (~450 files) into a taxonomy, rewrites EVERY
textual reference repo-wide, and leaves the live-infrastructure scripts in
place (they are invoked by absolute path from state/configs).

Rules:
  - LIVE set stays at scripts/<name> (invoked from package.json, mcp/, desk/,
    src/, Caddyfile, docs/ci-workflow.yml).
  - cg_client/cg_token + their 3 importers move together (sibling imports).
  - Every reference to a moved file — in code, docs, desk specs, scripts —
    is rewritten to the new path. git mv preserves history.
  - A MANIFEST.md at scripts/ root maps old→new for humans.
  - Idempotent-ish: re-running skips already-moved files.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/z/my-project")
SCRIPTS = ROOT / "scripts"

# ---------------------------------------------------------------------------
# taxonomy
# ---------------------------------------------------------------------------

# files that STAY at scripts/ top level (live entry points invoked by path
# from package.json / mcp / desk / src / Caddyfile / ci)
LIVE = {
    "start-server.mjs",
    "desk_daemon.mjs",
    "cg-session.mjs",
    "desk_cron_round.cjs",
    "desk_round.sh",
    "desk_deepscan.py",
    "desk_screen_itcls.py",
    "desk_score_xau.py",
    "desk_deepdive_itcls.py",
    "bell_alert.py",
    "wake_watcher.py",
    "wake_360.mjs",
    "wake_analysis.mjs",
    "verify_runtime_environment.py",
    "verify_runtime_paths.py",
    "verify-live.sh",
    "verify_round_evidence.py",
    "verify-micro-map.mjs",
    "round_preflight_bootstrap.py",
    "capture_round_evidence.py",
    "run_canonical_decide.py",
    "run_round_step_reads.py",
    "run_sop_reads.py",
    "walk_sop_reads.py",
    "read_all_anchors.py",
    "read_mw.py",
    "read_inventory_summary.py",
    "generate_canonical_section_tokens.py",
    "fix_managed_evidence.py",
    "mt5_cg_trader.py",
    "mt5_punch.py",
    "mt5_report.py",
    "mt5_order_risk.py",
    "mt5_sl_analysis.py",
    "mt5_ui_trader.py",
    "mt5_quant_engine.py",
    "mt5_confluence_scan.json",
    "mt5_full_scan.json",
    "list_all_mt5_symbols.py",
    "launch_mt5_gui.py",
    "launch_chrome.mjs",
    "binance_tier_verify.py",
    "binance_tier_verify2.py",
    "binance_keycheck.py",
    "blueberry_phase1_guard.py",
    "auto_punch_engine.py",
    "punch_now.py",
    "punch_test.py",
    "auto_prompt_paster.py",
    "auto_prompt_paster.ps1",
    "backfill_binance_vision.py",
    "backfill_dukascopy.py",
    "parity_check.sh",
    "parity_replay.py",
    "parity_debug.py",
    "parity_engine.mjs",
    "e2e-api-battery.sh",
    "e2e-sym-sweep.sh",
    "paperbook-e2e.sh",
    "test-live-terminal.mjs",
    "test-mcp-tools.cjs",
    "test-signal-parity.ts",
    "test-scan-lanes.ts",
    "test-notify-dedup.ts",
    "test-paperbook.ts",
    "test-quant-math.cjs",
    "test-quant-options.mjs",
    "test-venue-ws.cjs",
    "test-venue-liq-ws.cjs",
    "test-liq-live-units.cjs",
    "test-liq-stream.cjs",
    "parity-vs-coinglass.ts",
    "backtest-models.ts",
    "backtest_ea.py",
    "backtest_ea6_fix.py",
    "backtest_portfolio.py",
    "backfill_binance_vision.py",
    "backfill_dukascopy.py",
    # python sibling-import cluster (cg_client/cg_token importers)
    "cg_client.py",
    "cg_token.py",
    "probe_new_eps.py",
    "test_cookie_unlock.py",
    "test_liq_model.py",
    # shared modules imported via sys.path=scripts/ by round builders
    "delta_direct.py",
    # backtest cluster stays together (backtest_ea is the shared module)
    "backtest_portfolio.py",
    "backtest_ea6_fix.py",
}

# name patterns → destination subfolder (first match wins)
TAXONOMY = [
    # the report/playbook JS cluster moves TOGETHER to report/ (relative
    # ./requires keep working only if they share a folder)
    (r"^(report_lib|report_e2e_a|report_e2e_b|report_main|report_sections_a|playbook-content-a|playbook-content-b|build-playbook|postprocess-playbook)\.(js|py)$", "report/"),
    # one-off desk round evidence builders (r-numbers) — historical artifacts
    (r"^build_r\d+.*\.(py|js|json|md|txt|xlsx)$", "desk/rounds/"),
    (r"^(batch_capture_r\d+|capture_round|report_e2e|build_round|qr2026|r384_report|r501_report|r517_report|r546_report|r547_addendum|r549_|r550_|r552_|r8_brief|table7_scoring|build_tables|compile_report|make_charts|charts_r547|fix_toc_duplicate|build_coverage_xlsx|build_e2e_xlsx|build_tier_b_cards)\b.*\.(py|js|json|md|txt|xlsx)$", "desk/rounds/"),
    (r"^(audit|verify)_(bookwalls|apt|curated|delta|external|resting|crypto|alt|all|managed|fixed|user|active|spread|live|mt5|ndxt?|of_|tp|high|calibrated|realistic|winrate|losses|portfolio|telemetry|granular|individual|forensic).*\.(py|cjs|json|md)$", "desk/audit/"),
    (r"^desk_.*\.(py|sh|cjs|json)$", "desk/"),
    (r"^(run_|emit_|generate_itcls|round_) .*?\.py$", "desk/"),
    (r"^backtest_.*\.(py|ts)$", "backtest/"),
    (r"^analyze_.*\.py$", "analysis/"),
    (r"^scan_.*\.(py|cjs|sh|mjs)$", "scanner/"),
    (r"^screen_.*\.py$", "scanner/"),
    (r"^find_.*\.py$", "scanner/"),
    (r"^deep_(dive|candidate|confluence|sleeve|telemetry|individual|sleeve).*\.(py|cjs)$", "analysis/"),
    (r"^audit-.*\.(mjs|cjs)$", "desk/audit/"),
    (r"^probe[-_].*\.(mjs|cjs|ts|py)$", "research/probes/"),
    (r"^inquest_.*\.(py|json)$", "research/inquest/"),
    (r"^test[-_].*\.(mjs|cjs|ts|py|sh)$", "research/probes/"),
    (r"^verify[-_].*\.(mjs|sh|cjs|ts|py)$", "research/probes/"),
    (r"^parity[-_].*\.(mjs|sh|cjs|ts|py)$", "research/probes/"),
    (r"^build-.*\.(mjs|js)$", "research/builders/"),
    (r"^sweep_.*\.(mjs|py)$", "scanner/"),
    (r"^(fetch|pull)_.*\.(py|sh|mjs)$", "data-pipeline/"),
    (r"^(repair|fix|patch|v32|expand|apply|match|migrate|discover|optimize|clear|decrypt|explore|inspect|dump|parse|postprocess|get_fp|print_details|inspect_whales|dom_check|last_scan|deep_telemetry|t3_probe|crypto_domain|forensics).*?\.(py|mjs|cjs|js|sh|json)$", "ops/"),
    (r"^mt5_.*\.py$", "trading/mt5/"),
    (r"^(punch|binance_demo|bell_alert).*\.py$", "trading/"),
    (r"^(auto_|wake_|levels_digest|emit_directives|optimize_ram|mem-monitor|dom_check)\b.*\.(py|sh|mjs|json)$", "ops/"),
    (r"^(whale_radar|telemetry_scan|scan_360|score_all|check_other|check_active|check_delta|check_alt|check_spreads|check_live|check_mt5|parse_check_cg|quant_|score_assets|top_assets|cold_zone|contract_solver|generate_16d|generate_canonical|individual_asset|portfolio_|delta_direct|delta_portfolio|delta_quant|inquest|blueberry|binance_tier|backfill|build_r641|build_r642|discover_tier|screen_top|top_assets|read_all|read_mw|read_inventory|repair_state|repair_fills|update_full|emit_directives|make_generic|optimize_ram).*\.(py|cjs|mjs|sh|json)$", "trading/"),
]

FALLBACK = "archive/legacy-scripts/"


def classify(name: str) -> str:
    if name in LIVE:
        return ""
    for pat, dest in TAXONOMY:
        if re.match(pat, name):
            return dest
    return FALLBACK


def sh(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        print(f"  !! {' '.join(cmd)}\n     {r.stderr.strip()[:200]}")
    return r.stdout.strip()


def main() -> None:
    # 1. classify every top-level script file
    moves: dict[str, str] = {}  # old rel (scripts/x) -> new rel (scripts/sub/x)
    for f in sorted(SCRIPTS.iterdir()):
        if not f.is_file():
            continue
        if f.name in LIVE:
            continue
        dest = classify(f.name)
        if not dest:
            continue
        moves[f"scripts/{f.name}"] = f"scripts/{dest}{f.name}"

    # the sibling-import cluster must stay together — remove them from moves
    keep_together = {"cg_client.py", "cg_token.py", "probe_new_eps.py", "test_cookie_unlock.py", "test_liq_model.py"}
    moves = {o: n for o, n in moves.items() if Path(o).name not in keep_together}

    print(f"[plan] {len(moves)} files to move")
    for o, n in moves.items():
        print(f"  {o} -> {n}")

    if "--dry" in sys.argv:
        return

    # 2. create destination dirs
    for n in moves.values():
        (ROOT / n).parent.mkdir(parents=True, exist_ok=True)

    # 3. git mv (preserves history)
    for o, n in moves.items():
        if (ROOT / n).exists():
            print(f"  [skip] target exists {n}")
            continue
        r = subprocess.run(["git", "mv", o, n], capture_output=True, text=True, cwd=ROOT)
        if r.returncode != 0:
            print(f"  [git-mv-fail] {o}: {r.stderr.strip()[:150]}")

    # 4. rewrite references repo-wide (code + docs + desk specs)
    #    match scripts/<name> with word boundary at the extension end
    ref_files: list[Path] = []
    for base in ("src", "mcp", "desk", "docs", "scripts", "examples", "tests", "HFT", "Delta-Fibonacci-Institutional-Business"):
        p = ROOT / base
        if p.exists():
            ref_files.extend(
                q
                for q in p.rglob("*")
                if q.is_file()
                and q.suffix in {".ts", ".tsx", ".mjs", ".cjs", ".js", ".py", ".sh", ".md", ".json", ".txt", ".yml", ".yaml", ".ps1", ".html"}
                and "node_modules" not in q.parts
                and ".next" not in q.parts
                and ".git" not in q.parts
            )
    # root-level configs and docs
    for f in ROOT.glob("*.md"):
        ref_files.append(f)
    for f in (ROOT / "package.json", ROOT / "Caddyfile", ROOT / "AGENTS.md", ROOT / "AGENTS-PROTOCOL.md"):
        if f.exists():
            ref_files.append(f)

    # build the rename map old-stem -> (old full, new full)
    # a reference can be scripts/foo.py OR scripts/foo (no ext) OR ../scripts/foo
    rename_pairs: list[tuple[str, str]] = []
    for o, n in moves.items():
        rename_pairs.append((o, n))

    rewrites = 0
    touched = []
    for rf in ref_files:
        try:
            txt = rf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        new = txt
        for old, new_path in rename_pairs:
            # plain path replace, longest-first handled by iteration order
            if old in new:
                new = new.replace(old, new_path)
        if new != txt:
            # never rewrite the driver itself's move plan or the manifest
            rf.write_text(new, encoding="utf-8")
            rewrites += 1
            touched.append(str(rf.relative_to(ROOT)))
    print(f"[refs] rewrote references in {rewrites} files")
    for t in touched[:40]:
        print(f"  {t}")

    # 5. MANIFEST
    man = SCRIPTS / "MANIFEST.md"
    lines = [
        "# scripts/ — institutional layout (2026-11-22)",
        "",
        "Live entry points stay at the top level (invoked by absolute path from",
        "package.json, mcp/, desk/, src/, Caddyfile). Historical one-offs moved",
        "into the taxonomy below; every reference was rewritten repo-wide.",
        "",
        "| old path | new path |",
        "| --- | --- |",
    ]
    for o, n in sorted(moves.items()):
        lines.append(f"| `{o}` | `{n}` |")
    man.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[manifest] {len(moves)} entries -> {man}")


if __name__ == "__main__":
    main()
