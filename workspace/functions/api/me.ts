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
import { currentSession, clearCookieHeader, NO_STORE_HEADERS } from "../../src/lib/session";
import { EVENT, remainingUntil, inLondon } from "../../src/lib/countdown";
import { ConfigError, configErrorResponse, requireEnv } from "../../src/lib/config";

interface Env {
  SESSION_SECRET: string;
  GITHUB_ORG: string;
}

const UA = "if-hackathon-workspace";

export const onRequestGet: PagesFunction<Env> = async ({ request, env }) => {
  // Verifying against an unset secret is the dangerous case, not a failing one:
  // it would verify a forged cookie signed with the string "undefined" and hand
  // back a valid-looking session. 503 before any verification is attempted.
  let cfg: Record<"SESSION_SECRET" | "GITHUB_ORG", string>;
  try {
    cfg = requireEnv(env as unknown as Record<string, unknown>, [
      "SESSION_SECRET",
      "GITHUB_ORG",
    ] as const);
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

  const ghHeaders = {
    Authorization: `Bearer ${session.token}`,
    Accept: "application/vnd.github+json",
    "User-Agent": UA,
  };

  // RE-CHECK ORGANISATION MEMBERSHIP ON EVERY REQUEST. THIS IS A SAFEGUARDING
  // CONTROL, NOT A TIDINESS ONE.
  //
  // Sessions are signed cookies with no server-side store, so there is nothing
  // to delete to end one early. Checking membership only at login therefore made
  // "remove them from the organisation" — the sanction the Code of Conduct
  // actually relies on — take effect up to EIGHT HOURS later. If someone is
  // removed at 10:00 for harassing a young person, they keep the workspace until
  // their cookie expires. A legal review flagged that publishing the word
  // "immediately" would put a false statement about a child-protection control
  // into a participant-facing document.
  //
  // Asking GitHub each time costs one API call against the participant's own
  // 5,000/hour budget and closes the window to a single page load.
  //
  // The three-way split below matters. A definitive "not a member" evicts. A
  // GitHub OUTAGE must not evict, because logging every participant out mid-event
  // because api.github.com is having a bad afternoon is its own incident — and an
  // attacker cannot manufacture a 500 from GitHub to hold a session open.
  const memberRes = await fetch(
    `https://api.github.com/user/memberships/orgs/${encodeURIComponent(cfg.GITHUB_ORG)}`,
    { headers: ghHeaders },
  );

  if (memberRes.status === 401 || memberRes.status === 403 || memberRes.status === 404) {
    // Removed from the organisation, or the token was revoked on GitHub's side.
    // Clear the cookie on the way out so the browser stops presenting it.
    return new Response(JSON.stringify({ signedIn: false, error: "access_ended" }), {
      status: 401,
      headers: { ...NO_STORE_HEADERS, "Set-Cookie": clearCookieHeader() },
    });
  }

  if (memberRes.ok) {
    const membership = (await memberRes.json()) as { state?: string };
    if (membership.state !== "active") {
      return new Response(JSON.stringify({ signedIn: false, error: "access_ended" }), {
        status: 401,
        headers: { ...NO_STORE_HEADERS, "Set-Cookie": clearCookieHeader() },
      });
    }
  }
  // Any other status (5xx, or a network failure that threw before this point) is
  // treated as "GitHub is unwell", and the session is allowed to continue.

  let teams: Array<{ name: string; slug: string; repo: string | null }> = [];
  try {
    const res = await fetch("https://api.github.com/user/teams?per_page=100", {
      headers: ghHeaders,
    });

    // A dead token is NOT an outage, and must not be treated as one.
    //
    // The OAuth App issues tokens that expire after eight hours. Our session
    // cookie also lasts eight hours, but the two clocks start at different
    // moments and drift apart, so on a five-day event there is a window where
    // the session is still valid and the token behind it is not. Falling
    // through to the catch below would render "No team yet — find an
    // organiser", which is both wrong and pointed straight at the support rota.
    //
    // 401 means re-authenticate. The workspace page already redirects to the
    // login screen on a 401, so signing in again silently repairs it.
    if (res.status === 401) {
      return new Response(JSON.stringify({ signedIn: false, error: "token_expired" }), {
        status: 401,
        headers: NO_STORE_HEADERS,
      });
    }

    if (res.ok) {
      const all = (await res.json()) as Array<{
        name: string;
        slug: string;
        organization?: { login: string };
      }>;
      teams = all
        .filter((t) => t.organization?.login === cfg.GITHUB_ORG)
        .map((t) => ({
          name: t.name,
          slug: t.slug,
          // Convention, not a lookup: the team's repository is named after the
          // team. One less thing to store, and it cannot go stale.
          //
          // THIS LINE IS THE ONLY PLACE THE SYSTEM SAYS WHO OWNS TEAM WORK, AND
          // THREE LEGAL DOCUMENTS DEPEND ON THE ANSWER.
          //
          // Repositories live under the ORGANISATION, not under participants'
          // personal accounts. That is what makes the safeguarding position
          // workable: the Organiser holds admin, so it can moderate issues and
          // pull requests, take a repository down on a young person's behalf,
          // and create it private from the outset if the Designated
          // Safeguarding Lead decides a team containing a minor should not work
          // in public.
          //
          // If provisioning is ever changed to create repositories under
          // participants' own accounts, the Code of Conduct (section 7), the
          // IP, Media & Consent Policy (2.3 and the parental consent form) and
          // the Participant Privacy Notice all become false in the same breath,
          // because each states what the Organiser can do about published work.
          // Change this line and those documents must be amended with it.
          //
          // What org ownership does NOT buy: control over clones, forks,
          // mirrors and archives that other people have already taken. Deleting
          // the original never reaches those, which is why the notices promise
          // prompt action rather than removal.
          repo: `https://github.com/${cfg.GITHUB_ORG}/${t.slug}`,
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
      user: { login: session.login, name: session.name },
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
