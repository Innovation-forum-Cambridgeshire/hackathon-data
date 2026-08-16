"""Innovation Forum brand tokens, and the Data Docs stylesheet built from them.

The tokens are copied verbatim from the website's src/styles/global.css so the
assurance report and the public site cannot drift apart by accident. If a token
changes there, change it here — there is a check for this in verify_brand().

THE ONE THING THAT IS NOT A STRAIGHT COPY is the accent used behind white text.
global.css carries the reason in a comment and it is a real accessibility
constraint rather than a preference:

    white on #009540 measures 3.91:1, which fails WCAG AA for body text

so text-bearing surfaces use --color-accent-600 (#00863a). The brand green is
still used, but only for rules, motifs and large display type where the contrast
requirement is 3:1. The same rule is applied here.

HOW THE STYLING REACHES DATA DOCS
---------------------------------
Great Expectations renders every page through Jinja templates that contain:

    <style>{% include 'data_docs_custom_styles.css' ignore missing %}</style>

and SiteBuilder adds <plugins>/custom_data_docs/styles to the template search
path (great_expectations/render/renderer/site_builder.py, and view.py builds the
ChoiceLoader). Dropping a file at that path is therefore the supported extension
point, and the one GX scaffolds for you on `get_context(mode="file")`. We write
that file rather than post-processing the CSS, so an upgrade of GX keeps working.

Note the loader order: ChoiceLoader tries the packaged templates FIRST, so a file
in custom_data_docs/views cannot override a template GX ships. That is why the
logo and the external-asset rewrite happen in a post-processing pass (docs.py)
and not as a template override.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# --- neutrals / ground -------------------------------------------------------
BG = "#f2f2f3"
SURFACE = "#e9e9ea"
TEXT = "#1d1f20"
NEUTRAL_200 = "#e7e7ea"
NEUTRAL_300 = "#d4d4d7"
NEUTRAL_400 = "#b7b7ba"
NEUTRAL_500 = "#98989b"
NEUTRAL_600 = "#7a7a7d"
NEUTRAL_700 = "#5d5d60"
NEUTRAL_900 = "#2b2b2d"

# --- accent: Innovation Forum green ------------------------------------------
ACCENT = "#009540"  # brand green: rules, motifs, large display type only
ACCENT_100 = "#e9f7ee"
ACCENT_200 = "#cbebd8"
ACCENT_300 = "#97d9b4"
ACCENT_400 = "#4fbe83"
ACCENT_600 = "#00863a"  # the one to put white text on
ACCENT_700 = "#00662b"
ACCENT_800 = "#0a4a25"
ACCENT_900 = "#06251b"

# --- accent-2: aqua ----------------------------------------------------------
AQUA = "#8fd6d8"
AQUA_100 = "#eaf7f7"
AQUA_200 = "#d3efef"
AQUA_600 = "#3e9ea0"
AQUA_700 = "#176d6d"
AQUA_800 = "#0f4e4e"

# --- graphic-only extras -----------------------------------------------------
LIME = "#eceb85"
INK = "#04180f"

# --- status ------------------------------------------------------------------
# Green for pass is the brand accent, which is a happy accident rather than a
# design decision. Amber and red are NOT in the brand palette because the brand
# has no failure colour; these are chosen to hit 4.5:1 on the light ground and to
# stay distinguishable from the greens for the most common colour-vision
# deficiencies. Status is never signalled by colour alone — every status chip in
# the report carries a word as well, and the ERD uses shape as well as fill.
PASS = ACCENT_600
WARN = "#a8630a"
FAIL = "#a4211b"
BY_DESIGN = AQUA_700

FONT_HEADING = '"Barlow Condensed", "Barlow", system-ui, -apple-system, sans-serif'
FONT_BODY = '"Barlow", system-ui, -apple-system, "Segoe UI", sans-serif'
FONT_MONO = '"IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace'

# Vendored from @fontsource in the website repo, so the report renders on brand
# with no request leaving the machine. See quality/README.md.
_FONT_FILES = {
    "Barlow": [("barlow-latin-400-normal.woff2", 400), ("barlow-latin-600-normal.woff2", 600)],
    "Barlow Condensed": [("barlow-condensed-latin-600-normal.woff2", 600)],
    "IBM Plex Mono": [("ibm-plex-mono-latin-400-normal.woff2", 400)],
}


@lru_cache(maxsize=None)
def _data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


@lru_cache(maxsize=None)
def logo_data_uri() -> str:
    """The Innovation Forum mark, inlined.

    Inlined rather than copied next to the HTML because Data Docs pages sit at
    five different directory depths and a relative src would have to be computed
    per page. At 6.5 KB the duplication is cheaper than the bug.
    """
    return _data_uri(ASSETS / "Innovation-Forum-logo.jpeg", "image/jpeg")


@lru_cache(maxsize=None)
def font_face_css() -> str:
    """@font-face rules with the woff2 payloads inlined.

    ~80 KB of base64 repeated on every page. That is a real cost and it was
    weighed: the alternative is relative URLs, which break because Data Docs
    nests validation pages five levels deep, or absolute URLs, which break on a
    GitHub Pages project site served from a subpath. An 80 KB constant on a
    static internal report is the cheapest of the three, and it keeps the
    guarantee that the report renders identically offline and in five years.
    """
    out = []
    for family, files in _FONT_FILES.items():
        for filename, weight in files:
            path = ASSETS / "fonts" / filename
            if not path.exists():  # degrade to the system stack rather than fail
                continue
            uri = _data_uri(path, "font/woff2")
            out.append(
                f"@font-face{{font-family:'{family}';font-style:normal;"
                f"font-weight:{weight};font-display:swap;src:url({uri}) format('woff2');}}"
            )
    return "\n".join(out)


def data_docs_css() -> str:
    """The stylesheet GX inlines into every Data Docs page.

    Written against the markup GX actually emits (Bootstrap 4 plus its own
    ge-* classes), so the selectors are deliberately specific and a few carry
    !important where Bootstrap's own utilities would otherwise win.
    """
    return f"""
/* ==========================================================================
   Innovation Forum x R1X — Great Expectations Data Docs theme.
   Generated by quality/assurance/brand.py. Do not edit this file by hand;
   edit brand.py and re-run the assurance build.
   ========================================================================== */

{font_face_css()}

:root {{
  --if-bg: {BG};
  --if-surface: {SURFACE};
  --if-text: {TEXT};
  --if-accent: {ACCENT};
  --if-accent-600: {ACCENT_600};
  --if-accent-700: {ACCENT_700};
  --if-accent-100: {ACCENT_100};
  --if-accent-200: {ACCENT_200};
  --if-aqua: {AQUA};
  --if-aqua-100: {AQUA_100};
  --if-aqua-700: {AQUA_700};
  --if-lime: {LIME};
  --if-ink: {INK};
  --if-pass: {PASS};
  --if-fail: {FAIL};
  --if-warn: {WARN};
  --if-divider: rgba(29, 31, 32, 0.16);
}}

/* Square corners are the design system's signature. GX and Bootstrap round
   almost everything, so this is a blanket reset rather than a list. */
body, .card, .btn, .alert, .badge, .table, .modal-content, .nav-link,
.list-group-item, input, select, textarea, .popover, .tooltip-inner,
.breadcrumb, .progress, .dropdown-menu, .form-control, pre, code {{
  border-radius: 0 !important;
}}

body {{
  background: var(--if-bg) !important;
  color: var(--if-text) !important;
  font-family: {FONT_BODY} !important;
  font-size: 15px;
  line-height: 1.55;
}}

h1, h2, h3, h4, h5, h6, .ge-breadcrumbs, #ge-title {{
  font-family: {FONT_HEADING} !important;
  font-weight: 600 !important;
  letter-spacing: 0.01em;
  color: var(--if-text) !important;
}}

code, pre, .ge-expectation-string, kbd, samp {{
  font-family: {FONT_MONO} !important;
  font-size: 0.87em;
}}

a {{ color: var(--if-accent-700); text-underline-offset: 3px; }}
a:hover {{ color: {ACCENT_800}; }}
::selection {{ background: var(--if-accent-200); }}
:focus-visible {{ outline: 2px solid var(--if-accent); outline-offset: 2px; }}

/* --- the top bar ---------------------------------------------------------
   GX ships a dark navbar. Recoloured to the ink used behind the site's own
   footer, with the brand green as the underline rule. */
.navbar, nav.navbar, .navbar-dark, .bg-dark {{
  background: var(--if-ink) !important;
  border-bottom: 3px solid var(--if-accent) !important;
  padding: 10px 18px !important;
}}
.navbar a, .navbar .navbar-brand, .navbar-dark .navbar-nav .nav-link {{
  color: #ffffff !important;
  font-family: {FONT_HEADING} !important;
  font-weight: 600;
  letter-spacing: 0.02em;
}}
/* GX's own logo in the navbar. Ours replaces it in the injected header, and
   leaving both would read as a co-brand that does not exist. */
.navbar img[src*="logo"], .navbar .ge-logo, img[src*="short-logo"] {{ display: none !important; }}

/* --- the header we inject (see docs.py) ---------------------------------- */
.if-header {{
  display: flex; align-items: center; gap: 14px;
  background: var(--if-surface);
  border-bottom: 1px solid var(--if-divider);
  border-left: 4px solid var(--if-accent);
  padding: 12px 18px;
  margin: 0 0 18px 0;
}}
.if-header img {{ width: 34px; height: 34px; object-fit: contain; flex: none; }}
.if-header .if-titles {{ display: flex; flex-direction: column; min-width: 0; }}
.if-header .if-t1 {{
  font-family: {FONT_HEADING}; font-weight: 600; font-size: 17px;
  line-height: 1.15; letter-spacing: 0.02em; text-transform: uppercase;
}}
.if-header .if-t2 {{ font-size: 12.5px; color: {NEUTRAL_700}; }}
.if-header .if-spacer {{ flex: 1 1 auto; }}
.if-header .if-back {{
  font-family: {FONT_HEADING}; font-weight: 600; font-size: 13px;
  letter-spacing: 0.03em; text-transform: uppercase;
  border: 1px solid var(--if-divider); padding: 6px 12px;
  color: var(--if-text); text-decoration: none; white-space: nowrap;
}}
.if-header .if-back:hover {{ background: var(--if-accent-100); border-color: var(--if-accent); }}

/* --- pass / fail ---------------------------------------------------------
   GX uses Bootstrap's success/danger throughout. Both are remapped, and the
   left border is added so the state survives a greyscale print and does not
   depend on hue alone. */
.alert-success, .bg-success, .badge-success, .ge-success, td.success, tr.success {{
  background-color: var(--if-accent-100) !important;
  border-color: var(--if-accent-600) !important;
  color: {ACCENT_900} !important;
}}
.alert-danger, .bg-danger, .badge-danger, .ge-failure, td.danger, tr.danger {{
  background-color: #fbeceb !important;
  border-color: var(--if-fail) !important;
  color: #6d1613 !important;
}}
.alert-success, .alert-danger {{ border-left-width: 4px !important; }}
.badge-success {{ background-color: var(--if-accent-600) !important; color: #fff !important; }}
.badge-danger  {{ background-color: var(--if-fail) !important; color: #fff !important; }}
.text-success {{ color: var(--if-accent-700) !important; }}
.text-danger  {{ color: var(--if-fail) !important; }}

/* --- cards and tables ---------------------------------------------------- */
.card {{
  background: #ffffff;
  border: 1px solid var(--if-divider) !important;
  box-shadow: none !important;
  margin-bottom: 14px;
}}
.card-header {{
  background: var(--if-surface) !important;
  border-bottom: 1px solid var(--if-divider) !important;
  font-family: {FONT_HEADING}; font-weight: 600; letter-spacing: 0.02em;
}}
.table thead th {{
  background: var(--if-surface);
  border-bottom: 2px solid var(--if-accent) !important;
  font-family: {FONT_HEADING}; font-weight: 600;
  letter-spacing: 0.03em; text-transform: uppercase; font-size: 12.5px;
}}
.table td, .table th {{ border-color: var(--if-divider) !important; vertical-align: top; }}
.table-striped tbody tr:nth-of-type(odd) {{ background-color: rgba(0, 149, 64, 0.035); }}

/* --- the top-10 affected rows -------------------------------------------
   GX renders these under the heading "Sampled Unexpected Values". They are the
   most useful thing on the page — the difference between "this expectation
   failed" and "here are ten rows you can go and look at" — and GX gives them
   the same weight as everything else. Lifted out with the aqua accent. */
table[data-toggle="table"] th, .ge-unexpected-table th {{ font-size: 12px; }}
.show-scrollbars {{ max-height: 240px; overflow: auto; }}
.show-scrollbars span {{
  display: inline-block;
  font-family: {FONT_MONO}; font-size: 12px;
  background: var(--if-aqua-100);
  border: 1px solid {AQUA_200};
  padding: 1px 6px; margin: 1px 3px 1px 0;
}}

/* --- expectation strings ------------------------------------------------- */
.ge-expectation-string, li.ge-expectation-string {{ padding: 3px 0; }}
.ge-expectation-string strong, .ge-expectation-string .ge-param {{
  background: var(--if-accent-100);
  border-bottom: 1px solid var(--if-accent-300);
  padding: 0 3px; font-family: {FONT_MONO}; font-size: 0.92em;
}}

/* --- buttons -------------------------------------------------------------
   The validation filter is Bootstrap's primary blue out of the box, which is
   the one loud non-brand colour left on the page. */
.btn-primary, .btn-group-toggle .btn-primary {{
  background-color: {ACCENT_600} !important;
  border-color: {ACCENT_600} !important;
  color: #ffffff !important;
  font-family: {FONT_HEADING}; font-weight: 600; letter-spacing: 0.03em;
}}
.btn-primary:hover, .btn-primary.active, .btn-primary:not(:disabled):not(.disabled).active {{
  background-color: {ACCENT_700} !important;
  border-color: {ACCENT_700} !important;
}}

/* --- GX's own promotional chrome ----------------------------------------
   The walkthrough modal, the "How to Edit This Suite" button and the newsletter
   footer are aimed at someone building a suite. This is a signed-off assurance
   artefact for organisers: a button inviting the reader to edit the
   expectations is both noise and a bad suggestion, and a marketing link with
   utm_campaign on it does not belong in a governance document.

   `body > footer` is the newsletter strip. Scoped to a direct child of body so
   it cannot swallow a footer inside the report content. */
.ge-walkthrough-modal, #ge-walkthrough-modal, .ge-cta, .ge-cloud-cta, #ge-cta-footer,
button[data-target*="walkthrough"], button[data-target*="editing-instructions"],
.btn-warning[data-toggle="modal"],
a[href*="greatexpectations.io/cloud"], a[href*="greatexpectations.io/newsletter"],
body > footer {{
  display: none !important;
}}

/* GX's own wordmark is a CSS background-image pulled from an S3 bucket — a
   seventh external origin, and one the asset rewrite cannot reach because it is
   in CSS rather than in a src attribute. Killed here so the page makes no
   request we did not intend. */
.navbar-brand a, .navbar-brand {{ background-image: none !important; }}

/* --- footnote ------------------------------------------------------------ */
.if-footer {{
  margin: 28px 0 0; padding: 14px 18px;
  border-top: 1px solid var(--if-divider);
  color: {NEUTRAL_700}; font-size: 12.5px;
}}

@media print {{
  .navbar, .if-header .if-back {{ display: none !important; }}
  body {{ background: #fff !important; }}
  .card {{ break-inside: avoid; }}
}}
"""


# The tokens this module claims to have copied from the website. verify_brand()
# re-reads global.css and checks they still match, so a rebrand on the site
# surfaces here as a failed check rather than as two subtly different greens.
_TOKEN_EXPECTATIONS = {
    "--color-bg": BG,
    "--color-surface": SURFACE,
    "--color-text": TEXT,
    "--color-accent": ACCENT,
    "--color-accent-100": ACCENT_100,
    "--color-accent-600": ACCENT_600,
    "--color-accent-700": ACCENT_700,
    "--color-accent-2": AQUA,
    "--if-lime": LIME,
    "--if-ink": INK,
}


def verify_brand(global_css: Path) -> list[str]:
    """Compare our tokens against the website's global.css. Returns drift found."""
    import re

    if not global_css.exists():
        return [f"website stylesheet not found at {global_css} — brand drift unchecked"]
    text = global_css.read_text(encoding="utf-8")
    drift = []
    for token, ours in _TOKEN_EXPECTATIONS.items():
        m = re.search(rf"{re.escape(token)}\s*:\s*([^;]+);", text)
        if not m:
            drift.append(f"{token}: not found in global.css (we use {ours})")
        elif m.group(1).strip().lower() != ours.lower():
            drift.append(f"{token}: site has {m.group(1).strip()}, assurance uses {ours}")
    return drift
