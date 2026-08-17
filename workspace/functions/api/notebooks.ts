/**
 * The catalogue of worked-example notebooks: metadata only, no content.
 *
 * Behind the session for two reasons that are not "the notebooks are secret" —
 * they are public on GitHub and the reader links straight to them:
 *
 *   1. consistency. The workspace pages redirect to sign-in on a 401, and an
 *      endpoint that answered anonymously would leave one panel populated on a
 *      page that is otherwise logged out.
 *   2. it is the same gate as `/api/notebook/:id`, which does need one — that
 *      endpoint makes an outbound fetch, and an open one is a free proxy on our
 *      Cloudflare quota.
 */
import { currentSession, NO_STORE_HEADERS } from "../../src/lib/session";
import { ConfigError, configErrorResponse, requireEnv } from "../../src/lib/config";
import { NOTEBOOKS, SOURCE, codespaceUrl, githubDevUrl, githubUrl } from "../../src/lib/notebooks";
import { EVENT } from "../../src/lib/countdown";

interface Env {
  SESSION_SECRET: string;
  /** Optional. Defaults to SOURCE.defaultRef. */
  NOTEBOOKS_REF?: string;
}

export const onRequestGet: PagesFunction<Env> = async ({ request, env }) => {
  let cfg: Record<"SESSION_SECRET", string>;
  try {
    cfg = requireEnv(env as unknown as Record<string, unknown>, ["SESSION_SECRET"] as const);
  } catch (err) {
    if (err instanceof ConfigError) return configErrorResponse(err, true);
    throw err;
  }

  const session = await currentSession(request, cfg.SESSION_SECRET);
  if (!session) {
    return new Response(JSON.stringify({ signedIn: false }), {
      status: 401,
      headers: NO_STORE_HEADERS,
    });
  }

  const ref = env.NOTEBOOKS_REF?.trim() || SOURCE.defaultRef;

  return new Response(
    JSON.stringify({
      ref,
      // The page builds its "browse the repo" links from this rather than
      // hardcoding the org and repository in markup, so there is one place to
      // change if either is ever renamed.
      repo: `https://github.com/${SOURCE.owner}/${SOURCE.repo}`,
      // Which challenge is running, so the reader can lead with the one that is
      // actually theirs this week rather than an alphabetical list.
      currentChallengeSlug: EVENT.slug.replace(/^c\d+-/, ""),
      // One Codespace link for the whole repository — a Codespace is a checkout,
      // not a file, so it does not belong on individual notebooks.
      codespace: codespaceUrl(ref),
      notebooks: NOTEBOOKS.map((n) => ({
        id: n.id,
        title: n.title,
        challengeSlug: n.challengeSlug,
        challengeTitle: n.challengeTitle,
        technique: n.technique,
        summary: n.summary,
        github: githubUrl(n, ref),
        ide: githubDevUrl(n, ref),
      })),
    }),
    { headers: NO_STORE_HEADERS },
  );
};
