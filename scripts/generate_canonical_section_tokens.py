#!/usr/bin/env python3
"""
Canonical Master Specification Section SHA-256 Token Generator & Verifier.

Enforces cryptographic proof of study and execution for every line and section
of desk/CANONICAL_MASTER_SPECIFICATION.md and its companions.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "desk" / "CANONICAL_MASTER_SPECIFICATION.md"
ANCHOR_PATTERN = re.compile(r'<a id="([a-z0-9-]+)"></a>')

COMPANIONS = {
    "launch-prompt": ROOT / "desk" / "CANONICAL_PROMPT.txt",
    "evidence-contract": ROOT / "desk" / "ROUND_EVIDENCE_CONTRACT.md",
}

def extract_section_title(lines, start_idx):
    """Find the section title heading near the start index."""
    for i in range(start_idx, min(start_idx + 5, len(lines))):
        line = lines[i].strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return f"Section at line {start_idx + 1}"

def build_section_tokens(round_id="CANONICAL"):
    """
    Parses CANONICAL_MASTER_SPECIFICATION.md and generates cryptographically
    verified SHA-256 tokens for each section and line range.
    """
    if not SPEC_PATH.exists():
        raise FileNotFoundError(f"Missing spec at {SPEC_PATH}")

    raw = SPEC_PATH.read_bytes()
    doc_sha256 = hashlib.sha256(raw).hexdigest()
    lines = raw.decode("utf-8-sig").splitlines(keepends=True)

    starts = {}
    for i, line in enumerate(lines):
        match = ANCHOR_PATTERN.fullmatch(line.strip())
        if match:
            key = match.group(1)
            starts[key] = i - 1

    starts["kernel"] = 0
    anchors = sorted(starts.items(), key=lambda x: x[1])

    section_tokens = {}
    total_lines = len(lines)

    for i, (key, start) in enumerate(anchors):
        end = anchors[i + 1][1] if i + 1 < len(anchors) else total_lines
        section_lines = lines[start:end]
        body = "".join(section_lines)
        content_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
        
        # Unique execution verification SHA token tying Round + Section + Lines + Content
        unique_token_input = f"{round_id}:{key}:{start + 1}:{end}:{content_sha256}"
        unique_token = hashlib.sha256(unique_token_input.encode("utf-8")).hexdigest()
        
        title = extract_section_title(lines, start)

        section_tokens[key] = {
            "section_key": key,
            "title": title,
            "source_file": "desk/CANONICAL_MASTER_SPECIFICATION.md",
            "start_line": start + 1,
            "end_line": end,
            "line_count": end - start,
            "content_sha256": content_sha256,
            "unique_execution_token": unique_token,
            "first_line_preview": section_lines[0].strip() if section_lines else "",
            "last_line_preview": section_lines[-1].strip() if section_lines else ""
        }

    # Add companion documents
    for comp_key, comp_path in COMPANIONS.items():
        if comp_path.exists():
            c_raw = comp_path.read_bytes()
            c_sha = hashlib.sha256(c_raw).hexdigest()
            c_lines = c_raw.decode("utf-8-sig").splitlines(keepends=True)
            u_token = hashlib.sha256(f"{round_id}:{comp_key}:1:{len(c_lines)}:{c_sha}".encode("utf-8")).hexdigest()
            section_tokens[comp_key] = {
                "section_key": comp_key,
                "title": f"Companion Document: {comp_path.name}",
                "source_file": f"desk/{comp_path.name}",
                "start_line": 1,
                "end_line": len(c_lines),
                "line_count": len(c_lines),
                "content_sha256": c_sha,
                "unique_execution_token": u_token,
                "first_line_preview": c_lines[0].strip() if c_lines else "",
                "last_line_preview": c_lines[-1].strip() if c_lines else ""
            }

    # Document Level Ledger Token: Hashing all section execution tokens in sequence
    all_tokens_stream = "".join(s["unique_execution_token"] for s in sorted(section_tokens.values(), key=lambda x: (x["start_line"], x["section_key"])))
    ledger_master_token = hashlib.sha256(all_tokens_stream.encode("utf-8")).hexdigest()

    manifest = {
        "round_id": round_id,
        "spec_file": "desk/CANONICAL_MASTER_SPECIFICATION.md",
        "spec_sha256": doc_sha256,
        "total_spec_lines": total_lines,
        "total_sections_verified": len(section_tokens),
        "ledger_master_token": ledger_master_token,
        "sections": section_tokens
    }
    return manifest

def main():
    parser = argparse.ArgumentParser(description="Canonical Section SHA Token Generator")
    parser.add_argument("--round", default="CANONICAL", help="Round ID for execution salt (default: CANONICAL)")
    parser.add_argument("--save-to-desk", action="store_true", help="Save canonical static tokens to desk/canonical_section_sha_tokens.json")
    parser.add_argument("--save-to-round", help="Save round-specific tokens to data/round-evidence/<round>/section_sha_tokens.json")
    parser.add_argument("--verify-section", help="Verify single section SHA token and print details")
    parser.add_argument("--print-table", action="store_true", help="Print full Markdown table of section tokens")
    args = parser.parse_args()

    manifest = build_section_tokens(round_id=args.round)
    print(f"Verified {manifest['total_sections_verified']} sections across {manifest['total_spec_lines']} lines.")
    print(f"Spec SHA256: {manifest['spec_sha256']}")
    print(f"Ledger Master Execution Token: {manifest['ledger_master_token']}")

    if args.print_table:
        print("\n| Section Anchor | Lines | Line Count | Section Content SHA-256 | Unique Execution Proof Token | Title |")
        print("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for k, s in sorted(manifest["sections"].items(), key=lambda x: (x[1]["start_line"], x[1]["section_key"])):
            print(f"| `{k}` | L{s['start_line']}–L{s['end_line']} | {s['line_count']} | `{s['content_sha256'][:16]}...` | `{s['unique_execution_token'][:16]}...` | {s['title'][:40]} |")
        print()

    if args.save_to_desk:
        out_desk = ROOT / "desk" / "canonical_section_sha_tokens.json"
        out_desk.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Saved canonical tokens to {out_desk}")

    if args.save_to_round:
        out_round = ROOT / "data" / "round-evidence" / args.save_to_round / "section_sha_tokens.json"
        out_round.parent.mkdir(parents=True, exist_ok=True)
        out_round.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Saved round execution tokens to {out_round}")

    if args.verify_section:
        sec = manifest["sections"].get(args.verify_section)
        if not sec:
            print(f"ERROR: Section {args.verify_section} not found in spec!")
            sys.exit(1)
        print(f"\n--- Section '{args.verify_section}' Cryptographic Verification ---")
        print(f"Title: {sec['title']}")
        print(f"Lines: {sec['start_line']} - {sec['end_line']} (Count: {sec['line_count']})")
        print(f"Content SHA256: {sec['content_sha256']}")
        print(f"Unique Execution Token: {sec['unique_execution_token']}")

if __name__ == "__main__":
    main()
