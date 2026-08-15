#!/usr/bin/env python3
"""Generator for `synthetic-lsoa` — challenge 02, Mapping the Gaps.

Produces two gold tables:

    lsoa_deprivation    one row per LSOA
    lsoa_crime_monthly  one row per LSOA x month x crime category

WHY A STAND-IN
---------------
c02 has three licence-cleared sources — `iod2025`, `police-recorded-crime` and
`ons-geography` — and all three are REAL data needing fetchers that do not exist.
This corpus is built on the real geography grain (LSOA, 33,755 of them in England)
so the join shape teams will actually meet is present now, and swapping in the
real extracts later is a fetcher change rather than a redesign.

Every table description says it is synthetic.

THREE TRAPS ARE BUILT IN, BECAUSE THE CATALOGUE ASKS FOR THEM
--------------------------------------------------------------
c02's `handle_with_care` is unusually specific:

    "Deprivation is a measure of access, not a label on people; recorded crime
     shows what is reported, not what happened. Strong entries name these limits.
     Derived tables must not imply otherwise in their column names or descriptions."

That is a brief for the data, not just for the write-up. So:

  1. POPULATION VARIES 4x BETWEEN LSOAs. Raw crime counts are therefore almost
     meaningless — an LSOA with 2,900 residents will out-count one with 1,000 on
     nothing but headcount. A team that maps counts has drawn a population map.
     This is the single most common failure in civic-data hackathons.

  2. REPORTING PROPENSITY VARIES WITH DEPRIVATION, and differently by crime type.
     Recorded crime is `true incidence x reporting propensity`, and only the
     product is in the data — as in real life. For some categories the
     deprivation gradient in the RECORDED figures runs opposite to the gradient
     in true incidence. A team that treats recorded as true will confidently
     report the wrong direction. The true incidence is deliberately NOT published:
     if it were, the exercise would be arithmetic rather than judgement.

  3. THE IMD ALREADY CONTAINS A CRIME DOMAIN. Correlating recorded crime against
     the overall IMD rank is therefore partly correlating crime with itself. The
     `crime_score` column is present precisely so that a team who notices can
     exclude it and use the other six domains — and so that a team who does not
     can be shown, afterwards, why their correlation was flattering.

Column names are chosen to obey the brief: `recorded_count`, never `crime_count`;
`imd_decile`, never `deprivation_level`. The names say what was measured.

Usage:
    python build/generators/synthetic_lsoa.py --out dist/gold --seed 20261026
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np

DEFAULT_SEED = 20261026

# England's actual LSOA count, so the geography grain is right even though the
# values are generated.
N_LSOA = 33_755
MONTHS = 12
YEAR = 2026

REGIONS = [
    "North East", "North West", "Yorkshire and the Humber", "East Midlands",
    "West Midlands", "East of England", "London", "South East", "South West",
]
REGION_WEIGHTS = [0.05, 0.13, 0.10, 0.08, 0.11, 0.11, 0.16, 0.16, 0.10]

# (category, base rate per 1,000 residents per month, reporting gradient)
#
# The gradient is the interesting part. It says how reporting propensity moves
# with deprivation decile:
#   negative -> less reported in deprived areas (lower confidence in reporting,
#               under-recording of things people expect nothing to be done about)
#   positive -> more reported in deprived areas (more police contact, more
#               third-party reporting)
# Burglary is well reported everywhere because of insurance claims, so its
# gradient is near flat — which makes it the honest comparator, and the one a
# careful team will notice behaves differently.
# VIOLENCE IS TUNED TO FLIP, and that is the whole exercise. Its true incidence
# rises steeply with deprivation while its reporting propensity falls steeply, and
# at gradient -0.078 the product reverses: the RECORDED rate is higher in the
# LEAST deprived deciles. A team reading recorded crime as crime will report that
# violence is an affluent-area problem, with a clean chart and a real correlation
# behind it.
#
# The gradient was chosen by computing where the product changes sign, not by
# taste: -0.055 and -0.065 still show more in deprived areas, -0.072 is the first
# to reverse, and -0.078 gives a reversal wide enough to survive Poisson noise
# without being so extreme it looks contrived.
#
# Burglary is the honest comparator — well reported everywhere because of
# insurance claims, so its recorded gradient tracks its true one. A careful team
# notices that burglary and violence disagree and asks why, which is the moment
# the challenge is designed to produce.
CRIME_CATEGORIES = [
    ("Violence and sexual offences", 2.10, -0.078),
    ("Anti-social behaviour",        1.85, +0.040),
    ("Criminal damage and arson",    0.95, -0.030),
    ("Burglary",                     0.60, -0.004),
    ("Vehicle crime",                0.72, -0.018),
    ("Shoplifting",                  0.48, +0.062),
]


def build_deprivation(rng: np.random.Generator) -> tuple[list[str], list[list], dict]:
    header = [
        "lsoa_code", "lsoa_name", "local_authority", "region", "resident_population",
        "households", "imd_rank", "imd_decile", "income_score", "employment_score",
        "education_score", "health_score", "crime_score", "barriers_score",
        "living_environment_score",
    ]

    regions = rng.choice(REGIONS, N_LSOA, p=REGION_WEIGHTS)
    # Population varies about 4x. This is what makes raw counts useless.
    population = rng.integers(1_000, 4_000, N_LSOA)
    households = (population / rng.uniform(2.1, 2.9, N_LSOA)).astype(int)

    # A latent deprivation factor drives every domain, so the domains correlate
    # with each other the way real ones do.
    latent = rng.normal(0, 1, N_LSOA)
    order = np.argsort(latent)
    rank = np.empty(N_LSOA, dtype=int)
    rank[order] = np.arange(1, N_LSOA + 1)      # 1 = most deprived, as in the real IMD
    decile = np.ceil(rank / N_LSOA * 10).astype(int)

    def domain(weight: float) -> np.ndarray:
        return np.round(np.clip(0.5 - latent * weight + rng.normal(0, 0.16, N_LSOA), 0.01, 0.99), 4)

    income = domain(0.30)
    employment = domain(0.27)
    education = domain(0.24)
    health = domain(0.22)
    crime_score = domain(0.19)     # the domain that makes IMD-vs-crime circular
    barriers = domain(0.12)
    living_env = domain(0.15)

    rows: list[list] = []
    for i in range(N_LSOA):
        code = f"E0{1000000 + i:07d}"
        la = f"{regions[i]} LA {i % 40 + 1:02d}"
        rows.append([
            code, f"{la} {i % 900 + 1:03d}", la, str(regions[i]), int(population[i]),
            int(households[i]), int(rank[i]), int(decile[i]), float(income[i]),
            float(employment[i]), float(education[i]), float(health[i]),
            float(crime_score[i]), float(barriers[i]), float(living_env[i]),
        ])

    ctx = {
        "codes": [r[0] for r in rows],
        "population": population,
        "decile": decile,
        "latent": latent,
    }
    return header, rows, ctx


def build_crime(rng: np.random.Generator, ctx: dict) -> tuple[list[str], list[list]]:
    header = ["lsoa_code", "month", "crime_category", "recorded_count"]
    rows: list[list] = []

    codes = ctx["codes"]
    population = ctx["population"]
    decile = ctx["decile"]
    latent = ctx["latent"]
    months = [date(YEAR, m, 1) for m in range(1, MONTHS + 1)]

    for category, base_rate, gradient in CRIME_CATEGORIES:
        # TRUE incidence rises as deprivation rises (decile 1 = most deprived).
        true_rate = base_rate * (1.0 + 0.11 * (5.5 - decile))

        # REPORTING propensity moves with deprivation, and the direction differs
        # by category. Only the product is published.
        reporting = np.clip(0.62 + gradient * (5.5 - decile) + rng.normal(0, 0.03, len(codes)), 0.18, 0.99)

        expected = true_rate * (population / 1000.0) * reporting

        for m in months:
            # Seasonality, plus Poisson noise so small LSOAs are genuinely noisy —
            # which is what makes ranking by raw rate unstable at low counts.
            seasonal = 1.0 + (0.13 if m.month in (6, 7, 8, 12) else -0.05)
            counts = rng.poisson(np.clip(expected * seasonal, 0.01, None))
            for i, code in enumerate(codes):
                rows.append([code, m, category, int(counts[i])])

    return header, rows


def generate(seed: int = DEFAULT_SEED) -> dict[str, tuple[list[str], list[list]]]:
    rng = np.random.default_rng(seed)
    dep_header, dep_rows, ctx = build_deprivation(rng)
    crime_header, crime_rows = build_crime(rng, ctx)
    return {
        "lsoa_deprivation": (dep_header, dep_rows),
        "lsoa_crime_monthly": (crime_header, crime_rows),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = p.parse_args()
    import pandas as pd

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, (header, rows) in generate(args.seed).items():
        pd.DataFrame(rows, columns=header).to_parquet(out / f"{name}.parquet", index=False)
        print(f"  {name}: {len(rows):,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
