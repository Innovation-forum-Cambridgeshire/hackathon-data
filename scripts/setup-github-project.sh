#!/usr/bin/env bash
#
# Sets up the ORGANISER plane: a GitHub Project board, a private organisers repo, and
# the delivery epics and open decisions as tracked issues.
#
# WHY GITHUB PROJECTS AND NOT AZURE DEVOPS
#   Azure DevOps was the first choice and was abandoned for a hard blocker, not a
#   preference. Verified in the browser on 2026-08-15: creating an Azure DevOps
#   organisation on a work account requires selecting an Azure subscription for billing,
#   and the signup refuses with "You need to be an owner or contributor on the
#   subscription to set up billing." Yavin holds no role on either R1X subscription
#   (Keith Brown is sole Owner), and the form offers no "none" option. The plain
#   /signup/ route enforces the same rule.
#
#   Rather than take a dependency on Keith at step one, the organiser plane moved to
#   GitHub — which also removes the 5-user Basic cap, keeps tracking next to the data
#   and CI, and stays entirely free. (Note: linking a subscription would NOT have cost
#   anything; the free tier persists. It was a permissions blocker, not a cost one.)
#
# Prerequisites:
#   brew install gh && gh auth login
#   gh auth refresh -s project,read:project   # Projects v2 needs its own scope
#
# Usage:
#   ./setup-github-project.sh [--org <org>] [--dry-run]

set -euo pipefail

ORG="Innovation-forum-Cambridgeshire"
DATA_REPO="hackathon-data"
ORG_REPO="hackathon-organisers"
PROJECT_TITLE="Hackathon Programme"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --org)     ORG="${2:?}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
skip() { printf '    \033[2m· %s\033[0m\n' "$*"; }
run()  { if [[ $DRY_RUN -eq 1 ]]; then printf '    \033[2m[dry-run] %s\033[0m\n' "$*"; else eval "$@"; fi; }

say "Preflight"
command -v gh >/dev/null || { echo "ERROR: gh not found. brew install gh && gh auth login" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "ERROR: not authenticated. gh auth login" >&2; exit 1; }

if ! gh auth status 2>&1 | grep -q "project"; then
  info "NOTE: Projects v2 needs an extra scope. If the project steps fail, run:"
  info "      gh auth refresh -s project,read:project"
fi
gh api "orgs/${ORG}" >/dev/null 2>&1 || { echo "ERROR: cannot see org ${ORG}" >&2; exit 1; }
info "org ${ORG} reachable"

# ---------------------------------------------------------------------------
say "Private organisers repo"
# Split by audience, not by wrapping everything in auth: the participant repo is public
# so every tool works with no credentials; anything confidential lives here instead.
if gh repo view "${ORG}/${ORG_REPO}" >/dev/null 2>&1; then
  skip "${ORG_REPO} exists"
else
  run "gh repo create '${ORG}/${ORG_REPO}' --private \
        --description 'Organiser-only: judging rubrics, scores, DPIA working papers, sponsor-confidential material. Participants never see this.'"
fi

# ---------------------------------------------------------------------------
say "Project board"
PROJECT_NUMBER="$(gh project list --owner "$ORG" --format json 2>/dev/null \
  | python3 -c "
import sys, json
try:
    for p in json.load(sys.stdin).get('projects', []):
        if p.get('title') == '${PROJECT_TITLE}':
            print(p['number']); break
except Exception:
    pass
" || true)"

if [[ -n "$PROJECT_NUMBER" ]]; then
  skip "project '${PROJECT_TITLE}' exists (#${PROJECT_NUMBER})"
else
  info "Creating project '${PROJECT_TITLE}'"
  if [[ $DRY_RUN -eq 0 ]]; then
    PROJECT_NUMBER="$(gh project create --owner "$ORG" --title "$PROJECT_TITLE" --format json \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['number'])")"
    info "created #${PROJECT_NUMBER}"
  else
    PROJECT_NUMBER="N"
  fi
fi

# ---------------------------------------------------------------------------
say "Issues — decisions first (they block), then delivery epics"

# Cache existing titles so re-runs don't duplicate.
EXISTING="$(gh issue list --repo "${ORG}/${ORG_REPO}" --state all --limit 200 \
  --json title -q '.[].title' 2>/dev/null || true)"

mk() {
  local title="$1" body="$2" labels="${3:-}"
  if grep -Fxq "$title" <<<"$EXISTING"; then
    skip "$title"
    return
  fi
  info "$title"
  if [[ $DRY_RUN -eq 1 ]]; then return; fi
  local url
  url="$(gh issue create --repo "${ORG}/${ORG_REPO}" \
        --title "$title" --body "$body" ${labels:+--label "$labels"} 2>/dev/null)" || {
    # Labels may not exist yet on a fresh repo; retry without them.
    url="$(gh issue create --repo "${ORG}/${ORG_REPO}" --title "$title" --body "$body")"
  }
  gh project item-add "$PROJECT_NUMBER" --owner "$ORG" --url "$url" >/dev/null 2>&1 \
    || info "  (could not add to project — check the 'project' auth scope)"
}

mk "D2 — Decide: drop Postgres from v1?" \
"Recommendation: **DROP**.

Tableau Public (the free tier) cannot connect to any live database — it is file-only.
Power BI Desktop is Windows-only. So a hosted database serves a minority of participants
on paid or Windows-only tooling, while the CSV twins serve everyone.

DuckDB over HTTPS parquet already gives full SQL to anyone who wants it, with no server
to run. Postgres can be added in an afternoon later if a sponsor needs live SQL."

mk "D3 — Confirm October scope for all five challenges" \
"Proposed reading of 'all five': catalogue + docs + open-source gold tables for all five,
with C03 (Beyond the Mainframe) to full depth.

Full depth on all five is not achievable in ten weeks and would not pay for itself:
C01 needs a Sentinel imagery pipeline, and C04/C05 need DPIAs completed first. Those four
events run May–June 2027, so the backfill phase lands well ahead of them."

mk "D4 — Licence review: AHDB, Copernicus, DERI" \
"**BLOCKS mirroring any third-party bytes.** Not a technical task.

Confirm redistribution terms before a single byte is mirrored. Where redistribution is
not permitted, the catalogue sets \`redistributable: false\` and the build ships loader
code plus a pointer instead — this is enforced by \`build/build.py\`, not by memory.

The build already runs without this: it publishes the catalogue, manifest and documents,
and mirrors only the two synthetic datasets we author ourselves under CC0."

mk "P1 Skeleton — repo, first release, Worker, domain" \
"Public repo in ${ORG}. First tagged release with a hand-made sample. Cloudflare Worker on
data.inno-forum.co.uk.

**Acceptance test: CORS verified from a real browser on another origin.** Not curl — curl
does not enforce CORS and will pass whether or not the Worker is doing its job. GitHub
release assets are NOT browser-fetchable without the Worker, so this is the gate."

mk "P2 Challenge 03 — Beyond the Mainframe" \
"The one that must ship for 26–30 Oct 2026. Sponsor integration, synthetic FinOps gold
tables. The sponsor's own data lake and viewer stay theirs — we catalogue it, we do not
host it."

mk "P3 Challenge 02 + catalogue for 01/04/05" \
"C02 (Mapping the Gaps) fully mirrored — cleanest licensing, all OGL. C01/C04/C05
catalogued and documented."

mk "P4 Consumers — CSV twins, DuckDB-WASM, templates" \
"CSV twins for every gold table (UTF-8 BOM, ISO-8601 dates — otherwise the first thing a
participant sees is mangled accents and American dates). DuckDB-WASM page hosted on the
data subdomain. Power BI .pbit, Tableau workbook, starter notebooks."

mk "P5 LLM plane — llms.txt, markdown mirrors, MCP server" \
"llms.txt, manifest.json, page-anchored markdown mirrors of every PDF/Word doc,
chunks.jsonl with stable IDs. MCP server so agents can query the data natively.

chunks.jsonl matters more than it looks: it saves every AI team the four hours they would
otherwise lose to PDF parsing."

mk "P6 Dry run — 5 external testers" \
"**NOT OPTIONAL.** Five external testers, own laptops, venue-grade network, no help.
Every failure mode in this design is a laptop-and-wifi failure mode and none of them
appear on ours."

mk "GOVERNANCE — no personal or special-category data, ever" \
"Structural rule enforced by \`build/build.py\`, not by memory: a catalogue declaring
\`personal_data: true\` or \`special_category: true\` fails validation.

Challenges 04 (Safe in the Open) and 05 (Ahead of the Heat) touch sensitive domains:
public-record or synthetic only. C05's charity service knowledge is consent-held health
data and is never mirrored — a synthetic cohort stands in for it."

mk "GOTCHA — DuckDB-WASM must not go on the marketing site" \
"Embedding it on r1x.co.uk/public_hackathon would break \`scripts/verify-no-tracking.py\`
and invalidate the published claim that the site makes no third-party requests on page
load. Host it on data.inno-forum.co.uk instead.

If it ever moves, the legal copy, the cookie notice and the deploy gate change together —
not silently."

# ---------------------------------------------------------------------------
say "Done"
cat <<EOF

  Project  : https://github.com/orgs/${ORG}/projects/${PROJECT_NUMBER}
  Organisers repo (private) : https://github.com/${ORG}/${ORG_REPO}
  Data repo (public)        : https://github.com/${ORG}/${DATA_REPO}

  Everything free: unlimited private repos, Projects, and Actions minutes on public repos.
  No Azure subscription, no per-seat cap.

EOF
