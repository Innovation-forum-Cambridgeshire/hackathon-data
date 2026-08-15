# Safe in the Open — v1

Immutable snapshot. Judging is reproducible against this tag; it will never be rewritten.

## Access

```sql
INSTALL httpfs; LOAD httpfs;
SELECT * FROM read_parquet('https://data.inno-forum.co.uk/c04-safe-in-the-open/v1/gold/<table>.parquet');
```

No credentials, no account. Browse the catalogue at `https://data.inno-forum.co.uk/c04-safe-in-the-open/v1/manifest.json`.

## Tables

- **synthetic_councillor_register** — Synthetic register of interests matching the shape of a real one. No real member's data is present. ~4,200 rows
- **support_directory** — Reporting and support routes by area. Contact values are SYNTHETIC and must never be dialled or emailed — see the note above. ~180 rows
- **message_signals** — Synthetic message corpus with the derived signals a triage system would act on. Contains no real messages and no realistic abuse — severity is carried by structure and metadata, not by hostile text. See build/generators/synthetic_abuse.py. ~24,000 rows

## Not mirrored here

These sources are not redistributed by us — licence terms unconfirmed or not permitted. Loader code in the repo fetches them from the original publisher:

- `council-minutes`
- `public-posts`
- `support-routes`
- `toxicity-models`

## Handle with care

Public information and the participant's explicit consent only. Data protection by design, a DPIA before any live data, and a written data-sharing agreement following the ICO Data Sharing Code. No private citizens, no bulk collection, no council data or systems. Signpost support, never amplify harm.

## Attribution

Contains public sector information licensed under the Open Government Licence v3.0.
