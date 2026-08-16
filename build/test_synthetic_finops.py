#!/usr/bin/env python3
"""Verify the c03 synthetic FinOps corpus and its schema contract.

Run:  python3 build/test_synthetic_finops.py

Two classes of assertion here, and they fail for different reasons:

  * CONTRACT — the generator matches what the catalogue promises. These break when
    someone edits one and forgets the other, which is the common case.
  * TEACHABILITY — the estate still contains the things the challenge exists to find.
    A tidy estate would pass every contract test and be useless: no untagged spend,
    no idle waste, no cost gap between platforms, nothing to discover. These assert
    the mess is still there.

Determinism is tested because judging depends on it. A release tag is meant to be an
immutable snapshot; if the same seed stopped producing the same bytes, results judged
against an earlier build could not be reproduced and nothing would say so.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "generators"))

import yaml  # noqa: E402

from determinism import fingerprint_tables  # noqa: E402

import synthetic_finops as gen  # noqa: E402

CATALOGUE = Path(__file__).resolve().parent.parent / "catalogue" / "c03-beyond-the-mainframe.yml"
ROW_TOLERANCE = 0.20

# Column names that would mean personal data had entered a layer that forbids it.
# Deliberately crude: this is a tripwire for an accident, not a classifier.
FORBIDDEN_SUBSTRINGS = ("name", "email", "postcode", "phone", "dob", "nino", "address")
ALLOWED_EXACT = {"business_unit"}  # contains "unit", not a person


def main() -> int:
    failures: list[str] = []
    cat = yaml.safe_load(CATALOGUE.read_text())
    declared = {t["name"]: t for t in cat["gold_tables"]}

    tables = gen.generate()

    # --- CONTRACT ---

    if set(tables) != set(declared):
        failures.append(
            f"tables differ from catalogue: generated {sorted(tables)}, "
            f"declared {sorted(declared)}"
        )

    for name, (header, rows) in tables.items():
        tbl = declared.get(name)
        if tbl is None:
            continue

        expected = [c["name"] for c in tbl["columns"]]
        if header != expected:
            failures.append(f"{name}: columns {header} != catalogue {expected}")

        approx = tbl.get("approx_rows")
        if isinstance(approx, int) and approx > 0:
            drift = abs(len(rows) - approx) / approx
            if drift > ROW_TOLERANCE:
                failures.append(
                    f"{name}: {len(rows):,} rows vs declared ~{approx:,} ({drift:.0%} drift)"
                )

        for col in header:
            low = col.lower()
            if col in ALLOWED_EXACT:
                continue
            for bad in FORBIDDEN_SUBSTRINGS:
                if bad in low:
                    failures.append(
                        f"{name}.{col}: column name suggests personal data, which this "
                        f"layer prohibits without exception"
                    )

    # Determinism: judging reproducibility depends on it.
    if fingerprint_tables(gen.generate(gen.DEFAULT_SEED)) != fingerprint_tables(gen.generate(gen.DEFAULT_SEED)):
        failures.append("generator is not deterministic for a fixed seed")
    if gen.generate(1)["workload_cost_daily"][1] == gen.generate(2)["workload_cost_daily"][1]:
        failures.append("generator ignores its seed — two different seeds gave identical data")

    cost_header, cost_rows = tables["workload_cost_daily"]
    cb_header, cb_rows = tables["chargeback_allocation"]
    ci = {n: i for i, n in enumerate(cost_header)}
    bi = {n: i for i, n in enumerate(cb_header)}

    # The roll-up must reconcile. A chargeback table that does not tie back to the
    # cost table is the exact bug the challenge teaches people to hunt, so it must
    # not be present by accident in the data they are hunting it in.
    cost_total = sum(r[ci["cost_gbp"]] for r in cost_rows)
    cb_total = sum(r[bi["allocated_cost_gbp"]] for r in cb_rows)
    if abs(cost_total - cb_total) > 0.01:
        failures.append(
            f"chargeback does not reconcile: cost £{cost_total:,.2f} vs "
            f"chargeback £{cb_total:,.2f}"
        )

    # First appearance of a combination has no prior month — that must be NULL, not 0.
    # Zero would read as "no change", which is a different and wrong statement.
    if not any(r[bi["variance_vs_prior_month_pct"]] is None for r in cb_rows):
        failures.append("no NULL variance rows — first-month comparisons are being faked as 0")

    # --- TEACHABILITY ---

    workloads = {r[ci["workload_id"]] for r in cost_rows}
    unallocated = {
        r[ci["workload_id"]] for r in cost_rows
        if r[ci["business_unit"]] == gen.UNALLOCATED_LABEL
    }
    share = len(unallocated) / len(workloads)
    if not 0.02 <= share <= 0.12:
        failures.append(
            f"untagged workload share {share:.1%} outside 2–12% — the chargeback "
            f"exercise needs some ownership gaps to find"
        )

    util = defaultdict(list)
    cost_by_plat = defaultdict(float)
    vcpu_by_plat = defaultdict(float)
    for r in cost_rows:
        p = r[ci["platform"]]
        util[p].append(r[ci["utilisation_pct"]])
        cost_by_plat[p] += r[ci["cost_gbp"]]
        vcpu_by_plat[p] += r[ci["vcpu_hours"]]

    means = {p: sum(v) / len(v) for p, v in util.items()}
    if not means.get("mainframe", 0) > means.get("distributed", 0) > means.get("cloud", 0):
        failures.append(
            f"utilisation ordering lost (mainframe > distributed > cloud): {means}"
        )

    unit = {p: cost_by_plat[p] / vcpu_by_plat[p] for p in cost_by_plat if vcpu_by_plat[p]}
    if unit.get("mainframe", 0) < unit.get("cloud", 0) * 3:
        failures.append(
            f"mainframe/cloud unit cost gap too small to drive the migration question: {unit}"
        )

    if not any(r[ci["utilisation_pct"]] < 5.0 for r in cost_rows):
        failures.append("no near-idle workload-days — the waste exercise has nothing to find")

    if failures:
        print("c03 synthetic FinOps FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        f"c03 synthetic FinOps OK: {len(cost_rows):,} cost rows reconcile to "
        f"{len(cb_rows):,} chargeback rows, deterministic, "
        f"{share:.1%} untagged, mainframe {unit['mainframe'] / unit['cloud']:.1f}x cloud unit cost."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
