/**
 * Who am I, which team am I in, and where is my work.
 *
 * The only authenticated endpoint the browser calls. It proxies GitHub using the
 * token held in the HttpOnly cookie, so the token itself never reaches
 * JavaScript — an XSS bug cannot walk away with something that grants repository
 * access.
 *
 * TEAMS ARE GITHUB TEAMS
 * -----------------------
 * D7 removed the database, so there is no `teams` table to drift out of step
 * with reality. A participant's team IS their GitHub team, and their workspace
 * IS the repository that team can write to. Adding someone to a team in GitHub
 * is the whole of onboarding.
 *
 * Everything returned here is already visible to the caller on github.com. This
 * endpoint is a convenience, not a privilege boundary — the boundary is GitHub's
 * own permissions, which is the point of the design.
 */
import { currentSession, NO_STORE_HEADERS } from "../../src/lib/session";
import { EVENT, remainingUntil, inLondon } from "../../src/lib/countdown";

interface Env {
  SESSION_SECRET: string;
  GITHUB_ORG: string;
}

const UA = "if-hackathon-workspace";

export const onRequestGet: PagesFunction<Env> = async ({ request, env }) => {
  const session = await currentSession(request, env.SESSION_SECRET);
  if (!session) {
    return new Response(JSON.stringify({ signedIn: false }), {
      status: 401,
      headers: NO_STORE_HEADERS,
    });
  }

  const ghHeaders = {
    Authorization: `Bearer ${session.token}`,
    Accept: "application/vnd.github+json",
    "User-Agent": UA,
  };

  let teams: Array<{ name: string; slug: string; repo: string | null }> = [];
  try {
    const res = await fetch("https://api.github.com/user/teams?per_page=100", {
      headers: ghHeaders,
    });
    if (res.ok) {
      const all = (await res.json()) as Array<{
        name: string;
        slug: string;
        organization?: { login: string };
      }>;
      teams = all
        .filter((t) => t.organization?.login === env.GITHUB_ORG)
        .map((t) => ({
          name: t.name,
          slug: t.slug,
          // Convention, not a lookup: the team's repository is named after the
          // team. One less thing to store, and it cannot go stale.
          repo: `https://github.com/${env.GITHUB_ORG}/${t.slug}`,
        }));
    }
  } catch {
    // A GitHub outage should degrade to "signed in, team unknown" rather than
    // logging the participant out. Losing your session mid-event because an API
    // call failed is a worse experience than a missing panel.
    teams = [];
  }

  const deadline = remainingUntil(EVENT.submissionDeadlineUtc);

  return new Response(
    JSON.stringify({
      signedIn: true,
      user: { login: session.login, name: session.name, avatar: session.avatar },
      teams,
      event: {
        title: EVENT.title,
        startsAtUtc: EVENT.startsAtUtc,
        endsAtUtc: EVENT.endsAtUtc,
        submissionDeadlineUtc: EVENT.submissionDeadlineUtc,
        // Rendered server-side so every participant sees the same string, with
        // the zone named. BST ends the day before this event starts.
        submissionDeadlineLondon: inLondon(EVENT.submissionDeadlineUtc),
        deadlinePast: deadline.past,
      },
    }),
    { headers: NO_STORE_HEADERS },
  );
};
