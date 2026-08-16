"""The branded report: a landing page, the diagrams, and the written assessment.

Great Expectations Data Docs is the detail view and it is good at that. It is not
a report an organiser can be handed: it opens on a list of validation runs, it
has no idea which failures are deliberate, and it invites the reader to edit the
expectation suite. So this module builds the thing in front of it — a single
branded page that says what was checked, what holds, what does not, and which of
the failures are supposed to be there — and links into Data Docs for the rows.

It also does two things to the generated Data Docs that cannot be done through
GX's own extension points:

    the Innovation Forum header, because GX's ChoiceLoader tries its own
    templates before the custom views directory, so a template override never
    wins (see brand.py)

    optionally, vendoring the CDN assets. Stock Data Docs pulls Bootstrap,
    jQuery, Vega and Font Awesome from six external origins at view time. For a
    signed assurance artefact that is two separate problems: it does not render
    offline or in five years' time, and it emits third-party requests from a
    report about data governance. `--vendor` fetches them once and rewrites the
    references; without network the report still builds and the limitation is
    recorded rather than hidden.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import brand, diagrams

# Every external origin the stock templates reference, and where each lands.
CDN_ASSETS = {
    "https://unpkg.com/bootstrap-table@1.19.1/dist/bootstrap-table.min.css": "bootstrap-table.min.css",
    "https://maxcdn.bootstrapcdn.com/bootstrap/4.3.1/css/bootstrap.min.css": "bootstrap.min.css",
    "https://unpkg.com/bootstrap-table@1.19.0/dist/extensions/filter-control/bootstrap-table-filter-control.css": "bt-filter-control.css",
    "https://cdnjs.cloudflare.com/ajax/libs/bootstrap-datepicker/1.9.0/css/bootstrap-datepicker.min.css": "datepicker.min.css",
    "https://cdn.jsdelivr.net/npm/@forevolve/bootstrap-dark@1.1.0/dist/css/bootstrap-prefers-dark.css": "bootstrap-dark.css",
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.6.0/css/all.min.css": "fontawesome.min.css",
    "https://code.jquery.com/jquery-3.4.1.min.js": "jquery.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/popper.js/1.12.9/umd/popper.min.js": "popper.min.js",
    "https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/js/bootstrap.min.js": "bootstrap.min.js",
    "https://unpkg.com/bootstrap-table@1.19.1/dist/bootstrap-table.min.js": "bootstrap-table.min.js",
    "https://unpkg.com/bootstrap-table@1.19.1/dist/extensions/filter-control/bootstrap-table-filter-control.min.js": "bt-filter-control.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/bootstrap-datepicker/1.9.0/js/bootstrap-datepicker.min.js": "datepicker.min.js",
    "https://cdn.jsdelivr.net/npm/vega@5": "vega.js",
    "https://cdn.jsdelivr.net/npm/vega-lite@4": "vega-lite.js",
    "https://cdn.jsdelivr.net/npm/vega-embed@6": "vega-embed.js",
}


def _e(s: Any) -> str:
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------------------
# Data Docs post-processing
# ---------------------------------------------------------------------------
def _header_html(depth: int) -> str:
    back = "../" * depth + "../../index.html" if depth else "index.html"
    return (
        '<div class="if-header">'
        f'<img src="{brand.logo_data_uri()}" alt="">'
        '<div class="if-titles">'
        '<span class="if-t1">Innovation Forum &times; R1X</span>'
        '<span class="if-t2">Hackathon challenge data &mdash; quality assurance</span>'
        "</div>"
        '<span class="if-spacer"></span>'
        f'<a class="if-back" href="{back}">&larr; Assurance summary</a>'
        "</div>"
    )


def vendor_assets(site_dir: Path, timeout: int = 20) -> tuple[int, list[str]]:
    """Fetch the CDN assets once into the site. Returns (fetched, failures)."""
    vendor = site_dir / "static" / "vendor"
    vendor.mkdir(parents=True, exist_ok=True)
    fetched, failures = 0, []
    for url, name in CDN_ASSETS.items():
        target = vendor / name
        if target.exists() and target.stat().st_size > 0:
            fetched += 1
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "innovation-forum-assurance"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                target.write_bytes(resp.read())
            fetched += 1
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            failures.append(f"{name}: {exc}")
    return fetched, failures


def postprocess_data_docs(site_dir: Path, vendored: bool) -> int:
    """Inject the brand header, and point assets at the vendored copies."""
    if not site_dir.exists():
        return 0
    touched = 0
    for page in site_dir.rglob("*.html"):
        depth = len(page.relative_to(site_dir).parts) - 1
        text = page.read_text(encoding="utf-8", errors="ignore")

        if 'class="if-header"' not in text:
            # After the opening <body ...>, so the header sits above GX's navbar
            # content but inside the document flow.
            text = re.sub(r"(<body[^>]*>)", r"\1" + _header_html(depth), text, count=1)

        if vendored:
            prefix = "../" * depth + "static/vendor/"
            for url, name in CDN_ASSETS.items():
                text = text.replace(url, prefix + name)

        page.write_text(text, encoding="utf-8")
        touched += 1
    return touched


# ---------------------------------------------------------------------------
# findings
# ---------------------------------------------------------------------------
def load_findings(repo_root: Path) -> dict[str, dict]:
    """Acknowledged findings, from quality/known-findings.yml.

    Read from a thin public file rather than from FINDINGS.md, because the full
    write-ups live in the private organisers repository and this repository is
    public. The gate only needs to know that a failure is already known; it does
    not need the bug report.
    """
    path = repo_root / "quality" / "known-findings.yml"
    if not path.exists():
        return {}
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {f["id"]: f for f in (doc.get("findings") or []) if f.get("id")}


def only_known_findings(repo_root: Path, result) -> tuple[list, list]:
    """Split the failures into those already recorded and those that are new."""
    known_specs = load_findings(repo_root)
    known, unknown = [], []
    all_failures = [(t.table.key, f) for t in result.tables for f in t.failures]
    all_failures += [("derived-metrics", f) for f in result.metric_failures]

    for key, f in all_failures:
        matched = None
        for fid, spec in known_specs.items():
            if spec.get("table") and spec["table"] not in key:
                continue
            needle = spec.get("match", "")
            if needle and needle.lower() in (f.get("description", "") or "").lower():
                matched = fid
                break
        (known if matched else unknown).append((key, f, matched))
    return known, unknown


# ---------------------------------------------------------------------------
# the landing page
# ---------------------------------------------------------------------------
def _status_chip(ok: bool, label_ok: str = "PASS", label_bad: str = "FAIL") -> str:
    colour = brand.PASS if ok else brand.FAIL
    bg = brand.ACCENT_100 if ok else "#fbeceb"
    label = label_ok if ok else label_bad
    return (
        f'<span class="chip" style="color:{colour};background:{bg};border-color:{colour}">'
        f"{label}</span>"
    )


def _affected_rows_table(f: dict) -> str:
    """The top ten affected rows — the part of the report people actually use."""
    rows = f.get("top_10_affected_rows") or []
    if not rows:
        vals = f.get("partial_unexpected_list") or []
        if not vals:
            return ""
        cells = "".join(f"<code>{_e(v)}</code>" for v in vals[:10])
        return (
            '<div class="affected"><div class="affected-h">First 10 unexpected values</div>'
            f'<div class="chips">{cells}</div></div>'
        )

    if isinstance(rows[0], dict):
        cols = list(rows[0].keys())
        head = "".join(f"<th>{_e(c)}</th>" for c in cols)
        body = "".join(
            "<tr>" + "".join(f"<td><code>{_e(r.get(c, ''))}</code></td>" for c in cols) + "</tr>"
            for r in rows[:10]
        )
    else:
        head = "<th>row</th>"
        body = "".join(f"<tr><td><code>{_e(r)}</code></td></tr>" for r in rows[:10])

    total = f.get("unexpected_count")
    caption = (
        f"Top 10 of {total:,} affected rows" if isinstance(total, int) else "Top 10 affected rows"
    )
    return (
        f'<div class="affected"><div class="affected-h">{caption}</div>'
        f'<table class="rows"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
    )


def _failure_block(key: str, f: dict, known_id: str | None) -> str:
    deliberate = f.get("dimension") == "deliberate defect"
    if known_id:
        badge = f'<span class="chip known">KNOWN {_e(known_id)}</span>'
    elif deliberate:
        badge = '<span class="chip design">DEFECT LOST OR DRIFTED</span>'
    else:
        badge = '<span class="chip bad">CONTRACT BREACH</span>'
    notes = f.get("notes") or ""
    obs = f.get("observed_value")
    return f"""
    <div class="finding">
      <div class="finding-h">{badge}<code class="tbl">{_e(key)}</code></div>
      <div class="finding-d">{_e(f.get('description') or f.get('type'))}</div>
      {f'<div class="obs">Observed: <code>{_e(obs)}</code></div>' if obs is not None else ''}
      {f'<div class="why">{_e(notes)}</div>' if notes else ''}
      {_affected_rows_table(f)}
    </div>"""


def write_report(repo_root: Path, out_dir: Path, result, vendor: bool = False) -> Path:
    """Build diagrams, the landing page and the written assessment."""
    from .model import load_spec

    spec = load_spec(repo_root)
    contract_cfg = yaml.safe_load(
        (repo_root / "quality" / "config" / "contract.yml").read_text(encoding="utf-8")
    ).get("challenges", {})

    diagrams_dir = out_dir / "diagrams"
    diagrams_dir.mkdir(parents=True, exist_ok=True)

    swim = diagrams.swimlanes(spec.architecture)
    (diagrams_dir / "pipeline-swimlanes.svg").write_text(swim, encoding="utf-8")

    erds: dict[str, str] = {}
    for ch in spec.challenges:
        svg = diagrams.erd(ch, contract_cfg.get(ch.slug, {}))
        erds[ch.slug] = svg
        (diagrams_dir / f"erd-{ch.slug}.svg").write_text(svg, encoding="utf-8")

    known, unknown = only_known_findings(repo_root, result)

    site_dir = out_dir / "gx" / "gx" / "uncommitted" / "data_docs" / "local_site"
    docs_rel = "gx/gx/uncommitted/data_docs/local_site/index.html"

    vendored = False
    if vendor:
        fetched, failures = vendor_assets(site_dir)
        vendored = fetched == len(CDN_ASSETS)
        if failures:
            # Not fatal. A report that builds with external references is worse
            # than one without them and far better than no report, and the
            # limitation is recorded rather than hidden.
            result.brand_drift.append(
                f"{len(failures)} external asset(s) could not be vendored; Data Docs "
                f"will load them from their CDN: {failures[0]}"
            )
    pages = postprocess_data_docs(site_dir, vendored)
    print(f"  branded {pages} Data Docs page(s)"
          f"{' and vendored their assets' if vendored else ''}", flush=True)

    page = _render_landing(repo_root, spec, result, erds, swim, known, unknown, docs_rel)
    index = out_dir / "index.html"
    index.write_text(page, encoding="utf-8")

    _write_assessment(repo_root, out_dir, spec, result, known, unknown)
    return index


def _render_landing(repo_root, spec, result, erds, swim, known, unknown, docs_rel) -> str:
    n_tables = len(result.tables)
    n_exp = sum(t.expectations for t in result.tables)
    n_rows = sum(t.row_count for t in result.tables)
    contract_ok = sum(1 for t in result.tables if t.contract_success)
    defects_ok = sum(1 for t in result.tables if t.defect_success)

    failures_html = []
    for key, f, fid in known + [(k, f, None) for k, f, _ in unknown]:
        failures_html.append(_failure_block(key, f, fid))
    if not failures_html:
        failures_html.append(
            '<p class="ok">Every contract expectation holds, and every deliberate defect '
            "is still present and inside its declared bounds.</p>"
        )

    challenge_cards = []
    for ch in spec.challenges:
        rows = [t for t in result.tables if t.table.challenge == ch.slug]
        ok = all(t.contract_success and t.defect_success for t in rows)
        blocked = [f"{n} (blocked by {r})" for c, n, r in result.blocked_tables if c == ch.slug]
        challenge_cards.append(f"""
        <article class="ch">
          <header>
            <h3>{_e(ch.title)}</h3>
            {_status_chip(ok)}
          </header>
          <p class="meta"><code>{_e(ch.slug)}</code> · {_e(ch.domain)} · {len(rows)} tables ·
             {sum(t.row_count for t in rows):,} rows</p>
          <p class="care">{_e(ch.handle_with_care)}</p>
          {"<p class='blocked'>Not validated: " + _e(", ".join(blocked)) + " — no bytes exist to check.</p>" if blocked else ""}
          <div class="erd">{erds.get(ch.slug, '')}</div>
        </article>""")

    drift_rows = "".join(
        f"<tr><td>{_e(d.level)}</td><td><code>{_e(d.table)}</code></td>"
        f"<td><code>{_e(d.column)}</code></td><td>{_e(d.what)}</td>"
        f"<td><code>{_e(d.was)}</code></td><td><code>{_e(d.now)}</code></td></tr>"
        for t in result.tables
        for d in t.drifts
    )

    recon_html = ""
    if result.reconciliation is not None and len(result.reconciliation):
        r = result.reconciliation
        cols = ["table", "csv_present", "has_bom", "columns_match", "rows_match",
                "no_ambiguous_dates", "values_match", "naive_read_types_match",
                "mismatched_cells", "notes"]
        head = "".join(f"<th>{_e(c.replace('_', ' '))}</th>" for c in cols)
        body = ""
        for _, row in r.iterrows():
            tds = []
            for c in cols:
                v = row[c]
                if isinstance(v, bool):
                    tds.append(
                        f'<td class="{"good" if v else "bad"}">{"yes" if v else "no"}</td>'
                    )
                else:
                    tds.append(f"<td><code>{_e(v)}</code></td>")
            body += "<tr>" + "".join(tds) + "</tr>"
        recon_html = f'<table class="grid"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'

    brand_warn = ""
    if result.brand_drift:
        items = "".join(f"<li>{_e(d)}</li>" for d in result.brand_drift)
        brand_warn = (
            '<div class="warn"><strong>Brand drift.</strong> This report\'s tokens no longer '
            f"match the website's global.css:<ul>{items}</ul></div>"
        )

    metric_rows = "".join(
        f"<tr><td>{_e(m.table)}</td><td>{_e(m.title)}</td>"
        f"<td><code>{m.value:.4g}</code></td>"
        f"<td><code>{'' if m.min_value is None else format(m.min_value, '.4g')}"
        f" – {'' if m.max_value is None else format(m.max_value, '.4g')}</code></td>"
        f"<td>{_status_chip(m.ok, 'IN BOUNDS', 'OUT OF BOUNDS')}</td>"
        f"<td class='unit'>{_e(m.unit)}</td></tr>"
        for m in result.metrics
    )

    generated = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")

    return f"""<!doctype html>
<html lang="en-GB"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Challenge data assurance — Innovation Forum × R1X</title>
<style>
{brand.font_face_css()}
:root {{
  --bg:{brand.BG}; --surface:{brand.SURFACE}; --text:{brand.TEXT};
  --accent:{brand.ACCENT}; --accent-600:{brand.ACCENT_600}; --accent-700:{brand.ACCENT_700};
  --accent-100:{brand.ACCENT_100}; --aqua:{brand.AQUA}; --aqua-100:{brand.AQUA_100};
  --aqua-700:{brand.AQUA_700}; --ink:{brand.INK}; --lime:{brand.LIME};
  --pass:{brand.PASS}; --fail:{brand.FAIL}; --warn:{brand.WARN};
  --divider:rgba(29,31,32,.16); --muted:{brand.NEUTRAL_700};
}}
*,*::before,*::after{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);
  font-family:{brand.FONT_BODY};font-size:15px;line-height:1.6}}
h1,h2,h3,h4{{font-family:{brand.FONT_HEADING};font-weight:600;letter-spacing:.01em;margin:0}}
code{{font-family:{brand.FONT_MONO};font-size:.86em}}
a{{color:var(--accent-700)}}
.wrap{{max-width:1280px;margin:0 auto;padding:0 40px}}
header.top{{background:var(--ink);color:#fff;border-bottom:3px solid var(--accent);padding:26px 0}}
header.top .wrap{{display:flex;align-items:center;gap:18px}}
header.top img{{width:52px;height:52px;object-fit:contain}}
header.top h1{{font-size:30px;line-height:1.1;text-transform:uppercase;letter-spacing:.02em}}
header.top p{{margin:4px 0 0;font-size:13.5px;opacity:.82}}
.verdict{{margin-left:auto;text-align:right}}
.verdict .big{{font-family:{brand.FONT_HEADING};font-size:26px;font-weight:600;
  padding:6px 16px;display:inline-block;border:2px solid}}
section{{padding:34px 0;border-bottom:1px solid var(--divider)}}
section h2{{font-size:23px;text-transform:uppercase;letter-spacing:.03em;
  border-left:4px solid var(--accent);padding-left:12px;margin-bottom:6px}}
section .lede{{color:var(--muted);margin:0 0 20px;padding-left:16px;max-width:78ch}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px}}
.stat{{background:#fff;border:1px solid var(--divider);border-left:4px solid var(--accent);padding:14px 16px}}
.stat .v{{font-family:{brand.FONT_HEADING};font-size:29px;font-weight:600;line-height:1}}
.stat .l{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin-top:4px}}
.chip{{font-family:{brand.FONT_HEADING};font-weight:600;font-size:12px;letter-spacing:.05em;
  padding:3px 9px;border:1px solid;text-transform:uppercase;white-space:nowrap}}
.chip.bad{{color:var(--fail);background:#fbeceb;border-color:var(--fail)}}
.chip.design{{color:var(--aqua-700);background:var(--aqua-100);border-color:var(--aqua-700)}}
.chip.known{{color:var(--warn);background:#fdf4e7;border-color:var(--warn)}}
.ch{{background:#fff;border:1px solid var(--divider);padding:18px 20px;margin-bottom:18px}}
.ch header{{display:flex;align-items:center;gap:14px}}
.ch h3{{font-size:19px}}
.ch .meta{{color:var(--muted);font-size:12.5px;margin:4px 0 8px}}
.ch .care{{background:var(--accent-100);border-left:3px solid var(--accent-600);
  padding:9px 12px;font-size:13.5px;margin:0 0 14px}}
.ch .blocked{{color:var(--warn);font-size:13px;margin:0 0 12px}}
.erd{{overflow-x:auto;border:1px solid var(--divider);background:var(--bg)}}
.erd svg{{display:block;min-width:640px}}
.finding{{background:#fff;border:1px solid var(--divider);border-left:4px solid var(--fail);
  padding:14px 16px;margin-bottom:14px}}
.finding-h{{display:flex;align-items:center;gap:10px;margin-bottom:6px;flex-wrap:wrap}}
.finding-d{{font-weight:600}}
.finding .obs{{font-size:13px;color:var(--muted);margin-top:3px}}
.finding .why{{font-size:13.5px;color:var(--muted);margin-top:7px;white-space:pre-wrap;max-width:86ch}}
.tbl{{color:var(--muted);font-size:12.5px}}
.affected{{margin-top:12px}}
.affected-h{{font-family:{brand.FONT_HEADING};font-weight:600;font-size:12.5px;
  text-transform:uppercase;letter-spacing:.04em;color:var(--aqua-700);margin-bottom:5px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
table.rows,table.grid{{background:#fff}}
th,td{{border:1px solid var(--divider);padding:5px 9px;text-align:left;vertical-align:top}}
th{{background:var(--surface);font-family:{brand.FONT_HEADING};font-weight:600;
  text-transform:uppercase;font-size:11.5px;letter-spacing:.03em}}
td.good{{color:var(--pass)}} td.bad{{color:var(--fail);font-weight:600}}
td.unit{{color:var(--muted);font-size:12px}}
.scroll{{overflow-x:auto}}
.ok{{background:var(--accent-100);border-left:4px solid var(--accent-600);padding:12px 16px}}
.warn{{background:#fdf4e7;border-left:4px solid var(--warn);padding:12px 16px;margin-bottom:16px}}
.cta{{display:inline-block;background:var(--accent-600);color:#fff;padding:10px 20px;
  font-family:{brand.FONT_HEADING};font-weight:600;text-transform:uppercase;
  letter-spacing:.04em;text-decoration:none;margin-right:10px}}
.cta.sec{{background:transparent;color:var(--text);border:1px solid var(--divider)}}
footer{{padding:26px 0 44px;color:var(--muted);font-size:12.5px}}
.chips code{{background:var(--aqua-100);border:1px solid {brand.AQUA_200};padding:1px 6px;margin:0 4px 4px 0;display:inline-block}}
@media(max-width:820px){{.wrap{{padding:0 18px}}header.top .wrap{{flex-wrap:wrap}}.verdict{{margin-left:0}}}}
</style></head><body>

<header class="top"><div class="wrap">
  <img src="{brand.logo_data_uri()}" alt="Innovation Forum">
  <div>
    <h1>Challenge data assurance</h1>
    <p>Innovation Forum &times; R1X &middot; five hackathon corpora &middot; generated {generated}</p>
  </div>
  <div class="verdict">
    <span class="big" style="color:{'#fff' if result.success else brand.FAIL};
      background:{brand.ACCENT_600 if result.success else '#fbeceb'};
      border-color:{brand.ACCENT_600 if result.success else brand.FAIL}">
      {'ASSURED' if result.success else 'FINDINGS OPEN'}</span>
  </div>
</div></header>

<div class="wrap">

<section>
  <h2>At a glance</h2>
  <p class="lede">Two suites run against every table. The <strong>contract</strong> suite asserts
  what must be true; the <strong>defect profile</strong> asserts that the deliberate flaws are
  still present and still inside the range where they teach something. Both must pass.
  A corpus that validates clean is a corpus that has lost its point.</p>
  {brand_warn}
  <div class="stats">
    <div class="stat"><div class="v">{n_tables}</div><div class="l">tables validated</div></div>
    <div class="stat"><div class="v">{n_rows:,}</div><div class="l">rows read</div></div>
    <div class="stat"><div class="v">{n_exp}</div><div class="l">expectations run</div></div>
    <div class="stat"><div class="v">{contract_ok}/{n_tables}</div><div class="l">contract clean</div></div>
    <div class="stat"><div class="v">{defects_ok}/{n_tables}</div><div class="l">defects intact</div></div>
    <div class="stat"><div class="v">{len(unknown)}</div><div class="l">new findings</div></div>
  </div>
  <p style="margin-top:20px">
    <a class="cta" href="{docs_rel}">Open Great Expectations Data Docs</a>
    <a class="cta sec" href="ASSESSMENT.md">Written assessment</a>
    <a class="cta sec" href="diagrams/pipeline-swimlanes.svg">Pipeline diagram</a>
  </p>
</section>

<section>
  <h2>Findings</h2>
  <p class="lede">A finding is a contract expectation that failed, or a deliberate defect that has
  drifted out of bounds or been tidied away. Each carries the top ten affected rows, addressed by
  business key rather than row number so they can still be found after the corpus is rebuilt.</p>
  {''.join(failures_html)}
</section>

<section>
  <h2>The pipeline</h2>
  <p class="lede">Where the data comes from, what happens to it, and who owns each step. The
  handoffs are the interesting part: every arrow crossing a lane is a place a guarantee can be
  lost without anything raising an error.</p>
  <div class="erd">{swim}</div>
</section>

<section>
  <h2>The five challenges</h2>
  <p class="lede">One entity-relationship diagram per challenge, in crow's-foot notation. Dashed
  lines with struck ends are <em>hazards</em> — joins a participant will reasonably attempt that
  the data does not support. They are drawn rather than omitted, because a missing line reads as
  an oversight instead of a decision.</p>
  {''.join(challenge_cards)}
</section>

<section>
  <h2>Deliberate defects, measured</h2>
  <p class="lede">The flaws that make these corpora worth working on, each reduced to a number and
  bounded on both sides. Too little and the lesson does not bite; too much and there is nothing
  left to model.</p>
  <div class="scroll"><table class="grid"><thead><tr>
    <th>Table</th><th>Defect</th><th>Measured</th><th>Bounds</th><th>Status</th><th>Unit</th>
  </tr></thead><tbody>{metric_rows or '<tr><td colspan="6">none computed</td></tr>'}</tbody></table></div>
</section>

<section>
  <h2>CSV twin reconciliation</h2>
  <p class="lede">The contract suite validates the parquet. Participants using Excel, Power BI or R
  read the CSV. Every failure mode here is silent — the file still opens, it is just wrong — so the
  two are compared cell by cell, and the CSV is re-read the way a starter notebook would read it.</p>
  <div class="scroll">{recon_html or '<p>No CSV twins were checked.</p>'}</div>
</section>

<section>
  <h2>Profile drift</h2>
  <p class="lede">Measured against the committed baseline in <code>quality/baseline/</code>. Only
  <strong>structural</strong> drift fails the build — a column added, removed, retyped, or a
  category appearing in a closed domain. Material and ordinary drift are put in front of a human,
  because they are usually a reseed and occasionally the whole story.</p>
  <div class="scroll">
  {f'<table class="grid"><thead><tr><th>Level</th><th>Table</th><th>Column</th><th>What</th><th>Was</th><th>Now</th></tr></thead><tbody>{drift_rows}</tbody></table>' if drift_rows else '<p class="ok">No drift against the baseline.</p>'}
  </div>
</section>

<footer><div>
  Generated by <code>quality/run_assurance.py</code> using Great Expectations.
  Data root: <code>{_e(result.data_root)}</code>. Run started {_e(result.started)}.
  <br>This report is organiser-facing. It describes deliberate defects in the challenge
  corpora and should not be circulated to participants before their event.
</div></footer>
</div></body></html>"""


# ---------------------------------------------------------------------------
# the written assessment
# ---------------------------------------------------------------------------
def _write_assessment(repo_root: Path, out_dir: Path, spec, result, known, unknown) -> Path:
    today = datetime.now(timezone.utc).strftime("%d %B %Y")
    n_rows = sum(t.row_count for t in result.tables)
    n_exp = sum(t.expectations for t in result.tables)

    lines: list[str] = []
    w = lines.append

    w(f"# Challenge data — quality assessment\n")
    w(f"**Innovation Forum × R1X** · generated {today} · "
      f"`quality/run_assurance.py` · data root `{result.data_root}`\n")
    w(f"**Verdict: {'ASSURED' if result.success else 'FINDINGS OPEN'}** — "
      f"{len(result.tables)} tables, {n_rows:,} rows, {n_exp} expectations, "
      f"{len(unknown)} new finding(s).\n")

    w("## What was assessed, and on what basis\n")
    w("Five challenge corpora, thirteen gold tables. Every table is validated twice:\n")
    w("- **Contract** — schema and column order, declared types, completeness, key uniqueness,\n"
      "  closed value domains, numeric ranges the catalogue states in prose, cross-column\n"
      "  arithmetic, referential integrity across tables, and two safety rules on the c04\n"
      "  support directory. A failure here is a defect.\n")
    w("- **Defect profile** — the deliberate flaws, each reduced to a number and bounded on both\n"
      "  sides. A failure here means a flaw has been tidied away or has drifted out of the range\n"
      "  where it teaches anything. That is also a defect, in the opposite direction.\n")
    w("\nThe split exists because this data is *designed to be imperfect*. c01's catalogue says so\n"
      "outright: \"Sensor data is often miscalibrated, duplicated or missing. Strong entries surface\n"
      "data quality rather than hiding it behind a clean-looking chart.\" A single suite over this\n"
      "corpus could only produce a misleading answer — all-green would hide the flaws, all-red\n"
      "would drown the real ones. Two suites let the report state the true position.\n")

    w("\n## Scope\n")
    w("| Challenge | Tables | Rows | Contract | Defects intact |")
    w("|---|---:|---:|:--:|:--:|")
    for ch in spec.challenges:
        rows = [t for t in result.tables if t.table.challenge == ch.slug]
        if not rows:
            continue
        w(f"| {ch.title} | {len(rows)} | {sum(t.row_count for t in rows):,} | "
          f"{'pass' if all(t.contract_success for t in rows) else 'FAIL'} | "
          f"{'pass' if all(t.defect_success for t in rows) else 'FAIL'} |")

    if result.blocked_tables:
        w("\n### Declared but not validated\n")
        w("These tables appear in the catalogue and have no bytes, so there is nothing to check.\n")
        for c, n, r in result.blocked_tables:
            w(f"- `{c}` / `{n}` — blocked by `{r}` (licence gate not cleared)")
        w("\nThis is the licence gate working as designed: the build refuses to mirror any source\n"
          "that has not cleared both `redistributable` and `licence_reviewed`.\n")

    w("\n## Findings\n")
    if not known and not unknown:
        w("None. The contract holds on every table, and every deliberate defect is present and\n"
          "within bounds.\n")
    else:
        if unknown:
            w("### New\n")
            for key, f, _ in unknown:
                w(f"**{key}** — {f.get('description')}\n")
                if f.get("observed_value") is not None:
                    w(f"- Observed: `{f['observed_value']}`")
                if f.get("unexpected_count"):
                    w(f"- Affected rows: {f['unexpected_count']:,}")
                rows = f.get("top_10_affected_rows") or []
                if rows:
                    w(f"- Top 10 affected: `{json.dumps(rows[:10], default=str)[:400]}`")
                if f.get("notes"):
                    w(f"- Why it matters: {f['notes'].splitlines()[0]}")
                w("")
        if known:
            w("### Previously recorded\n")
            for key, f, fid in known:
                w(f"- **{fid}** · `{key}` — {f.get('description')}")
            w("\nSee `quality/FINDINGS.md` for triage and decisions.\n")

    w("\n## Hazards left in place deliberately\n")
    w("A hazard is a join or an interpretation a participant will reasonably attempt that the data\n"
      "does not support. These are not defects and are not fixed — several of them *are* the\n"
      "challenge. They are recorded so nobody mistakes one for a build failure.\n")
    for ch in spec.challenges:
        if not ch.hazards:
            continue
        w(f"\n### {ch.title}\n")
        for h in ch.hazards:
            flag = " **(high)**" if h.severity == "high" else ""
            w(f"- **{h.name.replace('_', ' ')}**{flag} — {' '.join(h.note.split())}")

    w("\n## Limitations\n")
    w("- **The corpus is generated.** These results describe the build at the data root above,\n"
      "  not an immutable artefact. A release must be validated after it is built, not before.\n")
    w("- **Population-level defect metrics cannot point at rows.** \"21% of NDVI is missing\" has no\n"
      "  ten rows to show. Row-level contract failures do carry their top ten.\n")
    w("- **Profile drift is advisory except where structural.** A quantile moving inside tolerance\n"
      "  is reported and does not fail the build; judgement is left with the reader.\n")
    w("- **The two blocked tables are unassessed**, and will stay so until their licence gates clear.\n")
    w("- **Great Expectations Data Docs loads assets from six external origins** unless the report\n"
      "  is built with `--vendor`. Vendored, the report renders offline and emits no third-party\n"
      "  requests, which is the right posture for an assurance artefact about data governance.\n")

    w("\n## Statement\n")
    if result.success:
        w("On the corpus at the data root above, the declared contract holds on every validated\n"
          "table, every deliberate defect is present and within its declared bounds, every CSV twin\n"
          "reconciles to its parquet, and no structural drift was found against the committed\n"
          "baseline. The corpora are fit to publish for their events.\n")
    else:
        w("On the corpus at the data root above, the checks below did not pass. Each is listed under\n"
          "Findings with the rows that caused it. The corpora should not be published for their\n"
          "events until each is either fixed or explicitly accepted and recorded in\n"
          "`quality/FINDINGS.md`.\n")

    w("\n| | |")
    w("|---|---|")
    w("| Prepared by | `quality/run_assurance.py` (automated) |")
    w("| Reviewed by | _______________________ |")
    w("| Date | _______________________ |")
    w("| Accepted for publication | ☐ yes  ☐ no |")
    w("")

    path = out_dir / "ASSESSMENT.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
def print_summary(result, out_dir: Path) -> None:
    ok, bad = "  ok  ", " FAIL "
    print("\n" + "=" * 74)
    print("  CHALLENGE DATA ASSURANCE")
    print("=" * 74)
    for t in result.tables:
        c = ok if t.contract_success else bad
        d = ok if t.defect_success else bad
        print(f"  contract[{c}] defects[{d}]  {t.table.key:44s} {t.row_count:>10,} rows")
    print("-" * 74)
    print(f"  expectations run     : {sum(t.expectations for t in result.tables)}")
    print(f"  derived metrics      : {len(result.metrics)} "
          f"({sum(1 for m in result.metrics if not m.ok)} out of bounds)")
    print(f"  csv twin reconcile   : {'ok' if result.reconciliation_success else 'FAIL'}")
    print(f"  structural drift     : {len(result.structural_drift)}")
    print(f"  material drift       : {len(result.material_drift)}")
    if result.brand_drift:
        print(f"  brand drift          : {len(result.brand_drift)} — report no longer matches the site")
    print(f"\n  report               : {out_dir / 'index.html'}")
    print(f"  assessment           : {out_dir / 'ASSESSMENT.md'}")
    if result.docs_url:
        print(f"  data docs            : {result.docs_url}")
    print("=" * 74)
    print(f"  {'ASSURED' if result.success else 'FINDINGS OPEN'}")
    print("=" * 74)
