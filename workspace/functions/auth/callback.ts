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
import { ConfigError, configErrorResponse, requireEnv } from "../../src/lib/config";

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

const REQUIRED = [
  "GITHUB_CLIENT_ID",
  "GITHUB_CLIENT_SECRET",
  "SESSION_SECRET",
  "GITHUB_ORG",
] as const;

export const onRequestGet: PagesFunction<Env> = async ({ request, env }) => {
  const url = new URL(request.url);

  // Nothing below may run on a partial configuration. An unset SESSION_SECRET
  // does not throw inside sign() — it signs with the literal string "undefined",
  // producing a session cookie anyone can forge, and every signature still
  // verifies. Fail closed here rather than issue a worthless credential.
  let cfg: Record<(typeof REQUIRED)[number], string>;
  try {
    cfg = requireEnv(env as unknown as Record<string, unknown>, REQUIRED);
  } catch (err) {
    if (err instanceof ConfigError) return configErrorResponse(err);
    throw err;
  }

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
      client_id: cfg.GITHUB_CLIENT_ID,
      client_secret: cfg.GITHUB_CLIENT_SECRET,
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
  // Only two fields are taken from this response, but be clear about what
  // ARRIVES: .json() parses the entire GitHub profile body into memory, and the
  // TypeScript annotation below constrains nothing at runtime. With read:user
  // scope that body can also carry a public email, bio, company and location.
  // We read two fields and let the rest fall out of scope unstored — but the
  // privacy notice must describe what is received, not merely what is kept.
  const user = (await userRes.json()) as { login: string; name?: string };

  // 204 = member, 302/404 = not. Checked with the USER's token so it reflects
  // their own visibility rather than an elevated one.
  const memberRes = await fetch(
    `https://api.github.com/user/memberships/orgs/${encodeURIComponent(cfg.GITHUB_ORG)}`,
    { headers: ghHeaders },
  );
  if (!memberRes.ok) return fail(url.origin, "not_a_member");
  const membership = (await memberRes.json()) as { state?: string };
  if (membership.state !== "active") return fail(url.origin, "membership_pending");

  const value = await sign(
    {
      login: user.login,
      name: user.name || user.login,
      token,
    },
    cfg.SESSION_SECRET,
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
