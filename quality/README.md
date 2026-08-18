# Data quality, assurance and assessment

Great Expectations suites over all five challenge corpora, with a branded report.

```bash
pip install -r quality/requirements.txt
python quality/run_assurance.py                 # against sample/data
open quality/out/index.html
```

## The problem this had to solve first

Every corpus in this repository is **deliberately imperfect**. c01's catalogue
says so outright:

> Sensor data is often miscalibrated, duplicated or missing. Strong entries
> surface data quality rather than hiding it behind a clean-looking chart.

NDVI is missing on 21% of field-days, in clustered runs correlated with
temperature. 1.5% of station-days are duplicated, and `quality_flag` deliberately
does *not* catch them, so `WHERE quality_flag = 'ok'` — every team's first
instinct — does not clean the data. `predicted_risk` in c05 is miscalibrated by
a factor of about 2.7 on purpose.

A conventional data-quality suite over this would light up red for reasons that
are all correct by design, and would be worthless. Worse, it would train everyone
to ignore it, so the one real defect in the pile goes unnoticed.

## So there are two suites per table, and they pull in opposite directions

| Suite | Asserts | A failure means |
|---|---|---|
| `<challenge>.<table>.schema` | columns, order, row count | the table changed shape |
| `<challenge>.<table>.contract` | types, completeness, keys, domains, ranges, cross-column arithmetic, referential integrity | **a real defect** |
| `<challenge>.<table>.defects` | the deliberate flaws are still present and inside declared bounds | **a flaw was tidied away, or drifted** |
| `<challenge>.derived-metrics.defects` | flaws needing a window, a join or a group comparison | as above |
| `programme.csv-twin.reconciliation` | every CSV equals its parquet | Excel and R users get different data |

Both must pass. A corpus that validates clean has lost its point; a corpus whose
contract fails is broken. The split is the only way the report can tell those
apart, and it is what lets an organiser read one page and believe it.

The declarations live in three files, deliberately separate:

- **`config/contract.yml`** — what must be TRUE.
- **`config/defects.yml`** — what must be WRONG, with bounds on both sides.
- **`config/relationships.yml`** — cross-table keys, join hazards, and the pipeline.

`model.py` cross-checks all three against `catalogue/*.yml` on load and **raises**
if they disagree. A suite that silently validates zero tables reports success,
which is worse than no suite.

## The top ten affected rows

Every failure carries up to ten affected rows, addressed by **business key** and
not by pandas row number:

```
station_id  observation_date
S-0001      2016-11-27
S-0001      2017-02-17
```

That comes from the checkpoint's result format:

```python
{"result_format": "SUMMARY",
 "partial_unexpected_count": 10,
 "unexpected_index_column_names": ["station_id", "observation_date"],
 "return_unexpected_index_query": True}
```

Row numbers would be useless here — the corpus is regenerated, so row 48,213 is a
different row tomorrow. Every table declares `index_columns` in `defects.yml`
for this reason, whether or not it has any defects.

## Branding

Tokens are copied verbatim from the website's `src/styles/global.css`, and
`brand.verify_brand()` re-reads that file on every run and reports drift, so a
rebrand on the site surfaces here as a warning rather than as two subtly
different greens.

The stylesheet reaches Data Docs through the supported extension point: GX's page
templates contain `{% include 'data_docs_custom_styles.css' ignore missing %}`,
and `SiteBuilder` adds `<plugins>/custom_data_docs/styles` to the Jinja search
path. We write that file; we do not patch GX.

Two things could **not** be done that way and are handled in a post-processing
pass instead:

- **The logo header.** GX builds its Jinja environment as
  `ChoiceLoader([packaged_templates, styles, custom_styles, custom_views])`, and
  `ChoiceLoader` returns the *first* loader that has the template. A file in
  `custom_data_docs/views` therefore cannot override a template GX ships. So the
  header is injected into the rendered HTML.
- **External assets.** Stock Data Docs loads Bootstrap, jQuery, Popper, Vega,
  Font Awesome and bootstrap-table from six external origins at *view* time. For
  an assurance artefact that is two problems: it does not render offline or in
  five years, and it emits third-party requests from a report about data
  governance — in a project that self-hosts its fonts specifically to avoid that.
  `--vendor` fetches them once and rewrites the references. Without network the
  report still builds and the limitation is recorded rather than hidden.

Fonts (Barlow, Barlow Condensed, IBM Plex Mono) are vendored from `@fontsource`
in the website repo and inlined as base64. That costs ~80 KB per page and was
weighed: relative URLs break because validation pages nest five levels deep, and
absolute URLs break on a GitHub Pages project site served from a subpath.

## Diagrams

`diagrams.py` emits SVG directly — a crow's-foot ERD per challenge and the
pipeline as swimlanes. Graphviz and Mermaid would both do it better and neither
is available without adding a system package or fetching a renderer at build
time, which is the dependency the rest of this avoids. Hand-drawn also means the
bytes are deterministic, so the committed diagrams do not churn on every build.

Dashed lines with struck ends are **hazards** — joins a participant will
reasonably attempt that the data does not support. They are drawn rather than
omitted, because a missing line reads as an oversight instead of a decision. The
important one is c05: `region_weather_daily.area` (41 county-level areas) and
`alert_history.region` (9 regions) have an **empty intersection** and no lookup
table ships. Building that mapping is part of the challenge.

## Profile baseline

`quality/baseline/*.json` holds a committed column profile. Each run diffs
against it:

- **structural** (column added, removed, retyped; a category appearing or
  vanishing in a closed domain) — **fails the build**
- **material** (null rate or cardinality moved a long way) — warns
- **ordinary** (quantiles moved within tolerance) — noted

Only structural drift fails, because only structural drift is unambiguously
wrong. The rest exists to answer the question expectations cannot: *what
changed?* A null rate moving from 21% to 29% is inside the declared band, is a
large change, and is exactly the shape of an accident.

Regenerate deliberately with `--update-baseline`, in its own commit.

## How the relationships were established

Every foreign key in `relationships.yml` was checked against the built corpus
before it was written down, because declaring one that does not hold is worse
than declaring none — the suite would fail on correct data and teach everyone to
ignore it. As measured on 2026-08-16:

| Relationship | Result |
|---|---|
| `field_daily.nearest_station_id` → `station_weather.station_id` | 0 orphans / 180,000 |
| `lsoa_crime_monthly.lsoa_code` → `lsoa_deprivation.lsoa_code` | 0 orphans / 2,430,360; parent unique |
| `carbon_by_workload.workload_id` → `workload_cost_daily.workload_id` | 0 orphans |
| `chargeback_allocation` ⇄ `workload_cost_daily` | both total £15,325,232.68, equal to the penny |
| `synthetic_cohort.region` ⊆ `alert_history.region` | 9 of 9 |
| `region_weather_daily.area` ∩ `alert_history.region` | **0 of 41 — no join key exists** |

## Running it

```bash
python quality/run_assurance.py --data-root sample/data
python quality/run_assurance.py --data-root /tmp/ci/c01-... --vendor
python quality/run_assurance.py --update-baseline
python quality/run_assurance.py --allow-known-findings   # see FINDINGS.md
```

Exit `0` when the contract holds, the deliberate defects are intact and there is
no structural drift; `1` otherwise. `--allow-known-findings` exits 0 if every
failure is already recorded in `FINDINGS.md`, so one triaged unfixed defect does
not block unrelated PRs. It is deliberately explicit — turning a red build green
requires a diff someone reviews.

The corpus is generated, not committed (`sample/.gitignore`), so a data root has
to exist first. CI builds it, then validates what it built.

## Output

```
quality/out/
├── index.html                     branded landing page — start here
├── ASSESSMENT.md                  the written assessment, with sign-off lines
├── diagrams/*.svg                 ERDs and swimlanes
├── profiles/*.json                this run's profile
└── gx/gx/uncommitted/data_docs/   Great Expectations Data Docs
```

`quality/out/` is gitignored. The report is **organiser-facing**: it documents
the deliberate traps and should not go to participants before their event.

## Known gaps

- Two catalogue tables (`market_prices`, `lsoa_digital_exclusion`) are pointer-only
  because their licence gates have not cleared, so there are no bytes to check.
  The report names them rather than omitting them.
- Population-level defect metrics cannot point at rows. "21% of NDVI is missing"
  has no ten rows to show. Row-level contract failures do carry their top ten.
- The suites validate a *build*, not a release. Validate after building the
  release artefact, not before.
