# The Useful Hour — Challenge 03, Beyond the Mainframe

**One unit of cost for a three-generation estate.** Divide cost by the work actually done
(vCPU-hours × utilisation) and mainframe, distributed and cloud share one comparable number.

| File | What it is |
|---|---|
| `the-useful-hour.pptx` | The pitch deck: 13 slides, with speaker notes on every slide |
| `the-useful-hour.ipynb` | The analysis, executed, with outputs saved so it reads without running |
| `outputs/savings_queue.csv` | 842 ranked actions, each with a workload, an owner and an annual value |
| `outputs/bu_scorecard.csv` | Spend, utilisation, £ per useful hour, savings and carbon per business unit |
| `outputs/deck_numbers.json` | Every figure the deck quotes, written by the notebook |
| `build_deck.js` | Rebuilds the deck from `deck_numbers.json` |

## Headline findings

1. **Per billed vCPU-hour the mainframe costs 7.2× cloud. Per useful hour it costs 2.2×.** Cloud runs at
   21% utilisation, and distributed is the cheapest place to do a unit of work.
2. **The migration case shrinks from an 86% saving to 54%** once the cloud's real utilisation is
   counted. It becomes a loss if one mainframe hour needs more than ~2.2 cloud vCPU-hours to replace.
3. **£1.2M a year is available without moving anything** (idle, right-sizing, and switching dev and
   test off at weekends on cloud and distributed). A further £1.19M of idle mainframe capacity is
   reported separately, because banking it needs a contract change.
4. **7.6% of spend (£1.16M) has no owner**, which is more than any real business unit. A model that
   infers owners scores at chance level (4.3% vs 4.2%), so the fix is a process: no tag, no deploy.
5. **Carbon per useful hour reverses the billed-hour ranking.** Grid intensity is synthetic, so this
   demonstrates the method and is not a finding.

## Reproduce

From the repo root:

```bash
python build/build.py build --challenge c03-beyond-the-mainframe --version v1 --out sample/data/c03-beyond-the-mainframe
cd submission/c03-the-useful-hour && jupyter nbconvert --to notebook --execute --inplace the-useful-hour.ipynb
NODE_PATH=<folder containing pptxgenjs>/node_modules node build_deck.js
```

If no local build is found, the notebook falls back to the published v1 release. It needs pandas,
pyarrow, matplotlib and scikit-learn.

**Data:** the challenge's synthetic FinOps estate only (CC0, seeded generator in this repo). No
client data.
