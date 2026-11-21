#!/usr/bin/env bash
# Direction audit for the union merge of local main (root-level working dir,
# 2765 commits) with remote newmain/main (Trading-Strategies import, 17
# commits, CG-Terminal/ nesting). For every file that differs between the two
# trees, classify who changed it since the remote import base (419e4560):
#   REMOTE-WINS  local == import, remote changed  -> take remote (hardened/newer)
#   LOCAL-WINS   remote == import, local changed  -> keep local
#   BOTH-CHANGED both differ from import          -> inspect individually
set -u
cd /home/z/my-project
IMPORT=419e4560

git ls-tree -r main | awk '{print $3"\t"$4}' | sort -k2 > /tmp/dir_l.txt
git ls-tree -r "newmain/main:CG-Terminal" | awk '{print $3"\t"$4}' | sort -k2 > /tmp/dir_r.txt
join -t$'\t' -1 2 -2 2 /tmp/dir_l.txt /tmp/dir_r.txt | awk -F'\t' '$2!=$3 {print $1}' > /tmp/dir_diff.txt

echo "differing shared files: $(wc -l < /tmp/dir_diff.txt)"
: > /tmp/dir_remote_wins.txt; : > /tmp/dir_local_wins.txt; : > /tmp/dir_both.txt
while IFS= read -r p; do
  loc=$(git rev-parse "main:$p" 2>/dev/null || echo NONE)
  rem=$(git rev-parse "newmain/main:CG-Terminal/$p" 2>/dev/null || echo NONE)
  imp=$(git rev-parse "$IMPORT:CG-Terminal/$p" 2>/dev/null || echo NONE)
  if [ "$loc" = "$imp" ]; then echo "$p" >> /tmp/dir_remote_wins.txt
  elif [ "$rem" = "$imp" ]; then echo "$p" >> /tmp/dir_local_wins.txt
  else echo "$p" >> /tmp/dir_both.txt; fi
done < /tmp/dir_diff.txt
echo "REMOTE-WINS (remote hardened post-import, local unchanged): $(wc -l < /tmp/dir_remote_wins.txt)"
cat /tmp/dir_remote_wins.txt
echo "LOCAL-WINS (local changed, remote == import): $(wc -l < /tmp/dir_local_wins.txt)"
cat /tmp/dir_local_wins.txt
echo "BOTH-CHANGED (inspect): $(wc -l < /tmp/dir_both.txt)"
cat /tmp/dir_both.txt

echo; echo "=== desk updatedAt comparison (local vs remote state.json):"
python3 - <<'PY'
import json, subprocess
def updatedAt(ref, path):
    out = subprocess.run(["git","show",f"{ref}:{path}"],capture_output=True,text=True)
    try: return json.loads(out.stdout).get("updatedAt")
    except Exception: return f"parse-fail(rc={out.returncode})"
print("local  desk/state.json updatedAt:", updatedAt("main","desk/state.json"))
print("remote desk/state.json updatedAt:", updatedAt("newmain/main","CG-Terminal/desk/state.json"))
PY

echo; echo "=== does remote track sensitive desk files?"
git ls-tree -r --name-only "newmain/main:CG-Terminal" | grep -E "desk/(mt5\.json|positioning\.json|alerts\.local\.json)$" || echo "(none — good)"
echo "=== does remote track scan JSON/CSV/XLSX artifacts (non-research)?"
git ls-tree -r --name-only "newmain/main:CG-Terminal/scripts" | grep -E "\.(json|csv|xlsx)$" | grep -v research || echo "(none — good)"
echo "=== did local UUID commit 1f56965c touch src/ or scripts/ code?"
git show 1f56965c --name-only --format="" | grep -E "^(src|scripts)/" | head -10 || echo "(no code files — docs/spec only)"
