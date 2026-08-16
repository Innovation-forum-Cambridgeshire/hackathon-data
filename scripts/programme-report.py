#!/usr/bin/env python3
"""Generate a programme report from the GitHub Project plus the repo itself.

    python3 scripts/programme-report.py --out report/

Writes:
    programme-report.html   the dashboard
    programme-items.csv     every board item, for a spreadsheet
    programme-kpis.json     the computed KPIs, machine-readable

WHY THIS EXISTS ALONGSIDE GITHUB'S OWN INSIGHTS PAGE
-----------------------------------------------------
Two separate limits, and only one of them is GitHub's fault.

1. THE PLAN. This project is PRIVATE and the org is on the FREE plan, which caps
   saved charts at TWO and puts historical (time-based) charts behind GitHub Team.
   Public projects get unlimited charts on any plan — but the items live in a
   private repo and their titles name unresolved compliance gaps, so making the
   project public to unlock charts would publish exactly the wrong thing.

2. THE KPIs THAT MATTER ARE NOT IN GITHUB. Whether October happens turns on how
   many sources have cleared licence review, how many challenges can actually
   build data, and whether the release path works. None of that is issue
   metadata — it lives in the catalogue YAML and the build. No chart configured
   on the Insights page can ever show it, at any price.

So this reads BOTH: the board for delivery state, the catalogues for programme
state, and puts them on one page.

A NOTE ON TIME SERIES, WHICH IS WHY THE BURN-UP LOOKS EMPTY
------------------------------------------------------------
Every item on the board was created on the same day the board was built, and
roughly half were closed the same day. There is ONE day of history. A burn-up
over one day is a vertical line, and so is every other time-based chart —
including any this script could draw.

That is not a charting problem and adding more time-based charts would not fix
it; it would produce five uninformative charts instead of one. This report
therefore draws POINT-IN-TIME structure, which is the only thing the data can
honestly support today. `--snapshot` appends the current KPIs to a history file,
so time series become possible once there is time to plot.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import date
from html import escape
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ORG = "Innovation-forum-Cambridgeshire"
PROJECT_NUMBER = 1

# Categorical slots 1-3, validated against both surfaces with the palette
# validator (light #fcfcfb, dark #1a1a19): all six checks pass. Assigned in fixed
# order Todo -> In Progress -> Done and never cycled or re-assigned per chart.
#
# The light aqua sits at 2.74:1 against the light surface, which is a documented
# WARN rather than a pass — the required relief is visible labels and a table
# view, and both are present. Do not "fix" it by darkening the aqua without
# re-running the validator; it currently sits inside the lightness band and
# moving it can break CVD separation against the orange.
SERIES = [
    ("Todo", "#2a78d6", "#3987e5"),
    ("In Progress", "#eb6834", "#d95926"),
    ("Done", "#1baf7a", "#199e70"),
]

PROJECT_QUERY = """
query($org: String!, $num: Int!) {
  organization(login: $org) {
    projectV2(number: $num) {
      title url
      items(first: 100) {
        nodes {
          fieldValues(first: 20) { nodes {
            ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2FieldCommon { name } } }
            ... on ProjectV2ItemFieldDateValue { date field { ... on ProjectV2FieldCommon { name } } }
          } }
          content {
            ... on Issue {
              number title state createdAt closedAt
              repository { name }
              subIssuesSummary { total completed }
              parent { number title }
            }
          }
        }
      }
    }
  }
}
"""


def gh_graphql(query: str, **variables) -> dict:
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        flag = "-F" if isinstance(v, int) else "-f"
        cmd += [flag, f"{k}={v}"]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"GitHub API call failed:\n{out.stderr.strip()}")
    return json.loads(out.stdout)


def load_board() -> tuple[dict, list[dict]]:
    data = gh_graphql(PROJECT_QUERY, org=ORG, num=PROJECT_NUMBER)
    proj = data["data"]["organization"]["projectV2"]
    rows = []
    for item in proj["items"]["nodes"]:
        content = item.get("content") or {}
        if not content.get("number"):
            continue
        fields = {}
        for fv in item["fieldValues"]["nodes"]:
            if not fv:
                continue
            name = (fv.get("field") or {}).get("name")
            if name:
                fields[name] = fv.get("name") or fv.get("date")
        sub = content.get("subIssuesSummary") or {}
        parent = content.get("parent") or {}
        rows.append({
            "number": content["number"],
            "title": content["title"],
            "state": content["state"],
            "status": fields.get("Status") or "(none)",
            "started": fields.get("Started") or "",
            "finished": fields.get("Finished") or "",
            "created": content["createdAt"][:10],
            "closed": (content.get("closedAt") or "")[:10],
            "repository": (content.get("repository") or {}).get("name", ""),
            "parent": parent.get("number") or "",
            "parent_title": parent.get("title") or "",
            "sub_total": sub.get("total", 0),
            "sub_done": sub.get("completed", 0),
        })
    return proj, sorted(rows, key=lambda r: r["number"])


def load_catalogue_kpis() -> dict:
    """Programme state, read from the catalogues rather than from issue metadata.

    This is the half GitHub structurally cannot report on.
    """
    try:
        import yaml
    except ImportError:
        sys.exit("PyYAML is required: pip install -r build/requirements.txt")

    challenges = []
    for path in sorted((REPO_ROOT / "catalogue").glob("*.yml")):
        cat = yaml.safe_load(path.read_text())
        sources = cat.get("sources") or []
        tables = cat.get("gold_tables") or []

        reviewed = [s for s in sources if s.get("licence_reviewed")]
        # "Restricted" means a deliberate decision not to mirror — not an
        # outstanding task. Separating the two matters: a burn-down that counts
        # restricted sources as work-in-hand never reaches zero and teaches people
        # to ignore it.
        restricted = [
            s for s in sources
            if not s.get("licence_reviewed") and not s.get("redistributable")
        ]
        pending = [
            s for s in sources
            if not s.get("licence_reviewed") and s.get("redistributable")
        ]
        mirrorable = {s["id"] for s in sources if s.get("licence_reviewed") and s.get("redistributable")}

        buildable = [
            t for t in tables
            if t.get("source") in mirrorable and not (
                t.get("blocked_by") and t["blocked_by"] not in mirrorable
            )
        ]
        with_columns = [t for t in tables if t.get("columns")]

        challenges.append({
            "slug": cat["challenge"],
            "title": cat["title"],
            "event_date": str(cat.get("event_date") or ""),
            "sources_total": len(sources),
            "sources_reviewed": len(reviewed),
            "sources_pending": len(pending),
            "sources_restricted": len(restricted),
            "tables_total": len(tables),
            "tables_buildable": len(buildable),
            "tables_with_columns": len(with_columns),
            "rows_declared": sum(t.get("approx_rows") or 0 for t in buildable),
        })
    return {"challenges": challenges}


def compute(proj: dict, rows: list[dict], cat: dict) -> dict:
    status_counts = {name: 0 for name, _, _ in SERIES}
    for r in rows:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    epics = sorted(
        [r for r in rows if r["sub_total"] > 0],
        key=lambda r: (-(r["sub_done"] / r["sub_total"]), -r["sub_total"]),
    )

    # Status split within each epic's children.
    by_parent: dict[int, dict] = {}
    for r in rows:
        if not r["parent"]:
            continue
        d = by_parent.setdefault(r["parent"], {n: 0 for n, _, _ in SERIES})
        d[r["status"]] = d.get(r["status"], 0) + 1

    ch = cat["challenges"]
    dates = sorted({r["created"] for r in rows} | {r["closed"] for r in rows if r["closed"]})

    return {
        "generated": date.today().isoformat(),
        "project": {"title": proj["title"], "url": proj["url"]},
        "totals": {
            "items": len(rows),
            "status": status_counts,
            "percent_done": round(status_counts.get("Done", 0) / len(rows) * 100, 1) if rows else 0,
            "epics": len(epics),
        },
        "history": {
            "distinct_days": len(dates),
            "first": dates[0] if dates else None,
            "last": dates[-1] if dates else None,
        },
        "epics": [
            {
                "number": e["number"],
                "title": e["title"],
                "done": e["sub_done"],
                "total": e["sub_total"],
                "percent": round(e["sub_done"] / e["sub_total"] * 100),
                "children": by_parent.get(e["number"], {}),
            }
            for e in epics
        ],
        "licence_review": {
            "reviewed": sum(c["sources_reviewed"] for c in ch),
            "pending": sum(c["sources_pending"] for c in ch),
            "restricted": sum(c["sources_restricted"] for c in ch),
            "total": sum(c["sources_total"] for c in ch),
        },
        "data_readiness": {
            "challenges_with_data": sum(1 for c in ch if c["tables_buildable"] > 0),
            "challenges_total": len(ch),
            "tables_buildable": sum(c["tables_buildable"] for c in ch),
            "tables_total": sum(c["tables_total"] for c in ch),
            "rows_declared": sum(c["rows_declared"] for c in ch),
        },
        "challenges": ch,
        "items": rows,
    }


# ── rendering ────────────────────────────────────────────────────────────────

def bar_row(label: str, value: int, total: int, colour: str, note: str = "") -> str:
    pct = (value / total * 100) if total else 0
    label = escape(label)
    return f"""      <div class="row">
        <div class="row-label" title="{label}">{label}</div>
        <div class="track"><div class="fill" style="width:{pct:.1f}%;background:{colour}"></div></div>
        <div class="row-value">{value}<span class="of">/{total}</span>{note}</div>
      </div>"""


def stacked_row(label: str, parts: list[tuple[str, int]], total: int) -> str:
    """Segments carry their own value label — the relief the contrast WARN requires."""
    label = escape(label)
    segs = []
    for (name, value), (_, light, _) in zip(parts, SERIES):
        name = escape(name)
        if not value:
            continue
        pct = value / total * 100 if total else 0
        # 2px surface gap between segments, per the mark spec.
        segs.append(
            f'<div class="seg" style="width:{pct:.2f}%;background:{light}" '
            f'title="{name}: {value}"><span class="seg-n">{value}</span></div>'
        )
    return f"""      <div class="row">
        <div class="row-label" title="{label}">{label}</div>
        <div class="track stacked">{''.join(segs)}</div>
        <div class="row-value">{total}</div>
      </div>"""


def render(k: dict) -> str:
    t = k["totals"]
    lr = k["licence_review"]
    dr = k["data_readiness"]

    epic_bars = "\n".join(
        bar_row(f"#{e['number']} {e['title']}", e["done"], e["total"], SERIES[2][1],
                f' <span class="pct">{e["percent"]}%</span>')
        for e in k["epics"]
    )

    epic_stacks = "\n".join(
        stacked_row(
            f"#{e['number']} {e['title']}",
            [(n, e["children"].get(n, 0)) for n, _, _ in SERIES],
            sum(e["children"].values()),
        )
        for e in k["epics"] if sum(e["children"].values())
    )

    lic_stacks = "\n".join(
        stacked_row(
            f"{c['slug']}",
            [("Reviewed", c["sources_reviewed"]),
             ("Pending review", c["sources_pending"]),
             ("Restricted by decision", c["sources_restricted"])],
            c["sources_total"],
        )
        for c in k["challenges"]
    )
    # Licence chart re-labels the three slots. Same fixed order, same colours —
    # colour follows position in this chart's own legend, which is stated below it.

    data_bars = "\n".join(
        bar_row(c["slug"], c["tables_buildable"], c["tables_total"], SERIES[0][1])
        for c in k["challenges"]
    )

    def item_row(r: dict) -> str:
        parent = f"#{r['parent']}" if r["parent"] else ""
        children = f"{r['sub_done']}/{r['sub_total']}" if r["sub_total"] else ""
        title = escape(r["title"])
        return (
            f"<tr><td>#{r['number']}</td><td>{title}</td><td>{escape(r['status'])}</td>"
            f"<td>{escape(r['repository'])}</td><td>{parent}</td><td>{children}</td></tr>"
        )

    rows_html = "\n".join(item_row(r) for r in k["items"])

    legend = "".join(
        f'<span class="key"><i style="background:{light}"></i>{name}</span>'
        for name, light, _ in SERIES
    )
    lic_legend = "".join(
        f'<span class="key"><i style="background:{light}"></i>{name}</span>'
        for name, (_, light, _) in zip(
            ["Reviewed", "Pending review", "Restricted by decision"], SERIES)
    )

    hist = k["history"]
    one_day = hist["distinct_days"] <= 1

    return f"""<title>Programme Report</title>
<style>
  .viz-root {{
    color-scheme: light;
    --surface-1: #fcfcfb; --surface-2: #f4f4f2;
    --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #6f6e6a;
    --rule: #e3e3df;
    --s1: {SERIES[0][1]}; --s2: {SERIES[1][1]}; --s3: {SERIES[2][1]};
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) .viz-root {{
      color-scheme: dark;
      --surface-1: #1a1a19; --surface-2: #232322;
      --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #9b9a92;
      --rule: #35342f;
      --s1: {SERIES[0][2]}; --s2: {SERIES[1][2]}; --s3: {SERIES[2][2]};
    }}
  }}
  :root[data-theme="dark"] .viz-root {{
    color-scheme: dark;
    --surface-1: #1a1a19; --surface-2: #232322;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #9b9a92;
    --rule: #35342f;
    --s1: {SERIES[0][2]}; --s2: {SERIES[1][2]}; --s3: {SERIES[2][2]};
  }}
  body {{ margin:0; background:var(--surface-1); }}
  .viz-root {{ background:var(--surface-1); color:var(--text-primary);
    font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
    padding:40px 28px 72px; max-width:1080px; margin:0 auto; }}
  h1 {{ font-size:30px; line-height:1.15; margin:0 0 6px; letter-spacing:-0.01em; }}
  .sub {{ color:var(--text-secondary); margin:0 0 34px; }}
  h2 {{ font-size:18px; margin:44px 0 4px; }}
  .lede {{ color:var(--text-secondary); margin:0 0 18px; max-width:70ch; font-size:14px; }}
  .tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin:26px 0 8px; }}
  .tile {{ background:var(--surface-2); border:1px solid var(--rule); border-radius:8px; padding:16px 18px; }}
  .tile .n {{ font-size:30px; font-weight:650; letter-spacing:-0.02em; line-height:1.05; }}
  .tile .l {{ font-size:12.5px; color:var(--text-secondary); margin-top:5px; }}
  .row {{ display:grid; grid-template-columns:minmax(140px,300px) 1fr 96px; gap:14px;
    align-items:center; padding:5px 0; }}
  .row-label {{ font-size:13px; color:var(--text-secondary); overflow:hidden;
    text-overflow:ellipsis; white-space:nowrap; }}
  .track {{ background:var(--surface-2); border-radius:4px; height:20px; overflow:hidden; }}
  .track.stacked {{ display:flex; gap:2px; }}
  .fill {{ height:100%; border-radius:4px; }}
  .seg {{ height:100%; border-radius:3px; display:flex; align-items:center;
    justify-content:center; min-width:3px; }}
  .seg-n {{ font-size:11px; font-weight:600; color:#fff; padding:0 4px;
    text-shadow:0 0 3px rgba(0,0,0,.45); }}
  .row-value {{ font-size:13px; font-variant-numeric:tabular-nums; color:var(--text-primary); }}
  .of {{ color:var(--text-muted); }}
  .pct {{ color:var(--text-muted); margin-left:5px; }}
  .legend {{ display:flex; gap:16px; flex-wrap:wrap; margin:12px 0 0; font-size:12.5px;
    color:var(--text-secondary); }}
  .key {{ display:inline-flex; align-items:center; gap:6px; }}
  .key i {{ width:11px; height:11px; border-radius:3px; display:inline-block; }}
  .note {{ background:var(--surface-2); border:1px solid var(--rule); border-left:3px solid var(--s2);
    border-radius:6px; padding:14px 18px; margin:22px 0; font-size:14px;
    color:var(--text-secondary); }}
  .note strong {{ color:var(--text-primary); }}
  table {{ border-collapse:collapse; width:100%; font-size:12.5px; margin-top:10px; }}
  th,td {{ text-align:left; padding:6px 10px; border-bottom:1px solid var(--rule); }}
  th {{ color:var(--text-secondary); font-weight:600; }}
  td:first-child {{ font-variant-numeric:tabular-nums; color:var(--text-muted); }}
  details {{ margin-top:14px; }}
  summary {{ cursor:pointer; color:var(--text-secondary); font-size:13.5px; }}
  .wrap {{ overflow-x:auto; }}
</style>

<div class="viz-root">
  <h1>{k['project']['title']} — programme report</h1>
  <p class="sub">Generated {k['generated']} · {t['items']} board items · {t['percent_done']}% complete</p>

  <div class="tiles">
    <div class="tile"><div class="n">{t['items']}</div><div class="l">board items</div></div>
    <div class="tile"><div class="n">{t['percent_done']}%</div><div class="l">complete</div></div>
    <div class="tile"><div class="n">{dr['challenges_with_data']}<span style="font-size:18px;color:var(--text-muted)">/{dr['challenges_total']}</span></div><div class="l">challenges with buildable data</div></div>
    <div class="tile"><div class="n">{lr['reviewed']}<span style="font-size:18px;color:var(--text-muted)">/{lr['total']}</span></div><div class="l">sources licence-reviewed</div></div>
    <div class="tile"><div class="n">{dr['rows_declared']:,}</div><div class="l">rows of challenge data</div></div>
  </div>

  {'''<div class="note"><strong>There is one day of history, which is why the burn-up looks empty.</strong>
  Every board item was created on the same day the board was built, and roughly half were closed the same day.
  A burn-up over one day is a vertical line — and so is every other time-based chart, including any this report
  could draw. Adding more time-based charts would produce several uninformative charts instead of one.
  Everything below is point-in-time structure, which is what the data can honestly support today.
  Run this with <code>--snapshot</code> after each working session and time series become possible.</div>''' if one_day else ''}

  <h2>Delivery by epic</h2>
  <p class="lede">Sub-issue completion. This is the view GitHub's Insights page cannot draw at all —
  it has no concept of a parent's child-completion ratio.</p>
{epic_bars}

  <h2>Status within each epic</h2>
  <p class="lede">Where the remaining work sits. An epic that is 0% done with everything in Todo is a
  different problem from one that is 0% done with everything in progress.</p>
{epic_stacks}
  <div class="legend">{legend}</div>

  <h2>Licence review (decision D4)</h2>
  <p class="lede">The gate on publishing any challenge data. <strong>Restricted</strong> is separated from
  <strong>pending</strong> deliberately: a restricted source is a decision not to mirror, not outstanding work.
  Counting the two together produces a burn-down that never reaches zero.</p>
{lic_stacks}
  <div class="legend">{lic_legend}</div>

  <h2>Data readiness by challenge</h2>
  <p class="lede">Gold tables that can actually be built today, against the total declared.
  A table is buildable when its source has cleared licence review and a generator exists.</p>
{data_bars}

  <h2>All items</h2>
  <details><summary>Show the full table ({t['items']} items) — the accessible view of every chart above</summary>
  <div class="wrap"><table>
    <thead><tr><th>#</th><th>Title</th><th>Status</th><th>Repo</th><th>Parent</th><th>Children</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table></div></details>
</div>
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="report")
    p.add_argument("--snapshot", action="store_true",
                   help="append today's KPIs to report/history.jsonl so time series become possible")
    args = p.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    proj, rows = load_board()
    kpis = compute(proj, rows, load_catalogue_kpis())

    (out / "programme-report.html").write_text(render(kpis), encoding="utf-8")

    with (out / "programme-items.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    slim = {k: v for k, v in kpis.items() if k != "items"}
    (out / "programme-kpis.json").write_text(json.dumps(slim, indent=2) + "\n")

    if args.snapshot:
        hist = out / "history.jsonl"
        with hist.open("a") as fh:
            fh.write(json.dumps({
                "date": kpis["generated"],
                "items": kpis["totals"]["items"],
                "status": kpis["totals"]["status"],
                "licence_reviewed": kpis["licence_review"]["reviewed"],
                "tables_buildable": kpis["data_readiness"]["tables_buildable"],
            }) + "\n")
        print(f"  snapshot appended to {hist}")

    print(f"Wrote {out}/programme-report.html, programme-items.csv, programme-kpis.json")
    print(f"  {kpis['totals']['items']} items · {kpis['totals']['percent_done']}% done · "
          f"{kpis['licence_review']['reviewed']}/{kpis['licence_review']['total']} sources reviewed · "
          f"{kpis['data_readiness']['tables_buildable']}/{kpis['data_readiness']['tables_total']} tables buildable")
    if kpis["history"]["distinct_days"] <= 1:
        print("  NOTE: one day of history — no time series is possible yet. Use --snapshot to start one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
