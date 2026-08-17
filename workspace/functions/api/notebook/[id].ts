/**
 * One notebook, fetched from GitHub server-side and handed over already
 * stripped of everything the browser must not be given.
 *
 * WHY THE SERVER FETCHES IT RATHER THAN THE BROWSER
 * --------------------------------------------------
 * The obvious build is `fetch("https://raw.githubusercontent.com/...")` from the
 * page. It is one line, and it undoes a privacy decision this workspace already
 * took deliberately: the participant's avatar used to be loaded from GitHub, and
 * it was removed because it handed GitHub their IP address and this origin as a
 * Referer on every page view. A direct fetch for notebook content does exactly
 * the same thing, on every notebook opened, and would need `connect-src` widened
 * in `public/_headers` to permit it — turning `default-src 'self'` from a fact
 * into a comment.
 *
 * Fetching here keeps the pages at zero third-party requests. GitHub sees our
 * Worker, once, cached.
 *
 * WHAT PROTECTS THE OUTBOUND REQUEST
 * -----------------------------------
 * A Function that fetches a URL derived from a path parameter is an SSRF. The
 * defence is that the parameter is NEVER used to build the URL: `findNotebook`
 * resolves it against a fixed list in `src/lib/notebooks.ts` and returns an
 * entry, and the URL comes from the entry. An id that is not in the list is a
 * 404 and no request leaves the Worker.
 *
 * The response is then normalised by `toSafeNotebook`, which drops `text/html`,
 * scripts and SVG before any of it reaches the participant. See that file for
 * why the filtering is server-side.
 */
import { currentSession, NO_STORE_HEADERS } from "../../../src/lib/session";
import { ConfigError, configErrorResponse, requireEnv } from "../../../src/lib/config";
import { findNotebook, rawUrl, githubUrl, githubDevUrl, SOURCE } from "../../../src/lib/notebooks";
import { toSafeNotebook } from "../../../src/lib/notebook-shape";

interface Env {
  SESSION_SECRET: string;
  NOTEBOOKS_REF?: string;
}

/** Notebooks change between deploys, not between requests. An hour at the edge
 *  means an event-day crowd all opening the same notebook costs one origin
 *  fetch, not one each — and GitHub's raw host has its own rate limits. */
const EDGE_TTL_SECONDS = 3600;

/** Our biggest today is 448 KB. A megabyte is generous; past that something is
 *  wrong upstream and streaming it to a phone helps nobody. */
const MAX_BYTES = 4_000_000;

function json(body: unknown, status = 200, extra: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...NO_STORE_HEADERS, ...extra },
  });
}

export const onRequestGet: PagesFunction<Env, "id"> = async ({ request, env, params }) => {
  let cfg: Record<"SESSION_SECRET", string>;
  try {
    cfg = requireEnv(env as unknown as Record<string, unknown>, ["SESSION_SECRET"] as const);
  } catch (err) {
    if (err instanceof ConfigError) return configErrorResponse(err, true);
    throw err;
  }

  const session = await currentSession(request, cfg.SESSION_SECRET);
  if (!session) return json({ signedIn: false }, 401);

  // params.id is a string for a single segment and an array for a catch-all.
  // findNotebook takes unknown and returns undefined for anything that is not
  // an exact match, so both shapes land on the same 404 without special-casing.
  const entry = findNotebook(Array.isArray(params.id) ? params.id[0] : params.id);
  if (!entry) return json({ error: "no_such_notebook" }, 404);

  const ref = env.NOTEBOOKS_REF?.trim() || SOURCE.defaultRef;

  let upstream: Response;
  try {
    upstream = await fetch(rawUrl(entry, ref), {
      headers: { "User-Agent": "if-hackathon-workspace", Accept: "application/json" },
      // Cloudflare's edge cache, keyed on the URL. The notebooks are public, so
      // there is nothing participant-specific in what gets cached here.
      cf: { cacheTtl: EDGE_TTL_SECONDS, cacheEverything: true },
    } as RequestInit);
  } catch (err) {
    console.error(`[notebook] fetch failed for ${entry.id}: ${String(err)}`);
    return json({ error: "upstream_unavailable" }, 503);
  }

  if (!upstream.ok) {
    // 404 here means the REF or the PATH is wrong — our misconfiguration, not
    // the participant's request, and it must not be reported to them as though
    // they asked for something that does not exist.
    console.error(`[notebook] ${entry.id}: upstream ${upstream.status} for ref ${ref}`);
    return json({ error: "upstream_unavailable" }, 502);
  }

  const len = Number(upstream.headers.get("content-length") ?? "0");
  if (len > MAX_BYTES) {
    console.error(`[notebook] ${entry.id}: ${len} bytes exceeds cap`);
    return json({ error: "notebook_too_large" }, 502);
  }

  let safe;
  try {
    const raw = await upstream.json();
    safe = toSafeNotebook(raw);
  } catch (err) {
    // A wrong ref serves an HTML error page, which fails at JSON.parse; a
    // truncated file fails in toSafeNotebook. Both are ours to fix and both
    // read to a participant as "the reader is broken", so both get logged.
    console.error(`[notebook] ${entry.id}: not usable — ${String(err)}`);
    return json({ error: "notebook_unreadable" }, 502);
  }

  return json({
    id: entry.id,
    title: entry.title,
    challengeSlug: entry.challengeSlug,
    challengeTitle: entry.challengeTitle,
    technique: entry.technique,
    summary: entry.summary,
    ref,
    github: githubUrl(entry, ref),
    ide: githubDevUrl(entry, ref),
    cells: safe.cells,
    truncated: safe.truncated,
  });
};
