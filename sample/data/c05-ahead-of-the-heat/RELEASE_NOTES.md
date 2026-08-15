# Ahead of the Heat — v1

Immutable snapshot. Judging is reproducible against this tag; it will never be rewritten.

## Access

```sql
INSTALL httpfs; LOAD httpfs;
SELECT * FROM read_parquet('https://data.inno-forum.co.uk/c05-ahead-of-the-heat/v1/gold/<table>.parquet');
```

No credentials, no account. Browse the catalogue at `https://data.inno-forum.co.uk/c05-ahead-of-the-heat/v1/manifest.json`.

## Tables

- **alert_history** — Heat-health alert level by region and day. SYNTHETIC — generated with a realistic seasonal pattern, not the UKHSA feed. Switch to `ukhsa-alerts` once a fetcher exists. ~26,298 rows
- **synthetic_cohort** — Synthetic cohort with risk factors and care setting. No real person is described. Health-adjacent, so k >= 10 rather than the default 5. ~5,000 rows
- **region_weather_daily** — Daily temperature and humidity by area. SYNTHETIC — `metoffice` is pointer-only after the D4 licence review, so nothing here is an observation. Do not report a temperature finding from this as if it were measured. ~119,802 rows

## Not mirrored here

These sources are not redistributed by us — licence terms unconfirmed or not permitted. Loader code in the repo fetches them from the original publisher:

- `charity-service`
- `metoffice`

## Handle with care

Health data about vulnerable adults — consent and data protection by design (UK GDPR), data minimisation and safeguarding throughout. The tool supports staff and carers; it never replaces professional judgement, and must fail safe.

## Attribution

Contains public sector information licensed under the Open Government Licence v3.0.
