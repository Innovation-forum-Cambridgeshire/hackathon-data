#!/usr/bin/env python3
"""Python starter — load a challenge and check it before trusting it.

    python consumers/python_starter.py

Reads a LOCAL build by default. Set PUBLISHED = True during the event.
"""

import json
import urllib.request

import pandas as pd

CHALLENGE = "c03-beyond-the-mainframe"
VERSION = "v2026-10-26"
PUBLISHED = False

if PUBLISHED:
    # Pinned, not /latest/ — judging is against an immutable tag, so a result
    # produced against a moving URL cannot be reproduced afterwards.
    BASE = f"https://data.inno-forum.co.uk/{CHALLENGE}/{VERSION}"
else:
    BASE = f"sample/data/{CHALLENGE}"

# The manifest carries names, types AND MEANINGS. Read it before the data: dtypes
# tell you a column is a float, the contract tells you whether it is a percentage
# or a fraction, which is the thing that produces wrong answers.
#
# json.load, NOT pd.read_json — the manifest is a nested object, and read_json tries
# to coerce it into a frame and fails. Easy mistake; it is the first line of the
# file, so it fails loudly rather than half-working.
if BASE.startswith("http"):
    with urllib.request.urlopen(f"{BASE}/manifest.json", timeout=30) as r:
        manifest = json.load(r)
else:
    manifest = json.loads(open(f"{BASE}/manifest.json").read())

print(f"{manifest['title']} — {len(manifest['tables'])} table(s)\n")

for t in manifest["tables"]:
    print(f"  {t['name']:<28} ~{t['approx_rows']:>9,} rows   {t['grain']}")
    if "SYNTHETIC" in (t.get("description") or "").upper():
        print("      ^ SYNTHETIC — do not report values from this as measurements")
print()

df = pd.read_parquet(f"{BASE}/gold/workload_cost_daily.parquet")

# Always confirm the grain before aggregating anything.
dupes = df.duplicated(["workload_id", "usage_date"]).sum()
print(f"rows {len(df):,} · workloads {df.workload_id.nunique():,} · duplicate keys {dupes}")

untagged = df[df.business_unit == "UNALLOCATED"].cost_gbp.sum()
print(f"untagged spend: GBP {untagged:,.0f} ({untagged / df.cost_gbp.sum():.1%} of total)")

unit = (df.groupby("platform")
          .apply(lambda g: pd.Series({
              "cost_gbp": g.cost_gbp.sum(),
              "cost_per_vcpu_hr": g.cost_gbp.sum() / g.vcpu_hours.sum(),
              "mean_util_pct": g.utilisation_pct.mean(),
          }), include_groups=False)
          .sort_values("cost_per_vcpu_hr", ascending=False))
print("\n", unit.to_string())
