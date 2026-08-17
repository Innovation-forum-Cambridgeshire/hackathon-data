// Session security assertions. Run: node --experimental-strip-types src/lib/session.test.mjs
//
// This is the only security-critical code in the workspace: the cookie is what
// stands between "signed in as me" and "signed in as anyone". Every assertion
// here is a way a forged or stale cookie could get accepted.
import { sign, verify, cookieHeader, clearCookieHeader } from "./session.ts";

const SECRET = "test-secret-not-the-real-one";
const OTHER = "a-different-secret";
const fails = [];
const check = (label, cond) => { if (!cond) fails.push(label); };

const base = { login: "octocat", name: "The Octocat", token: "gho_TESTTOKEN" };

// 1. Round trip
const good = await sign(base, SECRET);
const back = await verify(good, SECRET);
check("a validly signed session verifies", back !== null);
check("payload survives the round trip", back?.login === "octocat" && back?.token === "gho_TESTTOKEN");
check("expiry is set in the future", (back?.exp ?? 0) > Math.floor(Date.now() / 1000));

// 2. Wrong key must fail — otherwise anyone who can guess the format is in.
check("a session signed with another secret is rejected", (await verify(good, OTHER)) === null);

// 3. Tampering with the payload must fail. This is the real attack: change the
//    login to someone else's and keep the old signature.
const [body, sig] = good.split(".");
const tampered = Buffer.from(JSON.stringify({ ...base, login: "someone-else", iat: 1, exp: 9999999999 }))
  .toString("base64url");
check("a tampered payload is rejected", (await verify(`${tampered}.${sig}`, SECRET)) === null);

// 4. Truncated / malformed input must not throw, and must not pass.
for (const bad of ["", ".", "notasession", body, `${body}.`, `.${sig}`]) {
  check(`malformed input ${JSON.stringify(bad.slice(0, 12))} is rejected`, (await verify(bad, SECRET)) === null);
}

// 5. An expired session must be rejected even though the signature is valid.
//    Signature validity and freshness are different questions.
const expired = await sign(base, SECRET);
const [eb] = expired.split(".");
const past = Buffer.from(JSON.stringify({ ...base, iat: 1, exp: 2 })).toString("base64url");
const { subtle } = globalThis.crypto;
const k = await subtle.importKey("raw", new TextEncoder().encode(SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
const psig = Buffer.from(await subtle.sign("HMAC", k, new TextEncoder().encode(past))).toString("base64url");
check("an expired but correctly signed session is rejected", (await verify(`${past}.${psig}`, SECRET)) === null);

// 6. Cookie attributes. Each of these has a specific failure it prevents.
const c = cookieHeader("abc");
check("cookie is HttpOnly (token unreachable from JS)", c.includes("HttpOnly"));
check("cookie is Secure (never sent over http)", c.includes("Secure"));
check("cookie is SameSite=Lax (survives the OAuth redirect back)", c.includes("SameSite=Lax"));
check("cookie is not SameSite=Strict", !c.includes("SameSite=Strict"));
check("logout clears with Max-Age=0", clearCookieHeader().includes("Max-Age=0"));

if (fails.length) {
  console.error("Session security FAILED:");
  for (const f of fails) console.error("  - " + f);
  process.exit(1);
}
console.log("Session security OK: signing, tamper rejection, expiry, malformed input, and cookie flags all verified.");
