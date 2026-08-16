/**
 * Start the GitHub OAuth flow.
 *
 * Scopes are deliberately minimal: `read:org` to see which team you are in, and
 * `read:user` for a display name. NOT `repo` — the workspace never writes to a
 * participant's repository on their behalf. They push with their own git client,
 * which also means each participant carries their own API rate-limit budget
 * rather than everyone sharing one token at 15:55 on the Friday.
 */
import { ConfigError, configErrorResponse, requireEnv } from "../../src/lib/config";

interface Env {
  GITHUB_CLIENT_ID: string;
  SESSION_SECRET: string;
}

const SCOPES = "read:user read:org";

export const onRequestGet: PagesFunction<Env> = async ({ request, env }) => {
  const url = new URL(request.url);

  // Checked BEFORE the redirect is built. An unset client_id produces
  // `client_id=undefined`, which GitHub answers with its own error page on its
  // own domain — the participant is now off our site, reading a message we did
  // not write, with no link back. Better to fail here where we can say
  // something useful.
  let cfg: Record<"GITHUB_CLIENT_ID", string>;
  try {
    cfg = requireEnv(env as unknown as Record<string, unknown>, ["GITHUB_CLIENT_ID"] as const);
  } catch (err) {
    if (err instanceof ConfigError) return configErrorResponse(err);
    throw err;
  }

  // CSRF: a random state, stashed in a short-lived cookie and compared on the
  // way back. Without it an attacker can complete a login flow in someone
  // else's browser and bind their session to an attacker-controlled account.
  const state = crypto.randomUUID();

  const authorize = new URL("https://github.com/login/oauth/authorize");
  authorize.searchParams.set("client_id", cfg.GITHUB_CLIENT_ID);
  authorize.searchParams.set("redirect_uri", `${url.origin}/auth/callback`);
  authorize.searchParams.set("scope", SCOPES);
  authorize.searchParams.set("state", state);
  authorize.searchParams.set("allow_signup", "true");

  return new Response(null, {
    status: 302,
    headers: {
      Location: authorize.toString(),
      "Set-Cookie": `if_oauth_state=${state}; Path=/auth; HttpOnly; Secure; SameSite=Lax; Max-Age=600`,
      "Cache-Control": "private, no-store",
    },
  });
};
