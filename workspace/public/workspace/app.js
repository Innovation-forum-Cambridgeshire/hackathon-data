/**
 * Workspace shell: sign-in state, routing, and the panels.
 *
 * Two endpoints, both Functions on this origin: /api/me for who you are and
 * what your team is, /api/notebooks(+/:id) for the worked examples. Nothing here
 * talks to github.com — see functions/api/notebook/[id].ts for why that is a
 * deliberate privacy position and not an accident of implementation.
 *
 * ROUTING IS location.hash, NOT history.pushState
 * ------------------------------------------------
 * Every route resolves to the same document, which the server already serves at
 * /workspace/. A pushState router needs the server to serve that document for
 * every path underneath it too, and Cloudflare Pages would answer /workspace/
 * examples/c03 with a 404 unless a rewrite is configured. A hash never reaches
 * the server, so deep links, refreshes and the back button all work with no
 * routing configuration to keep in step.
 *
 * All text goes in with textContent, and the notebook body is built by
 * notebook-view.js, which constructs nodes rather than markup. Nothing in this
 * file produces HTML from data.
 */
import { renderNotebook } from "./notebook-view.js";

const $ = (id) => document.getElementById(id);

/** Populated once at boot; the panels read from it rather than re-fetching. */
let me = null;
let catalogue = null;
/** Notebook bodies are immutable for a given ref, so a second visit is free. */
const notebookCache = new Map();

// ── Boot ─────────────────────────────────────────────────────────────────────

async function boot() {
  const res = await fetch("/api/me", { credentials: "same-origin" });

  // location.replace() schedules a navigation, it does not halt the script.
  // Without the throw, the lines below read `data.user` off a 401 body and
  // throw anyway — so the last thing the participant sees before the redirect
  // is a broken page. Stop here instead.
  if (res.status === 401) {
    const why = await res.json().catch(() => ({}));
    // access_ended means membership was withdrawn while the session was still
    // valid. Send them somewhere that says so rather than looping them back
    // through sign-in, which would fail again and read as a bug.
    const REDIRECTS = {
      token_expired: "/?error=session_expired",
      access_ended: "/?error=access_ended",
    };
    location.replace(REDIRECTS[why.error] || "/");
    throw new Error("not signed in");
  }

  if (!res.ok) {
    $("loading").textContent =
      "The workspace can't load right now. Please refresh in a moment — your work is safe on GitHub.";
    throw new Error("workspace unavailable");
  }

  me = await res.json();

  $("loading").hidden = true;
  $("app").hidden = false;

  // textContent, never innerHTML: these come from a GitHub profile and are
  // therefore controllable by whoever owns that account.
  $("ava").textContent = (me.user.name || me.user.login || "?").trim().charAt(0).toUpperCase();
  $("who-name").textContent = me.user.name || me.user.login;
  $("who-login").textContent = "@" + me.user.login;
  $("ev-title").textContent = me.event.title;
  $("ev-deadline").textContent = me.event.submissionDeadlineLondon;
  $("sub-deadline").textContent = me.event.submissionDeadlineLondon;

  startClock(me.event.submissionDeadlineUtc);
  renderTeam();

  // The catalogue is small and every view links into it, so it is fetched once
  // at boot. A failure here must not take the rest of the workspace down: the
  // examples panel says so on its own and the team panel is unaffected.
  try {
    const c = await fetch("/api/notebooks", { credentials: "same-origin" });
    if (c.ok) {
      catalogue = await c.json();
      applyRepoLinks();
    }
  } catch {
    catalogue = null;
  }

  window.addEventListener("hashchange", route);
  $("q").addEventListener("input", () => renderExamples($("q").value));
  route();
}

// ── Countdown ────────────────────────────────────────────────────────────────

/** The deadline is a fixed UTC instant, rendered server-side with its zone
 *  named. Only the remaining time is computed here, so the clocks going back
 *  mid-event cannot shift it. */
function startClock(deadlineUtc) {
  const target = Date.parse(deadlineUtc);
  const pad = (n) => String(n).padStart(2, "0");
  (function tick() {
    const left = target - Date.now();
    if (left <= 0) {
      const clock = $("clock");
      clock.textContent = "";
      const u = document.createElement("div");
      u.className = "u";
      u.style.minWidth = "auto";
      const n = document.createElement("div");
      n.className = "n";
      n.textContent = "Closed";
      u.appendChild(n);
      clock.appendChild(u);
      return;
    }
    const s = Math.floor(left / 1000);
    $("cd").textContent = Math.floor(s / 86400);
    $("ch").textContent = pad(Math.floor((s % 86400) / 3600));
    $("cm").textContent = pad(Math.floor((s % 3600) / 60));
    $("cs").textContent = pad(s % 60);
    setTimeout(tick, 1000);
  })();
}

// ── Repo links ───────────────────────────────────────────────────────────────

/**
 * Fill in every `data-repo-path` link from the catalogue's repo and ref.
 *
 * The alternative is writing the org, repository and branch into the markup a
 * dozen times, which is a dozen places to miss when any of them changes. The
 * value is `<kind>/<path>` — `blob/consumers/duckdb.sql`, `tree/catalogue`.
 */
function applyRepoLinks() {
  if (!catalogue) return;
  for (const a of document.querySelectorAll("[data-repo-path]")) {
    const spec = a.getAttribute("data-repo-path");
    const slash = spec.indexOf("/");
    const kind = spec.slice(0, slash);
    const path = spec.slice(slash + 1);
    a.href = `${catalogue.repo}/${kind}/${catalogue.ref}/${path}`;
    a.rel = "noopener";
    a.target = "_blank";
  }
  $("ide-link").href = catalogue.notebooks[0]?.ide?.replace(/\/blob\/.*$/, "") || catalogue.repo;
  $("cs-link").href = catalogue.codespace;
}

// ── Team ─────────────────────────────────────────────────────────────────────

function card(title) {
  const c = document.createElement("div");
  c.className = "card";
  const h = document.createElement("h2");
  h.textContent = title;
  c.appendChild(h);
  return c;
}

function linkList(links) {
  const ul = document.createElement("ul");
  for (const [label, href] of links) {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = href;
    a.rel = "noopener";
    a.target = "_blank";
    a.textContent = label;
    li.appendChild(a);
    ul.appendChild(li);
  }
  return ul;
}

function renderTeam() {
  const root = $("team-body");
  root.textContent = "";
  const teams = me.teams || [];

  if (!teams.length) {
    // A real state on day one, not an error. Say what happens next rather than
    // implying something is broken.
    const note = document.createElement("div");
    note.className = "note warn";
    const h = document.createElement("h2");
    h.textContent = "No team yet";
    const p = document.createElement("p");
    p.textContent =
      "You're signed in, but you haven't been added to a team. That happens at kickoff — " +
      "if the event has started and you still see this, find an organiser.";
    note.append(h, p);
    root.appendChild(note);
    $("home-team-lede").textContent =
      "You'll be added to a team at kickoff. Your repository appears here when you are.";
    return;
  }

  const grid = document.createElement("div");
  grid.className = "grid";
  for (const t of teams) {
    const c = card(t.name);
    const p = document.createElement("p");
    p.className = "lede";
    p.textContent = "Your repository and board. Work lands here; this is what gets judged.";
    c.appendChild(p);
    c.appendChild(
      linkList([
        ["Repository", t.repo],
        ["Board", `${t.repo}/projects`],
        ["SUBMISSION.md", `${t.repo}/blob/main/SUBMISSION.md`],
        ["Open in github.dev", t.repo.replace("https://github.com/", "https://github.dev/")],
      ]),
    );
    grid.appendChild(c);
  }
  root.appendChild(grid);

  const first = teams[0];
  $("home-team-lede").textContent = `${first.name} — your repository, board and submission.`;
  $("sub-md").href = `${first.repo}/blob/main/SUBMISSION.md`;
  $("sub-repo").href = first.repo;
}

// ── Examples ─────────────────────────────────────────────────────────────────

function renderExamples(filter = "") {
  const root = $("nb-list");
  root.textContent = "";

  if (!catalogue) {
    const note = document.createElement("div");
    note.className = "note warn";
    const p = document.createElement("p");
    p.textContent =
      "The examples can't be listed right now. They are also on GitHub in the " +
      "hackathon-data repository, under sample/notebooks.";
    note.appendChild(p);
    root.appendChild(note);
    return;
  }

  // The challenge running this week goes first. Everything else keeps catalogue
  // order, which is deliberate rather than alphabetical.
  const current = catalogue.currentChallengeSlug;
  const ordered = [...catalogue.notebooks].sort(
    (a, b) => (b.challengeSlug === current) - (a.challengeSlug === current),
  );

  const q = filter.trim().toLowerCase();
  const shown = q
    ? ordered.filter((n) =>
        [n.title, n.technique, n.summary, n.challengeTitle || ""]
          .join(" ").toLowerCase().includes(q))
    : ordered;

  $("nb-empty").hidden = shown.length > 0;

  for (const n of shown) {
    const a = document.createElement("a");
    a.className = "nb-item";
    a.href = `#/examples/${encodeURIComponent(n.id)}`;

    const row = document.createElement("div");
    row.className = "row";
    const h = document.createElement("h3");
    h.textContent = n.title;
    row.appendChild(h);
    if (n.challengeSlug === current) {
      const chip = document.createElement("span");
      chip.className = "chip chip-solid";
      chip.textContent = "This event";
      row.appendChild(chip);
    }
    a.appendChild(row);

    const tech = document.createElement("div");
    tech.className = "tech";
    tech.textContent = n.technique;
    a.appendChild(tech);

    const sum = document.createElement("p");
    sum.className = "sum";
    sum.textContent = n.summary;
    a.appendChild(sum);

    root.appendChild(a);
  }
}

function actionButton(label, href, primary = false) {
  const a = document.createElement("a");
  a.className = primary ? "btn btn-primary" : "btn";
  a.href = href;
  a.rel = "noopener";
  a.target = "_blank";
  a.textContent = label;
  return a;
}

async function renderNotebookView(id) {
  const meta = catalogue?.notebooks.find((n) => n.id === id);

  $("nb-title").textContent = meta ? meta.title : "Notebook";
  $("nb-summary").textContent = meta ? meta.summary : "";
  const chip = $("nb-chip");
  chip.hidden = !meta?.challengeTitle;
  if (meta?.challengeTitle) chip.textContent = meta.challengeTitle;

  const actions = $("nb-actions");
  actions.textContent = "";
  if (meta) {
    // The IDE route. github.dev is a full VS Code in the browser, opening a
    // copy — we host nothing and run nothing, which is what keeps an editable
    // notebook out of our threat model entirely.
    actions.append(
      actionButton("Open in github.dev", meta.ide, true),
      actionButton("View on GitHub", meta.github),
    );
    if (catalogue?.codespace) actions.append(actionButton("New Codespace", catalogue.codespace));
  }

  const body = $("nb-body");
  body.textContent = "";
  $("nb-loading").hidden = false;

  try {
    let nb = notebookCache.get(id);
    if (!nb) {
      const res = await fetch(`/api/notebook/${encodeURIComponent(id)}`, {
        credentials: "same-origin",
      });
      if (res.status === 401) {
        location.replace("/?error=session_expired");
        return;
      }
      if (!res.ok) throw new Error(`status ${res.status}`);
      nb = await res.json();
      notebookCache.set(id, nb);
    }
    $("nb-loading").hidden = true;
    renderNotebook(body, nb);
  } catch {
    $("nb-loading").hidden = true;
    const note = document.createElement("div");
    note.className = "note warn";
    const h = document.createElement("h2");
    h.textContent = "This notebook won't load";
    const p = document.createElement("p");
    p.textContent =
      "That's a problem at our end. The same notebook is readable on GitHub — " +
      "use the buttons above.";
    note.append(h, p);
    body.appendChild(note);
  }
}

// ── Router ───────────────────────────────────────────────────────────────────

const VIEWS = {
  home: { el: "view-home", title: "Home", crumb: "Workspace", search: false },
  examples: { el: "view-examples", title: "Worked examples", crumb: "Workspace", search: true },
  notebook: { el: "view-notebook", title: "Worked examples", crumb: "Worked examples", search: false },
  team: { el: "view-team", title: "Your team", crumb: "Workspace", search: false },
  data: { el: "view-data", title: "Data & tools", crumb: "Workspace", search: false },
  submit: { el: "view-submit", title: "Submitting", crumb: "Workspace", search: false },
};

function route() {
  // "#/examples/c03-..." -> ["examples", "c03-..."]
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const head = parts[0] || "home";
  const name = head === "examples" && parts[1] ? "notebook" : VIEWS[head] ? head : "home";
  const view = VIEWS[name];

  for (const v of Object.values(VIEWS)) $(v.el).hidden = true;
  $(view.el).hidden = false;

  $("title").textContent = view.title;
  $("crumb").textContent = view.crumb;
  $("search-wrap").hidden = !view.search;

  // Highlight the nav item this view belongs to — the notebook reader is still
  // "Worked examples" as far as the sidebar is concerned.
  const navFor = name === "notebook" ? "examples" : name;
  for (const a of document.querySelectorAll("#nav a")) {
    if (a.dataset.view === navFor) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }

  if (name === "examples") renderExamples($("q").value);
  if (name === "notebook") renderNotebookView(decodeURIComponent(parts[1]));

  // A view change is a navigation as far as the reader is concerned, so put
  // them at the top of it rather than wherever the last one was scrolled to.
  window.scrollTo(0, 0);
}

boot();
