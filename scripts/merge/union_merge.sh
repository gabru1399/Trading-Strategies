#!/usr/bin/env bash
# Union merge: local main (root-level CG terminal, 2765 commits) adopts the
# Trading-Strategies remote (newmain/main, 17 commits) so the repo becomes the
# single source of truth. Layout after merge:
#   /            = CG Order-Flow Terminal (the working directory, source of truth)
#   /HFT, /Delta-Fibonacci-Institutional-Business = engine siblings (remote layout)
# Content policy (from scripts/merge/audit_direction.sh):
#   REMOTE-WINS (38) + BOTH-CHANGED (13, take remote — newest 11-21 fixes) -> remote version
#   LOCAL-WINS  (30)  -> local version
#   remote-only (194) -> copied in
#   local-only  (487) -> kept
#   telemetry (desk/deepscan, alerts.local.json) -> untracked (remote audit policy)
set -euo pipefail
cd /home/z/my-project
IMPORT=419e4560

echo "== 0. clean tree check"
[ -z "$(git status --porcelain)" ] || { echo "tree dirty — commit or reset first"; git status --short | head; exit 1; }

echo "== 1. ancestry merge (keeps local tree, records remote history)"
if ! git merge-base --is-ancestor newmain/main HEAD; then
  git merge -s ours --allow-unrelated-histories newmain/main \
    -m "merge(remote): adopt Trading-Strategies history (17-commit import) — content union follows in the consolidation commit"
else
  echo "already merged"
fi

echo "== 2. classify differing shared files (vs import base $IMPORT)"
git ls-tree -r HEAD | awk '{print $3"\t"$4}' | sort -k2 > /tmp/u_local.txt
git ls-tree -r "newmain/main:CG-Terminal" | awk '{print $3"\t"$4}' | sort -k2 > /tmp/u_remote.txt
join -t$'\t' -1 2 -2 2 /tmp/u_local.txt /tmp/u_remote.txt | awk -F'\t' '$2!=$3 {print $1}' > /tmp/u_diff.txt
: > /tmp/u_take_remote.txt
while IFS= read -r p; do
  loc=$(git rev-parse "HEAD:$p" 2>/dev/null || echo NONE)
  rem=$(git rev-parse "newmain/main:CG-Terminal/$p" 2>/dev/null || echo NONE)
  imp=$(git rev-parse "$IMPORT:CG-Terminal/$p" 2>/dev/null || echo NONE)
  # take remote when remote hardened (local==import), or both changed (remote has the 11-21 fixes)
  if [ "$loc" = "$imp" ] || { [ "$loc" != "$imp" ] && [ "$rem" != "$imp" ]; }; then
    echo "$p" >> /tmp/u_take_remote.txt
  fi
done < /tmp/u_diff.txt
echo "   differing: $(wc -l < /tmp/u_diff.txt), take-remote: $(wc -l < /tmp/u_take_remote.txt)"

echo "== 3. apply remote versions"
while IFS= read -r p; do
  mkdir -p "$(dirname "$p")"
  git show "newmain/main:CG-Terminal/$p" > "$p"
done < /tmp/u_take_remote.txt

echo "== 4. copy remote-only files"
copied=0
while IFS= read -r p; do
  if [ ! -e "$p" ]; then
    mkdir -p "$(dirname "$p")"
    git show "newmain/main:CG-Terminal/$p" > "$p"
    copied=$((copied+1))
  fi
done < <(git ls-tree -r --name-only "newmain/main:CG-Terminal")
echo "   copied $copied remote-only files"

echo "== 5. engines + root docs from remote (same paths in remote root)"
git checkout newmain/main -- HFT Delta-Fibonacci-Institutional-Business
git show newmain/main:INSTITUTIONAL_AUDIT_REPORT.md > INSTITUTIONAL_AUDIT_REPORT.md
git show newmain/main:SECURITY.md > SECURITY.md
git show newmain/main:docs/ci-workflow.yml > docs/ci-workflow.yml
git show newmain/main:scripts/ops/parse_check_cg.py > scripts/ops/parse_check_cg.py
mkdir -p .github/workflows && cp docs/ci-workflow.yml .github/workflows/ci.yml
echo "   engines: $(find HFT -type f | wc -l) + $(find Delta-Fibonacci-Institutional-Business -type f | wc -l) files"

echo "== 6. untrack telemetry (remote audit policy; files stay on disk)"
git rm -r -q --cached desk/deepscan 2>/dev/null || true
git rm -q --cached desk/alerts.local.json 2>/dev/null || true
echo "   untracked"

echo "== 7. done — tree now staged-ready; git status summary:"
git add -A
git status --short | awk '{print $1}' | sort | uniq -c
echo "== take-remote list =="
cat /tmp/u_take_remote.txt
