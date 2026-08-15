"""Load a challenge's gold tables into pandas.

One function, because the notebooks should spend their first cell on the data and
not on path wrangling.

WHY THIS READS manifest.json RATHER THAN GLOBBING THE DIRECTORY
---------------------------------------------------------------
The manifest carries the column contract — names, types and descriptions — that
the catalogue declares and the build enforces. Reading it means a notebook can
show a participant what a column MEANS without anyone restating the schema in
markdown, where it would immediately start drifting from the catalogue.

It also means a notebook fails loudly when the data it expects is not there,
rather than silently loading four of five tables and producing a plausible chart
from an incomplete join.

Nothing here touches the network. The data is built locally first — see
sample/README.md — which keeps the notebooks runnable on a train, in a room with
hostile wifi, and by someone who has not been given any credentials, because
there are none to give.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# sample/lib/loader.py -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA_DIR = REPO_ROOT / "sample" / "data"


@dataclass
class Challenge:
    """A loaded challenge: its tables, and the contract that describes them."""

    slug: str
    title: str
    tables: dict[str, pd.DataFrame]
    manifest: dict

    def describe(self, table: str) -> pd.DataFrame:
        """The published column contract for one table, as a frame.

        Use this instead of `df.dtypes`. The dtypes tell you a column is a float;
        the contract tells you it is a percentage rather than a fraction, which is
        the thing that actually causes wrong answers.
        """
        entry = next((t for t in self.manifest["tables"] if t["name"] == table), None)
        if entry is None:
            raise KeyError(f"{table!r} is not in the manifest. Have: {sorted(self.tables)}")
        return pd.DataFrame(entry.get("columns") or [])

    def caveats(self) -> list[str]:
        """Every table description that flags synthetic or otherwise limited data.

        Surfaced deliberately. Several tables in this programme look like
        observations and are not — c05's weather is generated because the Met
        Office source is pointer-only, and c03's grid intensity is synthetic. A
        finding reported from those as if measured is wrong in a way that is very
        hard to spot downstream.
        """
        out = []
        for t in self.manifest["tables"]:
            desc = t.get("description") or ""
            if "SYNTHETIC" in desc.upper() or "synthetic" in desc:
                out.append(f"{t['name']}: {desc.strip()}")
        return out

    def __repr__(self) -> str:
        rows = ", ".join(f"{n}={len(d):,}" for n, d in self.tables.items())
        return f"<Challenge {self.slug} ({rows})>"


def load(slug: str, data_dir: Path | str | None = None) -> Challenge:
    """Load every gold table for `slug` from a local build.

    Args:
        slug: challenge slug, e.g. "c03-beyond-the-mainframe".
        data_dir: where the builds live. Defaults to sample/data/.
    """
    base = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    root = base / slug

    if not root.exists():
        raise FileNotFoundError(
            f"No build found at {root}.\n\n"
            f"Build it first, from the repo root:\n\n"
            f"    python build/build.py build --challenge {slug} \\\n"
            f"        --version v1 --out sample/data/{slug}\n\n"
            f"The data is deliberately not committed — it is release payload, and a "
            f"71 MB CSV in the tree would defeat the whole point of publishing via "
            f"GitHub Releases."
        )

    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"{manifest_path} is missing — the build did not complete.")
    manifest = json.loads(manifest_path.read_text())

    tables: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for entry in manifest["tables"]:
        pq = root / "gold" / f"{entry['name']}.parquet"
        if pq.exists():
            tables[entry["name"]] = pd.read_parquet(pq)
        else:
            missing.append(entry["name"])

    if missing:
        # Loud, not silent. A notebook that quietly loses a table still produces
        # charts, and they look fine.
        raise FileNotFoundError(
            f"{slug}: the manifest declares {len(manifest['tables'])} table(s) but "
            f"{missing} were not built.\n"
            f"Most likely the source is still pointer-only — check the build output "
            f"for a licence or generator note."
        )

    return Challenge(slug=slug, title=manifest["title"], tables=tables, manifest=manifest)


def available(data_dir: Path | str | None = None) -> list[str]:
    """Challenge slugs that have been built locally."""
    base = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if (p / "manifest.json").exists())
