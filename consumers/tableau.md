# Tableau

## Tableau Public cannot connect to a database, or read parquet

The free tier is **file-only** — no live database connections, no parquet. That is a
platform limit, not a configuration problem, and it is exactly why every table here
ships a **CSV twin**. A challenge that required a paid licence to enter would not be
much of an open programme.

## Tableau Public

1. Download the CSV twin:
   `https://data.inno-forum.co.uk/<challenge>/<version>/gold/<table>.csv`
2. **Connect → To a File → Text file**
3. Check the date columns are typed as **Date**, not String. They are ISO-8601, so
   Tableau usually gets this right — but confirm it rather than assume, because a
   date read as text sorts lexicographically and looks almost correct.

**Tables over a million rows ship a sample instead of a twin.** Fine for exploring
the shape; not fine for a headline figure. `manifest.json` says which is which.

> **Anything you publish to Tableau Public is public.** That is the whole model. It
> is harmless for this data — it is open by design — but do not develop the habit
> here and repeat it at work with something that is not.

## Tableau Desktop

Reads parquet via a connector, and can point at the URL directly. Prefer that: real
types, roughly a tenth the size, and no download step.

## Both versions

Use the **pinned** `/<version>/` URL in anything you present. Judging is against an
immutable tag, and a dashboard built on `latest` cannot be checked afterwards.
