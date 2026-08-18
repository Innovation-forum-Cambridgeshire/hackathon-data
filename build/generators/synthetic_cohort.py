#!/usr/bin/env python3
"""Generator for `synthetic-cohort` — challenge 05, Ahead of the Heat.

Produces three gold tables:

    synthetic_cohort       one row per synthetic person
    alert_history          one row per region x day
    region_weather_daily   one row per area x day

WHY EVERY ROW HERE IS GENERATED, INCLUDING THE ONES THAT LOOK PUBLIC
--------------------------------------------------------------------
The cohort is obvious: the real service data is consent-held special-category
health data about vulnerable adults. It must never enter this layer, and no
lawful basis makes publishing it a good idea.

The weather and alerts are less obvious and worth stating, because both have
licence-cleared real sources in the catalogue:

  * `ukhsa-alerts` IS cleared (OGL, UKHSA data dashboard) but has no fetcher, and
    inventing a fetcher's output is not the same as fetching. The alert history
    here is generated and labelled as such. When a fetcher lands, this table
    should switch to the real feed — the schema is built to make that a swap.

  * `metoffice` is POINTER-ONLY after the D4 review: the Met Office prices
    commercial reuse under the EUMETNET licence, and "Met Office weather data" is
    a publisher rather than a dataset. So the weather here cannot be real, and a
    team that reports a temperature finding as if it were observed has misread the
    corpus. The table description says so on the table itself.

k >= 10, NOT THE DEFAULT 5
---------------------------
Challenge 05 is health-adjacent, so the compliance design sets a higher
k-anonymity floor. The quasi-identifiers are declared as a human judgement in the
catalogue — age band, region, care setting — and this generator is built so every
combination of them holds at least 10 people. That is asserted by the test rather
than hoped for: a generator that drifts below k=10 on a tail cell publishes a
re-identifiable group, and nothing about the file would look wrong.

The risk score is deliberately NOT well calibrated. See the note on
`predicted_risk` below — that is the teaching point of the challenge notebook.

Usage:
    python build/generators/synthetic_cohort.py --out dist/gold --seed 20261026
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

DEFAULT_SEED = 20261026

N_PEOPLE = 5_000
YEARS = 8
WINDOW_END = date(2026, 9, 30)
ALERT_DAYS = YEARS * 365 + 2  # 2,922 -> 9 regions x 2,922 = 26,298 rows

# The nine English regions UKHSA issues weather-health alerts for.
REGIONS = [
    "North East", "North West", "Yorkshire and the Humber", "East Midlands",
    "West Midlands", "East of England", "London", "South East", "South West",
]

# Finer geography for observations. 41 areas x 2,922 days ~= 120k rows, matching
# the declared grain. Alerts are issued regionally; weather is observed locally,
# and keeping them at different grains is realistic and forces a real join.
AREAS = [
    "Cambridgeshire", "Norfolk", "Suffolk", "Essex", "Hertfordshire", "Bedfordshire",
    "Northamptonshire", "Lincolnshire", "Leicestershire", "Nottinghamshire",
    "Derbyshire", "Staffordshire", "Warwickshire", "Worcestershire", "Shropshire",
    "Herefordshire", "Gloucestershire", "Wiltshire", "Somerset", "Dorset", "Devon",
    "Cornwall", "Hampshire", "Berkshire", "Surrey", "Kent", "Sussex", "Oxfordshire",
    "Buckinghamshire", "Greater London", "Greater Manchester", "Merseyside",
    "Lancashire", "Cheshire", "Cumbria", "West Yorkshire", "South Yorkshire",
    "North Yorkshire", "Tyne and Wear", "Durham", "Northumberland",
]

AGE_BANDS = ["65-69", "70-74", "75-79", "80-84", "85+"]
CARE_SETTINGS = ["Own home", "Sheltered housing", "Residential care", "Nursing care"]
MOBILITY = ["Independent", "Walks with aid", "Limited mobility", "Immobile"]

ALERT_LEVELS = ["Green", "Yellow", "Amber", "Red"]

# k-anonymity floor for health-adjacent data (compliance design; ISO/IEC 20889).
K_THRESHOLD = 10


def build_cohort(rng: np.random.Generator) -> tuple[list[str], list[list]]:
    """One row per synthetic person, built to hold k >= 10 on the quasi-identifiers.

    Assignment is round-robin across the (age_band x region x care_setting) cells
    rather than random. Random assignment gives an expected 27 per cell at this
    size, but the tail cells land in single figures often enough to matter, and a
    cell of 3 people is re-identifiable however synthetic the names are. Cycling
    guarantees the floor by construction instead of relying on the average.
    """
    header = [
        "person_id", "age_band", "region", "care_setting", "mobility",
        "lives_alone", "has_cardiovascular", "has_respiratory", "on_diuretics",
        "cognitive_impairment", "prior_heat_admission", "care_visits_per_week",
        "predicted_risk", "risk_band", "heat_event_last_summer",
    ]
    cells = [(a, r, c) for a in AGE_BANDS for r in REGIONS for c in CARE_SETTINGS]
    rows: list[list] = []

    for i in range(N_PEOPLE):
        age, region, care = cells[i % len(cells)]
        age_idx = AGE_BANDS.index(age)

        # Risk factors rise with age band and with care intensity.
        base = 0.10 + 0.055 * age_idx + 0.05 * CARE_SETTINGS.index(care)
        cardio = bool(rng.random() < base + 0.16)
        resp = bool(rng.random() < base + 0.08)
        diuretics = bool(rng.random() < base + 0.12)
        cognitive = bool(rng.random() < base * 0.7)
        prior = bool(rng.random() < base * 0.35)
        alone = bool(rng.random() < (0.62 if care == "Own home" else 0.10))
        mobility = str(rng.choice(MOBILITY, p=[0.34, 0.31, 0.26, 0.09]))
        visits = int(rng.integers(0, 4) if care == "Own home" else rng.integers(3, 22))

        # The true underlying probability of a heat-related event.
        true_p = min(
            0.92,
            0.02
            + 0.022 * age_idx
            + 0.035 * cardio
            + 0.030 * resp
            + 0.022 * diuretics
            + 0.028 * cognitive
            + 0.075 * prior
            + 0.020 * alone,
        )
        event = bool(rng.random() < true_p)

        # predicted_risk is deliberately MISCALIBRATED — monotonic in true risk, so
        # it ranks well, but systematically inflated. A model that ranks correctly
        # and is wrong about absolute probability is the single most common failure
        # in deployed risk scoring, and in a heat-health setting the absolute number
        # is what triggers a visit. The c05 notebook exists to make this visible.
        # Clamped at BOTH ends. The upper cap was here from the start; the lower
        # one was not, and without it ~11 of 5,000 rows came out NEGATIVE — the
        # noise term is wide enough to push the lowest-risk people below zero,
        # since true_p floors at 0.02 and 0.02 * 2.6 is only 0.052.
        #
        # That was a real defect (F-001), not part of the planted miscalibration.
        # The planted defect is that the score is inflated by ~2.6x and therefore
        # ranks well but is not a probability; a NEGATIVE score is not inflated,
        # it is outside the declared 0-1 domain and cannot be read as a risk at
        # all. It also invited the wrong lesson — "this column is broken" rather
        # than "this column ranks but does not calibrate".
        #
        # max() rather than a re-draw on purpose: re-drawing would consume extra
        # values from rng and shift every subsequent field in the corpus, for a
        # fix that needs to touch 11 numbers. This leaves the stream untouched,
        # so determinism holds and no other column moves.
        predicted = float(
            min(0.99, max(0.0, round(true_p * 2.6 + rng.normal(0, 0.03), 4)))
        )
        band = (
            "High" if predicted >= 0.55 else "Medium" if predicted >= 0.28 else "Low"
        )

        rows.append([
            f"P-{i + 1:05d}", age, region, care, mobility, alone, cardio, resp,
            diuretics, cognitive, prior, visits, predicted, band, event,
        ])

    return header, rows


def build_alerts(rng: np.random.Generator) -> tuple[list[str], list[list]]:
    """Regional alert level per day. SYNTHETIC — see the module docstring."""
    header = [
        "region", "alert_date", "alert_level", "in_alert_season",
        "consecutive_days_at_level", "issued_at",
    ]
    start = WINDOW_END - timedelta(days=ALERT_DAYS - 1)
    rows: list[list] = []

    for region in REGIONS:
        # Southern regions run hotter, so alerts escalate more often.
        southern = region in ("London", "South East", "South West", "East of England")
        run_level, run_len = "Green", 0
        for d in range(ALERT_DAYS):
            day = start + timedelta(days=d)
            # Core heat alerting season is 1 Jun - 30 Sep (England).
            in_season = 6 <= day.month <= 9

            if not in_season:
                level = "Green"
            else:
                p = rng.random()
                if southern:
                    level = "Red" if p < 0.006 else "Amber" if p < 0.045 else "Yellow" if p < 0.18 else "Green"
                else:
                    level = "Red" if p < 0.002 else "Amber" if p < 0.022 else "Yellow" if p < 0.11 else "Green"

            run_len = run_len + 1 if level == run_level else 1
            run_level = level
            rows.append([
                region, day, level, in_season, run_len,
                f"{day.isoformat()}T09:00:00",
            ])

    return header, rows


def build_weather(rng: np.random.Generator) -> tuple[list[str], list[list]]:
    """Daily observations per area. SYNTHETIC — `metoffice` is pointer-only."""
    header = [
        "area", "observation_date", "temp_max_c", "temp_min_c",
        "relative_humidity_pct", "heat_index_c", "is_synthetic",
    ]
    start = WINDOW_END - timedelta(days=ALERT_DAYS - 1)
    doy = np.array([(start + timedelta(days=i)).timetuple().tm_yday for i in range(ALERT_DAYS)])
    seasonal = 8.5 * np.sin(2 * np.pi * (doy - 110) / 365.0)

    rows: list[list] = []
    for area in AREAS:
        # A crude north-south gradient so the join to regional alerts is coherent.
        offset = rng.uniform(-1.8, 2.2)
        tmax = 14.2 + offset + seasonal + rng.normal(0, 3.1, ALERT_DAYS)
        tmin = tmax - rng.uniform(4.5, 9.0, ALERT_DAYS)
        rh = np.clip(rng.normal(74, 11, ALERT_DAYS), 28, 100)
        # Heat index only diverges from temperature when it is both hot and humid.
        hi = tmax + np.where(tmax > 26, (rh - 40) * 0.045, 0.0)

        for i in range(ALERT_DAYS):
            rows.append([
                area, start + timedelta(days=i), round(float(tmax[i]), 1),
                round(float(tmin[i]), 1), round(float(rh[i]), 1),
                round(float(hi[i]), 1), True,
            ])

    return header, rows


def generate(seed: int = DEFAULT_SEED) -> dict[str, tuple[list[str], list[list]]]:
    rng = np.random.default_rng(seed)
    return {
        "synthetic_cohort": build_cohort(rng),
        "alert_history": build_alerts(rng),
        "region_weather_daily": build_weather(rng),
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
