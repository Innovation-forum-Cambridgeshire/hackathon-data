#!/usr/bin/env bash
#
# Sets up the Azure DevOps ORGANISER plane for the Innovation Forum hackathon programme.
#
# Scope note (important): Azure DevOps here is for ORGANISERS ONLY — Boards for delivery
# tracking and a private Repo for confidential material. Participants never touch it.
# Participant data is served from the public GitHub repo in Innovation-forum-Cambridgeshire.
# See docs/SETUP.md §"Why the split" for the reasoning.
#
# Prerequisites (one-off, browser required — see docs/SETUP.md):
#   1. An Azure DevOps organisation must already exist. This script cannot create one:
#      org creation auto-provisions a user profile and is only possible via
#      https://dev.azure.com sign-in. Verified 2026-08-15 (profile API returns
#      VSS011031 "no profile for the authenticated user" until you sign in once).
#   2. az CLI + azure-devops extension:  az extension add --name azure-devops
#   3. Authenticate as EITHER:
#        az login                                    (Entra-backed orgs), or
#        export AZURE_DEVOPS_EXT_PAT=<pat>           (PAT with Work Items + Code: read/write)
#
# Usage:
#   ./setup-azure-devops.sh --org <org-name> [--project "<name>"] [--dry-run]
#
# Idempotent: safe to re-run. Existing projects, repos, iterations and work items
# (matched by title) are left alone rather than duplicated.

set -euo pipefail

ORG_NAME=""
PROJECT="Innovation Forum Hackathon"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --org)      ORG_NAME="${2:?--org needs a value}"; shift 2 ;;
    --project)  PROJECT="${2:?--project needs a value}"; shift 2 ;;
    --dry-run)  DRY_RUN=1; shift ;;
    -h|--help)  sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$ORG_NAME" ]] || { echo "ERROR: --org is required (e.g. --org innovation-forum)" >&2; exit 2; }
ORG_URL="https://dev.azure.com/${ORG_NAME}"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
skip() { printf '    \033[2m· %s\033[0m\n' "$*"; }
run()  { if [[ $DRY_RUN -eq 1 ]]; then printf '    \033[2m[dry-run] %s\033[0m\n' "$*"; else eval "$@"; fi; }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
say "Preflight"

command -v az >/dev/null || { echo "ERROR: az CLI not found. brew install azure-cli" >&2; exit 1; }

if ! az extension list -o tsv --query "[].name" 2>/dev/null | grep -qx azure-devops; then
  info "Installing azure-devops extension..."
  az extension add --name azure-devops --only-show-errors
fi
info "azure-devops extension present"

if ! az devops project list --org "$ORG_URL" -o none 2>/dev/null; then
  cat >&2 <<EOF

ERROR: cannot reach ${ORG_URL}

  Most likely the organisation does not exist yet. This script cannot create it —
  Azure DevOps org creation requires an interactive browser sign-in.

  Do this once, then re-run:
    1. Open https://dev.azure.com and sign in as yavin.owens@r1x.co.uk
    2. Create a new organisation named: ${ORG_NAME}
    3. Region: UK South (keeps programme data in-region)
    4. Re-run this script

  If the org DOES exist, authenticate first:
    az login    --or--    export AZURE_DEVOPS_EXT_PAT=<pat>

EOF
  exit 1
fi
info "Reached ${ORG_URL}"

az devops configure --defaults organization="$ORG_URL" >/dev/null

# ---------------------------------------------------------------------------
# Project — PRIVATE. Public projects are retired (Microsoft, 2026): new public
# projects cannot be created and existing ones convert to private in 2027.
# Microsoft's own documented migration path for public projects is *to GitHub*,
# which is exactly what the participant plane already does.
# ---------------------------------------------------------------------------
say "Project"

if az devops project show --project "$PROJECT" --org "$ORG_URL" -o none 2>/dev/null; then
  skip "project '$PROJECT' already exists"
else
  info "Creating private project '$PROJECT' (Agile process)"
  run "az devops project create \
        --name '$PROJECT' \
        --org '$ORG_URL' \
        --description 'Innovation Forum x R1X hackathon programme — organiser plane. Participant data lives in the public GitHub repo (Innovation-forum-Cambridgeshire/hackathon-data).' \
        --process Agile \
        --source-control git \
        --visibility private \
        -o none"
fi

# ---------------------------------------------------------------------------
# Repos — private, organiser-only. NOT the participant data repo.
# ---------------------------------------------------------------------------
say "Repos (private, organiser-only)"

# Azure DevOps always creates a default repo named after the project; we reuse it.
create_repo() {
  local name="$1" purpose="$2"
  if az repos show --repository "$name" --project "$PROJECT" --org "$ORG_URL" -o none 2>/dev/null; then
    skip "repo '$name' exists"
  else
    info "Creating repo '$name' — $purpose"
    run "az repos create --name '$name' --project '$PROJECT' --org '$ORG_URL' -o none"
  fi
}

create_repo "hackathon-organisers"  "judging rubrics, scores, DPIA working papers"
create_repo "hackathon-sponsors"    "sponsor-confidential material (challenge 03)"

# ---------------------------------------------------------------------------
# Iterations — the delivery plan from the architecture doc, §16
# ---------------------------------------------------------------------------
say "Iterations"

add_iteration() {
  local name="$1" start="$2" finish="$3"
  if az boards iteration project list --project "$PROJECT" --org "$ORG_URL" -o json 2>/dev/null \
     | grep -q "\"name\": \"$name\""; then
    skip "iteration '$name' exists"
  else
    info "Creating iteration '$name'  ($start → $finish)"
    run "az boards iteration project create \
          --name '$name' --start-date '$start' --finish-date '$finish' \
          --project '$PROJECT' --org '$ORG_URL' -o none"
  fi
}

add_iteration "P1 Skeleton"          2026-08-18 2026-08-31
add_iteration "P2 Challenge 03"      2026-09-01 2026-09-21
add_iteration "P3 C02 + catalogue"   2026-09-14 2026-09-27
add_iteration "P4 Consumers"         2026-09-21 2026-10-04
add_iteration "P5 LLM plane"         2026-10-05 2026-10-11
add_iteration "P6 Dry run"           2026-10-12 2026-10-25
add_iteration "EVENT C03"            2026-10-26 2026-10-30

# ---------------------------------------------------------------------------
# Boards — decisions first (they block), then delivery epics
# ---------------------------------------------------------------------------
say "Work items"

# Cache existing titles once so re-runs are cheap and don't duplicate.
EXISTING_TITLES="$(az boards query --org "$ORG_URL" --project "$PROJECT" \
  --wiql "SELECT [System.Title] FROM WorkItems WHERE [System.TeamProject] = '$PROJECT'" \
  -o json 2>/dev/null | python3 -c "
import sys, json
try:
    for wi in json.load(sys.stdin):
        print(wi.get('fields', {}).get('System.Title', ''))
except Exception:
    pass
" || true)"

add_item() {
  local type="$1" title="$2" desc="$3"
  if grep -Fxq "$title" <<<"$EXISTING_TITLES"; then
    skip "$type '$title' exists"
    return
  fi
  info "Creating $type: $title"
  run "az boards work-item create \
        --title '${title//\'/\'\\\'\'}' \
        --type '$type' \
        --project '$PROJECT' --org '$ORG_URL' \
        --description '${desc//\'/\'\\\'\'}' \
        -o none"
}

# --- Open decisions (architecture doc §17). These gate the build. ---
add_item "Issue" "D1 — Confirm GitHub org for participant data" \
  "RESOLVED pending confirmation: use the existing Innovation-forum-Cambridgeshire GitHub org (r1x.co.uk already has access). Supersedes the personal-account option. Verified 2026-08-15: org exists, currently no public repos."

add_item "Issue" "D2 — Decide: drop Postgres from v1?" \
  "Recommendation is DROP. Tableau Public (free) cannot connect to any live database (file-only), and Power BI Desktop is Windows-only — so a hosted database serves a minority on paid/Windows-only tooling while CSV twins serve everyone. Can be added in an afternoon later if a sponsor needs live SQL."

add_item "Issue" "D3 — Confirm October scope for all five challenges" \
  "Proposed: catalogue + docs + open-source gold tables for all five, with C03 to full depth. Full depth on all five is not achievable in ten weeks (C01 needs a Sentinel pipeline; C04/C05 need DPIAs first) and those four events run May-Jun 2027."

add_item "Issue" "D4 — Licence review: AHDB, Copernicus, DERI" \
  "BLOCKS the build. Confirm redistribution terms before mirroring any bytes. Not a technical task. Where redistribution is not permitted, the catalogue entry sets redistributable=false and we ship loader code plus a pointer instead."

add_item "Issue" "D5 — Azure Pipelines parallelism needs an Azure subscription link" \
  "The Microsoft-hosted free tier (1 job, 1800 min/month) is only granted once the Azure DevOps org is linked to a valid Azure subscription. Yavin has no role on either R1X subscription — Keith Brown is sole Owner. Options: (a) build on GitHub Actions instead (free, unlimited for public repos, no dependency) — RECOMMENDED; (b) ask Keith to link a subscription; (c) register a self-hosted agent (free, unlimited minutes, automatically granted)."

# --- Delivery epics ---
add_item "Epic" "P1 Skeleton — repo, first release, Worker, domain" \
  "Public repo in Innovation-forum-Cambridgeshire. First tagged release with a hand-made sample. Cloudflare Worker on data.inno-forum.co.uk. CORS verified in a real browser — this is the acceptance test, because GitHub release assets are NOT browser-fetchable without the Worker."

add_item "Epic" "P2 Challenge 03 — Beyond the Mainframe" \
  "The one that must ship for 26-30 Oct 2026. Sponsor integration, synthetic FinOps gold tables. Sponsor's own data lake and viewer stay theirs — we catalogue, we do not host."

add_item "Epic" "P3 Challenge 02 + catalogue for 01/04/05" \
  "C02 (Mapping the Gaps) fully mirrored — cleanest licensing, all OGL. C01/C04/C05 catalogued and documented."

add_item "Epic" "P4 Consumers — CSV twins, DuckDB-WASM, templates" \
  "CSV twins for every gold table (UTF-8 BOM, ISO-8601 dates). DuckDB-WASM browser page hosted on the data subdomain, NOT the marketing site. Power BI .pbit and Tableau workbook. Starter notebooks."

add_item "Epic" "P5 LLM plane — llms.txt, markdown mirrors, MCP server" \
  "llms.txt, manifest.json, page-anchored markdown mirrors of every PDF/Word doc, chunks.jsonl with stable IDs. MCP server so agents can query the data natively. Confirmed in scope."

add_item "Epic" "P6 Dry run — 5 external testers" \
  "NOT OPTIONAL. Five external testers, own laptops, venue-grade network, no help. Every failure mode in this design is a laptop-and-wifi failure mode and none appear on ours."

# --- Standing governance ---
add_item "Issue" "GOVERNANCE — no personal or special-category data, ever" \
  "Structural rule enforced by the build, not by memory. Challenges 04 (Safe in the Open) and 05 (Ahead of the Heat) touch sensitive domains: public-record or synthetic only. No exceptions, no 'just for the demo'. C05 charity service knowledge is consent-held health data — synthetic only."

add_item "Issue" "GOTCHA — DuckDB-WASM must not go on the marketing site" \
  "Embedding it on r1x.co.uk/public_hackathon would break scripts/verify-no-tracking.py and invalidate the published claim that the site makes no third-party requests on page load. Host on data.inno-forum.co.uk. If it ever moves, the legal copy, cookie notice and deploy gate change together."

# ---------------------------------------------------------------------------
say "Done"
cat <<EOF

  Organisation : ${ORG_URL}
  Project      : ${PROJECT}  (private)
  Boards       : ${ORG_URL}/${PROJECT// /%20}/_boards/board
  Repos        : hackathon-organisers, hackathon-sponsors

  Azure DevOps here is the ORGANISER plane only. Participants never sign in.
  Next: scripts/setup-github.sh to create the public participant repo.

EOF
