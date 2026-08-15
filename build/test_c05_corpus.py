#!/usr/bin/env python3
"""Verify the c05 corpus and its schema contract.

Run:  python3 build/test_c05_corpus.py

The k-anonymity assertion is the one that matters. c05 is health-adjacent, so the
floor is k >= 10 rather than the default 5, and a generator that drifts below it on
a tail cell publishes a re-identifiable group while nothing about the file looks
wrong. It is asserted here rather than assumed from the design.

The calibration assertions are the opposite kind: they check that a DELIBERATE
flaw is still present. `predicted_risk` ranks correctly and is roughly 2.7x too
high in absolute terms, which is the single most common failure in deployed risk
scoring and the point of the challenge notebook. If someone "fixes" it, the
exercise quietly loses its teeth, so the test guards it.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "generators"))

import yaml  # noqa: E402

import synthetic_cohort as gen  # noqa: E402

CATALOGUE = Path(__file__).resolve().parent.parent / "catalogue" / "c05-ahead-of-the-heat.yml"
ROW_TOLERANCE = 0.20
K_FLOOR = 10


def main() -> int:
    failures: list[str] = []
    cat = yaml.safe_load(CATALOGUE.read_text())
    declared = {t["name"]: t for t in cat["gold_tables"]}
    tables = gen.generate()

    # ---------- CONTRACT ----------
    if set(tables) != set(declared):
        failures.append(
            f"tables differ from catalogue: generated {sorted(tables)}, declared {sorted(declared)}"
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
                failures.append(f"{name}: {len(rows):,} rows vs declared ~{approx:,} ({drift:.0%})")

    if gen.generate(gen.DEFAULT_SEED) != gen.generate(gen.DEFAULT_SEED):
        failures.append("generator is not deterministic for a fixed seed")

    # ---------- k-ANONYMITY ----------
    ch, cr = tables["synthetic_cohort"]
    ci = {n: i for i, n in enumerate(ch)}
    tbl = declared.get("synthetic_cohort", {})
    qis = tbl.get("quasi_identifiers") or []
    k_declared = tbl.get("k_threshold")

    if k_declared != K_FLOOR:
        failures.append(
            f"synthetic_cohort declares k_threshold={k_declared}; c05 is health-adjacent "
            f"and the floor is {K_FLOOR}"
        )

    missing = [q for q in qis if q not in ci]
    if missing:
        failures.append(f"declared quasi-identifiers absent from the data: {missing}")
    elif qis:
        cells = Counter(tuple(r[ci[q]] for q in qis) for r in cr)
        smallest = min(cells.values())
        if smallest < K_FLOOR:
            offenders = [c for c, n in cells.items() if n < K_FLOOR]
            failures.append(
                f"k-anonymity VIOLATED on {qis}: smallest cell holds {smallest} people "
                f"(floor {K_FLOOR}); {len(offenders)} cell(s) below it, e.g. {offenders[:3]}"
            )

    # ---------- TEACHABILITY ----------
    bands = ["Low", "Medium", "High"]
    stats = {}
    for b in bands:
        rows = [r for r in cr if r[ci["risk_band"]] == b]
        if not rows:
            failures.append(f"risk band {b!r} is empty — the stratification exercise needs all three")
            continue
        stats[b] = (
            sum(r[ci["predicted_risk"]] for r in rows) / len(rows),
            sum(r[ci["heat_event_last_summer"]] for r in rows) / len(rows),
        )

    if len(stats) == 3:
        actual = [stats[b][1] for b in bands]
        if not actual[0] < actual[1] < actual[2]:
            failures.append(
                f"risk bands do not rank correctly on the actual event rate: {actual}. "
                f"The model must be MIScalibrated, not broken — if ranking fails too, "
                f"the notebook cannot show that ranking and calibration are different things."
            )
        ratios = [stats[b][0] / stats[b][1] for b in bands if stats[b][1] > 0]
        if ratios and min(ratios) < 1.5:
            failures.append(
                f"predicted_risk is too well calibrated (ratios {[round(r,1) for r in ratios]}). "
                f"The calibration gap is the deliberate teaching point of this corpus."
            )

    ah, ar = tables["alert_history"]
    ai = {n: i for i, n in enumerate(ah)}
    in_season_levels = {r[ai["alert_level"]] for r in ar if r[ai["in_alert_season"]]}
    off_season_levels = {r[ai["alert_level"]] for r in ar if not r[ai["in_alert_season"]]}
    if off_season_levels != {"Green"}:
        failures.append(
            f"alerts outside the 1 Jun - 30 Sep season are not all Green: {off_season_levels}"
        )
    if not {"Amber", "Red"} & in_season_levels:
        failures.append("no Amber or Red alerts in season — nothing for a team to act on")

    wh, wr = tables["region_weather_daily"]
    wi = {n: i for i, n in enumerate(wh)}
    if not all(r[wi["is_synthetic"]] for r in wr):
        failures.append(
            "region_weather_daily has rows with is_synthetic false. Nothing here is an "
            "observation — metoffice is pointer-only after the D4 review — and the flag "
            "exists so the caveat survives a join and an export."
        )
    if any(r[wi["temp_min_c"]] > r[wi["temp_max_c"]] for r in wr):
        failures.append("some rows have temp_min_c above temp_max_c")

    if failures:
        print("c05 corpus FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    cells = Counter(tuple(r[ci[q]] for q in qis) for r in cr)
    print(
        f"c05 corpus OK: {len(cr):,} people across {len(cells)} quasi-identifier cells "
        f"(smallest {min(cells.values())}, floor {K_FLOOR}), risk bands rank correctly "
        f"while predicted_risk runs ~{stats['High'][0] / stats['High'][1]:.1f}x actual, "
        f"{len(ar):,} alert-days and {len(wr):,} weather-days."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
