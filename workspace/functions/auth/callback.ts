/**
 * GitHub OAuth callback. Exchanges the code, verifies org membership, and issues
 * the session cookie.
 *
 * ORG MEMBERSHIP IS THE ACCESS CONTROL
 * -------------------------------------
 * There is no user table to consult, so "may this person in" is answered by
 * GitHub: are they a member of the organisation? That means access is granted
 * and revoked in one place, by the same people who manage the repositories, and
 * there is no second list to drift out of step with the first.
 */
import { sign, cookieHeader, readCookie } from "../../src/lib/session";

interface Env {
  GITHUB_CLIENT_ID: string;
  GITHUB_CLIENT_SECRET: string;
  SESSION_SECRET: string;
  GITHUB_ORG: string;
}

const UA = "if-hackathon-workspace";

function fail(origin: string, reason: string): Response {
  const to = new URL("/", origin);
  to.searchParams.set("error", reason);
  return new Response(null, {
    status: 302,
    headers: { Location: to.toString(), "Cache-Control": "private, no-store" },
  });
}

export const onRequestGet: PagesFunction<Env> = async ({ request, env }) => {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");

  const expected = (request.headers.get("Cookie") || "")
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith("if_oauth_state="))
    ?.slice("if_oauth_state=".length);

  if (!code) return fail(url.origin, "no_code");
  if (!state || !expected || state !== expected) return fail(url.origin, "bad_state");

  const tokenRes = await fetch("https://github.com/login/oauth/access_token", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json", "User-Agent": UA },
    body: JSON.stringify({
      client_id: env.GITHUB_CLIENT_ID,
      client_secret: env.GITHUB_CLIENT_SECRET,
      code,
      redirect_uri: `${url.origin}/auth/callback`,
    }),
  });

  const tokenJson = (await tokenRes.json()) as { access_token?: string; error?: string };
  if (!tokenJson.access_token) return fail(url.origin, tokenJson.error || "no_token");
  const token = tokenJson.access_token;

  const ghHeaders = {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "User-Agent": UA,
  };

  const userRes = await fetch("https://api.github.com/user", { headers: ghHeaders });
  if (!userRes.ok) return fail(url.origin, "user_lookup_failed");
  const user = (await userRes.json()) as { login: string; name?: string; avatar_url?: string };

  // 204 = member, 302/404 = not. Checked with the USER's token so it reflects
  // their own visibility rather than an elevated one.
  const memberRes = await fetch(
    `https://api.github.com/user/memberships/orgs/${env.GITHUB_ORG}`,
    { headers: ghHeaders },
  );
  if (!memberRes.ok) return fail(url.origin, "not_a_member");
  const membership = (await memberRes.json()) as { state?: string };
  if (membership.state !== "active") return fail(url.origin, "membership_pending");

  const value = await sign(
    {
      login: user.login,
      name: user.name || user.login,
      avatar: user.avatar_url || "",
      token,
    },
    env.SESSION_SECRET,
  );

  return new Response(null, {
    status: 302,
    headers: [
      ["Location", new URL("/workspace/", url.origin).toString()],
      ["Set-Cookie", cookieHeader(value)],
      // Clear the CSRF state cookie now it has been used.
      ["Set-Cookie", "if_oauth_state=; Path=/auth; HttpOnly; Secure; SameSite=Lax; Max-Age=0"],
      ["Cache-Control", "private, no-store"],
    ],
  });
};
