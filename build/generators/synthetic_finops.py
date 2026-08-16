#!/usr/bin/env python3
"""Generator for the `synthetic-finops` source — challenge 03, Beyond the Mainframe.

Produces the three gold tables declared in `catalogue/c03-beyond-the-mainframe.yml`
from nothing but a seed. There is no fetch stage here and there is not meant to be:
c03 is declared a synthetic environment in the catalogue's `handle_with_care`, and no
client system or client data may enter it under any circumstances.

WHY A GENERATOR RATHER THAN A SAMPLE OF REAL DATA
-------------------------------------------------
Judging has to be reproducible against an immutable release tag. A seeded generator
committed to the repo means anyone can rebuild the exact corpus a team worked on and
check a result, which a hand-curated extract cannot offer. It also means the estate
can be regenerated at a different size for a dry run without renegotiating anything.

DETERMINISM IS A JUDGING REQUIREMENT, NOT A CONVENIENCE
-------------------------------------------------------
`numpy.random.default_rng(seed)` uses PCG64, which NumPy documents as
stream-compatible across releases — verified here across numpy 1.26.4 and 2.2.6,
where every value in all thirteen tables was identical.

Be precise about what that buys, because the looser version of this claim is
wrong: same seed gives the same VALUES anywhere, but the same BYTES only within
a pinned environment. Parquet embeds its writer version, so pyarrow 21 and 23
produce different files with identical contents. Only value-identity matters for
fairness — judging runs against the downloaded release asset, a fixed file. See
build/determinism.py. Do not swap it for `numpy.random.seed()` (legacy
global state, and shared with any library that touches it) or for Python's `random`
(different stream, and unusably slow at this row count).

The seed is the event date. It is arbitrary but it must never change for a published
version: regenerating a release with a different seed would silently invalidate every
result judged against the old one.

THE ESTATE IS DELIBERATELY MESSY
---------------------------------
A clean estate teaches nothing. FinOps work is mostly finding the untagged spend, the
idle reserved capacity and the workload nobody owns, so those are built in on purpose
and documented here rather than left as surprises:

  * ~6% of workloads have no owning business unit — they land as "UNALLOCATED",
    which is the single most common real chargeback problem.
  * Mainframe workloads run at high, flat utilisation; cloud workloads are spiky and
    often over-provisioned. That contrast is the whole point of the challenge.
  * A minority of workloads are near-idle (<5% utilisation) but still cost money.
  * Month-end and quarter-end drive batch peaks on the mainframe.
  * Grid carbon intensity follows a daily and seasonal shape, so carbon per unit of
    compute is not constant and moving a workload in time actually matters.

GRID INTENSITY HERE IS SYNTHETIC
---------------------------------
The catalogue lists a real NESO carbon-intensity feed (`sustainability`), but it is
`licence_reviewed: false` and therefore not mirrorable. Rather than block the carbon
table on D4, the intensity curve is generated with a realistic shape and labelled as
synthetic in the manifest. Nobody should publish a carbon *finding* from this against
the real grid — it is for method, not for measurement.

Usage:
    python build/generators/synthetic_finops.py --out dist/gold --seed 20261026
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

# The event date. Never change this for a version already published — see the module
# docstring on why a reseeded release invalidates prior judging.
DEFAULT_SEED = 20261026

# A full trailing year, ending the month before the event. 365 days x 1,150 workloads
# is ~420k rows, which matches the catalogue's declared grain and stays under the
# 1,000,000-row CSV twin threshold so file-only tools get the whole table.
WINDOW_END = date(2026, 9, 30)
WINDOW_DAYS = 365
N_WORKLOADS = 1_150

# Share of workloads with no owning business unit. The classic chargeback gap.
UNALLOCATED_SHARE = 0.06
UNALLOCATED_LABEL = "UNALLOCATED"

BUSINESS_UNITS = [
    "Retail Banking", "Commercial Banking", "Wealth Management", "Insurance",
    "Payments", "Cards", "Mortgages", "Treasury", "Risk", "Compliance",
    "Internal Audit", "Finance", "Human Resources", "Legal", "Procurement",
    "Marketing", "Customer Operations", "Fraud Operations", "Collections",
    "Data and Analytics", "Cyber Security", "Infrastructure", "Digital Channels",
    "Group Technology",
]

# (service, platform, unit cost basis). Three platforms is the spine of the challenge:
# the same business capability costs very differently depending where it runs.
SERVICES = [
    # --- mainframe ---
    ("CICS Transaction Server", "mainframe"), ("IMS Transaction Manager", "mainframe"),
    ("Db2 for z/OS", "mainframe"), ("MQ for z/OS", "mainframe"),
    ("COBOL Batch", "mainframe"), ("JCL Scheduler", "mainframe"),
    ("VSAM Storage", "mainframe"), ("z/OS Connect", "mainframe"),
    ("Tape Virtualisation", "mainframe"), ("RACF Security", "mainframe"),
    ("SMF Analytics", "mainframe"), ("Sysplex Coupling", "mainframe"),
    # --- distributed / on-premises ---
    ("VMware vSphere", "distributed"), ("Red Hat Enterprise Linux", "distributed"),
    ("Windows Server", "distributed"), ("Oracle Database", "distributed"),
    ("SQL Server", "distributed"), ("WebSphere Application Server", "distributed"),
    ("Tomcat", "distributed"), ("NetApp Storage", "distributed"),
    ("Veeam Backup", "distributed"), ("F5 Load Balancing", "distributed"),
    ("Active Directory", "distributed"), ("Nagios Monitoring", "distributed"),
    # --- cloud ---
    ("Compute Instances", "cloud"), ("Kubernetes Service", "cloud"),
    ("Object Storage", "cloud"), ("Block Storage", "cloud"),
    ("Managed PostgreSQL", "cloud"), ("Managed Redis", "cloud"),
    ("Serverless Functions", "cloud"), ("Message Queue", "cloud"),
    ("Data Warehouse", "cloud"), ("Streaming Ingest", "cloud"),
    ("Container Registry", "cloud"), ("API Gateway", "cloud"),
    ("Content Delivery", "cloud"), ("Secrets Manager", "cloud"),
    ("Machine Learning Platform", "cloud"), ("Log Analytics", "cloud"),
]

ENVIRONMENTS = ["production", "staging", "development", "test"]
ENVIRONMENT_WEIGHTS = [0.52, 0.16, 0.20, 0.12]

REGIONS = ["uk-south", "uk-west", "eu-west", "on-premises-uk", "on-premises-eu"]

# Indicative unit economics, GBP. Mainframe is priced per MIPS-equivalent hour and is
# an order of magnitude dearer per unit of compute than cloud — that gap is what makes
# the migration question in this challenge non-trivial.
PLATFORM_ECONOMICS = {
    #            £/vcpu-hr  £/GB-mem-hr  £/GB-storage-mo  kWh per vcpu-hr
    "mainframe":   (0.412,     0.0180,          0.0420,        0.0195),
    "distributed": (0.068,     0.0042,          0.0180,        0.0128),
    "cloud":       (0.041,     0.0051,          0.0092,        0.0071),
}

# Utilisation profiles by platform: (mean %, spread). Mainframe estates are run hot
# and predictably; cloud estates are the opposite, which is where the waste hides.
UTILISATION = {
    "mainframe":   (78.0, 9.0),
    "distributed": (41.0, 18.0),
    "cloud":       (23.0, 16.0),
}

# Share of workloads that are near-idle but still billed.
IDLE_SHARE = 0.11
IDLE_UTILISATION_MAX = 5.0

# Grid carbon intensity, gCO2e/kWh. Range and shape are typical of the UK grid:
# cleaner in windy winter months and overnight, dirtier on still summer evenings.
CARBON_BASE = 168.0
CARBON_SEASONAL_AMPLITUDE = 54.0
CARBON_NOISE = 26.0
CARBON_FLOOR = 22.0


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def build_workloads(rng: np.random.Generator) -> dict:
    """The workload dimension. Everything else is derived from this."""
    service_idx = rng.integers(0, len(SERVICES), N_WORKLOADS)
    services = np.array([SERVICES[i][0] for i in service_idx])
    platforms = np.array([SERVICES[i][1] for i in service_idx])

    bu = rng.choice(BUSINESS_UNITS, N_WORKLOADS)
    # Punch holes in ownership — the untagged-spend problem, built in on purpose.
    unallocated = rng.random(N_WORKLOADS) < UNALLOCATED_SHARE
    bu = np.where(unallocated, UNALLOCATED_LABEL, bu)

    environments = rng.choice(ENVIRONMENTS, N_WORKLOADS, p=ENVIRONMENT_WEIGHTS)

    # Mainframe and distributed workloads sit on-premises; cloud ones do not.
    regions = np.empty(N_WORKLOADS, dtype=object)
    for i, plat in enumerate(platforms):
        if plat == "cloud":
            regions[i] = rng.choice(REGIONS[:3])
        else:
            regions[i] = rng.choice(REGIONS[3:])

    # Log-normal size distribution: a few very large workloads, a long tail of small
    # ones. A uniform estate would make the ranking exercise trivial and unrealistic.
    scale = rng.lognormal(mean=0.0, sigma=0.85, size=N_WORKLOADS)

    idle = rng.random(N_WORKLOADS) < IDLE_SHARE

    return {
        "workload_id": np.array([f"WL-{i + 1:05d}" for i in range(N_WORKLOADS)]),
        "business_unit": bu,
        "service": services,
        "platform": platforms,
        "environment": environments,
        "region": regions,
        "scale": scale,
        "idle": idle,
    }


def build_cost_daily(rng: np.random.Generator, wl: dict) -> tuple[list[str], list[list]]:
    """workload_cost_daily — one row per workload x day."""
    start = WINDOW_END - timedelta(days=WINDOW_DAYS - 1)
    days = np.array([start + timedelta(days=i) for i in range(WINDOW_DAYS)])
    dow = np.array([d.weekday() for d in days])
    is_month_end = np.array([(d + timedelta(days=1)).day == 1 for d in days])
    is_quarter_end = np.array(
        [(d + timedelta(days=1)).day == 1 and d.month in (3, 6, 9, 12) for d in days]
    )

    header = [
        "workload_id", "usage_date", "business_unit", "service", "platform",
        "environment", "region", "vcpu_hours", "memory_gb_hours", "storage_gb",
        "utilisation_pct", "cost_gbp",
    ]
    rows: list[list] = []

    for i in range(N_WORKLOADS):
        plat = wl["platform"][i]
        cpu_rate, mem_rate, storage_rate, _ = PLATFORM_ECONOMICS[plat]
        mean_u, spread_u = UTILISATION[plat]
        scale = wl["scale"][i]

        base_vcpu = 24.0 * max(1.0, scale * (6.0 if plat == "mainframe" else 3.2))

        # Weekday shape. Batch-heavy mainframe work spikes at period end; cloud
        # workloads mostly track the working week.
        weekday_factor = np.where(dow >= 5, 0.62, 1.0)
        if plat == "mainframe":
            weekday_factor = weekday_factor * np.where(is_month_end, 2.4, 1.0)
            weekday_factor = weekday_factor * np.where(is_quarter_end, 1.6, 1.0)

        noise = rng.normal(1.0, 0.11, WINDOW_DAYS).clip(0.45, 2.2)
        vcpu_hours = (base_vcpu * weekday_factor * noise).round(2)

        mem_ratio = 4.0 if plat == "mainframe" else rng.uniform(2.0, 8.0)
        memory_gb_hours = (vcpu_hours * mem_ratio).round(2)

        storage_gb = float(round(max(8.0, scale * (900 if plat == "mainframe" else 260)), 2))

        if wl["idle"][i]:
            utilisation = rng.uniform(0.4, IDLE_UTILISATION_MAX, WINDOW_DAYS)
        else:
            utilisation = rng.normal(mean_u, spread_u, WINDOW_DAYS)
        utilisation = utilisation.clip(0.2, 99.5).round(1)

        cost = (
            vcpu_hours * cpu_rate
            + memory_gb_hours * mem_rate
            + (storage_gb * storage_rate / 30.0)
        ).round(2)

        wid, bu = wl["workload_id"][i], wl["business_unit"][i]
        svc, env, reg = wl["service"][i], wl["environment"][i], wl["region"][i]
        for d in range(WINDOW_DAYS):
            rows.append([
                wid, days[d], bu, svc, plat, env, reg,
                float(vcpu_hours[d]), float(memory_gb_hours[d]), storage_gb,
                float(utilisation[d]), float(cost[d]),
            ])

    return header, rows


def build_chargeback(cost_header: list[str], cost_rows: list[list]) -> tuple[list[str], list[list]]:
    """chargeback_allocation — one row per business unit x month x service.

    A pure roll-up of workload_cost_daily, deliberately: a chargeback table that does
    not reconcile to the underlying cost table is the bug this challenge exists to
    teach people to find, so it must not be independently generated.
    """
    ix = {name: n for n, name in enumerate(cost_header)}
    agg: dict[tuple, dict] = {}

    for row in cost_rows:
        key = (row[ix["business_unit"]], _month_start(row[ix["usage_date"]]), row[ix["service"]])
        entry = agg.setdefault(key, {"cost": 0.0, "workloads": set()})
        entry["cost"] += row[ix["cost_gbp"]]
        entry["workloads"].add(row[ix["workload_id"]])

    # Business-unit monthly totals, for the share column.
    bu_month_total: dict[tuple, float] = {}
    for (bu, month, _svc), v in agg.items():
        bu_month_total[(bu, month)] = bu_month_total.get((bu, month), 0.0) + v["cost"]

    header = [
        "business_unit", "month", "service", "workload_count",
        "allocated_cost_gbp", "share_of_bu_pct", "variance_vs_prior_month_pct",
    ]
    rows: list[list] = []
    for (bu, month, svc) in sorted(agg, key=lambda k: (k[0], k[1], k[2])):
        v = agg[(bu, month, svc)]
        prior_month = _month_start(month - timedelta(days=1))
        prior = agg.get((bu, prior_month, svc))
        if prior and prior["cost"] > 0:
            variance = round((v["cost"] - prior["cost"]) / prior["cost"] * 100.0, 2)
        else:
            variance = None  # first month for this combination — no prior to compare
        total = bu_month_total[(bu, month)]
        rows.append([
            bu, month, svc, len(v["workloads"]), round(v["cost"], 2),
            round(v["cost"] / total * 100.0, 2) if total else 0.0,
            variance,
        ])

    return header, rows


def build_carbon(
    rng: np.random.Generator, cost_header: list[str], cost_rows: list[list]
) -> tuple[list[str], list[list]]:
    """carbon_by_workload — one row per workload x day.

    Grid intensity is SYNTHETIC (see the module docstring). Shape is realistic;
    the values are not measurements and must not be reported as such.
    """
    start = WINDOW_END - timedelta(days=WINDOW_DAYS - 1)
    day_of_year = np.array([(start + timedelta(days=i)).timetuple().tm_yday for i in range(WINDOW_DAYS)])
    # Cleaner in winter (windier), dirtier in still summer months.
    seasonal = CARBON_SEASONAL_AMPLITUDE * np.cos(2 * np.pi * (day_of_year - 190) / 365.0)
    intensity_by_day = (
        CARBON_BASE + seasonal + rng.normal(0, CARBON_NOISE, WINDOW_DAYS)
    ).clip(CARBON_FLOOR, None).round(1)

    day_index = {start + timedelta(days=i): i for i in range(WINDOW_DAYS)}
    ix = {name: n for n, name in enumerate(cost_header)}

    header = [
        "workload_id", "usage_date", "business_unit", "platform",
        "energy_kwh", "grid_intensity_gco2_per_kwh", "carbon_kg",
    ]
    rows: list[list] = []
    for row in cost_rows:
        plat = row[ix["platform"]]
        kwh_per_vcpu_hr = PLATFORM_ECONOMICS[plat][3]
        energy = round(row[ix["vcpu_hours"]] * kwh_per_vcpu_hr, 4)
        intensity = float(intensity_by_day[day_index[row[ix["usage_date"]]]])
        rows.append([
            row[ix["workload_id"]], row[ix["usage_date"]], row[ix["business_unit"]],
            plat, energy, intensity, round(energy * intensity / 1000.0, 5),
        ])

    return header, rows


def generate(seed: int = DEFAULT_SEED) -> dict[str, tuple[list[str], list[list]]]:
    """Build all three gold tables. Returns {table_name: (header, rows)}."""
    rng = np.random.default_rng(seed)
    wl = build_workloads(rng)
    cost_header, cost_rows = build_cost_daily(rng, wl)
    cb_header, cb_rows = build_chargeback(cost_header, cost_rows)
    carbon_header, carbon_rows = build_carbon(rng, cost_header, cost_rows)
    return {
        "workload_cost_daily": (cost_header, cost_rows),
        "chargeback_allocation": (cb_header, cb_rows),
        "carbon_by_workload": (carbon_header, carbon_rows),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, help="Output directory for parquet files")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = p.parse_args()

    try:
        import pandas as pd
    except ImportError:
        print("pandas is required: pip install -r build/requirements.txt", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, (header, rows) in generate(args.seed).items():
        df = pd.DataFrame(rows, columns=header)
        df.to_parquet(out / f"{name}.parquet", index=False)
        print(f"  {name}: {len(rows):,} rows -> {name}.parquet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
