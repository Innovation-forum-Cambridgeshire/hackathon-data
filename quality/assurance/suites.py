"""Build the Great Expectations suites.

Two suites per table, and the split is the point of the whole exercise:

    <challenge>.<table>.contract   things that must be TRUE.  A failure is a bug.
    <challenge>.<table>.defects    things that must be WRONG. A failure means a
                                   deliberate flaw has been tidied away, or has
                                   drifted out of the range where it teaches
                                   anything.

Reading a single all-green Data Docs page for this corpus would be a lie, and
reading a single all-red one would be useless. Two suites let the report say the
true thing: the contract holds, and the flaws are still exactly as flawed as they
were designed to be.

Every expectation carries `description` and `notes`. GX renders both, so the
report explains itself to an organiser who has never opened Great Expectations —
which is most of the audience for it.

RESULT FORMAT
    Set once on the checkpoint, not per expectation: SUMMARY with
    partial_unexpected_count = 10 and unexpected_index_column_names set to the
    table's business key. That is what turns "142 rows failed" into ten rows
    somebody can go and look at, addressed by field_id and observation_date
    rather than by pandas row number, which would be meaningless the moment the
    corpus is rebuilt.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

import great_expectations as gx
import great_expectations.expectations as gxe

from .model import DTYPE_KINDS, Table

# Columns we add to the frame before validating. Named with a leading underscore
# so they cannot collide with a catalogue column, and stripped from the ordered
# column-list expectation so the schema check still sees the real schema.
# Prefix for the columns we add to a frame before validating it.
#
# `check_` rather than something obviously internal like `_gxq_`, because GX uses
# the COLUMN NAME as the section heading in Data Docs. A reader of the report
# sees this text, and "_gxq_fk_cohort_region_within_alert_regions" reads as
# something that leaked out of the tooling. "check_fk_..." reads as what it is.
#
# Collision with a catalogue column is checked at runtime (assert_no_collision)
# rather than being assumed away by an unlikely prefix, which is the more honest
# guarantee and costs one set lookup.
DERIVED_PREFIX = "check_"


def assert_no_collision(df: pd.DataFrame, declared: list[str], name: str) -> None:
    """A derived column must never shadow a real one."""
    if name in declared:
        raise SystemExit(
            f"derived column {name!r} collides with a column declared in the "
            f"catalogue. Rename the relationship or the check that produces it — "
            f"silently overwriting real data would make every result downstream a lie."
        )


# ---------------------------------------------------------------------------
# derived columns
# ---------------------------------------------------------------------------
def add_referential_columns(
    frames: dict[str, pd.DataFrame], relationships: list
) -> dict[str, list[dict[str, Any]]]:
    """Add a boolean 'does this key resolve' column for each enforced relationship.

    GX has no cross-table foreign-key expectation for pandas, and the obvious
    workaround — ExpectColumnValuesToBeInSet with the parent keys as the value
    set — puts all 33,755 LSOA codes into the rendered page and into the stored
    suite JSON. So the join is resolved here into one boolean column, and the
    expectation asserts that column is true. The failing rows still carry the
    business key, so the top-ten list stays useful.
    """
    added: dict[str, list[dict[str, Any]]] = {}
    for rel in relationships:
        if not rel.enforced:
            continue
        if rel.from_table not in frames or rel.to_table not in frames:
            continue
        child, parent = frames[rel.from_table], frames[rel.to_table]
        col = f"{DERIVED_PREFIX}fk_{rel.name}"
        assert_no_collision(child, list(child.columns), col)

        if len(rel.from_columns) == 1:
            resolves = child[rel.from_columns[0]].isin(set(parent[rel.to_columns[0]].dropna()))
        else:
            parent_keys = set(map(tuple, parent[rel.to_columns].dropna().to_numpy().tolist()))
            resolves = pd.Series(
                [tuple(r) in parent_keys for r in child[rel.from_columns].to_numpy().tolist()],
                index=child.index,
            )

        frames[rel.from_table][col] = resolves.astype(bool)
        added.setdefault(rel.from_table, []).append(
            {
                "column": col,
                "name": rel.name,
                "description": (
                    f"every {rel.from_table}.{'+'.join(rel.from_columns)} resolves to a "
                    f"{rel.to_table}.{'+'.join(rel.to_columns)}"
                ),
                "notes": rel.note,
                "cardinality": rel.cardinality,
            }
        )
    return added


def add_contract_columns(df: pd.DataFrame, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Derived columns for computed definitions and rank permutations."""
    derived: list[dict[str, Any]] = []

    for spec in cfg.get("computed") or []:
        col, expr = spec["column"], spec["expression"]
        expected = df.eval(expr)
        out = f"{DERIVED_PREFIX}computed_{col}"

        # The stored column is ROUNDED, so the identity can only ever hold to the
        # precision it was stored at. Comparing on a relative tolerance alone
        # fails on the smallest rows and nowhere else, which reads as a data
        # defect and is not one: carbon_kg is written to 5 decimal places, so a
        # row whose true value is 0.00899489 stores 0.00899, and the relative
        # error of that is 0.05% purely because the number is small.
        #
        # `round_to` states the storage precision, and the tolerance becomes half
        # a unit in the last place — the largest error rounding can introduce,
        # and a bound a genuine arithmetic bug would blow straight through.
        round_to = spec.get("round_to")
        rel_tol = float(spec.get("tolerance", 0.0))
        abs_tol = 0.5 * 10 ** (-int(round_to)) + 1e-12 if round_to is not None else 0.0

        residual = (df[col] - expected).abs()
        denom = expected.abs().where(expected.abs() > 1e-12, 1.0)
        within = (residual <= abs_tol) | (residual / denom <= rel_tol)
        df[out] = within.astype(bool)

        if round_to is not None:
            band = f"to the {round_to} decimal places it is stored at"
        else:
            band = f"within {rel_tol:g} relative"
        derived.append(
            {
                "column": out,
                "description": f"{col} equals {expr}, {band}",
                "notes": spec.get("reason", ""),
            }
        )

    rp = cfg.get("rank_permutation")
    if rp:
        col = rp["column"]
        n = len(df)
        ranks = df[col]
        is_perm = bool(
            ranks.notna().all()
            and ranks.min() == 1
            and ranks.max() == n
            and ranks.nunique() == n
        )
        out = f"{DERIVED_PREFIX}rank_is_permutation"
        # A whole-table property, so the same answer on every row. That reads
        # oddly in a row-level expectation and is deliberate: it keeps the check
        # on the page beside the column it is about.
        df[out] = np.full(n, is_perm, dtype=bool)
        derived.append(
            {
                "column": out,
                "description": f"{col} is exactly the permutation 1..{n:,} — no ties, no gaps",
                "notes": rp.get("reason", ""),
            }
        )
        if rp.get("derived_decile"):
            dec = rp["derived_decile"]
            expected_dec = np.ceil(ranks / (n / 10)).clip(1, 10)
            out2 = f"{DERIVED_PREFIX}decile_matches_rank"
            df[out2] = (df[dec] == expected_dec).astype(bool)
            derived.append(
                {
                    "column": out2,
                    "description": f"{dec} is the decile implied by {col}",
                    "notes": (
                        "The decile is derived from the rank. If they disagree, one of the two "
                        "is stale and every decile-based comparison in the challenge is wrong."
                    ),
                }
            )
    return derived


# ---------------------------------------------------------------------------
# the contract suite
# ---------------------------------------------------------------------------
def build_schema_suite(table: Table, row_tolerance: float = 0.20) -> gx.ExpectationSuite:
    """Table-shape expectations, validated against the RAW frame.

    Kept separate from the contract suite for one specific reason: the contract
    suite is validated against a frame carrying derived columns (foreign-key
    resolution flags, computed residuals), and an ordered-column-list expectation
    against that frame would either fail on every table or have to be widened to
    include the derived names — which would stop it detecting an extra column in
    the parquet, the exact thing it is for.

    So this runs first, on the frame as it was read.
    """
    suite = gx.ExpectationSuite(name=f"{table.challenge}.{table.name}.schema")
    suite.add_expectation(
        gxe.ExpectTableColumnsToMatchOrderedList(
            column_list=table.column_names,
            description=f"columns are exactly those declared in catalogue/{table.challenge}.yml, in order",
            notes=(
                "Order is asserted as well as membership. The CSV twin is positional for "
                "anyone reading it without a header, and a reordered column is a silent "
                "break for them."
            ),
            meta={"dimension": "schema"},
        )
    )
    if table.approx_rows:
        lo = int(table.approx_rows * (1 - row_tolerance))
        hi = int(table.approx_rows * (1 + row_tolerance))
        suite.add_expectation(
            gxe.ExpectTableRowCountToBeBetween(
                min_value=lo, max_value=hi,
                description=f"row count is within {row_tolerance:.0%} of the declared ~{table.approx_rows:,}",
                notes=(
                    "The catalogue declares an approximate size. A large drift means the "
                    "generator changed shape, which invalidates every rate in the defect "
                    "profile even if each one still lands inside its bounds."
                ),
                meta={"dimension": "schema"},
            )
        )
    return suite


def build_contract_suite(
    table: Table,
    cfg: dict[str, Any],
    df: pd.DataFrame,
    fk_columns: list[dict[str, Any]],
    derived: list[dict[str, Any]],
    row_tolerance: float = 0.20,
) -> gx.ExpectationSuite:
    suite = gx.ExpectationSuite(name=f"{table.challenge}.{table.name}.contract")
    add = suite.add_expectation

    # Table shape is asserted by build_schema_suite against the raw frame.

    # --- types --------------------------------------------------------------
    for col in table.columns:
        allowed = DTYPE_KINDS.get(col.type)
        if not allowed:
            continue
        add(
            gxe.ExpectColumnValuesToBeInTypeList(
                column=col.name, type_list=list(allowed),
                description=f"{col.name} is a {col.type}",
                notes=(
                    f"Declared as {col.type} in the catalogue. An integer arriving as a float "
                    "is the classic sign of a null having been introduced somewhere upstream."
                ),
                meta={"dimension": "schema"},
            )
        )

    # --- completeness -------------------------------------------------------
    not_null = cfg.get("not_null")
    if not_null == "all":
        not_null_cols = table.column_names
    else:
        not_null_cols = list(not_null or [])
    for col in not_null_cols:
        add(
            gxe.ExpectColumnValuesToNotBeNull(
                column=col,
                description=f"{col} is never null",
                notes="Completeness is a contract here. Columns that are deliberately "
                      "incomplete are excluded from this list and appear in the defect suite.",
                meta={"dimension": "completeness"},
            )
        )

    # --- uniqueness ---------------------------------------------------------
    key = cfg.get("unique_key")
    if key:
        if len(key) == 1:
            add(
                gxe.ExpectColumnValuesToBeUnique(
                    column=key[0],
                    description=f"{key[0]} uniquely identifies a row",
                    notes=f"The declared grain is: {table.grain}",
                    meta={"dimension": "uniqueness"},
                )
            )
        else:
            add(
                gxe.ExpectCompoundColumnsToBeUnique(
                    column_list=list(key),
                    description=f"({', '.join(key)}) uniquely identifies a row",
                    notes=f"The declared grain is: {table.grain}",
                    meta={"dimension": "uniqueness"},
                )
            )

    # --- closed value domains ----------------------------------------------
    for col, values in (cfg.get("domains") or {}).items():
        add(
            gxe.ExpectColumnValuesToBeInSet(
                column=col, value_set=list(values),
                description=f"{col} is one of the {len(values)} known values",
                notes=(
                    "Asserted as a closed set. A new category would pass every other check "
                    "here — group-bys keep working and simply grow a row — so this is the "
                    "only place it would be noticed."
                ),
                meta={"dimension": "validity"},
            )
        )

    # --- numeric ranges -----------------------------------------------------
    for col, rng in (cfg.get("ranges") or {}).items():
        add(
            gxe.ExpectColumnValuesToBeBetween(
                column=col,
                min_value=rng.get("min"), max_value=rng.get("max"),
                description=(
                    f"{col} is between {rng.get('min', '-inf')} and {rng.get('max', 'inf')}"
                ),
                notes=rng.get("reason", ""),
                meta={"dimension": "validity"},
            )
        )

    # --- patterns -----------------------------------------------------------
    for col, spec in (cfg.get("patterns") or {}).items():
        add(
            gxe.ExpectColumnValuesToMatchRegex(
                column=col, regex=spec["regex"],
                description=f"{col} matches {spec['regex']}",
                notes=spec.get("reason", ""),
                meta={"dimension": "validity"},
            )
        )

    # --- safety -------------------------------------------------------------
    for spec in cfg.get("safety") or []:
        add(
            gxe.ExpectColumnValuesToNotMatchRegex(
                column=spec["column"], regex=spec["must_not_match"],
                description=f"{spec['column']} carries no real-world contact detail",
                notes=spec.get("reason", ""),
                meta={"dimension": "safety"},
            )
        )

    # --- cross-column ordering ---------------------------------------------
    for pair in cfg.get("pairs") or []:
        rel = pair.get("relation", "lte")
        # A <= B is expressed as B >= A with or_equal, which is the only pair
        # expectation GX ships.
        add(
            gxe.ExpectColumnPairValuesAToBeGreaterThanB(
                column_A=pair["right"], column_B=pair["left"],
                or_equal=(rel == "lte"),
                description=f"{pair['left']} <= {pair['right']} on every row",
                notes=pair.get("reason", ""),
                meta={"dimension": "consistency"},
            )
        )

    # --- constants ----------------------------------------------------------
    for col, value in (cfg.get("constant") or {}).items():
        add(
            gxe.ExpectColumnValuesToBeInSet(
                column=col, value_set=[value],
                description=f"{col} is always {value}",
                notes=(
                    "Present in the data so the caveat survives a join, a filter and an "
                    "export into someone's slide deck."
                ),
                meta={"dimension": "validity"},
            )
        )

    # --- referential integrity ---------------------------------------------
    for fk in fk_columns:
        add(
            gxe.ExpectColumnValuesToBeInSet(
                column=fk["column"], value_set=[True],
                description=fk["description"],
                notes=fk["notes"],
                meta={"dimension": "referential integrity", "cardinality": fk["cardinality"]},
            )
        )

    # --- computed definitions and rank permutations ------------------------
    for d in derived:
        add(
            gxe.ExpectColumnValuesToBeInSet(
                column=d["column"], value_set=[True],
                description=d["description"], notes=d["notes"],
                meta={"dimension": "consistency"},
            )
        )

    return suite


# ---------------------------------------------------------------------------
# the defect suite
# ---------------------------------------------------------------------------
def build_defect_suite(table: Table, df: pd.DataFrame) -> gx.ExpectationSuite | None:
    """Expectations that assert the deliberate flaws are still present.

    Only the defects expressible directly against the table are built here. The
    rest become derived metrics (metrics.py) validated in a separate per-challenge
    suite, because they are population properties rather than row properties.
    """
    suite = gx.ExpectationSuite(name=f"{table.challenge}.{table.name}.defects")
    n = 0

    for d in table.defects:
        kind = d.get("kind")
        bounds = d.get("bounds") or {}
        notes = (d.get("lesson", "") or "").strip()
        if d.get("if_it_disappears"):
            notes += "\n\nIF THIS STOPS FAILING: " + d["if_it_disappears"].strip()
        meta = {
            "dimension": "deliberate defect",
            "defect_id": d["id"],
            "severity": d.get("severity", "by-design"),
            "observed_when_declared": d.get("observed", {}),
        }

        # A null rate that must stay inside a band. ExpectColumnProportionOf
        # NonNullValuesToBeBetween is the inverse of the declared rate, so the
        # bounds are flipped here rather than in the config, where flipping them
        # would be the kind of thing a reader has to hold in their head.
        if kind == "null_rate":
            lo, hi = bounds.get("min_rate"), bounds.get("max_rate")
            suite.add_expectation(
                gxe.ExpectColumnProportionOfNonNullValuesToBeBetween(
                    column=d["column"],
                    min_value=None if hi is None else 1 - hi,
                    max_value=None if lo is None else 1 - lo,
                    description=(
                        f"{d['column']} is missing on between {lo:.0%} and {hi:.0%} of rows "
                        f"— deliberately"
                    ),
                    notes=notes, meta=meta,
                )
            )
            n += 1

        # A sentinel category that must keep carrying real weight.
        elif kind == "sentinel_category":
            col, sentinel = d["column"], d["sentinel"]
            flag = f"{DERIVED_PREFIX}sentinel_{col}"
            df[flag] = df[col].eq(sentinel)
            lo, hi = bounds.get("min_cost_share"), bounds.get("max_cost_share")
            # Share of ROWS via mostly; the cost share is a derived metric.
            suite.add_expectation(
                gxe.ExpectColumnValuesToBeInSet(
                    column=col, value_set=[sentinel],
                    mostly=lo if lo else 0.01,
                    description=(
                        f"at least {(lo or 0.01):.0%} of rows still carry {col} = {sentinel!r}"
                    ),
                    notes=notes, meta=meta,
                )
            )
            n += 1

        elif kind == "class_balance":
            col = d["column"]
            lo, hi = bounds.get("min_rate"), bounds.get("max_rate")
            suite.add_expectation(
                gxe.ExpectColumnMeanToBeBetween(
                    column=col, min_value=lo, max_value=hi,
                    description=f"between {lo:.0%} and {hi:.0%} of rows have {col} true",
                    notes=notes, meta=meta,
                )
            )
            n += 1

        elif kind == "category_coverage":
            for value in d.get("required_values") or []:
                flag = f"{DERIVED_PREFIX}has_{d['column']}_{value}"
                df[flag] = df[d["column"]].eq(value)
                suite.add_expectation(
                    gxe.ExpectColumnValuesToBeInSet(
                        column=d["column"], value_set=[value],
                        mostly=max(1.0 / len(df), 1e-9) if len(df) else 0.0,
                        description=f"{d['column']} = {value!r} has at least one row",
                        notes=notes, meta=meta,
                    )
                )
                n += 1

        elif kind == "conditional_domain":
            cond, col = d["condition_column"], d["column"]
            allowed = d.get("condition_false_allowed") or []
            ok = f"{DERIVED_PREFIX}cond_{col}"
            df[ok] = np.where(df[cond].astype(bool), True, df[col].isin(allowed))
            suite.add_expectation(
                gxe.ExpectColumnValuesToBeInSet(
                    column=ok, value_set=[True],
                    description=(
                        f"where {cond} is false, {col} is one of {allowed}"
                    ),
                    notes=notes, meta=meta,
                )
            )
            n += 1

        # out_of_range: assert the absurd values are STILL PRESENT. Expressed as
        # "not every row is inside the plausible range", which GX has no direct
        # form for, so it becomes an indicator column.
        elif kind == "out_of_range":
            col, rng = d["column"], d["plausible_range"]
            flag = f"{DERIVED_PREFIX}absurd_{col}"
            df[flag] = (df[col] < rng["min"]) | (df[col] > rng["max"])
            floor = bounds.get("min_rows", 1)
            suite.add_expectation(
                gxe.ExpectColumnValuesToBeInSet(
                    column=flag, value_set=[True],
                    mostly=max(floor / len(df), 1e-9) if len(df) else 0.0,
                    description=(
                        f"at least {floor} row(s) still carry a physically impossible {col} "
                        f"(outside {rng['min']} to {rng['max']})"
                    ),
                    notes=notes, meta=meta,
                )
            )
            n += 1

        # compound_key_not_unique is asserted as a derived metric so the RATE is
        # bounded in both directions; asserting non-uniqueness here as well would
        # double-count the same fact in the report.

    return suite if n else None


def build_metric_suite(challenge: str, metrics: list) -> gx.ExpectationSuite | None:
    """One range expectation per derived metric (see metrics.py)."""
    if not metrics:
        return None
    suite = gx.ExpectationSuite(name=f"{challenge}.derived-metrics.defects")
    for mt in metrics:
        notes = (mt.lesson or "").strip()
        if mt.if_it_disappears:
            notes += "\n\nIF THIS STOPS FAILING: " + mt.if_it_disappears.strip()
        if mt.detail:
            notes += "\n\nMeasured: " + ", ".join(f"{k}={v}" for k, v in mt.detail.items())
        lo = "" if mt.min_value is None else f"at least {mt.min_value:g}"
        hi = "" if mt.max_value is None else f"at most {mt.max_value:g}"
        band = " and ".join(x for x in (lo, hi) if x)
        suite.add_expectation(
            gxe.ExpectColumnValuesToBeBetween(
                column=mt.id, min_value=mt.min_value, max_value=mt.max_value,
                description=f"{mt.table}: {mt.title} — {band} ({mt.unit})",
                notes=notes,
                meta={
                    "dimension": "deliberate defect",
                    "defect_id": mt.defect_id,
                    "table": mt.table,
                    "severity": mt.severity,
                    "measured": mt.detail,
                },
            )
        )
    return suite
