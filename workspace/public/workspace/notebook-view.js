/**
 * Turn a normalised notebook into DOM. The reader half of the notebook feature.
 *
 * THE ONE RULE: THIS FILE NEVER PRODUCES HTML
 * --------------------------------------------
 * There is no `innerHTML` here, no `insertAdjacentHTML`, no template string that
 * becomes markup. Every node is `createElement`, every piece of text is
 * `textContent`. That is not stylistic. Notebook content is authored elsewhere
 * and rendered on an origin that holds a session cookie, so the moment this file
 * builds a markup string from notebook text, the escaping of that string becomes
 * a security control — and escaping is the control people get wrong.
 *
 * Building nodes has no escaping step to get wrong. `textContent` cannot create
 * an element, so `<img onerror=...>` in a notebook is five words on the page.
 *
 * The server has already dropped `text/html`, scripts and SVG (see
 * `src/lib/notebook-shape.ts`). This is the second of the two controls, and it
 * does not rely on the first having worked.
 *
 * The markdown subset is deliberately small — headings, bold, italic, inline
 * code, links, lists, rules, fences, quotes. It is what the six notebooks
 * actually use, plus links, which none of them use yet and one of them will.
 * A feature that is not implemented cannot be implemented wrongly; anything
 * unrecognised renders as its own literal text, which is legible and honest.
 *
 * `parseMarkdown` and `safeHref` are pure and are unit-tested under node in
 * `src/lib/notebook-markdown.test.mjs`. Everything below them needs a document.
 */

// ── Inline ───────────────────────────────────────────────────────────────────

/**
 * Only http(s) and mailto survive. Everything else — `javascript:`, `data:`,
 * `vbscript:`, and the protocol-relative `//host` form — returns null and the
 * link is rendered as plain text instead of being dropped, so the reader can
 * still see where it was meant to point.
 *
 * The leading-control-character strip matters: `java\tscript:alert(1)` is parsed
 * by browsers as a javascript: URL, and a naive `startsWith("javascript:")`
 * check does not see it.
 */
export function safeHref(url) {
  if (typeof url !== "string") return null;
    // Strip C0 controls and space before testing the scheme. Browsers ignore
  // them when parsing a URL, so `java\tscript:alert(1)` IS a javascript: URL
  // while `startsWith("javascript:")` says it is not.
  const cleaned = url.replace(/[\u0000-\u0020]/g, "");
  if (!cleaned) return null;
  if (cleaned.startsWith("//")) return null;
  if (/^(https?:|mailto:)/i.test(cleaned)) return cleaned;
  // Relative and anchor links are fine — they cannot leave this origin.
  if (/^[./#?]/.test(cleaned)) return cleaned;
  return null;
}

const INLINE = [
  // Code first: whatever is inside a code span is literal, including asterisks.
  { type: "code", re: /`([^`]+)`/ },
  { type: "link", re: /\[([^\]]*)\]\(([^)\s]+)\)/ },
  { type: "strong", re: /\*\*([^*]+)\*\*/ },
  { type: "em", re: /(?<![*\w])[*_]([^*_\n]+)[*_](?![*\w])/ },
];

/** Split a line into `{type, text, href}` tokens. Unmatched text is `"text"`. */
export function parseInline(src) {
  const out = [];
  let rest = String(src);

  while (rest) {
    let best = null;
    for (const { type, re } of INLINE) {
      const m = re.exec(rest);
      if (m && (best === null || m.index < best.m.index)) best = { type, m };
    }
    if (!best) {
      out.push({ type: "text", text: rest });
      break;
    }
    if (best.m.index > 0) out.push({ type: "text", text: rest.slice(0, best.m.index) });

    if (best.type === "link") {
      const href = safeHref(best.m[2]);
      // An unsafe target degrades to text rather than vanishing — "this said
      // something and pointed somewhere" is more useful than a silent gap.
      out.push(
        href
          ? { type: "link", text: best.m[1] || href, href }
          : { type: "text", text: `${best.m[1]} (${best.m[2]})` },
      );
    } else {
      out.push({ type: best.type, text: best.m[1] });
    }
    rest = rest.slice(best.m.index + best.m[0].length);
  }
  return out;
}

// ── Blocks ───────────────────────────────────────────────────────────────────

/** Parse markdown into blocks. Pure: no document, no HTML, node-testable. */
export function parseMarkdown(src) {
  const lines = String(src).replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let i = 0;

  const flushPara = (buf) => {
    if (buf.length) blocks.push({ type: "p", text: buf.join(" ").trim() });
    return [];
  };
  let para = [];

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code. Runs to the closing fence or the end — an unclosed fence
    // renders the rest as code rather than swallowing it.
    const fence = /^\s*```+\s*(\S*)\s*$/.exec(line);
    if (fence) {
      para = flushPara(para);
      const body = [];
      i++;
      while (i < lines.length && !/^\s*```+\s*$/.test(lines[i])) body.push(lines[i++]);
      i++;
      blocks.push({ type: "code", lang: fence[1] || "", text: body.join("\n") });
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      para = flushPara(para);
      blocks.push({ type: "h", level: heading[1].length, text: heading[2].trim() });
      i++;
      continue;
    }

    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      para = flushPara(para);
      blocks.push({ type: "hr" });
      i++;
      continue;
    }

    const bullet = /^\s*[-*+]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (bullet || numbered) {
      para = flushPara(para);
      const ordered = Boolean(numbered);
      const items = [];
      while (i < lines.length) {
        const b = /^\s*[-*+]\s+(.*)$/.exec(lines[i]);
        const n = /^\s*\d+[.)]\s+(.*)$/.exec(lines[i]);
        const m = ordered ? n : b;
        if (!m) break;
        items.push(m[1].trim());
        i++;
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      para = flushPara(para);
      const quoted = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        quoted.push(lines[i].replace(/^\s*>\s?/, ""));
        i++;
      }
      blocks.push({ type: "quote", text: quoted.join(" ").trim() });
      continue;
    }

    if (!line.trim()) {
      para = flushPara(para);
      i++;
      continue;
    }

    para.push(line.trim());
    i++;
  }
  flushPara(para);
  return blocks;
}

// ── DOM ──────────────────────────────────────────────────────────────────────

function el(tag, className) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  return n;
}

function appendInline(parent, src) {
  for (const t of parseInline(src)) {
    if (t.type === "text") {
      parent.appendChild(document.createTextNode(t.text));
      continue;
    }
    if (t.type === "link") {
      const a = el("a");
      a.href = t.href;
      a.rel = "noopener noreferrer";
      // Notebook links point off-site; a new tab keeps the reader's place.
      a.target = "_blank";
      a.textContent = t.text;
      parent.appendChild(a);
      continue;
    }
    const tag = t.type === "code" ? "code" : t.type === "strong" ? "strong" : "em";
    const n = el(tag);
    n.textContent = t.text;
    parent.appendChild(n);
  }
}

/** Render markdown into `root`. Clears it first. */
export function renderMarkdown(root, src) {
  root.textContent = "";
  for (const b of parseMarkdown(src)) {
    if (b.type === "hr") {
      root.appendChild(el("hr"));
      continue;
    }
    if (b.type === "code") {
      const pre = el("pre", "nb-pre");
      const c = el("code");
      c.textContent = b.text;
      pre.appendChild(c);
      root.appendChild(pre);
      continue;
    }
    if (b.type === "list") {
      const list = el(b.ordered ? "ol" : "ul");
      for (const item of b.items) {
        const li = el("li");
        appendInline(li, item);
        list.appendChild(li);
      }
      root.appendChild(list);
      continue;
    }
    if (b.type === "quote") {
      const q = el("blockquote");
      appendInline(q, b.text);
      root.appendChild(q);
      continue;
    }
    if (b.type === "h") {
      // Notebook headings start at h1, but the page already has one and the
      // reader sits inside a section — so they are shifted down a level to keep
      // the document outline sane for a screen reader.
      const n = el(`h${Math.min(6, b.level + 1)}`);
      appendInline(n, b.text);
      root.appendChild(n);
      continue;
    }
    const p = el("p");
    appendInline(p, b.text);
    root.appendChild(p);
  }
}

function renderOutput(out) {
  if (out.kind === "image") {
    const fig = el("div", "nb-out nb-out-img");
    const img = el("img");
    // The server verified this is base64 and one of four raster types, so the
    // URI cannot carry a document. CSP already permits `img-src data:`.
    img.src = `data:${out.mime};base64,${out.data}`;
    img.alt = "Chart produced by the code above";
    img.loading = "lazy";
    fig.appendChild(img);
    return fig;
  }
  if (out.kind === "omitted") {
    const n = el("div", "nb-out nb-omitted");
    n.textContent = `Output not shown here: ${out.reason}.`;
    return n;
  }
  const pre = el("pre", out.stream === "stderr" ? "nb-out nb-err" : "nb-out");
  pre.textContent = out.text;
  return pre;
}

/** Render a notebook (the shape `toSafeNotebook` produces) into `root`. */
export function renderNotebook(root, nb) {
  root.textContent = "";

  for (const cell of nb.cells || []) {
    if (cell.type === "markdown") {
      const box = el("div", "nb-md");
      renderMarkdown(box, cell.source);
      root.appendChild(box);
      continue;
    }

    const box = el("div", "nb-cell");
    const pre = el("pre", "nb-src");
    const code = el("code");
    code.textContent = cell.source;
    pre.appendChild(code);
    box.appendChild(pre);
    for (const out of cell.outputs || []) box.appendChild(renderOutput(out));
    root.appendChild(box);
  }

  if (nb.truncated) {
    const n = el("p", "nb-omitted");
    n.textContent = "This notebook was too long to show in full — open it on GitHub for the rest.";
    root.appendChild(n);
  }
}
