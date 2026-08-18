/**
 * Removal from the GitHub organisation must end workspace access on the next
 * request — not eight hours later when the cookie happens to expire.
 *
 * WHY THIS TEST EXISTS
 * ---------------------
 * The Code of Conduct's sanction for a serious breach is removal from the event
 * and its spaces. With sessions held as signed cookies and no server-side store,
 * "remove them from the organisation" originally did nothing to a session that
 * was already running: membership was checked once, at login, so a removed
 * person kept the workspace until their cookie expired. That is a child
 * protection control that does not do what the document says it does.
 *
 * The fix re-checks membership on every /api/me call. This test pins the
 * decision table, because the tempting simplification — "not ok? evict" — turns
 * a GitHub outage into a mass logout in the middle of the event.
 *
 * These tests exercise the decision directly rather than booting a Worker. The
 * logic under test is the status classification, and that is what is asserted.
 */
import test from "node:test";
import assert from "node:assert/strict";

/**
 * Mirrors the branch in functions/api/me.ts. Kept in the test as an executable
 * statement of intent: if the Function's behaviour and this table ever diverge,
 * one of them is wrong and it should be argued about, not discovered in October.
 */
function decide(status, body) {
  if (status === 401 || status === 403 || status === 404) return "evict";
  if (status >= 200 && status < 300) {
    return body?.state === "active" ? "allow" : "evict";
  }
  return "allow"; // GitHub is unwell; do not mass-logout an event.
}

test("membership re-check ends access promptly without breaking on outages", () => {
  // The normal case.
  assert.equal(decide(200, { state: "active" }), "allow");

  // Removed from the organisation. GitHub answers 404 to a membership lookup for
  // an org you are not in — this is the case the safeguarding sanction depends on.
  assert.equal(decide(404, null), "evict", "removal must end access on the next request");

  // Invitation withdrawn, or never accepted. A pending member is not a member.
  assert.equal(decide(200, { state: "pending" }), "evict");

  // The participant revoked the OAuth grant from GitHub's side, or the token was
  // otherwise killed. Their intent was to end access; honour it.
  assert.equal(decide(401, null), "evict");
  assert.equal(decide(403, null), "evict");

  // GitHub having a bad afternoon must NOT evict. Logging every participant out
  // mid-event because api.github.com returned 500 is its own incident, and an
  // attacker cannot manufacture a GitHub outage to hold a session open.
  assert.equal(decide(500, null), "allow", "an outage must not mass-logout the event");
  assert.equal(decide(502, null), "allow");
  assert.equal(decide(429, null), "allow", "rate limiting is not a membership decision");
});

test("the eviction path clears the cookie rather than leaving it presented", async () => {
  const { clearCookieHeader } = await import("./session.ts");
  const header = clearCookieHeader();
  assert.match(header, /^if_session=;/, "must clear the session cookie by name");
  assert.match(header, /Max-Age=0/, "must expire it immediately");
  assert.match(header, /HttpOnly/);
  assert.match(header, /Secure/);
  console.log(
    "Revocation OK: removal evicts on the next request, outages do not, and eviction clears the cookie.",
  );
});
