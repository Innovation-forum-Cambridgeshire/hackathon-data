#!/usr/bin/env python3
"""Generator for `synthetic-farm` — challenge 01, One Farm, One Picture.

Produces two gold tables:

    field_daily      one row per field x day
    station_weather  one row per station x day  (plus deliberate duplicates)

WHY A STAND-IN RATHER THAN THE REAL SOURCES
--------------------------------------------
c01 has one licence-cleared source (`midas-open`, OGL, confirmed on the CEDA
catalogue record) and it is REAL data needing a fetcher that does not exist.
`defra` is held: it bundles three datasets and field boundaries are Ordnance
Survey derived, so it needs splitting before anything is mirrored. `ahdb` and
`copernicus-sentinel` are pointer-only.

So this corpus is modelled on the SHAPE of the intended join — field x day joined
to the nearest weather station — so that schemas, notebooks and team tooling exist
now. Swapping in the real CEDA extract later is a fetcher change, not a redesign.

Every table description says it is synthetic. That is a labelling requirement on
the table itself, not a note in the catalogue, because the caveat has to survive a
join and an export into somebody's slide.

THE DATA IS DELIBERATELY DIRTY, AND THAT IS THE CHALLENGE
----------------------------------------------------------
The catalogue's `handle_with_care` is explicit:

    "Sensor data is often miscalibrated, duplicated or missing. Strong entries
     surface data quality rather than hiding it behind a clean-looking chart."

A clean corpus would make that instruction meaningless. So the defects below are
built in on purpose, each modelled on a failure that really happens to field
sensor networks. None of them is announced in the data — finding them IS the work:

  DUPLICATES        ~1.5% of station-days appear twice, from the classic double
                    ingest. A naive mean over the table is wrong and looks fine.
  STUCK SENSORS     a handful of stations report an identical value for days at a
                    time. Not missing, not obviously absurd, and it drags any
                    average toward the stuck value.
  MISCALIBRATION    three stations carry a systematic offset. Each is internally
                    consistent, so the only way to see it is to compare against
                    neighbours.
  MISSING           NDVI is absent on roughly a fifth of field-days, which is what
                    cloud cover does to optical satellite readings. It is NOT
                    missing at random: it clusters in runs, so dropping nulls
                    silently biases toward clear weather.
  OUT OF RANGE      a small number of physically impossible readings survive.

`quality_flag` is NOT a shortcut. It carries the flags a real ingest pipeline
would have caught — never the ones it would have missed — so filtering on it
leaves the interesting defects untouched. That asymmetry is the point.

Usage:
    python build/generators/synthetic_farm.py --out dist/gold --seed 20261026
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

DEFAULT_SEED = 20261026

N_STATIONS = 250
STATION_DAYS = 3_600            # ~10 years, matching MIDAS Open's archive shape
N_FIELDS = 500
FIELD_DAYS = 360                # one growing season
WINDOW_END = date(2026, 9, 30)

DUPLICATE_SHARE = 0.015
STUCK_STATIONS = 4
STUCK_RUN_DAYS = 21
MISCALIBRATED_STATIONS = 3
MISCALIBRATION_C = 2.8          # large enough to matter, small enough to look plausible
NDVI_MISSING_SHARE = 0.20
OUT_OF_RANGE_COUNT = 140

COUNTIES = [
    "Cambridgeshire", "Norfolk", "Suffolk", "Lincolnshire", "Essex",
    "Bedfordshire", "Hertfordshire", "Northamptonshire", "Leicestershire", "Rutland",
]
CROPS = ["Winter wheat", "Spring barley", "Oilseed rape", "Sugar beet", "Field beans", "Potatoes"]
SOILS = ["Clay", "Sandy loam", "Silty clay loam", "Chalk", "Peat", "Sandy clay loam"]


def build_stations(rng: np.random.Generator) -> dict:
    ids = [f"S-{i + 1:04d}" for i in range(N_STATIONS)]
    return {
        "station_id": np.array(ids),
        "county": rng.choice(COUNTIES, N_STATIONS),
        "latitude": np.round(rng.uniform(51.9, 53.4, N_STATIONS), 5),
        "longitude": np.round(rng.uniform(-0.9, 1.7, N_STATIONS), 5),
        # Which stations are broken, and how. Chosen once so the defect is stable
        # across runs — a data-quality exercise that moves every rebuild is not
        # markable.
        "stuck": set(rng.choice(ids, STUCK_STATIONS, replace=False)),
        "miscalibrated": set(rng.choice(ids, MISCALIBRATED_STATIONS, replace=False)),
    }


def build_station_weather(rng: np.random.Generator, st: dict) -> tuple[list[str], list[list]]:
    header = [
        "station_id", "observation_date", "county", "latitude", "longitude",
        "temp_max_c", "temp_min_c", "rainfall_mm", "quality_flag",
    ]
    start = WINDOW_END - timedelta(days=STATION_DAYS - 1)
    days = [start + timedelta(days=i) for i in range(STATION_DAYS)]
    doy = np.array([d.timetuple().tm_yday for d in days])
    seasonal = 8.6 * np.sin(2 * np.pi * (doy - 110) / 365.0)

    rows: list[list] = []
    for i in range(N_STATIONS):
        sid = st["station_id"][i]
        lat_effect = (53.4 - st["latitude"][i]) * 1.4
        tmax = 13.6 + lat_effect + seasonal + rng.normal(0, 3.0, STATION_DAYS)
        tmin = tmax - rng.uniform(4.0, 9.5, STATION_DAYS)
        rain = np.where(rng.random(STATION_DAYS) < 0.42, rng.exponential(3.4, STATION_DAYS), 0.0)

        # A systematic offset. Internally consistent, so it is invisible unless you
        # compare this station against its neighbours.
        if sid in st["miscalibrated"]:
            tmax = tmax + MISCALIBRATION_C
            tmin = tmin + MISCALIBRATION_C

        # A sensor that stops moving. Not null, not absurd — just wrong, and it
        # quietly drags any average toward the frozen value.
        if sid in st["stuck"]:
            begin = int(rng.integers(0, STATION_DAYS - STUCK_RUN_DAYS))
            tmax[begin:begin + STUCK_RUN_DAYS] = tmax[begin]
            tmin[begin:begin + STUCK_RUN_DAYS] = tmin[begin]
            rain[begin:begin + STUCK_RUN_DAYS] = rain[begin]

        for d in range(STATION_DAYS):
            rows.append([
                sid, days[d], str(st["county"][i]), float(st["latitude"][i]),
                float(st["longitude"][i]), round(float(tmax[d]), 1),
                round(float(tmin[d]), 1), round(float(rain[d]), 1), "ok",
            ])

    # Physically impossible values that survived ingest. Flagged as 'suspect'
    # because a real pipeline WOULD catch a 61 degree reading — these are the easy
    # ones, and finding them teaches nothing except to check the flag.
    for idx in rng.choice(len(rows), OUT_OF_RANGE_COUNT, replace=False):
        rows[idx][5] = round(float(rng.uniform(52.0, 71.0)), 1)
        rows[idx][8] = "suspect"

    # Double ingest. NOT flagged, because a pipeline that knew about them would
    # have removed them. This is the defect that survives a quality_flag filter.
    n_dupes = int(len(rows) * DUPLICATE_SHARE)
    for idx in rng.choice(len(rows), n_dupes, replace=False):
        rows.append(list(rows[idx]))

    return header, rows


def build_field_daily(
    rng: np.random.Generator, st: dict, station_temps: dict[str, "np.ndarray"] | None = None
) -> tuple[list[str], list[list]]:
    header = [
        "field_id", "observation_date", "farm_id", "crop", "soil_type", "area_ha",
        "nearest_station_id", "distance_to_station_km", "ndvi", "soil_moisture_pct",
    ]
    start = WINDOW_END - timedelta(days=FIELD_DAYS - 1)
    days = [start + timedelta(days=i) for i in range(FIELD_DAYS)]
    doy = np.array([d.timetuple().tm_yday for d in days])

    rows: list[list] = []
    for f in range(N_FIELDS):
        fid = f"F-{f + 1:05d}"
        farm = f"FARM-{f // 8 + 1:04d}"
        crop = str(rng.choice(CROPS))
        soil = str(rng.choice(SOILS))
        area = round(float(rng.lognormal(2.4, 0.55)), 2)
        station = str(rng.choice(st["station_id"]))
        dist = round(float(rng.uniform(0.8, 28.0)), 2)

        # NDVI follows the crop cycle: green up, peak, senescence.
        curve = 0.28 + 0.46 * np.clip(np.sin(np.pi * (doy - 60) / 200.0), 0, None)
        ndvi = np.clip(curve + rng.normal(0, 0.045, FIELD_DAYS), 0.02, 0.98)
        moisture = np.clip(rng.normal(31, 8.5, FIELD_DAYS), 3, 62)

        # Cloud cover, which is what actually removes optical satellite readings.
        # CLUSTERED, not scattered: cloud sits over a field for days. That makes the
        # missingness non-random, so dropping nulls biases the sample toward clear
        # weather — and clear weather is hotter and drier, which is exactly the
        # thing a yield model should not be silently conditioned on.
        missing = np.zeros(FIELD_DAYS, dtype=bool)
        target = int(FIELD_DAYS * NDVI_MISSING_SHARE)

        # CLOUD FALLS ON THE COLDER DAYS AT THIS FIELD'S OWN STATION.
        #
        # An earlier version scattered runs at random dates. That gave clustered
        # gaps — half the point — but the surviving days were only 0.15C warmer
        # than the lost ones, so the sampling bias the catalogue and notebook both
        # CLAIM was not actually present. A corpus that fails to demonstrate its
        # own stated lesson is worse than one that never claimed it, because
        # somebody checks and finds nothing.
        #
        # Cloud really does depress daytime temperature, so weighting run starts
        # toward this station's colder days is both more realistic and what makes
        # dropna() genuinely biased: what survives is the warmer, clearer weather,
        # and a yield model fitted on it has been conditioned on sunshine.
        temps = (station_temps or {}).get(station)
        if temps is not None:
            weight = np.exp(-(temps - temps.mean()) / max(float(temps.std()), 0.5))
            weight = weight / weight.sum()
        else:
            weight = None

        while missing.sum() < target:
            run = int(rng.integers(2, 14))
            if weight is not None:
                j = min(int(rng.choice(FIELD_DAYS, p=weight)), FIELD_DAYS - run)
            else:
                j = int(rng.integers(0, max(1, FIELD_DAYS - run)))
            missing[j:j + run] = True

        for i in range(FIELD_DAYS):
            rows.append([
                fid, days[i], farm, crop, soil, area, station, dist,
                None if missing[i] else round(float(ndvi[i]), 4),
                round(float(moisture[i]), 1),
            ])

    return header, rows


def generate(seed: int = DEFAULT_SEED) -> dict[str, tuple[list[str], list[list]]]:
    rng = np.random.default_rng(seed)
    st = build_stations(rng)
    weather = build_station_weather(rng, st)

    # Each station's temperature over the FIELD window, so cloud can be placed on
    # its colder days — see the note in build_field_daily on why that coupling is
    # what makes the missingness informative rather than merely clustered.
    wh, wr = weather
    wi = {n: i for i, n in enumerate(wh)}
    field_start = WINDOW_END - timedelta(days=FIELD_DAYS - 1)
    per_station: dict = {}
    for r in wr:
        d = r[wi["observation_date"]]
        if d >= field_start:
            per_station.setdefault(r[wi["station_id"]], {})[d] = r[wi["temp_max_c"]]

    days = [field_start + timedelta(days=i) for i in range(FIELD_DAYS)]
    station_temps = {
        sid: np.array([vals.get(d, 14.0) for d in days]) for sid, vals in per_station.items()
    }

    return {
        "station_weather": weather,
        "field_daily": build_field_daily(rng, st, station_temps),
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
