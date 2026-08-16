/**
 * Environment guards. A misconfigured deploy must fail closed and loudly.
 *
 * WHY THIS EXISTS — THE FAILURE IT PREVENTS IS NOT A UX ONE
 * ----------------------------------------------------------
 * Workers hand you `env.FOO` as `undefined` when a variable is unset. Nothing
 * throws. The first deploy of this workspace proved what that costs:
 *
 *   * `/auth/login` redirected to `github.com/...?client_id=undefined`, sending
 *     the participant off our origin to a GitHub error page with no route back.
 *     Annoying, visible, survivable.
 *
 *   * an unset SESSION_SECRET reaches crypto.subtle as a zero-length key, which
 *     WebCrypto refuses to import. That throws — so it already failed closed,
 *     but as a bare 500 with nothing useful in it for either the participant or
 *     whoever is on shift.
 *
 *   * the genuinely dangerous case is narrower and does NOT throw: a secret that
 *     is PRESENT but guessable. A deploy script interpolating an unset variable
 *     writes the literal text "undefined", which is a perfectly valid 9-byte
 *     HMAC key. It signs, it verifies, every signature checks out, and nothing
 *     in the logs looks wrong — while anyone who guesses the key can forge a
 *     session for any GitHub login they like.
 *
 * So this file does two separate jobs: turn the opaque crash into a message
 * someone can act on, and refuse the weak-but-present secret that would
 * otherwise sail straight through. `src/lib/config.test.mjs` pins both.
 *
 * This is the same lesson as `requireEnv()` on the marketing site, learned again
 * in a second codebase: the dangerous configuration bug is not the one that
 * crashes, it is the one that quietly keeps working.
 */

/** Long enough that a leaked deploy log or a lazy default is not a live key. */
const MIN_SECRET_LENGTH = 32;

export class ConfigError extends Error {
  readonly missing: string[];
  constructor(missing: string[]) {
    super(`Missing or invalid environment variables: ${missing.join(", ")}`);
    this.name = "ConfigError";
    this.missing = missing;
  }
}

function isPresent(v: unknown): v is string {
  // "undefined" and "null" are checked as strings deliberately: a shell pipeline
  // that interpolates an unset variable sets it to that text rather than leaving
  // it unset, which passes a naive truthiness test.
  if (typeof v !== "string") return false;
  const t = v.trim();
  return t !== "" && t !== "undefined" && t !== "null";
}

/**
 * Assert every named variable is present, and that anything secret-shaped is
 * long enough to be worth having. Throws ConfigError listing everything wrong at
 * once — a deploy that is missing three variables should say so in one go rather
 * than revealing them one failed request at a time.
 */
export function requireEnv<K extends string>(
  env: Record<string, unknown>,
  keys: readonly K[],
): Record<K, string> {
  const problems: string[] = [];
  const out = {} as Record<K, string>;

  for (const k of keys) {
    const v = env[k];
    if (!isPresent(v)) {
      problems.push(`${k} (unset)`);
      continue;
    }
    if (k.includes("SECRET") && v.length < MIN_SECRET_LENGTH) {
      problems.push(`${k} (shorter than ${MIN_SECRET_LENGTH} characters)`);
      continue;
    }
    out[k] = v;
  }

  if (problems.length) throw new ConfigError(problems);
  return out;
}

/**
 * What a participant sees when the service is misconfigured.
 *
 * Deliberately says nothing about WHICH variable is missing. The person reading
 * this is a seventeen-year-old at 09:00 on the Monday, not an operator, and the
 * variable names are not their business — naming them here would also hand an
 * attacker a map of the configuration. The detail goes to the logs instead.
 */
export function configErrorResponse(err: ConfigError, wantsJson = false): Response {
  console.error(`[config] ${err.message}`);

  const headers: Record<string, string> = {
    "Cache-Control": "private, no-store, max-age=0, must-revalidate",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
  };

  if (wantsJson) {
    return new Response(JSON.stringify({ signedIn: false, error: "service_unavailable" }), {
      status: 503,
      headers: { ...headers, "Content-Type": "application/json; charset=utf-8" },
    });
  }

  return new Response(
    `<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Workspace unavailable</title>
<style>
  body { margin:0; min-height:100vh; display:grid; place-items:center; padding:32px 20px;
    background:#fcfcfb; color:#0b0b0b;
    font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }
  main { max-width:440px; }
  h1 { font-size:26px; margin:0 0 12px; letter-spacing:-.01em; }
  p { color:#52514e; margin:0 0 14px; }
  @media (prefers-color-scheme: dark) { body { background:#12211a; color:#fff; } p { color:#c3d2c7; } }
</style></head>
<body><main>
  <h1>The workspace isn't ready yet</h1>
  <p>Sign-in is temporarily unavailable. This is a problem at our end, not with
     your account, and nothing you did caused it.</p>
  <p>Please tell an organiser — they have been notified, but a nudge helps.</p>
</main></body></html>`,
    { status: 503, headers: { ...headers, "Content-Type": "text/html; charset=utf-8" } },
  );
}
