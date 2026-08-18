"""Reconcile each CSV twin against its parquet original.

WHY THIS IS A SEPARATE CHECK FROM THE CONTRACT SUITE
The contract suite validates the parquet. Participants using Excel, Power BI or
R read the CSV. Nothing in this repository previously compared the two on real
data: build/test_csv_contract.py asserts the ENCODING rules on a hand-made
one-row fixture, which is the right test for the writer and says nothing about
whether the 913,500-row file that shipped actually round-trips.

Both failure modes here are silent. The file still opens. It is just wrong:

    a missing BOM      Excel reads UTF-8 as Windows-1252 and 'cafe' arrives mangled
    a locale date      03/04 is the 3rd of April or the 4th of March, and both parse
    an integer drift   a null forces the column to float and IDs gain a '.0'
    a dropped row      no error anywhere, just a quieter total

So this reads both files and compares them, and separately re-reads the CSV the
way a naive consumer would (pandas defaults, no dtype hints) to see what that
person actually gets — which is the thing that matters and is not the same
question as whether the bytes are correct.

The result is one row per table, which is then validated by ordinary
expectations so it lands in Data Docs with everything else.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pandas as pd

import great_expectations as gx
import great_expectations.expectations as gxe

BOM = b"\xef\xbb\xbf"

# A date that is ambiguous under a locale swap: both parts are <= 12, so
# 03/04/2026 is a valid reading in either order and nothing errors.
AMBIGUOUS_DATE_HINTS = ("/",)


def reconcile_table(
    name: str, challenge: str, parquet: Path, csv_path: Path, declared_columns: list[str]
) -> dict[str, Any]:
    """Compare one CSV twin against its parquet. Never raises; reports instead."""
    row: dict[str, Any] = {
        "table": f"{challenge}/{name}",
        "csv_present": csv_path.exists(),
        "has_bom": False,
        "columns_match": False,
        "rows_match": False,
        "no_ambiguous_dates": True,
        "values_match": False,
        "naive_read_types_match": False,
        "parquet_rows": 0,
        "csv_rows": 0,
        "mismatched_cells": -1,
        "notes": "",
    }
    if not parquet.exists():
        row["notes"] = "parquet missing"
        return row

    pq = pd.read_parquet(parquet)
    row["parquet_rows"] = len(pq)

    if not csv_path.exists():
        # Not automatically a failure: the catalogue marks some tables csv_twin:
        # false because they are too large to ship twice. The caller decides.
        row["notes"] = "no CSV twin declared or present"
        return row

    raw_head = csv_path.open("rb").read(4096)
    row["has_bom"] = raw_head.startswith(BOM)

    # utf-8-sig strips the BOM if present and is harmless if not.
    cs = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str, keep_default_na=False, na_values=[""])
    row["csv_rows"] = len(cs)
    row["columns_match"] = list(cs.columns) == declared_columns
    row["rows_match"] = len(cs) == len(pq)

    # --- ambiguous dates -----------------------------------------------------
    # Any '/' inside a value in a date-ish column means it was not written
    # ISO-8601. Checked on the header row plus a sample rather than the whole
    # file, because this is a formatting property of the writer and is uniform.
    date_cols = [
        c
        for c in cs.columns
        if any(k in c for k in ("date", "month", "_at", "day"))
    ]
    sample = cs[date_cols].head(2000) if date_cols else pd.DataFrame()
    row["no_ambiguous_dates"] = not any(
        sample[c].astype(str).str.contains("/", regex=False).any() for c in sample.columns
    )

    # --- value equality ------------------------------------------------------
    # Compare as strings on the columns both files have, so a float formatting
    # difference does not read as a data difference. Numeric columns are compared
    # numerically with a tight tolerance instead.
    if row["columns_match"] and row["rows_match"]:
        mismatches = 0
        worst: list[str] = []
        for col in declared_columns:
            left, right = pq[col], cs[col]

            if pd.api.types.is_numeric_dtype(left) and not pd.api.types.is_bool_dtype(left):
                lnum = pd.to_numeric(left, errors="coerce")
                rnum = pd.to_numeric(right, errors="coerce")
                both_null = lnum.isna() & rnum.isna()
                close = (lnum - rnum).abs() <= (lnum.abs() * 1e-9 + 1e-9)
                bad = int((~(close | both_null)).sum())

            elif pd.api.types.is_datetime64_any_dtype(left):
                # Compare as INSTANTS, not as text. The parquet side holds a
                # Timestamp whose str() is "2026-06-09 14:31:09"; the CSV
                # correctly writes ISO-8601 "2026-06-09T14:31:09". Those are the
                # same moment and different strings, and comparing the strings
                # reports every row in the table as a mismatch — which is what
                # the first version of this did, on all 24,000 rows of
                # message_signals. The separator is the CSV being right.
                rdt = pd.to_datetime(right, errors="coerce", format="ISO8601")
                both_null = left.isna() & rdt.isna()
                bad = int((~((left == rdt) | both_null)).sum())

            else:
                lstr = left.astype(str).str.strip()
                rstr = right.astype(str).str.strip()
                both_null = left.isna() & right.isna()
                bad = int((~((lstr == rstr) | both_null)).sum())

            mismatches += bad
            if bad:
                worst.append(f"{col} ({bad:,})")

        row["mismatched_cells"] = mismatches
        row["values_match"] = mismatches == 0
        if worst and not row["notes"]:
            row["notes"] = "differs in: " + ", ".join(worst[:3])

    # --- what a naive consumer actually gets ---------------------------------
    # No dtype hints, exactly as `pd.read_csv(path)` in a starter notebook. If an
    # integer column comes back as float here, every ID in it has gained a '.0'
    # and every join a participant writes against it will silently return zero
    # rows. That is a real defect in the FILE even though the bytes are correct.
    try:
        naive = pd.read_csv(csv_path, nrows=5000)
        drift = []
        for col in declared_columns:
            if col not in naive.columns:
                continue
            want, got = pq[col].dtype.kind, naive[col].dtype.kind
            # b=bool, i/u=int, f=float, O=object, M=datetime
            if want in "iu" and got == "f":
                drift.append(f"{col}: integer read back as float")
            elif want == "b" and got not in "bO":
                drift.append(f"{col}: boolean read back as {naive[col].dtype}")
        row["naive_read_types_match"] = not drift
        if drift:
            row["notes"] = "; ".join(drift[:3])
    except Exception as exc:  # a CSV that pandas cannot read at all is the finding
        row["naive_read_types_match"] = False
        row["notes"] = f"pandas could not read the CSV with defaults: {exc}"

    return row


def build_suite(frame: pd.DataFrame) -> gx.ExpectationSuite:
    """Expectations over the reconciliation frame — one row per table."""
    suite = gx.ExpectationSuite(name="programme.csv-twin.reconciliation")
    checks = [
        ("has_bom", "every CSV twin starts with a UTF-8 BOM",
         "Without it Excel reads the file as Windows-1252 and every accented place "
         "name arrives mangled. The file still opens, which is why this is asserted."),
        ("columns_match", "CSV columns match the catalogue, in order",
         "The CSV is positional for anyone reading it without a header."),
        ("rows_match", "CSV and parquet have the same number of rows",
         "A dropped row produces no error anywhere — just a quieter total."),
        ("no_ambiguous_dates", "dates are ISO-8601, never locale-dependent",
         "03/04/2026 is the 3rd of April or the 4th of March depending on where the "
         "reader sits, and both parse without complaint."),
        ("values_match", "every cell in the CSV equals its parquet counterpart",
         "Compared numerically where the column is numeric, so this is a data "
         "difference and not a formatting one."),
        ("naive_read_types_match",
         "pd.read_csv with no options returns the declared types",
         "This is what a starter notebook does. An integer key read back as a float "
         "gains a '.0' and every join written against it silently returns nothing."),
    ]
    for col, description, notes in checks:
        suite.add_expectation(
            gxe.ExpectColumnValuesToBeInSet(
                column=col, value_set=[True],
                description=description, notes=notes,
                meta={"dimension": "csv twin reconciliation"},
            )
        )
    suite.add_expectation(
        gxe.ExpectColumnValuesToBeBetween(
            column="mismatched_cells", min_value=0, max_value=0,
            description="no cell differs between the CSV and the parquet",
            notes="Reported separately from values_match so the report shows the size "
                  "of a difference, not only that there is one.",
            meta={"dimension": "csv twin reconciliation"},
        )
    )
    return suite
