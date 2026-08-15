# Beyond the Mainframe — v1

Immutable snapshot. Judging is reproducible against this tag; it will never be rewritten.

## Access

```sql
INSTALL httpfs; LOAD httpfs;
SELECT * FROM read_parquet('https://data.inno-forum.co.uk/c03-beyond-the-mainframe/v1/gold/<table>.parquet');
```

No credentials, no account. Browse the catalogue at `https://data.inno-forum.co.uk/c03-beyond-the-mainframe/v1/manifest.json`.

## Tables

- **workload_cost_daily** — Synthetic workload cost and utilisation by day, across a hybrid mainframe, on-premises and cloud estate. ~419,750 rows
- **chargeback_allocation** — Monthly cost allocation and chargeback by business unit and service. A pure roll-up of workload_cost_daily. ~8,136 rows
- **carbon_by_workload** — Estimated carbon per workload per day. Grid intensity is SYNTHETIC — realistic in shape, not a measurement. ~419,750 rows

## Not mirrored here

These sources are not redistributed by us — licence terms unconfirmed or not permitted. Loader code in the repo fetches them from the original publisher:

- `finops-open`
- `sponsor-lake`

## Handle with care

Teams work on a SYNTHETIC environment: workloads, cost data, logs and expert scenarios. No client systems, no client data. Practitioner mentors contribute knowledge throughout the event.
