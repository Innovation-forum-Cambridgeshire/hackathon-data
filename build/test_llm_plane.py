#!/usr/bin/env python3
"""Verify the LLM plane and the document licence gate.

Run:  python3 build/test_llm_plane.py

Two things are asserted here and they protect different failures.

THE DOCUMENT GATE is the licence one. Six documents across the catalogues carried
`extract_markdown: true` — an instruction to mirror them — and none declared a
licence. The manifest published `original` and `markdown` URLs for all of them,
asserting we host copies of somebody else's PDFs. Extracting a publisher's PDF
into markdown is a derivative work and is redistribution, exactly as mirroring a
parquet file is. The sources had a rigorous gate; documents walked past it.

THE LLM PLANE is a correctness one. Every team will point a model at this data,
and the failure mode is not that the model cannot find the files — it is that it
finds them and confidently misreads them. So llms.txt must carry the caveats, and
chunk IDs must be STABLE, because an answer that cites a chunk has to still
resolve after the next release.
"""

from __future__ import annotations

import glob
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from build import (  # noqa: E402
    build_chunks,
    build_llms_txt,
    build_manifest,
    document_mirrorable,
    load_catalogue,
    validate,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    failures: list[str] = []
    slugs = sorted(Path(p).stem for p in glob.glob(str(REPO_ROOT / "catalogue" / "*.yml")))

    all_chunk_ids: set[str] = set()

    for slug in slugs:
        cat = load_catalogue(slug)
        manifest = build_manifest(cat, "vTEST")

        # ---------- DOCUMENT LICENCE GATE ----------
        for doc, entry in zip(cat.get("documents") or [], manifest["documents"]):
            wants = doc.get("extract_markdown") or doc.get("chunk")
            cleared = document_mirrorable(doc)

            if entry["mirrored"] != cleared:
                failures.append(
                    f"{slug}/doc:{doc['id']}: manifest says mirrored={entry['mirrored']} "
                    f"but the licence test says {cleared}"
                )

            if not cleared:
                for key in ("original", "markdown"):
                    if entry.get(key):
                        failures.append(
                            f"{slug}/doc:{doc['id']}: publishes a {key} URL without a "
                            f"cleared licence. Extracting or hosting a publisher's "
                            f"document is redistribution — it needs the same gate a "
                            f"source does."
                        )
                if not entry.get("publisher_url"):
                    failures.append(
                        f"{slug}/doc:{doc['id']}: not mirrored and no publisher_url, so a "
                        f"reader has no way to reach it at all"
                    )
            elif wants and not doc.get("licence_evidence"):
                failures.append(
                    f"{slug}/doc:{doc['id']}: cleared for mirroring with no licence_evidence"
                )

        # ---------- llms.txt ----------
        text = build_llms_txt(cat, manifest, "vTEST")

        synthetic_tables = [
            t["name"] for t in manifest["tables"]
            if "SYNTHETIC" in (t.get("description") or "").upper()
        ]
        for name in synthetic_tables:
            if name not in text:
                failures.append(
                    f"{slug}: llms.txt omits synthetic table {name!r}. A model reading "
                    f"this will treat generated values as measurements."
                )

        if manifest["pointer_only"]:
            if "NOT mirrored" not in text:
                failures.append(
                    f"{slug}: llms.txt does not say which sources are pointer-only, so a "
                    f"model may assume our licence covers all of them"
                )

        # The caveats must come BEFORE the file listing. A model that reads top-down
        # and stops early should hit the warnings, not the download URLs.
        if "## Tables" in text and "## Read this before using any number" in text:
            if text.index("## Read this before using any number") > text.index("## Tables"):
                failures.append(f"{slug}: llms.txt puts the caveats after the table listing")

        for t in manifest["tables"]:
            if t.get("columns") and f"`{t['columns'][0]['name']}`" not in text:
                failures.append(f"{slug}: llms.txt omits the column contract for {t['name']}")

        # ---------- chunks.jsonl ----------
        raw = build_chunks(cat, manifest, "vTEST")
        chunks = [json.loads(l) for l in raw.strip().split("\n") if l]

        ids = [c["id"] for c in chunks]
        if len(ids) != len(set(ids)):
            failures.append(f"{slug}: duplicate chunk IDs")

        # Stability: IDs must be derived from names, never from position, or a cited
        # chunk silently repoints when a column is added.
        for c in chunks:
            if c["kind"] == "column" and c["id"] != f"{slug}#{c['table']}.{c['column']}":
                failures.append(f"{slug}: column chunk ID {c['id']!r} is not name-derived")
            if not c["text"].strip():
                failures.append(f"{slug}: chunk {c['id']} has empty text")

        expected_cols = sum(len(t.get("columns") or []) for t in manifest["tables"])
        got_cols = sum(1 for c in chunks if c["kind"] == "column")
        if got_cols != expected_cols:
            failures.append(
                f"{slug}: {got_cols} column chunks for {expected_cols} declared columns"
            )

        overlap = all_chunk_ids & set(ids)
        if overlap:
            failures.append(f"{slug}: chunk IDs collide with another challenge: {sorted(overlap)[:3]}")
        all_chunk_ids |= set(ids)

    # Determinism — a rebuild of the same version must produce identical chunks, or
    # a cited ID could resolve to different text.
    cat = load_catalogue(slugs[0])
    m = build_manifest(cat, "vTEST")
    if build_chunks(cat, m, "vTEST") != build_chunks(cat, m, "vTEST"):
        failures.append("build_chunks is not deterministic")

    if failures:
        print("LLM plane FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        f"LLM plane OK: {len(slugs)} challenges, {len(all_chunk_ids)} stable chunk IDs, "
        f"caveats ahead of the listing, and every uncleared document ships as a pointer."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
