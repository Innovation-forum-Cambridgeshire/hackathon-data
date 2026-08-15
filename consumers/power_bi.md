# Power BI Desktop

**Power BI reads parquet directly** — use it rather than the CSV twin.

> Power BI Desktop is **Windows-only**. On a Mac, use DuckDB or the notebooks; the
> data is identical and nothing in the challenge requires Power BI.

## Connect

**Get Data → Web**, paste a parquet URL:

```
https://data.inno-forum.co.uk/<challenge>/<version>/gold/<table>.parquet
```

Power Query recognises parquet and infers types from the file's own schema, so dates
arrive as dates rather than as text — one of the reasons parquet is worth preferring
over CSV even here.

## Use the pinned version

Point at `/<version>/`, never `/latest/`. A published report that reads `latest`
changes underneath its own conclusions the next time a release lands, and nobody —
including you — can reproduce what the numbers were when you wrote the commentary.

## Joining tables

The manifest tells you the join keys. Two worth knowing:

- **c03** — `carbon_by_workload` joins `workload_cost_daily` on `workload_id` **and**
  `usage_date`. Both, not just the id.
- **c05** — `alert_history` is **regional**, `region_weather_daily` is **county-level**.
  That is a real join across different grains, not a rename, and collapsing one to the
  other without saying so will quietly change your answer.

## Before you publish a visual

Check `manifest.json` for tables described as SYNTHETIC. Several look like
observations and are not — c05's weather, c03's grid intensity. A Power BI report
titled "Carbon by business unit" implies measurement it cannot support.
