#!/usr/bin/env python3
"""
k-anonymity assessment and remediation.

Implements the de-identification controls described in the compliance design, §D.
Terminology and technique classification follow ISO/IEC 20889.

    python build/kanon.py assess  --file dist/gold/x.parquet --qids ward,role --k 5
    python build/kanon.py remediate --file dist/gold/x.parquet --qids ward,role --k 5 \
                                    --generalise ward=district --out dist/gold/x.parquet

WHY THIS IS THE BINDING CONTROL
    The published gold layer is claimed to be ANONYMISED, not pseudonymised — no
    surrogate mapping survives a build. That claim does not rest on having removed
    names; it rests on whether a row can be singled out by combining the columns
    that remain. "The councillor for X ward who chairs planning" names nobody and
    identifies one person.

    So k-anonymity is what earns the anonymisation claim, and a build that cannot
    reach the threshold must not ship. UK GDPR Recital 26 and the ICO's guidance
    both frame the test as "all means reasonably likely to be used" — which
    includes linkage against other datasets, so the quasi-identifier set is a
    HUMAN judgement recorded in the register, never inferred by this tool.

HONEST LIMITATION
    k-anonymity defends against re-identification, not attribute disclosure: if
    every member of an equivalence class shares a sensitive value, membership
    alone reveals it. l-diversity addresses that and is reported here as a
    diagnostic, but is not currently a gate — see the design doc §D.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    sys.exit("pandas is required: pip install -r build/requirements.txt")

# Defaults. Health-adjacent data (challenge 05) uses the higher floor.
DEFAULT_K = 5
HEALTH_K = 10


@dataclass
class Assessment:
    """Evidence written to the De-identification sheet of the Data Asset Register."""

    table: str
    quasi_identifiers: list[str]
    k_threshold: int
    k_achieved: int
    total_rows: int
    equivalence_classes: int
    failing_classes: int
    rows_at_risk: int
    l_diversity_min: int | None = None
    sensitive_attribute: str | None = None
    technique: str = "none"
    rows_generalised: int = 0
    rows_suppressed: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.k_achieved >= self.k_threshold

    def to_dict(self) -> dict:
        d = asdict(self)
        d["passed"] = self.passed
        return d


def _load(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix in {".csv", ".txt"}:
        return pd.read_csv(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def assess(
    df: pd.DataFrame,
    qids: list[str],
    k_threshold: int = DEFAULT_K,
    sensitive: str | None = None,
    table: str = "<unnamed>",
) -> Assessment:
    """Compute k for the given quasi-identifier set.

    k is the size of the SMALLEST equivalence class — the group of rows sharing an
    identical combination of quasi-identifier values. k=1 means at least one row is
    unique on those columns and can be singled out.
    """
    missing = [q for q in qids if q not in df.columns]
    if missing:
        raise KeyError(f"{table}: quasi-identifiers not present in data: {missing}")

    if df.empty:
        return Assessment(
            table=table, quasi_identifiers=qids, k_threshold=k_threshold,
            k_achieved=0, total_rows=0, equivalence_classes=0,
            failing_classes=0, rows_at_risk=0,
            notes=["empty dataset — nothing to assess"],
        )

    # NaN must be treated as a value, not dropped: rows sharing a missing ward are
    # still an equivalence class. dropna=False is load-bearing, not incidental.
    classes = df.groupby(qids, dropna=False, observed=True).size()

    k_achieved = int(classes.min())
    failing = classes[classes < k_threshold]

    a = Assessment(
        table=table,
        quasi_identifiers=list(qids),
        k_threshold=k_threshold,
        k_achieved=k_achieved,
        total_rows=int(len(df)),
        equivalence_classes=int(len(classes)),
        failing_classes=int(len(failing)),
        rows_at_risk=int(failing.sum()),
    )

    if sensitive and sensitive in df.columns:
        # l-diversity: distinct sensitive values per equivalence class.
        l_min = int(df.groupby(qids, dropna=False, observed=True)[sensitive].nunique().min())
        a.l_diversity_min = l_min
        a.sensitive_attribute = sensitive
        if l_min < 2:
            a.notes.append(
                f"l-diversity = {l_min}: at least one class shares a single value of "
                f"'{sensitive}', so membership discloses it even at k={k_achieved}."
            )

    if not a.passed:
        a.notes.append(
            f"{a.rows_at_risk} row(s) across {a.failing_classes} class(es) fall below "
            f"k={k_threshold}. Generalise or suppress before publication."
        )
    return a


def remediate(
    df: pd.DataFrame,
    qids: list[str],
    k_threshold: int = DEFAULT_K,
    generalise: dict[str, str] | None = None,
    table: str = "<unnamed>",
) -> tuple[pd.DataFrame, Assessment]:
    """Bring a table up to threshold: generalise first, suppress only what remains.

    Generalisation is tried first because it preserves rows — suppression throws
    away data and skews the distribution, so it is the last resort, and how much
    was suppressed is recorded as evidence.
    """
    working = df.copy()
    techniques: list[str] = []
    rows_generalised = 0

    for col, replacement in (generalise or {}).items():
        if col not in working.columns:
            continue
        if replacement not in working.columns:
            raise KeyError(
                f"{table}: generalisation target '{replacement}' is not a column. "
                f"Provide a coarser column (e.g. ward → district) in the source data."
            )
        rows_generalised += int(working[col].notna().sum())
        working[col] = working[replacement]
        techniques.append(f"generalisation({col}→{replacement})")

    a = assess(working, qids, k_threshold, table=table)

    rows_suppressed = 0
    if not a.passed:
        sizes = working.groupby(qids, dropna=False, observed=True)[qids[0]].transform("size")
        keep = sizes >= k_threshold
        rows_suppressed = int((~keep).sum())
        working = working[keep]
        techniques.append("suppression")
        a = assess(working, qids, k_threshold, table=table)

    a.technique = " + ".join(techniques) if techniques else "none"
    a.rows_generalised = rows_generalised
    a.rows_suppressed = rows_suppressed
    if rows_suppressed:
        pct = 100 * rows_suppressed / max(len(df), 1)
        a.notes.append(f"Suppressed {rows_suppressed} row(s) ({pct:.1f}% of input).")
        if pct > 10:
            a.notes.append(
                "WARNING: >10% suppressed. The result may no longer be representative — "
                "prefer a coarser generalisation over discarding this much data."
            )
    return working, a


def _report(a: Assessment) -> None:
    status = "PASS" if a.passed else "FAIL"
    print(f"\n  {status}  {a.table}")
    print(f"    quasi-identifiers : {', '.join(a.quasi_identifiers)}")
    print(f"    k achieved        : {a.k_achieved}  (threshold {a.k_threshold})")
    print(f"    rows              : {a.total_rows:,} in {a.equivalence_classes:,} class(es)")
    if a.failing_classes:
        print(f"    below threshold   : {a.failing_classes} class(es), {a.rows_at_risk} row(s)")
    if a.l_diversity_min is not None:
        print(f"    l-diversity (min) : {a.l_diversity_min}")
    if a.technique != "none":
        print(f"    technique         : {a.technique}")
    for n in a.notes:
        print(f"    • {n}")


def cmd_assess(args) -> int:
    df = _load(Path(args.file))
    qids = [q.strip() for q in args.qids.split(",") if q.strip()]
    a = assess(df, qids, args.k, sensitive=args.sensitive, table=args.table or Path(args.file).stem)
    _report(a)
    if args.json:
        Path(args.json).write_text(json.dumps(a.to_dict(), indent=2) + "\n")
    return 0 if a.passed else 1


def cmd_remediate(args) -> int:
    src = Path(args.file)
    df = _load(src)
    qids = [q.strip() for q in args.qids.split(",") if q.strip()]
    gen = dict(p.split("=", 1) for p in args.generalise.split(",") if "=" in p) if args.generalise else {}

    out_df, a = remediate(df, qids, args.k, gen, table=args.table or src.stem)
    _report(a)

    if not a.passed:
        print("\n  Could not reach threshold. Refusing to write output.", file=sys.stderr)
        return 1

    out = Path(args.out or args.file)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix == ".parquet":
        out_df.to_parquet(out, index=False)
    else:
        out_df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n  wrote {len(out_df):,} rows → {out}")
    if args.json:
        Path(args.json).write_text(json.dumps(a.to_dict(), indent=2) + "\n")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    for name, fn in (("assess", cmd_assess), ("remediate", cmd_remediate)):
        s = sub.add_parser(name)
        s.add_argument("--file", required=True)
        s.add_argument("--qids", required=True, help="comma-separated quasi-identifier columns")
        s.add_argument("--k", type=int, default=DEFAULT_K)
        s.add_argument("--table")
        s.add_argument("--json", help="write the assessment as JSON (register evidence)")
        if name == "assess":
            s.add_argument("--sensitive", help="column to test for l-diversity")
        else:
            s.add_argument("--generalise", help="col=coarser_col,col2=coarser_col2")
            s.add_argument("--out")
        s.set_defaults(func=fn)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
