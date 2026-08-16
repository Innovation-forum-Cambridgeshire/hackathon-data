"""Column-level profile, and the drift check against a committed baseline.

A profile is a MEASUREMENT, not an assertion, and the distinction is the reason
this is a separate module from suites.py. Nothing here can fail a build on its
own: a column's quantiles moving is not by itself wrong, because the corpus is
regenerated and a reseed legitimately moves them a little.

What it is for is the question the expectations cannot answer — "what changed?"
A suite tells you the NDVI null rate is still inside 12-30%. It does not tell you
it moved from 21% to 29% in one commit, which is inside the band, is a large
change, and is exactly the shape of an accident. The baseline catches that.

Drift is reported at three levels:
    structural  a column appeared, vanished, or changed type       -> failure
    material    a null rate or cardinality moved a long way        -> warning
    ordinary    quantiles moved within tolerance                   -> noted

Only structural drift fails, because only structural drift is unambiguously
wrong. The rest is put in front of a human, which is the honest treatment of a
signal that is usually noise and occasionally the whole story.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Quantiles worth storing. The extremes matter more than the middle for this
# corpus: the planted defects live in the tails (the absurd temperatures, the
# stuck sensors), and a median barely moves when a tail is mangled.
QUANTILES = [0.0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0]

# Above these, a change is "material" and gets a warning.
NULL_RATE_TOLERANCE = 0.05      # absolute percentage points
CARDINALITY_TOLERANCE = 0.20    # relative
QUANTILE_TOLERANCE = 0.15       # relative to the interquartile range
ROW_COUNT_TOLERANCE = 0.20      # relative


def _json_safe(value: Any) -> Any:
    """Numpy and pandas scalars are not JSON-serialisable; dates need care."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if math.isnan(float(value)) else round(float(value), 6)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def profile_frame(df: pd.DataFrame, declared_columns: list[str]) -> dict[str, Any]:
    """Descriptive profile of one table."""
    out: dict[str, Any] = {"row_count": int(len(df)), "columns": {}}

    for col in declared_columns:
        if col not in df.columns:
            out["columns"][col] = {"present": False}
            continue
        s = df[col]
        entry: dict[str, Any] = {
            "present": True,
            "dtype": str(s.dtype),
            "kind": s.dtype.kind,
            "null_count": int(s.isna().sum()),
            "null_rate": round(float(s.isna().mean()), 6),
            "distinct": int(s.nunique(dropna=True)),
        }

        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            clean = s.dropna()
            if len(clean):
                qs = clean.quantile(QUANTILES)
                entry["quantiles"] = {str(q): _json_safe(qs.loc[q]) for q in QUANTILES}
                entry["mean"] = _json_safe(clean.mean())
                entry["stdev"] = _json_safe(clean.std())
                # Kept because the planted defects are tail events, and a jump in
                # either is the cheapest signal that a tail changed shape.
                entry["skew"] = _json_safe(clean.skew())
                entry["zero_rate"] = round(float((clean == 0).mean()), 6)
        elif pd.api.types.is_bool_dtype(s):
            entry["true_rate"] = round(float(s.dropna().mean()), 6) if s.notna().any() else None
        else:
            counts = s.value_counts(dropna=True)
            # Only store the domain when it is genuinely a closed set. Storing
            # the top values of a 33,755-value key column would make the baseline
            # enormous and would diff noisily for no benefit.
            if len(counts) <= 30:
                entry["domain"] = {str(k): int(v) for k, v in counts.items()}
            else:
                entry["top_values"] = {str(k): int(v) for k, v in counts.head(5).items()}
            lengths = s.dropna().astype(str).str.len()
            if len(lengths):
                entry["length_min"] = int(lengths.min())
                entry["length_max"] = int(lengths.max())

        out["columns"][col] = entry

    return out


@dataclass
class Drift:
    level: str  # structural | material | ordinary
    table: str
    column: str
    what: str
    was: Any
    now: Any

    @property
    def is_failure(self) -> bool:
        return self.level == "structural"


def compare(table: str, baseline: dict[str, Any], current: dict[str, Any]) -> list[Drift]:
    """Diff a fresh profile against the committed baseline."""
    drifts: list[Drift] = []

    b_rows, c_rows = baseline.get("row_count", 0), current.get("row_count", 0)
    if b_rows and abs(c_rows - b_rows) / b_rows > ROW_COUNT_TOLERANCE:
        drifts.append(Drift("material", table, "", "row count", b_rows, c_rows))

    b_cols, c_cols = baseline.get("columns", {}), current.get("columns", {})

    for col in sorted(set(b_cols) | set(c_cols)):
        b, c = b_cols.get(col), c_cols.get(col)
        if b is None:
            drifts.append(Drift("structural", table, col, "column added", None, c.get("dtype")))
            continue
        if c is None:
            drifts.append(Drift("structural", table, col, "column removed", b.get("dtype"), None))
            continue
        if not c.get("present", False):
            drifts.append(Drift("structural", table, col, "column missing from data", b.get("dtype"), None))
            continue
        # Compare dtype KIND, not the exact dtype: int32 -> int64 is a storage
        # detail, int -> float is a data change.
        if b.get("kind") != c.get("kind"):
            drifts.append(Drift("structural", table, col, "type kind changed", b.get("dtype"), c.get("dtype")))
            continue

        if abs(c.get("null_rate", 0) - b.get("null_rate", 0)) > NULL_RATE_TOLERANCE:
            drifts.append(Drift("material", table, col, "null rate", b.get("null_rate"), c.get("null_rate")))

        b_d, c_d = b.get("distinct", 0), c.get("distinct", 0)
        if b_d and abs(c_d - b_d) / b_d > CARDINALITY_TOLERANCE:
            drifts.append(Drift("material", table, col, "distinct values", b_d, c_d))

        # A category appearing or vanishing is structural for a closed domain —
        # every group-by downstream silently grows or loses a row.
        if "domain" in b and "domain" in c:
            gone = sorted(set(b["domain"]) - set(c["domain"]))
            new = sorted(set(c["domain"]) - set(b["domain"]))
            if gone:
                drifts.append(Drift("structural", table, col, "category disappeared", gone, None))
            if new:
                drifts.append(Drift("structural", table, col, "category appeared", None, new))

        if "quantiles" in b and "quantiles" in c:
            try:
                iqr = float(b["quantiles"]["0.75"]) - float(b["quantiles"]["0.25"])
            except (TypeError, KeyError):
                iqr = 0.0
            scale = abs(iqr) if iqr else 1.0
            for q in ("0.0", "0.5", "1.0"):
                bv, cv = b["quantiles"].get(q), c["quantiles"].get(q)
                if bv is None or cv is None:
                    continue
                if abs(float(cv) - float(bv)) / scale > QUANTILE_TOLERANCE:
                    label = {"0.0": "minimum", "0.5": "median", "1.0": "maximum"}[q]
                    drifts.append(Drift("ordinary", table, col, label, bv, cv))

    return drifts


def load_baseline(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_baseline(path: Path, profile: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8")
