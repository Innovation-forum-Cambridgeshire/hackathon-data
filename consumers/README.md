# Getting the data into your tool

Every recipe here works two ways: against a **local build** while you are setting up,
and against the **published URL** during the event. Nothing needs a key, an account
or a login, because there is nothing to log into — the data is anonymous HTTPS by
design, and that is the single decision the whole platform is built around.

Pick your tool:

| Tool | File | Reads parquet? |
|---|---|---|
| DuckDB (CLI, Python, R) | [duckdb.sql](duckdb.sql) | yes, directly over HTTPS |
| Python / pandas | [python_starter.py](python_starter.py) | yes |
| R | [r_starter.R](r_starter.R) | yes, via `arrow` |
| Excel | [excel.md](excel.md) | **no** — use the CSV twin |
| Power BI Desktop | [power_bi.md](power_bi.md) | yes |
| Tableau Public | [tableau.md](tableau.md) | **no** — use the CSV twin |

## Two URLs, and the difference matters

```
https://data.inno-forum.co.uk/<challenge>/<version>/gold/<table>.parquet   ← pinned
https://data.inno-forum.co.uk/<challenge>/latest/...                       ← moves
```

**Judging is against a pinned version.** A release tag is immutable — the same URL
returns the same bytes forever, which is what lets anyone reproduce your result
afterwards. `latest` is the only mutable object in the whole design and it exists
for convenience, not for citation.

Put the **pinned** version in anything you submit. If your notebook says `latest`,
nobody can check your numbers a month later, including you.

## Start from the manifest, not from a filename

```
https://data.inno-forum.co.uk/<challenge>/<version>/manifest.json
```

It lists every table, its grain, its row count, and **what each column means**.
Guessing whether `utilisation_pct` is a percentage or a fraction is exactly the
error that survives all the way to a final demo.

There is also `llms.txt` in the same directory if you are pointing a model at this,
and `chunks.jsonl` if you are building retrieval over it.

## Parquet or CSV?

**Prefer parquet.** It is roughly 10× smaller, it carries real types so dates arrive
as dates, and every tool above except Excel and Tableau Public reads it directly.

CSV twins exist because Excel and Tableau Public cannot read parquet at all, and a
challenge that excluded everyone without a paid BI licence would not be much of an
open programme. They carry a **UTF-8 BOM** so Excel detects the encoding instead of
mangling accented place names, and **ISO-8601 dates** so `03/04` cannot be read as
3 April here and 4 March in a US locale.

Tables over a million rows ship a **sample** instead of a full twin — a 2.4M-row CSV
helps nobody. The manifest tells you which is which.

## Before you quote a number

Some tables **look like observations and are not**. c05's weather is generated
because the Met Office source is pointer-only; c03's grid intensity is synthetic.
Each table says so in its own description, and `llms.txt` collects them at the top.

Some sources are **catalogued but not mirrored** — we may read them, we may not
republish them. The manifest's `pointer_only` list names them. If you fetch one
yourself, that is fine; **committing a copy of it may not be**, because reading at
source and redistributing are different acts under most licences.
