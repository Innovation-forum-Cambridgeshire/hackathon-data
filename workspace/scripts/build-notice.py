#!/usr/bin/env python3
"""
Render the Workspace Privacy Notice into public/legal/workspace-privacy/.

    python3 scripts/build-notice.py

Why this exists
---------------
The notice has to be reachable from the sign-in page, because that is the point
at which collection starts — a notice a participant can only find after they
have signed in is not much of a notice. It was published in the marketing site's
legal section, and that section deploys by `ftp/deploy.sh` in a different
repository. On 2026-08-17 the workspace was live and
`r1x.co.uk/public_hackathon/legal/workspace-privacy/` returned 404, which is the
wrong way round and is exactly the failure mode a cross-repo deploy dependency
produces.

So the workspace serves its own copy. The single source of truth stays the Word
master; this script is the only way the copy is allowed to change.

    Word master  ──┬── legal-from-docx.py ──▶ marketing site  (canonical, public)
                   └── build-notice.py    ──▶ workspace       (at the point of collection)

Both read the same .docx, so the two cannot say different things unless someone
edits generated output by hand — which is why the output carries a "do not edit"
banner and this script is idempotent.

If the master moves or is renamed, this fails loudly rather than shipping a
stale notice.
"""
import html
import re
import sys
from pathlib import Path

try:
    import docx
except ImportError:
    sys.exit("python-docx is required:  pip3 install python-docx")

HERE = Path(__file__).resolve().parent.parent
MASTER = Path(
    "/Users/yavinowens/Library/CloudStorage/OneDrive-R1x/R1X Foundry - Documents/"
    "05_PRODUCT_AND_PLATFORM/Innovation Forum x R1X - Documentation/"
    "01 Legal & Compliance/06 - Workspace Privacy Notice.docx"
)
OUT = HERE / "public" / "legal" / "workspace-privacy" / "index.html"

# Everything before section 1 is the Word cover block — title, the
# "DRAFT FOR LEGAL REVIEW" stamp, document control. None of it belongs on a
# published page; the same cut is made by the marketing site's importer.
FIRST_SECTION = re.compile(r"^\s*1\.\s")
# A numbered heading: "1. What this notice covers".
HEADING = re.compile(r"^\s*(\d+)\.\s+(\S.*)$")


def blocks(path):
    """Yield ('h2'|'p'|'li', text) from the master, cover block removed."""
    doc = docx.Document(str(path))
    started = False
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        if not started:
            if not FIRST_SECTION.match(text):
                continue
            started = True
        if HEADING.match(text):
            yield "h2", text
        elif p.style.name == "List Bullet":
            yield "li", text
        else:
            yield "p", text
    if not started:
        sys.exit(f"no numbered section found in {path.name} — has the master changed shape?")


def render(items):
    out, in_list = [], False
    for kind, text in items:
        if kind != "li" and in_list:
            out.append("  </ul>")
            in_list = False
        if kind == "h2":
            out.append(f"  <h2>{html.escape(text)}</h2>")
        elif kind == "li":
            if not in_list:
                out.append("  <ul>")
                in_list = True
            out.append(f"    <li>{html.escape(text)}</li>")
        else:
            out.append(f"  <p>{html.escape(text)}</p>")
    if in_list:
        out.append("  </ul>")
    return "\n".join(out)


TEMPLATE = """<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Workspace Privacy Notice — Innovation Forum × R1X</title>
<meta name="theme-color" content="#04180f">
<meta name="robots" content="noindex, nofollow">
<!-- GENERATED FILE — DO NOT EDIT.
     Source: "01 Legal & Compliance/06 - Workspace Privacy Notice.docx"
     Rebuild: python3 scripts/build-notice.py
     Editing this file by hand puts it out of step with the marketing site's
     copy of the same notice, which is generated from the same master. Two
     versions of one legal document saying different things is the failure this
     pipeline exists to prevent. -->
<link rel="icon" href="/brand/if-mark.png">
<link rel="stylesheet" href="/tokens.css">
<style>
  body {{ background: var(--bg); color: var(--text); }}
  .wrap {{ max-width: 760px; margin: 0 auto; padding: 40px 22px 80px; }}
  .kicker {{
    font-family: var(--font-heading); font-size: 12.5px; font-weight: 600;
    letter-spacing: .18em; text-transform: uppercase; color: var(--accent-600);
    margin-bottom: 12px;
  }}
  h1 {{ font-size: clamp(30px, 5vw, 40px); margin-bottom: 10px; }}
  .standfirst {{ color: var(--muted); font-size: 17px; margin-bottom: 30px; }}
  h2 {{
    font-size: 21px; margin: 34px 0 10px;
    padding-top: 18px; border-top: 1px solid var(--rule);
  }}
  p {{ margin-bottom: 13px; }}
  ul {{ margin: 0 0 13px; padding-left: 22px; }}
  li {{ margin-bottom: 6px; }}
  .back {{
    display: inline-block; margin-bottom: 26px; font-family: var(--font-heading);
    font-size: 14px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
    color: var(--accent-600);
  }}
  /* Placeholders are left visible on purpose — see the standing decision in the
     marketing repo's scripts/fill-doc-placeholders.py. Marking them rather than
     hiding them means nobody mistakes one for finished copy. */
  .wrap p, .wrap li {{ overflow-wrap: break-word; }}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="/">← Back to sign-in</a>
  <div class="kicker">Innovation Forum × R1X</div>
  <h1>Workspace Privacy Notice</h1>
  <p class="standfirst">
    What the participant workspace collects about you, who it is shared with, and
    what you can ask us to do about it.
  </p>
{body}
</div>
</body>
</html>
"""


def main():
    if not MASTER.exists():
        sys.exit(f"master not found:\n  {MASTER}\nHas it been moved or renamed?")
    body = render(blocks(MASTER))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(TEMPLATE.format(body=body), encoding="utf-8")

    placeholders = sorted(set(re.findall(r"\[[A-Z][A-Z /&'-]+\]", body)))
    print(f"wrote {OUT.relative_to(HERE)}  ({len(body.splitlines())} blocks)")
    if placeholders:
        print("\n  Placeholders still unfilled — deliberate, not a bug:")
        for p in placeholders:
            print(f"    {p}")
        print("  Filling these with invented values would turn a visible gap into")
        print("  an invisible false statement. They need a person, a mailbox and a")
        print("  retention decision.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
