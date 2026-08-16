/**
 * Guards against the fail-open configuration bug found on the first deploy.
 *
 * The headline assertion is the last one: signing with an absent secret must be
 * impossible to do accidentally, because the platform will happily let you sign
 * with the literal string "undefined" and every signature will then verify.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { requireEnv, ConfigError, configErrorResponse } from "./config.ts";
import { sign, verify } from "./session.ts";

const GOOD_SECRET = "d3f2a1b0c9e8d7f6a5b4c3d2e1f0a9b8c7d6e5f4"; // 40 chars

test("config guards fail closed", async () => {
  // Present and valid.
  const ok = requireEnv(
    { GITHUB_CLIENT_ID: "Iv1.abc123", SESSION_SECRET: GOOD_SECRET },
    ["GITHUB_CLIENT_ID", "SESSION_SECRET"],
  );
  assert.equal(ok.GITHUB_CLIENT_ID, "Iv1.abc123");

  // Absent.
  assert.throws(() => requireEnv({}, ["GITHUB_CLIENT_ID"]), ConfigError);

  // Empty and whitespace are not "set".
  assert.throws(() => requireEnv({ A: "" }, ["A"]), ConfigError);
  assert.throws(() => requireEnv({ A: "   " }, ["A"]), ConfigError);

  // The string "undefined" is the one that bit us: a shell interpolating an
  // unset variable produces this, and it passes a naive truthiness check.
  assert.throws(() => requireEnv({ A: "undefined" }, ["A"]), ConfigError);
  assert.throws(() => requireEnv({ A: "null" }, ["A"]), ConfigError);

  // A short secret is a weak secret. Anything named *SECRET* must be long.
  assert.throws(() => requireEnv({ SESSION_SECRET: "hunter2" }, ["SESSION_SECRET"]), ConfigError);

  // Every problem is reported at once, not one failed request at a time.
  try {
    requireEnv({ SESSION_SECRET: "short" }, ["GITHUB_CLIENT_ID", "SESSION_SECRET", "GITHUB_ORG"]);
    assert.fail("should have thrown");
  } catch (err) {
    assert.ok(err instanceof ConfigError);
    assert.equal(err.missing.length, 3, "all three problems reported together");
  }

  // The participant-facing response must not name the variables — that page is
  // read by entrants, and by anyone probing the service.
  const res = configErrorResponse(new ConfigError(["SESSION_SECRET (unset)"]));
  assert.equal(res.status, 503);
  assert.equal(res.headers.get("Cache-Control"), "private, no-store, max-age=0, must-revalidate");
  const body = await res.text();
  assert.ok(!body.includes("SESSION_SECRET"), "must not leak variable names to the browser");
  assert.ok(body.includes("noindex"), "error page must not be indexed");

  const json = await configErrorResponse(new ConfigError(["X (unset)"]), true).json();
  assert.deepEqual(json, { signedIn: false, error: "service_unavailable" });
});

test("a weak-but-present secret is the real risk, and is rejected", async () => {
  // First, what the platform actually does with an ABSENT secret, pinned so the
  // severity is not misremembered later. TextEncoder.encode() defaults its
  // argument to "", so `undefined` yields a ZERO-LENGTH key, and WebCrypto
  // refuses to import that. It throws rather than signing.
  //
  // So an unset variable already failed closed — just opaquely, as a bare 500
  // with nothing in it for the participant or the operator.
  await assert.rejects(
    () => sign({ login: "a", name: "A", avatar: "", token: "x" }, undefined),
    /zero-length key/i,
    "an absent secret throws; it does not silently sign",
  );

  // The dangerous case is narrower and does NOT throw: a secret that is present
  // but guessable. A shell interpolating an unset variable writes the literal
  // text "undefined", and that is a perfectly valid 9-byte HMAC key — it signs,
  // it verifies, and nothing anywhere looks wrong.
  const forged = await sign({ login: "attacker", name: "A", avatar: "", token: "x" }, "undefined");
  const accepted = await verify(forged, "undefined");
  assert.equal(accepted?.login, "attacker", "a placeholder secret produces real, valid sessions");

  // Which is what the guard is for: reject it before it can ever be used as a key.
  assert.throws(() => requireEnv({ SESSION_SECRET: "undefined" }, ["SESSION_SECRET"]), ConfigError);
  assert.throws(() => requireEnv({ SESSION_SECRET: "hunter2" }, ["SESSION_SECRET"]), ConfigError);

  // And a session signed with the real secret must not verify under the weak one.
  const real = await sign({ login: "someone", name: "S", avatar: "", token: "t" }, GOOD_SECRET);
  assert.equal(await verify(real, "undefined"), null, "keys must not be interchangeable");
});
