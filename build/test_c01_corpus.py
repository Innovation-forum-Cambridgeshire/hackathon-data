#!/usr/bin/env python3
"""Verify the c01 corpus and its schema contract.

Run:  python3 build/test_c01_corpus.py

Unusually, most of this file asserts that the data is BROKEN.

c01's catalogue says it plainly: "Sensor data is often miscalibrated, duplicated
or missing. Strong entries surface data quality rather than hiding it behind a
clean-looking chart." A clean corpus makes that instruction meaningless, so each
defect is a feature with a test, and a well-meaning tidy-up that removes one would
fail the build rather than quietly gutting the challenge.

The one that matters most is the quality_flag asymmetry: filtering on it must NOT
clean the data. If someone later flags the duplicates, a team's first instinct —
`WHERE quality_flag = 'ok'` — starts working, and the exercise is over.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "generators"))

import yaml  # noqa: E402

from determinism import fingerprint_tables  # noqa: E402

import synthetic_farm as gen  # noqa: E402

CATALOGUE = Path(__file__).resolve().parent.parent / "catalogue" / "c01-one-farm-one-picture.yml"
ROW_TOLERANCE = 0.20


def longest_flat_run(values: list) -> int:
    best = cur = 1
    for i in range(1, len(values)):
        cur = cur + 1 if values[i] == values[i - 1] else 1
        best = max(best, cur)
    return best


def main() -> int:
    failures: list[str] = []
    cat = yaml.safe_load(CATALOGUE.read_text())
    declared = {t["name"]: t for t in cat["gold_tables"]}
    tables = gen.generate()

    # ---------- CONTRACT ----------
    for name, (header, rows) in tables.items():
        tbl = declared.get(name)
        if tbl is None:
            failures.append(f"generated table {name!r} is not declared in the catalogue")
            continue
        expected = [c["name"] for c in tbl["columns"]]
        if header != expected:
            failures.append(f"{name}: columns {header} != catalogue {expected}")
        approx = tbl.get("approx_rows")
        if isinstance(approx, int) and approx > 0:
            drift = abs(len(rows) - approx) / approx
            if drift > ROW_TOLERANCE:
                failures.append(f"{name}: {len(rows):,} rows vs declared ~{approx:,} ({drift:.0%})")

    if fingerprint_tables(gen.generate(gen.DEFAULT_SEED)) != fingerprint_tables(gen.generate(gen.DEFAULT_SEED)):
        failures.append("generator is not deterministic for a fixed seed")

    wh, wr = tables["station_weather"]
    wi = {n: i for i, n in enumerate(wh)}
    fh, fr = tables["field_daily"]
    fi = {n: i for i, n in enumerate(fh)}

    # ---------- THE DEFECTS MUST STILL BE THERE ----------

    keys = Counter((r[wi["station_id"]], r[wi["observation_date"]]) for r in wr)
    dupes = sum(v - 1 for v in keys.values() if v > 1)
    if dupes == 0:
        failures.append(
            "no duplicate station-days. The double-ingest case is the most common "
            "real defect in sensor data and a naive mean over the table should be wrong."
        )

    # THE LOAD-BEARING ASSERTION. quality_flag carries only what a real pipeline
    # would have caught. If duplicates ever become flagged, `WHERE quality_flag =
    # 'ok'` starts cleaning the data and the exercise collapses.
    flagged_dupes = Counter(
        (r[wi["station_id"]], r[wi["observation_date"]])
        for r in wr
        if r[wi["quality_flag"]] != "ok"
    )
    surviving = sum(1 for k, v in keys.items() if v > 1 and flagged_dupes.get(k, 0) == 0)
    if surviving == 0:
        failures.append(
            "every duplicate is flagged in quality_flag, so filtering on it cleans "
            "the data. The flag must carry ONLY the defects an ingest pipeline would "
            "have caught, or a team's first instinct works and they learn nothing."
        )

    by_station: dict[str, list] = {}
    for r in sorted(wr, key=lambda r: r[wi["observation_date"]]):
        by_station.setdefault(r[wi["station_id"]], []).append(r[wi["temp_max_c"]])

    stuck = [s for s, v in by_station.items() if longest_flat_run(v) >= 15]
    if not stuck:
        failures.append(
            "no stuck sensors. A frozen reading is not null and not absurd, so it "
            "survives every naive check while dragging any average toward itself."
        )

    means = {s: sum(v) / len(v) for s, v in by_station.items()}
    spread = max(means.values()) - min(means.values())
    if spread < 2.0:
        failures.append(
            f"station mean temperatures span only {spread:.1f}C — too tight for a "
            f"miscalibrated station to hide in. Miscalibration is only findable by "
            f"comparison against neighbours, so the natural spread has to be wide "
            f"enough that a single offset station is not obvious from one column."
        )

    if not any(r[wi["temp_max_c"]] > 50 for r in wr):
        failures.append("no out-of-range readings")

    missing = sum(1 for r in fr if r[fi["ndvi"]] is None)
    share = missing / len(fr)
    if not 0.12 <= share <= 0.30:
        failures.append(
            f"NDVI missing share is {share:.1%}, outside 12-30%. Too little and the "
            f"bias lesson does not bite; too much and there is nothing left to model."
        )

    # Missingness must be CLUSTERED. Scattered nulls are missing-at-random and
    # dropping them is harmless — which is the opposite of the lesson. Cloud sits
    # over a field for days, so dropping nulls biases toward clear (hotter, drier)
    # weather.
    one_field = [r for r in fr if r[fi["field_id"]] == fr[0][fi["field_id"]]]
    one_field.sort(key=lambda r: r[fi["observation_date"]])
    runs, cur = [], 0
    for r in one_field:
        if r[fi["ndvi"]] is None:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    if not runs or max(runs) < 2:
        failures.append(
            "NDVI gaps are not clustered — scattered nulls are missing-at-random, "
            "so dropping them is harmless and the sampling-bias lesson disappears."
        )

    # Clustering alone is NOT enough, and this assertion exists because the first
    # version got that wrong. The gaps have to be clustered ON SOMETHING THAT
    # MATTERS, or dropna() is unbiased in practice and the claim in the catalogue
    # and the notebook is one the data does not support. Scattering runs at random
    # dates left the surviving days only 0.15C warmer; cloud now falls on the
    # colder days at each field's own station, which is realistic and makes the
    # loss informative.
    temps: dict = {}
    for r in wr:
        temps.setdefault((r[wi["station_id"]], r[wi["observation_date"]]), r[wi["temp_max_c"]])

    kept_t, lost_t = [], []
    for r in fr:
        t = temps.get((r[fi["nearest_station_id"]], r[fi["observation_date"]]))
        if t is None:
            continue
        (lost_t if r[fi["ndvi"]] is None else kept_t).append(t)

    if kept_t and lost_t:
        bias = sum(kept_t) / len(kept_t) - sum(lost_t) / len(lost_t)
        if bias < 1.0:
            failures.append(
                f"dropping NDVI nulls shifts mean temperature by only {bias:+.2f}C. "
                f"The gaps are clustered but not on anything that matters, so dropna() "
                f"is effectively unbiased and the sampling-bias lesson is a claim the "
                f"data does not support."
            )

    if failures:
        print("c01 corpus FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        f"c01 corpus OK: {len(wr):,} station-days with {dupes:,} duplicates "
        f"({surviving:,} unflagged), {len(stuck)} stuck sensor(s), {spread:.1f}C mean "
        f"spread, {len(fr):,} field-days with {share:.1%} NDVI missing in runs up to "
        f"{max(runs)} days."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
