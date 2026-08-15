# Sample notebooks

One notebook per challenge. Each loads the data, orients you, surfaces one real
finding, and demonstrates one technique you can carry into a solution.

**These are not solutions.** A notebook that solved the challenge would remove the
reason to turn up. What they remove instead is the cold start — the first hour
spent working out what the columns mean, which is time that has nothing to do with
the problem you came to solve.

## Setup

```bash
./sample/setup.sh
```

Creates `sample/.venv`, installs pinned dependencies, and registers a Jupyter
kernel called **IF Hackathon**.

## Build the data first

The notebooks read a local build. Nothing here touches the network at run time —
there are no credentials, no accounts and no rate limits, which is the same
anonymous-access principle the whole platform is built on.

From the **repo root**:

```bash
python build/build.py build --challenge c03-beyond-the-mainframe \
    --version v1 --out sample/data/c03-beyond-the-mainframe
```

Takes about 7 seconds. Repeat for whichever challenges you want.

> **Built data is deliberately not committed.** It is release payload — published
> as GitHub Release assets, which have no total-size cap and no bandwidth quota.
> Committing it would blow the ~100 MB per-file repo limit, bloat every clone
> forever, and defeat the reason the delivery design uses Releases at all. c03
> alone is 71 MB of CSV twins.

## Run

```bash
cd sample && .venv/bin/jupyter lab notebooks/
```

## What each notebook covers

| Challenge | Technique | Why this one |
|---|---|---|
| c01 One Farm, One Picture | spatial join and seasonality | the join is the hard part, not the model |
| c02 Mapping the Gaps | rates, not counts | the ecological fallacy, which sinks most civic-data entries |
| c03 Beyond the Mainframe | cost attribution and unit economics | untagged spend and the platform cost gap |
| c04 Safe in the Open | classification under class imbalance | accuracy is the wrong metric when positives are rare |
| c05 Ahead of the Heat | calibration, not just ranking | a well-ranked model can still be badly wrong |

## Read this before quoting a number

Several tables **look like observations and are not**:

- **c03 `carbon_by_workload`** — grid intensity is synthetic. Carbon findings do
  not transfer to the real grid.
- **c05 `region_weather_daily`** — every row carries `is_synthetic = true`. The
  Met Office source is pointer-only because the Met Office prices commercial
  reuse under the EUMETNET licence, so nothing here is measured.
- **c05 `alert_history`** — generated with a realistic seasonal pattern, not the
  UKHSA feed.
- **c04 everything** — synthetic by legal necessity. Republishing real social
  content would risk PHA 1997, the Defamation Act 2013 and misuse of private
  information.

Each notebook prints its own caveats in the first cell via
`challenge.caveats()`, so you do not have to remember this page.

## The data contract

Do not restate the schema in a markdown cell — it will drift from the catalogue
within a day. Ask the manifest:

```python
from lib.loader import load
c = load("c03-beyond-the-mainframe")
c.describe("workload_cost_daily")   # name, type and MEANING of every column
```

`dtypes` tells you a column is a float. The contract tells you whether it is a
percentage or a fraction, which is the thing that actually produces wrong answers.
