"""Load catalogue/*.yml, defects.yml and relationships.yml into one spec.

The catalogue is the contract and is authoritative for schema. This module does
not second-guess it: if a column is declared, it is expected, and if it is not
declared, its presence is a contract failure. The defect and relationship files
add what the catalogue cannot express (deliberate flaws, cross-table keys) and
are checked for consistency against it on load, so a table renamed in one file
and not the other fails immediately rather than silently validating nothing.

That last point is the reason load_spec() raises rather than warns. A quality
suite that quietly validates zero tables is worse than no suite, because it
reports success.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    description: str = ""


@dataclass
class Table:
    challenge: str
    name: str
    grain: str
    description: str
    approx_rows: int | None
    csv_twin: bool
    columns: list[Column]
    index_columns: list[str] = field(default_factory=list)
    defects: list[dict[str, Any]] = field(default_factory=list)

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    @property
    def key(self) -> str:
        return f"{self.challenge}.{self.name}"

    def parquet_path(self, data_root: Path) -> Path:
        return data_root / self.challenge / "gold" / f"{self.name}.parquet"

    def csv_path(self, data_root: Path) -> Path:
        return data_root / self.challenge / "gold" / f"{self.name}.csv"


@dataclass
class Relationship:
    challenge: str
    name: str
    from_table: str
    from_columns: list[str]
    to_table: str
    to_columns: list[str]
    cardinality: str
    enforced: bool
    note: str
    parent_key_unique: bool = False
    reconciliation: dict[str, Any] | None = None


@dataclass
class Hazard:
    challenge: str
    name: str
    tables: list[str]
    note: str
    severity: str = "medium"


@dataclass
class Challenge:
    slug: str
    title: str
    domain: str
    event_date: str
    attribution: str
    handle_with_care: str
    sensitivity: dict[str, Any]
    tables: list[Table]
    relationships: list[Relationship]
    hazards: list[Hazard]
    blocked_tables: list[tuple[str, str]]  # (table name, blocked_by)


@dataclass
class Spec:
    challenges: list[Challenge]
    architecture: dict[str, Any]

    @property
    def tables(self) -> list[Table]:
        return [t for c in self.challenges for t in c.tables]

    def challenge(self, slug: str) -> Challenge:
        for c in self.challenges:
            if c.slug == slug:
                return c
        raise KeyError(slug)


# Catalogue types -> the type names GX will accept for them.
#
# THE NAMES ARE NOT PANDAS DTYPE STRINGS, and assuming they were cost an hour.
# ExpectColumnValuesToBeInTypeList resolves a name three different ways depending
# on how the column is stored, and this corpus contains all three:
#
#   nullable extension dtypes  matched on the DTYPE CLASS name.  A column of
#                              dtype `string[python]` matches "StringDtype" and
#                              matches neither "string" nor "object" nor "str".
#                              Most identifier columns here are like this.
#   object columns             matched ELEMENT-WISE on the Python type. The date
#                              columns hold datetime.date objects in an object
#                              column, so they match "date" and not
#                              "datetime64[ns]".
#   numpy dtypes               matched on the dtype name, with SQL-ish aliases —
#                              float64 matches "float64", "double" and "FLOAT".
#
# The list is a disjunction, so listing every spelling is safe. Being permissive
# across storage classes is also the right STRENGTH of check: the point is to
# catch an integer arriving as a float — which is how an integer key comes back
# after a naive CSV read, taking a ".0" with it and breaking every join — not to
# pin down whether pandas chose Int64 or int64 on this particular build.
#
# Verified against all 13 gold tables: 0 columns fail.
DTYPE_KINDS: dict[str, tuple[str, ...]] = {
    "string": ("StringDtype", "str", "object", "string"),
    "integer": (
        "Int64Dtype", "Int32Dtype", "Int16Dtype", "Int8Dtype",
        "int64", "int32", "int16", "int8",
    ),
    "double": ("Float64Dtype", "Float32Dtype", "float64", "float32", "double"),
    "boolean": ("BooleanDtype", "bool", "bool_"),
    # Every time PRECISION, not just [ns]. pandas 2 with pyarrow 21 hands back
    # datetime64[ns]; pandas 3 with pyarrow 25 preserves the parquet's own unit,
    # which is microseconds. Listing only [ns] made the suite pass on the machine
    # it was written on and fail in CI on identical data — the worst failure mode
    # a data-quality tool has, because it looks exactly like a data defect.
    #
    # Precision is not something this contract has an opinion about: the
    # catalogue says "date" and "datetime", and a timestamp is the same instant
    # at any unit. What it does have an opinion about is a date arriving as a
    # string, which every spelling below still rejects.
    "date": (
        "date", "Timestamp",
        "datetime64[ns]", "datetime64[us]", "datetime64[ms]", "datetime64[s]",
    ),
    "datetime": (
        "datetime", "date", "Timestamp",
        "datetime64[ns]", "datetime64[us]", "datetime64[ms]", "datetime64[s]",
        "datetime64[ns, UTC]", "datetime64[us, UTC]",
    ),
}


def _as_columns(raw: list[dict[str, Any]]) -> list[Column]:
    return [
        Column(name=c["name"], type=c.get("type", "string"), description=c.get("description", ""))
        for c in raw
    ]


def load_spec(repo_root: Path) -> Spec:
    """Assemble the full spec, cross-checking the three config files."""
    catalogue_dir = repo_root / "catalogue"
    config_dir = repo_root / "quality" / "config"

    defects_doc = yaml.safe_load((config_dir / "defects.yml").read_text(encoding="utf-8"))
    rel_doc = yaml.safe_load((config_dir / "relationships.yml").read_text(encoding="utf-8"))
    defects_by_challenge = defects_doc.get("challenges") or {}
    rel_by_challenge = rel_doc.get("challenges") or {}

    problems: list[str] = []
    challenges: list[Challenge] = []

    catalogue_files = sorted(catalogue_dir.glob("*.yml"))
    if not catalogue_files:
        raise SystemExit(f"no catalogue files under {catalogue_dir} — nothing to validate")

    for path in catalogue_files:
        cat = yaml.safe_load(path.read_text(encoding="utf-8"))
        slug = cat["challenge"]
        c_defects = defects_by_challenge.get(slug, {}) or {}
        c_rels = rel_by_challenge.get(slug, {}) or {}

        tables: list[Table] = []
        blocked: list[tuple[str, str]] = []

        for t in cat.get("gold_tables") or []:
            if "columns" not in t:
                # Pointer-only: the source has not cleared its licence gate, so no
                # bytes exist to validate. Recorded so the report can say why a
                # declared table is absent instead of silently omitting it.
                blocked.append((t["name"], str(t.get("blocked_by", "unknown"))))
                continue

            td = c_defects.get(t["name"], {}) or {}
            tables.append(
                Table(
                    challenge=slug,
                    name=t["name"],
                    grain=t.get("grain", ""),
                    description=t.get("description", ""),
                    approx_rows=t.get("approx_rows"),
                    csv_twin=bool(t.get("csv_twin", False)),
                    columns=_as_columns(t["columns"]),
                    index_columns=list(td.get("index_columns") or []),
                    defects=list(td.get("defects") or []),
                )
            )

        declared = {t.name for t in tables}

        # --- consistency: defects.yml must not name a table the catalogue lacks
        for tname in c_defects:
            if tname not in declared:
                problems.append(f"{slug}: defects.yml declares defects for unknown table {tname!r}")

        # --- consistency: every index column must exist
        for t in tables:
            missing = [c for c in t.index_columns if c not in t.column_names]
            if missing:
                problems.append(f"{slug}.{t.name}: index_columns not in catalogue: {missing}")

        # --- relationships
        rels: list[Relationship] = []
        for r in c_rels.get("relationships") or []:
            rel = Relationship(
                challenge=slug,
                name=r["name"],
                from_table=r["from"]["table"],
                from_columns=list(r["from"]["columns"]),
                to_table=r["to"]["table"],
                to_columns=list(r["to"]["columns"]),
                cardinality=r.get("cardinality", "many-to-one"),
                enforced=bool(r.get("enforced", True)),
                note=r.get("note", ""),
                parent_key_unique=bool(r.get("parent_key_unique", False)),
                reconciliation=r.get("reconciliation"),
            )
            for tbl, cols in ((rel.from_table, rel.from_columns), (rel.to_table, rel.to_columns)):
                if tbl not in declared:
                    problems.append(f"{slug}: relationship {rel.name!r} names unknown table {tbl!r}")
                    continue
                have = {t.name: t.column_names for t in tables}[tbl]
                bad = [c for c in cols if c not in have]
                if bad:
                    problems.append(f"{slug}: relationship {rel.name!r} — {tbl} has no column(s) {bad}")
            rels.append(rel)

        hazards = [
            Hazard(
                challenge=slug,
                name=h["name"],
                tables=list(h.get("tables") or []),
                note=h.get("note", ""),
                severity=h.get("severity", "medium"),
            )
            for h in (c_rels.get("hazards") or [])
        ]

        challenges.append(
            Challenge(
                slug=slug,
                title=cat.get("title", slug),
                domain=cat.get("domain", ""),
                event_date=str(cat.get("event_date", "")),
                attribution=cat.get("attribution", ""),
                handle_with_care=cat.get("handle_with_care", ""),
                sensitivity=cat.get("sensitivity") or {},
                tables=tables,
                relationships=rels,
                hazards=hazards,
                blocked_tables=blocked,
            )
        )

    # A config error here means the suite would validate the wrong thing, or
    # nothing. Both report success. Fail loudly instead.
    if problems:
        raise SystemExit(
            "quality config is inconsistent with the catalogue:\n  - " + "\n  - ".join(problems)
        )

    return Spec(challenges=challenges, architecture=rel_doc.get("architecture") or {})
