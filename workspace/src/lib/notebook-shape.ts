/**
 * Turn raw .ipynb JSON into the small, safe shape the browser is allowed to see.
 *
 * WHY THE FILTERING HAPPENS HERE AND NOT IN THE BROWSER
 * ------------------------------------------------------
 * A notebook is not a document. It is a container for arbitrary MIME bundles,
 * and the interesting ones for an attacker are `text/html` (which is how pandas
 * renders a DataFrame, so it is present in real, innocent notebooks) and
 * `application/javascript`. Anything that renders those is one `innerHTML` away
 * from executing whatever the notebook author wrote, on an origin that holds a
 * session cookie.
 *
 * The browser renderer is written not to do that. But "the renderer is careful"
 * is a property of today's renderer. Dropping the dangerous parts server-side
 * means the browser never receives them at all, so a future careless edit to the
 * front end has nothing dangerous to be careless with. Two independent controls,
 * and the outer one does not depend on the inner one being right.
 *
 * NOTHING IS LOST BY REFUSING text/html
 * --------------------------------------
 * Checked against all six notebooks on 2026-08-17: there are 10 `text/html`
 * outputs and every one of them also carries a `text/plain` alternative, which
 * is the pandas ASCII table. So the fallback is not a degraded experience, it is
 * the same table in a monospace font. If a notebook ever ships HTML with no
 * plain-text alternative, the reader shows a labelled placeholder rather than
 * pretending the output was not there — silence would be the worse failure.
 *
 * This module is pure and has no Workers dependencies, so it runs under plain
 * node for the tests.
 */

/** Image types worth rendering. Everything else is described, not drawn.
 *  No SVG: an SVG is a document that can carry script, and the CSP allows
 *  `img-src data:`, so an inline SVG data URI is a live attack surface for a
 *  gain of nothing — every plot in these notebooks is a PNG. */
const RENDERABLE_IMAGES = ["image/png", "image/jpeg", "image/gif", "image/webp"] as const;

/** Base64 characters. ~2.7 MB of base64 is ~2 MB of image — past that, a plot is
 *  not a plot, and the payload cost lands on a phone on event wifi. */
const MAX_IMAGE_B64 = 2_800_000;

/** A notebook longer than this is almost certainly not one of ours. */
const MAX_CELLS = 400;

/** Per-output text cap. A runaway loop can leave megabytes of stdout in a cell. */
const MAX_TEXT_CHARS = 200_000;

export interface SafeOutput {
  /** `text` renders in a monospace block, `image` as a data URI, `omitted` as a
   *  labelled placeholder naming what was dropped. */
  readonly kind: "text" | "image" | "omitted";
  readonly text?: string;
  /** Present when kind === "image". Always one of RENDERABLE_IMAGES. */
  readonly mime?: string;
  /** Base64 payload, already stripped of whitespace. */
  readonly data?: string;
  /** Present when kind === "omitted": what it was, in words a participant can act on. */
  readonly reason?: string;
  /** stderr is styled differently — it is usually the interesting one. */
  readonly stream?: "stdout" | "stderr";
}

export interface SafeCell {
  readonly type: "markdown" | "code";
  readonly source: string;
  readonly outputs: readonly SafeOutput[];
}

export interface SafeNotebook {
  readonly cells: readonly SafeCell[];
  /** True when MAX_CELLS clipped the notebook, so the reader can say so. */
  readonly truncated: boolean;
}

/** .ipynb stores multi-line strings as either a string or an array of lines. */
function joinSource(v: unknown): string {
  if (typeof v === "string") return v;
  if (Array.isArray(v)) return v.filter((x) => typeof x === "string").join("");
  return "";
}

/**
 * Strip ANSI escape sequences.
 *
 * Exception tracebacks in a notebook are stored WITH the terminal colour codes
 * IPython emitted. Rendered literally they read as `[0;31m---------` noise
 * wrapped around the one line the participant needs. This is cosmetic, not a
 * security control — the output is escaped either way.
 */
function stripAnsi(s: string): string {
  // \u001b is written as an escape, not as a literal ESC byte. The literal is
  // invisible in every editor and does not survive a careless copy-paste — and
  // losing it does not break the regex, it silently widens it to match any
  // bracketed run, which then eats real output: `df.iloc[0]` and `[0.5, 0.5]`
  // both look like the tail of an escape sequence once the ESC has gone.
  return s.replace(/\u001b\[[0-9;?]*[ -/]*[@-~]/g, "");
}

function clamp(s: string): string {
  if (s.length <= MAX_TEXT_CHARS) return s;
  return s.slice(0, MAX_TEXT_CHARS) + "\n… output truncated.";
}

/** Base64 in .ipynb is line-wrapped or array-of-lines. Normalise, then verify. */
function normaliseBase64(v: unknown): string | null {
  const raw = joinSource(v).replace(/\s+/g, "");
  if (!raw) return null;
  // Anything that is not base64 does not belong in a data: URI. Reject rather
  // than pass through — a data URI is parsed by the browser, so a malformed one
  // is not merely a broken image.
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(raw)) return null;
  return raw;
}

function mapOutput(o: unknown): SafeOutput | null {
  if (!o || typeof o !== "object") return null;
  const out = o as Record<string, unknown>;

  // stdout / stderr from a running cell.
  if (out.output_type === "stream") {
    const text = clamp(stripAnsi(joinSource(out.text)));
    if (!text.trim()) return null;
    return { kind: "text", text, stream: out.name === "stderr" ? "stderr" : "stdout" };
  }

  // A raised exception. Participants need this one MORE than the happy path —
  // half the value of a worked example is seeing what the error looks like.
  if (out.output_type === "error") {
    const tb = Array.isArray(out.traceback)
      ? out.traceback.filter((t): t is string => typeof t === "string").join("\n")
      : `${String(out.ename ?? "Error")}: ${String(out.evalue ?? "")}`;
    return { kind: "text", text: clamp(stripAnsi(tb)), stream: "stderr" };
  }

  if (out.output_type === "execute_result" || out.output_type === "display_data") {
    const data = (out.data ?? {}) as Record<string, unknown>;

    // Prefer a picture when there is one — a plot is the point of the cell.
    for (const mime of RENDERABLE_IMAGES) {
      if (mime in data) {
        const b64 = normaliseBase64(data[mime]);
        if (!b64) continue;
        if (b64.length > MAX_IMAGE_B64) {
          return { kind: "omitted", reason: "an image too large to show here" };
        }
        return { kind: "image", mime, data: b64 };
      }
    }

    // Then the plain-text alternative. This is the pandas table, and it is why
    // refusing text/html costs nothing.
    if ("text/plain" in data) {
      const text = clamp(stripAnsi(joinSource(data["text/plain"])));
      if (text.trim()) return { kind: "text", text };
    }

    // Deliberately last, and deliberately not rendered. Naming it is the point:
    // a participant who sees this knows to open the notebook on GitHub rather
    // than assuming the cell produced nothing.
    if ("text/html" in data) {
      return { kind: "omitted", reason: "an HTML table — open on GitHub to see it rendered" };
    }

    const other = Object.keys(data)[0];
    if (other) return { kind: "omitted", reason: `a ${other} output` };
  }

  return null;
}

/**
 * Normalise a parsed .ipynb into the shape the reader consumes.
 *
 * Throws on anything that is not a notebook. A wrong ref makes GitHub return an
 * HTML 404 page, which parses as neither JSON nor a notebook — failing here
 * turns that into one clear error rather than an empty reader.
 */
export function toSafeNotebook(raw: unknown): SafeNotebook {
  if (!raw || typeof raw !== "object" || !Array.isArray((raw as { cells?: unknown }).cells)) {
    throw new Error("not a notebook: no cells array");
  }
  const cells = (raw as { cells: unknown[] }).cells;
  const truncated = cells.length > MAX_CELLS;

  const safe: SafeCell[] = [];
  for (const c of cells.slice(0, MAX_CELLS)) {
    if (!c || typeof c !== "object") continue;
    const cell = c as Record<string, unknown>;
    const type = cell.cell_type === "markdown" ? "markdown" : cell.cell_type === "code" ? "code" : null;
    // `raw` cells are neither prose nor code and are usually export scaffolding.
    if (!type) continue;

    const source = joinSource(cell.source);
    const outputs =
      type === "code" && Array.isArray(cell.outputs)
        ? cell.outputs.map(mapOutput).filter((o): o is SafeOutput => o !== null)
        : [];

    // An empty markdown cell is a blank line in the reader. Drop it.
    if (type === "markdown" && !source.trim()) continue;
    if (type === "code" && !source.trim() && outputs.length === 0) continue;

    safe.push({ type, source, outputs });
  }

  return { cells: safe, truncated };
}
