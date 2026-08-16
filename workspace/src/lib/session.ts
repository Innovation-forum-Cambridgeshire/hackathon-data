/**
 * Session handling. An HMAC-signed cookie and nothing else.
 *
 * WHY THERE IS NO SESSION STORE
 * ------------------------------
 * D7 removed the database. A session here is a signed JSON payload in a cookie:
 * nothing to pause, nothing to back up, nothing to leak if a row-level-security
 * policy is written wrongly, and no third processor to put through Article 28
 * onboarding. The cost is that sessions cannot be revoked server-side before they
 * expire, which is why the lifetime is short and why the GitHub token inside it
 * is the only thing of value — revoking the OAuth grant on GitHub kills it at
 * source.
 *
 * WHY THE GITHUB TOKEN NEVER REACHES JAVASCRIPT
 * ---------------------------------------------
 * The access token lives inside the HttpOnly cookie and is used only by Functions
 * running server-side. The browser never sees it, so an XSS bug cannot exfiltrate
 * a token that would grant write access to a participant's repositories. Pages
 * fetch `/api/me`, which proxies GitHub using the token from the cookie.
 *
 * WHY HMAC AND NOT ENCRYPTION
 * ----------------------------
 * The payload is signed, not encrypted, so it is readable by anyone holding the
 * cookie. That is deliberate and safe here ONLY because the cookie is HttpOnly
 * and Secure — the holder is the browser it was issued to. Signing prevents
 * tampering, which is the actual threat: a forged cookie claiming a different
 * GitHub login. If anything genuinely secret ever needs to live in a session,
 * this must become AES-GCM rather than staying HMAC and hoping.
 */

const COOKIE_NAME = "if_session";

// Deliberately short. With no server-side revocation, lifetime IS the revocation
// window. Eight hours covers a working day of the event without carrying a live
// GitHub token around for a week.
const MAX_AGE_SECONDS = 8 * 60 * 60;

export interface Session {
  login: string; // GitHub login
  name: string;
  avatar: string;
  token: string; // GitHub access token — never sent to the browser
  iat: number;
  exp: number;
}

const enc = new TextEncoder();

function b64urlEncode(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlDecode(s: string): Uint8Array {
  const pad = s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4);
  const raw = atob(pad);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

async function key(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

export async function sign(session: Omit<Session, "iat" | "exp">, secret: string): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const payload: Session = { ...session, iat: now, exp: now + MAX_AGE_SECONDS };
  const body = b64urlEncode(enc.encode(JSON.stringify(payload)));
  const sig = await crypto.subtle.sign("HMAC", await key(secret), enc.encode(body));
  return `${body}.${b64urlEncode(new Uint8Array(sig))}`;
}

export async function verify(value: string, secret: string): Promise<Session | null> {
  const dot = value.lastIndexOf(".");
  if (dot < 1) return null;

  const body = value.slice(0, dot);
  const sig = value.slice(dot + 1);

  // crypto.subtle.verify is constant-time, which matters: a hand-rolled string
  // comparison of the signature leaks it a byte at a time under timing analysis.
  const ok = await crypto.subtle.verify(
    "HMAC",
    await key(secret),
    b64urlDecode(sig),
    enc.encode(body),
  );
  if (!ok) return null;

  try {
    const session = JSON.parse(new TextDecoder().decode(b64urlDecode(body))) as Session;
    if (typeof session.exp !== "number" || session.exp < Math.floor(Date.now() / 1000)) {
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export function cookieHeader(value: string): string {
  // SameSite=Lax rather than Strict: the OAuth callback is a cross-site
  // top-level navigation back from github.com, and Strict would drop the cookie
  // on exactly that hop, producing a login that appears to succeed and then
  // silently is not signed in.
  return [
    `${COOKIE_NAME}=${value}`,
    "Path=/",
    "HttpOnly",
    "Secure",
    "SameSite=Lax",
    `Max-Age=${MAX_AGE_SECONDS}`,
  ].join("; ");
}

export function clearCookieHeader(): string {
  return `${COOKIE_NAME}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`;
}

export function readCookie(request: Request): string | null {
  const header = request.headers.get("Cookie");
  if (!header) return null;
  for (const part of header.split(";")) {
    const [k, ...rest] = part.trim().split("=");
    if (k === COOKIE_NAME) return rest.join("=");
  }
  return null;
}

export async function currentSession(request: Request, secret: string): Promise<Session | null> {
  const raw = readCookie(request);
  return raw ? verify(raw, secret) : null;
}

/**
 * Every authenticated response carries these.
 *
 * `private, no-store` is not optional. Cloudflare Pages sits behind an edge
 * cache, and this is the same failure class that disqualified the marketing site
 * from hosting the workspace at all: a shared cache keyed on URL will happily
 * hand one participant's response to the next one.
 */
export const NO_STORE_HEADERS: Record<string, string> = {
  "Cache-Control": "private, no-store, max-age=0, must-revalidate",
  "Content-Type": "application/json; charset=utf-8",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "same-origin",
};
