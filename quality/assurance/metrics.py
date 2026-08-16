"""Metrics for the defects Great Expectations cannot express directly.

MOST of the defect profile maps onto stock expectations: a null rate is
ExpectColumnProportionOfNonNullValuesToBeBetween, a class balance is a mean, a
closed domain is a value set. Those are built straight onto the table in
suites.py and are not here.

What is here is the residue — the defects whose definition needs a window, a
join, or a comparison between two groups:

    clustering of nulls along time within a partition
    whether the missingness is correlated with something that matters
    a run of identical readings from a stuck sensor
    whether a quality flag catches the duplicates it ought to
    calibration of a score against an outcome
    the spread of group means

Each is reduced to a single number. Those numbers are then collected into a
one-row DataFrame per challenge and validated with ordinary range expectations,
which is what puts them in Data Docs next to everything else rather than in a
log nobody reads.

WHY ONE ROW WIDE RATHER THAN MANY ROWS LONG
    A long frame (one row per metric) would need one expectation per row and GX
    applies a column expectation to every row in the column, so the bounds would
    have to be the same for all of them. Wide gives each metric its own column,
    its own bounds, and its own line in the report.

The cost of this approach is that a failing metric cannot point at the rows that
caused it — there is one row and it is the metric. That is accepted: these are
population-level properties, and "21% of NDVI is missing" has no ten rows to
show. The row-level failures, which do carry their top ten, are the contract
ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class Metric:
    """One computed number, with the bounds it must fall inside."""

    id: str
    challenge: str
    table: str
    defect_id: str
    title: str
    value: float
    min_value: float | None
    max_value: float | None
    unit: str
    lesson: str
    if_it_disappears: str
    severity: str
    detail: dict[str, Any]

    @property
    def ok(self) -> bool:
        if self.value is None or (isinstance(self.value, float) and np.isnan(self.value)):
            return False
        if self.min_value is not None and self.value < self.min_value:
            return False
        if self.max_value is not None and self.value > self.max_value:
            return False
        return True


def _longest_flat_run(series: pd.Series) -> int:
    """Longest run of identical consecutive values."""
    if series.empty:
        return 0
    changed = series.ne(series.shift())
    return int(changed.cumsum().value_counts().max())


def _longest_null_run(mask: pd.Series) -> int:
    """Longest run of consecutive True in a boolean mask."""
    if mask.empty or not mask.any():
        return 0
    groups = (~mask).cumsum()
    return int(mask.groupby(groups).sum().max())


def compute(
    challenge: str,
    table: str,
    defect: dict[str, Any],
    frames: dict[str, pd.DataFrame],
) -> Metric | None:
    """Compute one defect metric, or None if this defect needs no derived metric.

    Returning None is normal and expected: a defect whose `kind` is handled
    natively in suites.py, or one that is a purely semantic guarantee with no
    number attached (`kind: semantic`), has nothing to compute here.
    """
    kind = defect.get("kind", "")
    df = frames[table]
    bounds = defect.get("bounds") or {}
    base = dict(
        challenge=challenge,
        table=table,
        defect_id=defect["id"],
        title=defect.get("title", defect["id"]),
        lesson=defect.get("lesson", ""),
        if_it_disappears=defect.get("if_it_disappears", ""),
        severity=defect.get("severity", "by-design"),
    )

    def m(mid: str, value, lo, hi, unit, **detail) -> Metric:
        return Metric(
            id=f"{table}__{defect['id']}__{mid}",
            value=float(value) if value is not None else float("nan"),
            min_value=None if lo is None else float(lo),
            max_value=None if hi is None else float(hi),
            unit=unit,
            detail=detail,
            **base,
        )

    # ---- a compound key that is deliberately not unique -------------------
    if kind == "compound_key_not_unique":
        cols = defect["columns"]
        excess = int(df.duplicated(cols).sum())
        return m(
            "rate",
            excess / len(df) if len(df) else 0.0,
            bounds.get("min_rate"),
            bounds.get("max_rate"),
            "share of rows",
            duplicate_rows=excess,
            total_rows=int(len(df)),
        )

    # ---- the flag that must NOT catch the duplicates ----------------------
    if kind == "flag_asymmetry":
        keys = defect["key_columns"]
        flag, clean = defect["flag_column"], defect["clean_value"]
        dup_mask = df.duplicated(keys, keep=False)
        if not dup_mask.any():
            # No duplicates at all. The asymmetry is vacuously "true" and that is
            # not a pass — the sibling defect has already failed, and reporting
            # this one as green would be actively misleading.
            return m("unflagged_groups", 0, bounds.get("min_unflagged_groups"), None,
                     "duplicate groups", note="no duplicates present at all")
        flagged_per_group = (
            df[dup_mask].assign(_bad=df.loc[dup_mask, flag].ne(clean)).groupby(keys)["_bad"].sum()
        )
        unflagged = int((flagged_per_group == 0).sum())
        return m(
            "unflagged_groups",
            unflagged,
            bounds.get("min_unflagged_groups"),
            None,
            "duplicate groups carrying no flag",
            duplicate_groups=int(len(flagged_per_group)),
        )

    # ---- values outside anything physically plausible ---------------------
    if kind == "out_of_range":
        col = defect["column"]
        rng = defect["plausible_range"]
        outside = int(((df[col] < rng["min"]) | (df[col] > rng["max"])).sum())
        return m("rows_outside", outside, bounds.get("min_rows"), bounds.get("max_rows"),
                 "rows", column=col, observed_max=float(df[col].max()))

    # ---- a sensor stuck on one reading ------------------------------------
    if kind == "flat_run":
        col, part, order = defect["column"], defect["partition_by"], defect["order_by"]
        runs = df.sort_values(order).groupby(part)[col].apply(_longest_flat_run)
        return m("longest_run", int(runs.max()), bounds.get("min_longest_run"), None,
                 "consecutive identical readings",
                 partitions_affected=int((runs >= bounds.get("min_longest_run", 10)).sum()),
                 partitions_total=int(len(runs)))

    # ---- group means spread wide enough to hide a calibration offset ------
    if kind == "group_mean_spread":
        col, part = defect["column"], defect["partition_by"]
        means = df.groupby(part)[col].mean()
        return m("spread", float(means.max() - means.min()), bounds.get("min_spread_c"), None,
                 "degrees C between the highest and lowest station mean",
                 partitions=int(len(means)))

    # ---- nulls that run in blocks rather than at random -------------------
    if kind == "null_clustering":
        col, part, order = defect["column"], defect["partition_by"], defect["order_by"]
        runs = (
            df.sort_values(order)
            .assign(_n=df[col].isna())
            .groupby(part)["_n"]
            .apply(_longest_null_run)
        )
        return m("max_run", int(runs.max()), bounds.get("min_max_run"), None,
                 "consecutive missing days within one partition")

    # ---- missingness correlated with something that matters ---------------
    if kind == "missingness_bias":
        col, cmp_col, via = defect["null_column"], defect["compare_column"], defect["via"]
        other = frames[via["table"]]
        # The parent side is deliberately not unique here (that IS c01's defect),
        # so take the first reading per key rather than merging and fanning out.
        join_cols = list(via["join_on"].items())
        right = other.drop_duplicates([v for _, v in join_cols])[
            [v for _, v in join_cols] + [cmp_col]
        ]
        merged = df.merge(
            right,
            left_on=[k for k, _ in join_cols],
            right_on=[v for _, v in join_cols],
            how="left",
        )
        kept = merged.loc[merged[col].notna(), cmp_col].dropna()
        lost = merged.loc[merged[col].isna(), cmp_col].dropna()
        bias = float(kept.mean() - lost.mean()) if len(kept) and len(lost) else float("nan")
        return m("bias", bias, bounds.get("min_bias_c"), None,
                 f"degrees C shift in mean {cmp_col} when nulls are dropped",
                 kept_rows=int(len(kept)), dropped_rows=int(len(lost)))

    # ---- a null that must line up exactly with a condition ----------------
    if kind == "conditional_null":
        nul, cond = defect["null_column"], defect["condition_column"]
        aligned = bool((df[nul].isna() == df[cond].astype(bool)).all())
        rate = float(df[cond].astype(bool).mean())
        if bounds.get("require_exact_alignment") and not aligned:
            # Report the misalignment rather than the rate — it is the failure.
            mismatch = int((df[nul].isna() != df[cond].astype(bool)).sum())
            return m("misaligned_rows", mismatch, None, 0, "rows",
                     note="declaration_detail must be null exactly where withheld is true")
        return m("rate", rate, bounds.get("min_rate"), bounds.get("max_rate"),
                 "share of rows withheld", alignment_exact=aligned)

    # ---- a score that ranks correctly but is not a probability ------------
    if kind == "calibration":
        score, outcome = defect["score_column"], defect["outcome_column"]
        y = df[outcome].astype(bool)
        mean_pred, mean_actual = float(df[score].mean()), float(y.mean())
        ratio = mean_pred / mean_actual if mean_actual else float("nan")
        # Rank AUC via the Mann-Whitney identity, so scipy is not needed.
        ranks = df[score].rank()
        n_pos, n_neg = int(y.sum()), int((~y).sum())
        auc = (
            (ranks[y].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
            if n_pos and n_neg
            else float("nan")
        )
        metric = m("ratio", ratio, bounds.get("min_ratio"), bounds.get("max_ratio"),
                   "x mean predicted risk over observed rate",
                   mean_predicted=round(mean_pred, 4), mean_actual=round(mean_actual, 4),
                   rank_auc=round(float(auc), 4))
        metric.detail["auc_floor"] = bounds.get("min_rank_auc")
        return metric

    # ---- two classes that must NOT separate on one feature ----------------
    if kind == "distribution_overlap":
        col, cls = defect["column"], defect["class_column"]
        hard = defect["hard_negative"]
        pos = df.loc[df[cls].astype(bool), col]
        neg = df.loc[df[hard["column"]] == hard["value"], col]
        sep = abs(float(pos.mean() - neg.mean()))
        return m("mean_separation", sep, None, bounds.get("max_mean_separation"),
                 f"absolute gap in mean {col} between flagged and the hard negative",
                 flagged_mean=round(float(pos.mean()), 4),
                 hard_negative_mean=round(float(neg.mean()), 4))

    # ---- a denominator that must vary enough for the trap to bite ---------
    if kind == "denominator_trap":
        den = defect["denominator"]
        parent = frames[den["table"]]
        col = den["column"]
        ratio = float(parent[col].max() / parent[col].min()) if parent[col].min() else float("nan")
        return m("population_ratio", ratio, bounds.get("min_population_ratio"), None,
                 "x between the largest and smallest area",
                 population_min=int(parent[col].min()), population_max=int(parent[col].max()))

    # ---- a category that must exist but stay rare -------------------------
    if kind == "category_rarity":
        col = defect["column"]
        counts = df[col].value_counts()
        # Emitted as one metric per constrained category, so the caller expects a
        # list here; handled by compute_all rather than returned from compute.
        return None

    # `semantic`, `circularity`, `category_coverage`, `sentinel_category`,
    # `null_rate`, `class_balance`, `conditional_domain` are all handled natively
    # in suites.py as ordinary expectations on the table itself.
    return None


def compute_rarity(
    challenge: str, table: str, defect: dict[str, Any], df: pd.DataFrame
) -> list[Metric]:
    """category_rarity fans out to one metric per constrained category."""
    col = defect["column"]
    bounds = defect.get("bounds") or {}
    counts = df[col].value_counts()
    total = len(df)
    out: list[Metric] = []

    for value, floor in (bounds.get("min_rows") or {}).items():
        out.append(
            Metric(
                id=f"{table}__{defect['id']}__{value}__rows",
                challenge=challenge, table=table, defect_id=defect["id"],
                title=f"{defect.get('title', defect['id'])} — {value} present",
                value=float(counts.get(value, 0)), min_value=float(floor), max_value=None,
                unit=f"rows at level {value}",
                lesson=defect.get("lesson", ""), if_it_disappears=defect.get("if_it_disappears", ""),
                severity=defect.get("severity", "by-design"), detail={"level": value},
            )
        )
    for value, ceiling in (bounds.get("max_rate") or {}).items():
        out.append(
            Metric(
                id=f"{table}__{defect['id']}__{value}__rate",
                challenge=challenge, table=table, defect_id=defect["id"],
                title=f"{defect.get('title', defect['id'])} — {value} stays rare",
                value=float(counts.get(value, 0)) / total if total else 0.0,
                min_value=None, max_value=float(ceiling), unit=f"share of rows at level {value}",
                lesson=defect.get("lesson", ""), if_it_disappears=defect.get("if_it_disappears", ""),
                severity=defect.get("severity", "by-design"), detail={"level": value},
            )
        )
    return out


def compute_all(challenge: str, tables: dict[str, list[dict]], frames: dict[str, pd.DataFrame]):
    """Every derived metric for one challenge."""
    metrics: list[Metric] = []
    for table, defects in tables.items():
        if table not in frames:
            continue
        for d in defects:
            if d.get("kind") == "category_rarity":
                metrics.extend(compute_rarity(challenge, table, d, frames[table]))
                continue
            got = compute(challenge, table, d, frames)
            if got is not None:
                metrics.append(got)
    return metrics


def to_frame(metrics: list[Metric]) -> pd.DataFrame:
    """One row, one column per metric — the shape the suite validates."""
    return pd.DataFrame([{mt.id: mt.value for mt in metrics}]) if metrics else pd.DataFrame()
