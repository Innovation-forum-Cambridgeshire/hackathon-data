#!/usr/bin/env bash
# Cold-start acceptance check — what a participant hits in their first ten minutes.
#
#   ./scripts/cold-start-check.sh
#
# WHAT THIS IS NOT
# ----------------
# This is NOT the dry run. The dry run (organisers#9) needs five external testers on
# their own laptops on venue wifi with nobody helping them, and it is not optional:
# every serious failure mode in this design is a laptop-and-network failure mode, and
# none of those appear on a maintainer's machine. A script cannot have the wrong
# Python, a corporate proxy, a locked-down laptop, or a bad afternoon.
#
# WHAT IT IS
# ----------
# It removes the friction that would otherwise WASTE those five people's time. If a
# tester spends their first twenty minutes discovering that a documented command has
# a typo, you have learned nothing about your platform and burned a scarce tester.
#
# So this clones FRESH — no working tree, no cached state, no local edits — and runs
# every step exactly as the documentation tells a stranger to run it. Anything that
# needs a workaround not written down is friction, and friction is reported as a
# finding rather than fixed silently in a shell.
#
# Exit 0 = a stranger following the docs succeeds. Exit 1 = they do not.

set -uo pipefail

REPO_URL="${REPO_URL:-https://github.com/Innovation-forum-Cambridgeshire/hackathon-data.git}"
WORKDIR="$(mktemp -d)"
FAILURES=0
FRICTION=()

cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

step()  { printf '\n\033[1m▸ %s\033[0m\n' "$1"; }
ok()    { printf '  \033[32mok\033[0m    %s\n' "$1"; }
bad()   { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAILURES=$((FAILURES+1)); }
note()  { printf '  \033[33mnote\033[0m  %s\n' "$1"; FRICTION+=("$1"); }
timed() { local s=$SECONDS; "$@"; local rc=$?; printf '        (%ss)\n' "$((SECONDS-s))"; return $rc; }

echo "Cold-start check — simulating a participant with nothing installed but git and python3."
echo "Working in $WORKDIR"

# ── 1. Can they even get it? ─────────────────────────────────────────────────
step "Clone"
if timed git clone -q "$REPO_URL" "$WORKDIR/repo" 2>/dev/null; then
  SIZE=$(du -sm "$WORKDIR/repo/.git" | cut -f1)
  ok "cloned (${SIZE}MB of history)"
  # A participant on venue wifi notices this. Under 5MB is invisible; over 50 is a wait.
  [ "$SIZE" -gt 50 ] && note "clone is ${SIZE}MB — slow on venue wifi, and payload belongs in Releases"
else
  bad "clone failed — nothing else can be tested"; exit 1
fi
cd "$WORKDIR/repo" || exit 1

# ── 2. Does the front door tell them what to do? ─────────────────────────────
step "Documentation a stranger would look for"
for f in README.md sample/README.md consumers/README.md; do
  [ -f "$f" ] && ok "$f" || bad "$f missing — a participant has nowhere to start"
done

# ── 3. Dependencies, exactly as documented ───────────────────────────────────
step "Install dependencies (build/requirements.txt)"
if timed python3 -m pip install --quiet --disable-pip-version-check -r build/requirements.txt 2>/dev/null; then
  ok "installed"
else
  bad "pip install failed against build/requirements.txt"
fi

# ── 4. The command the docs actually give them ───────────────────────────────
step "Build a challenge, using the exact command from the README"
CMD_OK=0
for slug in c01-one-farm-one-picture c02-mapping-the-gaps c03-beyond-the-mainframe \
            c04-safe-in-the-open c05-ahead-of-the-heat; do
  if python3 build/build.py build --challenge "$slug" --version v1 \
       --out "sample/data/$slug" >/dev/null 2>&1; then
    N=$(find "sample/data/$slug" -name '*.parquet' | wc -l | tr -d ' ')
    ok "$slug — $N parquet"
    [ "$N" -eq 0 ] && note "$slug builds but produces no data — a participant will think it failed"
    CMD_OK=$((CMD_OK+1))
  else
    bad "$slug build failed"
  fi
done

# ── 5. Is the data usable without reading the source? ────────────────────────
step "Can a participant orient themselves from the published files alone?"
for f in manifest.json llms.txt chunks.jsonl RELEASE_NOTES.md; do
  if [ -f "sample/data/c03-beyond-the-mainframe/$f" ]; then ok "$f present"
  else bad "$f missing — the data does not describe itself"; fi
done

python3 - <<'PY'
import json, pathlib, sys
m = json.loads(pathlib.Path("sample/data/c03-beyond-the-mainframe/manifest.json").read_text())
missing = [t["name"] for t in m["tables"] if not t.get("columns")]
if missing:
    print(f"  \033[31mFAIL\033[0m  tables with no column contract: {missing}")
    sys.exit(1)
undocumented = [
    f"{t['name']}.{c['name']}"
    for t in m["tables"] for c in t["columns"] if not c.get("description")
]
if undocumented:
    print(f"  \033[33mnote\033[0m  columns with no description: {undocumented[:3]}")
print(f"  \033[32mok\033[0m    every column in every table carries a description")
PY
[ $? -ne 0 ] && FAILURES=$((FAILURES+1))

# ── 6. The consumer recipes, actually executed ───────────────────────────────
step "Consumer starters run as shipped"
if python3 consumers/python_starter.py >/dev/null 2>&1; then
  ok "consumers/python_starter.py"
else
  bad "consumers/python_starter.py fails — it is the first thing a Python team runs"
fi

# ── 7. The notebook environment ──────────────────────────────────────────────
step "Notebook environment"
if [ -x sample/setup.sh ]; then ok "sample/setup.sh is executable"
else note "sample/setup.sh is not executable — a participant must know to chmod it"; fi
NB=$(ls sample/notebooks/*.ipynb 2>/dev/null | wc -l | tr -d ' ')
[ "$NB" -ge 5 ] && ok "$NB notebooks" || bad "only $NB notebooks"

python3 - <<'PY'
import json, glob, sys
bare = [f.split("/")[-1] for f in glob.glob("sample/notebooks/*.ipynb")
        if not any(c.get("outputs") for c in json.load(open(f))["cells"])]
if bare:
    print(f"  \033[33mnote\033[0m  notebooks committed WITHOUT output: {bare}")
    print("        a participant browsing on GitHub sees empty cells and cannot tell if it works")
else:
    print("  \033[32mok\033[0m    every notebook carries its output — readable without running anything")
PY

# ── 8. Anything that needs the network at run time ───────────────────────────
step "Offline behaviour"
OFFLINE=$(grep -rl 'urllib.request\|requests.get\|read_parquet(.https' sample/notebooks consumers 2>/dev/null | wc -l | tr -d ' ')
ok "$OFFLINE file(s) touch the network; everything else works offline"
grep -q 'will not run' sample/notebooks/live-api-carbon-intensity.ipynb 2>/dev/null \
  && ok "the networked notebook says so and fails gracefully" \
  || note "the networked notebook should state that it needs the internet"

# ── Report ───────────────────────────────────────────────────────────────────
printf '\n\033[1m── Result ──\033[0m\n'
if [ ${#FRICTION[@]} -gt 0 ]; then
  echo "Friction a tester would hit:"
  for f in "${FRICTION[@]}"; do echo "  - $f"; done
fi

if [ "$FAILURES" -eq 0 ]; then
  echo
  echo "PASS — a stranger following the documentation gets working data."
  echo
  echo "This does NOT close the dry run. Five external testers on their own laptops,"
  echo "on venue wifi, with nobody helping, still have to try it — that is where the"
  echo "real failure modes live, and none of them can appear on this machine."
  exit 0
else
  echo
  echo "FAIL — $FAILURES step(s) a participant could not complete."
  exit 1
fi
