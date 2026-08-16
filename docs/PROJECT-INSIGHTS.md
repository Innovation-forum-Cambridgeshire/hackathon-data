# Configuring the two Insights charts

The project is **private** and the org is on the **free** plan, which allows
**two saved charts**. This is how to spend them.

> **These have to be configured in the UI.** There is no GitHub API for Insights
> charts — the GraphQL schema exposes no chart or insight mutation, only board
> `views`. Everything else about the project is scripted; this part cannot be.

---

## What was blocking a useful second chart

A chart can only group by a field that has values. Before this, the project had
exactly one populated field — **Status**. Labels, Milestone and Assignees were all
empty, so both charts could only ever have been "count of items by Status", and
the second would have been a restatement of the first.

An **Area** field now exists and is populated on all 83 items. It is derived
mechanically by walking each item up its parent chain to the owning EPIC — not
assigned by judgement — so it is accurate by construction and stays that way for
new items as long as they are filed under an epic.

| Area | Covers |
|---|---|
| Data platform | catalogues, generators, build, releases, Worker |
| Marketing site | public site, forms, accessibility, deploy |
| Compliance & legal | legal pack, DPIA, ICO, processor agreements |
| Commercial | membership, sponsorship, pricing, VAT |
| Decisions | open programme decisions |
| Event delivery | running Challenge 03, 26–30 Oct 2026 |
| Documentation | programme artefacts and written outputs |

---

## Chart 1 — Burn up (keep)

Leave it. It is the default historical chart and it is the right one to keep,
**but read it knowing what it currently shows**: every board item was created on
the same day the board was built, so the burn-up is a vertical line rather than a
trend. It becomes informative from the first working session that spans more than
one day, and there is nothing to fix in the meantime.

Do **not** regroup it by Area. Splitting one day of history seven ways produces
seven vertical lines instead of one.

---

## Chart 2 — "Where the work sits" (create this)

**Insights → New chart**, then:

| Setting | Value |
|---|---|
| Chart name | `Where the work sits` |
| Layout | **Column** (stacked) |
| X-axis | **Area** |
| Group by | **Status** |
| Filter | *(leave empty — see below)* |

Leave the filter empty on purpose. `is:open` would hide the Done column, and the
completed work is half the message: it is what tells you an area is genuinely
finished rather than untouched.

### What it shows today

```
Area                  Todo  In Prog  Done  Total
Data platform            4        2    26     32
Marketing site           2        1    10     13
Compliance & legal       4        3     4     11
Commercial               4        3     2      9
Decisions                2        2     3      7
Event delivery           6        0     0      6
Documentation            0        1     4      5
TOTAL                   22       12    49     83
```

**The line that matters is Event delivery: six items, none started, for an event
on 26–30 October.** The burn-up cannot show that — at 59% complete overall it
reads as a programme comfortably ahead. This chart shows the completion is
concentrated in the data platform while the work of actually running the event has
not begun.

That contrast is the entire reason to spend the second chart slot here rather than
on another view of Status.

---

## Why not a different second chart

- **Status alone** — already the burn-up's grouping. Two charts saying the same
  thing wastes the only other slot you have.
- **Items by repository** — splits 83 items into two buckets that mean nothing to
  a reader; the repo an issue lives in is a filing detail.
- **A second historical chart** — not available. Historical charts require GitHub
  Team or Enterprise; the free plan gets current charts plus the default burn-up.
- **Anything by assignee** — the field is empty, and populating it would be
  inventing ownership that has not been agreed.

---

## If you want a third view without paying

Two options, both already in place:

**`scripts/programme-report.py`** produces an HTML dashboard, a CSV and a JSON
export, with no chart cap and no plan limit. It also covers the KPIs GitHub
structurally cannot see — licence-review progress and data readiness live in the
catalogue YAML, not in issue metadata, so no Insights configuration can ever
reach them.

**Making the project public** would give unlimited charts on the free plan. It is
listed here to be dismissed rather than rediscovered: the items live in a private
repo and their titles name unresolved compliance gaps — *"Article 28 processor
agreement does not exist"*, *"ICO registration number unknown"*. Publishing those
to unlock charting would be a bad trade.

---

## Adding a field later

Fields are unlimited; only charts are capped. If the second chart stops earning
its slot, the most useful replacement dimension is probably **what each open item
is waiting on** — us, an SLT decision, or an external party. That was deliberately
not created here, because populating it accurately needs decisions this repo
cannot make on its own, and a half-filled field makes a worse chart than no field.
