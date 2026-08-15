#!/usr/bin/env bash
#
# Creates the PUBLIC participant data repo in the Innovation-forum-Cambridgeshire org
# and pushes this scaffold to it.
#
# This is the participant plane. Everything here is public and anonymous by design —
# that is the entire point. Anonymous access is the only model that scales to ~100
# external participants with zero onboarding.
#
# Prerequisites:
#   brew install gh          (not currently installed on this Mac — verified 2026-08-15)
#   gh auth login            (as someone with repo-create rights in the org)
#
# Usage:
#   ./setup-github.sh [--org <org>] [--repo <name>] [--dry-run]

set -euo pipefail

ORG="Innovation-forum-Cambridgeshire"
REPO="hackathon-data"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --org)     ORG="${2:?}"; shift 2 ;;
    --repo)    REPO="${2:?}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
run() { if [[ $DRY_RUN -eq 1 ]]; then printf '    \033[2m[dry-run] %s\033[0m\n' "$*"; else eval "$@"; fi; }

say "Preflight"
command -v gh >/dev/null || { echo "ERROR: gh not found. brew install gh && gh auth login" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "ERROR: not authenticated. Run: gh auth login" >&2; exit 1; }
echo "    gh authenticated"

if ! gh api "orgs/${ORG}" >/dev/null 2>&1; then
  echo "ERROR: cannot see org ${ORG}. Check the name and that your account is a member." >&2
  exit 1
fi
echo "    org ${ORG} reachable"

say "Repository"
if gh repo view "${ORG}/${REPO}" >/dev/null 2>&1; then
  echo "    ${ORG}/${REPO} already exists — skipping creation"
else
  run "gh repo create '${ORG}/${REPO}' \
        --public \
        --description 'Open data for the Innovation Forum x R1X hackathon challenges. Parquet, CSV, PDF and Word, served anonymously — no account needed.' \
        --homepage 'https://data.inno-forum.co.uk'"
fi

say "Repository settings"
# Releases are the delivery mechanism, so make sure nothing disables them, and turn off
# the features that invite noise we will not staff during an event.
run "gh api -X PATCH 'repos/${ORG}/${REPO}' \
      -f has_issues=true \
      -f has_wiki=false \
      -f has_projects=false \
      -F allow_squash_merge=true \
      -F delete_branch_on_merge=true >/dev/null"

# Issues are how participants report data problems — label them up front so triage during
# the event is a filter, not an archaeology exercise.
for spec in \
  "data-quality:d73a4a:A value or column looks wrong" \
  "licence:0e8a16:Attribution or redistribution question" \
  "access:1d76db:Cannot download or connect" \
  "docs:5319e7:Documentation gap" \
  "during-event:fbca04:Raised live — triage first"
do
  IFS=: read -r name colour desc <<<"$spec"
  run "gh label create '$name' --repo '${ORG}/${REPO}' --color '$colour' --description '$desc' --force >/dev/null"
done

say "Push scaffold"
if [[ $DRY_RUN -eq 0 ]]; then
  git -C "$(dirname "$0")/.." rev-parse --git-dir >/dev/null 2>&1 || git -C "$(dirname "$0")/.." init -q
  cd "$(dirname "$0")/.."
  git add -A
  git diff --cached --quiet || git commit -qm "Scaffold: catalogue, build, worker, pipelines"
  git branch -M main
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/${ORG}/${REPO}.git"
  git push -u origin main
else
  echo "    [dry-run] would commit and push to ${ORG}/${REPO}"
fi

cat <<EOF

  Repo   : https://github.com/${ORG}/${REPO}
  Data   : https://data.inno-forum.co.uk  (once the Worker is deployed)

  Next:
    1. cd worker && npx wrangler deploy      # needs the inno-forum.co.uk zone in Cloudflare
    2. Verify CORS from a real browser — this is the acceptance test:
         fetch('https://data.inno-forum.co.uk/manifest.json').then(r => r.json()).then(console.log)
       If that works from a page on another origin, the whole participant plane works.

EOF
