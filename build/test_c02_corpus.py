#!/usr/bin/env python3
"""Verify the c02 corpus and its schema contract.

Run:  python3 build/test_c02_corpus.py

Like c01, most of this asserts that a deliberate flaw is still present. c02's
`handle_with_care` is a brief for the DATA, not just the write-up:

    "Deprivation is a measure of access, not a label on people; recorded crime
     shows what is reported, not what happened."

A corpus where recorded crime tracked true incidence, or where every area held
the same population, would make that instruction untestable. So the three traps
are asserted, and a well-meaning tidy-up that removes one fails the build.

The naming assertion is here too. The brief says derived tables "must not imply
otherwise in their column names", so `crime_count` is a spec violation and the
test treats it as one.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "generators"))

import yaml  # noqa: E402

from determinism import fingerprint_tables  # noqa: E402

import synthetic_lsoa as gen  # noqa: E402

CATALOGUE = Path(__file__).resolve().parent.parent / "catalogue" / "c02-mapping-the-gaps.yml"
ROW_TOLERANCE = 0.20

# Column names that would assert incidence rather than recording, or would label
# people rather than places. Both are explicitly out of bounds in the brief.
BANNED_NAMES = {
    "crime_count", "crimes", "offences_committed", "actual_crime",
    "deprivation_level", "deprived", "poverty_level",
}


def corr(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


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

        for col in header:
            if col.lower() in BANNED_NAMES:
                failures.append(
                    f"{name}.{col}: column name asserts more than the data supports. "
                    f"The brief requires names that say what was MEASURED — "
                    f"'recorded_count', not 'crime_count'."
                )

    if gen.generate(gen.DEFAULT_SEED) != gen.generate(gen.DEFAULT_SEED):
        failures.append("generator is not deterministic for a fixed seed")

    dh, dr = tables["lsoa_deprivation"]
    di = {n: i for i, n in enumerate(dh)}
    ch, cr = tables["lsoa_crime_monthly"]
    ci = {n: i for i, n in enumerate(ch)}

    pop = {r[di["lsoa_code"]]: r[di["resident_population"]] for r in dr}
    dec = {r[di["lsoa_code"]]: r[di["imd_decile"]] for r in dr}

    # ---------- TRAP 1: raw counts must track population ----------
    totals: dict[str, int] = {}
    for r in cr:
        totals[r[ci["lsoa_code"]]] = totals.get(r[ci["lsoa_code"]], 0) + r[ci["recorded_count"]]

    codes = list(totals)
    raw = [float(totals[c]) for c in codes]
    pops = [float(pop[c]) for c in codes]
    rate = [totals[c] / pop[c] * 1000 for c in codes]

    r_raw = corr(raw, pops)
    r_rate = corr(rate, pops)
    if r_raw < 0.4:
        failures.append(
            f"raw counts correlate only {r_raw:+.2f} with population. The corpus needs "
            f"population to drive raw counts, or 'map counts and you have drawn a "
            f"population map' is not demonstrable."
        )
    if abs(r_rate) > 0.25:
        failures.append(
            f"the RATE still correlates {r_rate:+.2f} with population — normalising "
            f"should remove the effect, and if it does not the lesson is muddied."
        )

    # ---------- TRAP 2: at least one category must flip ----------
    gradients: dict[str, float] = {}
    for category, _, _ in gen.CRIME_CATEGORIES:
        per: dict[str, int] = {}
        for r in cr:
            if r[ci["crime_category"]] == category:
                per[r[ci["lsoa_code"]]] = per.get(r[ci["lsoa_code"]], 0) + r[ci["recorded_count"]]
        cs = list(per)
        rates = [per[c] / pop[c] * 1000 for c in cs]
        decs = [float(dec[c]) for c in cs]
        gradients[category] = corr(rates, decs)

    # decile 1 = most deprived, so a POSITIVE correlation means the recorded rate
    # rises with affluence — the reversal.
    flipped = [c for c, g in gradients.items() if g > 0.05]
    tracking = [c for c, g in gradients.items() if g < -0.3]

    if not flipped:
        failures.append(
            "no crime category shows a reversed recorded gradient. Without one, "
            "'recorded crime is not crime' is an assertion in the docs rather than "
            "something a team can discover in the data. Gradients: "
            + ", ".join(f"{c}={g:+.2f}" for c, g in gradients.items())
        )
    if not tracking:
        failures.append(
            "no category tracks the true gradient. Burglary is meant to be the honest "
            "comparator — without it there is nothing to notice the disagreement against."
        )

    # ---------- TRAP 3: the circular domain must be exposed ----------
    if "crime_score" not in di:
        failures.append(
            "crime_score is absent. It is a COMPONENT of the overall deprivation rank, "
            "so without it exposed a team cannot exclude it and the circularity is "
            "invisible rather than merely subtle."
        )

    if failures:
        print("c02 corpus FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        f"c02 corpus OK: {len(dr):,} LSOAs, {len(cr):,} crime rows. "
        f"raw~pop {r_raw:+.2f} vs rate~pop {r_rate:+.2f}; "
        f"{len(flipped)} category reversed ({flipped[0]} {gradients[flipped[0]]:+.2f}), "
        f"{len(tracking)} tracking truth; crime_score exposed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
