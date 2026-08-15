# Innovation Forum × R1X — hackathon data

Open data for the five hackathon challenges. **No account, no login, no API key.**

```sql
INSTALL httpfs; LOAD httpfs;
SELECT * FROM read_parquet(
  'https://data.inno-forum.co.uk/c03-beyond-the-mainframe/v2026-10-01/gold/workload_cost_daily.parquet'
);
```

Start at **<https://data.inno-forum.co.uk/manifest.json>** — every dataset, its schema,
licence, row count and direct URL.

---

## Get the data

Pick whichever matches your tools. They all reach the same files.

**Python**
```python
import pandas as pd
df = pd.read_parquet('https://data.inno-forum.co.uk/<challenge>/<version>/gold/<table>.parquet')
```

**DuckDB** — reads only the columns you ask for, over the network, no download
```sql
INSTALL httpfs; LOAD httpfs;
SELECT * FROM read_parquet('https://data.inno-forum.co.uk/.../gold/<table>.parquet');
```

**R**
```r
arrow::read_parquet('https://data.inno-forum.co.uk/.../gold/<table>.parquet')
```

**Power BI** — Get Data → Web → paste the `.parquet` or `.csv` URL.
*Power BI Desktop is Windows only.*

**Tableau** — use the `.csv` twin.
*Tableau Public (the free version) cannot connect to live databases at all, which is why
every table under a million rows ships a CSV twin and larger ones ship a sample.*

**Excel / Sheets** — `samples/<table>_1000.csv`. UTF-8 with BOM and ISO-8601 dates, so
accents and dates survive the trip.

**Browser, no install** — a DuckDB-WASM console is at
<https://data.inno-forum.co.uk/play>. Type SQL, get a table. Nothing to set up.

**LLMs and agents** — see below. This is a first-class path, not an afterthought.

---

## Using this with an LLM

| File | What it is |
|---|---|
| `/llms.txt` | What lives here and how to fetch it |
| `/manifest.json` | Full catalogue — schemas, licences, row counts, URLs |
| `<challenge>/<version>/docs/text/*.md` | Every PDF and Word doc as page-anchored markdown |
| `<challenge>/<version>/chunks.jsonl` | Pre-chunked with stable IDs and source anchors |

A model cannot read a PDF over HTTPS, but it reads markdown instantly. Both are published —
the original for citation, the markdown for reasoning. `chunks.jsonl` means you build a RAG
index in one line instead of losing an afternoon to PDF parsing.

There is also an **MCP server** so agents can query the data natively — see `docs/mcp.md`.

---

## How it is organised

```
data.inno-forum.co.uk/<challenge>/<version>/
├── gold/      analysis-ready, joined, documented   ← start here
├── silver/    cleaned but not joined
├── samples/   1,000-row CSVs for Excel and quick looks
├── docs/original/   the PDFs and Word documents
├── docs/text/       the same, as markdown
├── chunks.jsonl
└── manifest.json · LICENCE.md · ATTRIBUTION.md
```

**Versions never change.** `v2026-10-01` will hold the same bytes forever, because judging
has to be reproducible. The current version for a challenge is in
`<challenge>/latest.json` — the only thing here that ever moves.

---

## The five challenges

| | Challenge | Domain |
|---|---|---|
| 01 | [One Farm, One Picture](https://r1x.co.uk/public_hackathon/challenges/one-farm-one-picture) | AgTech |
| 02 | [Mapping the Gaps](https://r1x.co.uk/public_hackathon/challenges/mapping-the-gaps) | Civic |
| 03 | [Beyond the Mainframe](https://r1x.co.uk/public_hackathon/challenges/beyond-the-mainframe) | Enterprise FinOps |
| 04 | [Safe in the Open](https://r1x.co.uk/public_hackathon/challenges/safe-in-the-open) | Civic online safety |
| 05 | [Ahead of the Heat](https://r1x.co.uk/public_hackathon/challenges/ahead-of-the-heat) | Charity · patient safety |

---

## Licences, and what we don't ship

Every source carries an explicit `redistributable` flag in `catalogue/*.yml`. **Where we
don't hold redistribution rights, we ship loader code and a pointer rather than bytes** —
the build refuses to mirror anything that hasn't cleared review. So some sources you fetch
from the original publisher; `manifest.json` says which, under `pointer_only`.

Most sources are Open Government Licence v3.0 and need attribution. `ATTRIBUTION.md` in
each release has the wording — please carry it into anything you publish.

Two datasets are **synthetic**, generated in this repo under CC0: the FinOps estate for
challenge 03 and the cohort for challenge 05. Generators and seeds are here, so they are
reproducible and auditable.

**No personal or special-category data appears anywhere in this repository.** Challenges 04
and 05 touch sensitive domains and are deliberately built from public-record or synthetic
sources only. The build enforces this — a catalogue declaring personal data fails
validation rather than warning.

---

## Something wrong with the data?

Open an issue. During an event, label it `during-event` and it gets triaged first.

Data quality problems are genuinely useful to us — a miscalibrated sensor or a duplicated
row is worth reporting, and noticing it is a legitimate part of the work rather than a
distraction from it.

---

## For organisers

`docs/SETUP.md` covers the Azure DevOps and GitHub setup and, more usefully, why the work
is split the way it is. `scripts/` holds the setup automation.
