#!/usr/bin/env python3
"""Verify the judging rubric against the criteria actually published to entrants.

Run:  python3 build/validate_rubric.py

WHY THIS EXISTS
---------------
The criteria a team is judged against are a term of their entry. Three documents
state them and, before this check existed, they had already drifted apart with
nobody noticing:

  * the five challenge pages publish five criteria each, and the names differ
    per challenge
  * the home page publishes "Five criteria, equal weight"
  * Participant T&Cs 12.1 names FOUR — "usefulness, clarity,
    integration/feasibility, and creativity" — which matches challenge 01 only

That is a live contract defect, not a typo. 12.2 says "The judges' decision is
final and no correspondence will be entered into", which is precisely the clause
that gets tested when a team is judged against criteria they did not agree to.

So this compares the rubric against the PUBLISHED SOURCE — `challenges.ts` in the
website repo, which is what an entrant actually reads — and fails on any
disagreement. It is deliberately not a check of the rubric against itself.

WHAT IT CANNOT CHECK
--------------------
The Word masters. The T&Cs live in `02 Event & Participant/` as .docx and are
generated into the site's legal pack by `scripts/legal-from-docx.py` in the
website repo. This script prints a reminder rather than pretending to verify
them; fixing 12.1 is a human editing a Word file.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install -r build/requirements.txt")

REPO_ROOT = Path(__file__).resolve().parent.parent
RUBRIC = REPO_ROOT / "rubric" / "rubric.yml"

# The website repo is a sibling of this one. Located rather than hardcoded so the
# check degrades to a clear skip rather than a confusing failure on a machine
# that only has one of the two repositories.
CHALLENGES_TS_CANDIDATES = [
    REPO_ROOT.parent / "website_" / "src" / "data" / "challenges.ts",
    REPO_ROOT.parent.parent / "website_" / "src" / "data" / "challenges.ts",
]

EXPECTED_CRITERIA_COUNT = 5  # published on the home page as "Five criteria, equal weight"


def find_challenges_ts() -> Path | None:
    return next((p for p in CHALLENGES_TS_CANDIDATES if p.is_file()), None)


def published_criteria(path: Path) -> dict[str, list[str]]:
    """Criteria per challenge, as an entrant reads them on the challenge page.

    Parsed from the source rather than the built HTML so this runs without a
    build. `criteria` and `sources` both use `{ name: '...', desc: '...' }`, so
    the criteria array is isolated first — matching on the shape alone would
    silently fold the dataset names in, which is how the earlier hand-count
    reported nine "criteria" for challenge 01.
    """
    text = path.read_text(encoding="utf-8")
    out: dict[str, list[str]] = {}

    for slug_match in re.finditer(r"slug:\s*'([a-z0-9-]+)'", text):
        slug = slug_match.group(1)
        tail = text[slug_match.end():]
        block = re.search(r"criteria:\s*\[(.*?)\n\s*\]", tail, re.S)
        if not block:
            continue
        names = re.findall(r"name:\s*'([^']+)'", block.group(1))
        if names:
            out[slug] = names
    return out


def main() -> int:
    failures: list[str] = []
    rubric = yaml.safe_load(RUBRIC.read_text(encoding="utf-8"))

    declared: dict[str, list[str]] = {
        slug: entry["criteria"] for slug, entry in rubric["challenges"].items()
    }

    # --- the rubric must be internally complete ---
    guidance = rubric.get("criterion_guidance") or {}
    for slug, names in declared.items():
        if len(names) != EXPECTED_CRITERIA_COUNT:
            failures.append(
                f"{slug}: {len(names)} criteria, but the home page publishes "
                f"'Five criteria, equal weight'"
            )
        for name in names:
            if name not in guidance:
                failures.append(f"{slug}/{name}: no entry in criterion_guidance")

    for name, g in guidance.items():
        for key in ("scoring", "a_five_looks_like"):
            if not g.get(key):
                failures.append(f"criterion_guidance/{name}: missing {key!r}")

    scale = rubric.get("scale") or {}
    anchors = scale.get("anchors") or {}
    for band in range(scale.get("min", 1), scale.get("max", 5) + 1):
        if band not in anchors:
            failures.append(
                f"scale: no written anchor for band {band}. Without anchors at every "
                f"band a five-point scale is five private opinions wearing the same number."
            )

    if not rubric.get("gates"):
        failures.append("no eligibility gates — the output rules must remain enforceable")

    # --- and it must match what entrants are actually told ---
    ts = find_challenges_ts()
    if ts is None:
        print(
            "  NOTE: challenges.ts not found alongside this repo, so the rubric was "
            "checked for internal consistency only.\n"
            "        The comparison against what entrants read is the point of this "
            "script — run it where both repositories are present.",
            file=sys.stderr,
        )
    else:
        published = published_criteria(ts)
        if not published:
            failures.append(f"could not parse any criteria from {ts}")

        for slug, names in published.items():
            key = next((k for k in declared if k.endswith(slug) or slug in k), None)
            if key is None:
                failures.append(f"{slug}: published on the site but absent from the rubric")
                continue
            if declared[key] != names:
                failures.append(
                    f"{slug}: rubric and published brief disagree.\n"
                    f"      published: {names}\n"
                    f"      rubric:    {declared[key]}\n"
                    f"      The published brief is what the entrant agreed to. Change the "
                    f"rubric, or amend the brief deliberately and re-run."
                )

        for key in declared:
            if not any(key.endswith(s) or s in key for s in published):
                failures.append(f"{key}: in the rubric but not published on any challenge page")

    if failures:
        print("Rubric FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    total = sum(len(v) for v in declared.values())
    print(
        f"Rubric OK: {len(declared)} challenges x {EXPECTED_CRITERIA_COUNT} criteria "
        f"({total} scored dimensions), {len(anchors)} scale anchors, "
        f"{len(rubric['gates'])} eligibility gates."
    )
    print(
        "  REMINDER — not checkable from here: Participant T&Cs 12.1 names four "
        "criteria and matches challenge 01 only.\n"
        "  Fix it in the Word master under '02 Event & Participant/', not in the "
        "generated JSON."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
