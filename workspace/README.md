# Participant workspace

Sign in with GitHub · see your team, your repository, your board · countdown to the
submission deadline.

**Status: built, not deployed, and not open to participants.** See "Before this can
go live" — one of those items is a hard blocker, not a formality.

---

## What it is

A static site plus four Cloudflare Pages Functions. **There is no database.**

```
public/index.html            sign-in page
public/workspace/index.html  your team, your links, the countdown
functions/auth/login.ts      redirect to GitHub
functions/auth/callback.ts   exchange code, check org membership, issue session
functions/auth/logout.ts     clear session
functions/api/me.ts          who am I, which team, when is the deadline
src/lib/session.ts           HMAC-signed cookie
src/lib/countdown.ts         event timing, UTC in and Europe/London out
```

Everything else is native GitHub: teams are **GitHub Teams**, the workspace is the
team's **repository**, the board is a **GitHub Project**, and a submission is
whatever is on `main` at the deadline. See `docs/KDD-D7-github-as-sole-identity.md`
for why there is no database, and what that buys.

### Two design points worth not undoing

**The GitHub token never reaches JavaScript.** It lives inside the HttpOnly
session cookie and is used only by Functions. Pages call `/api/me`, which proxies
GitHub. An XSS bug therefore cannot walk away with a token that grants repository
access.

**Org membership is the access control.** There is no user table to consult and
none to drift out of step with reality. Adding someone to the org and a team is
the whole of onboarding; removing them is the whole of offboarding.

---

## Before this can go live

### Blocker — the workspace is outside every published notice

The Cookie Policy says, in terms:

> "The Website is the hackathon microsite at `https://r1x.co.uk/public_hackathon/`
> and its pages (including /apply, /challenges, /insights and /sponsorship)."

The Privacy Policy adds:

> "The only place on the Website where we deliberately collect personal data is
> the registration form on the /apply page."

A workspace on a different origin, that sets a session cookie and sends a GitHub
handle to a US processor, is covered by **none** of that. The register already
tracks this as `PROG-DOC-04 — Subdomain privacy and cookie wording — Not started`.

**So: no participant signs in until the workspace has its own privacy notice and
the Privacy Policy and Terms are amended.** Organiser testing is fine — that is
staff processing their own data internally.

Amend the **Word masters**, then re-run `scripts/legal-from-docx.py`. Editing
`legal.json` is overwritten.

### Also outstanding

| | Why it blocks |
|---|---|
| **DPIA** | Mandatory: novel processing, children's data if 17-year-olds attend, systematic monitoring |
| **Governance roles** | Data Owner, DPO, SIRO, Safeguarding lead all TBC — nobody can sign the above off |
| **Art 28 DPAs** | GitHub's and Cloudflare's standard DPAs need accepting and filing. Adequacy covers the *transfer*; it does not create the *processor* contract |
| **D6 — minimum age** | Decides whether the children's regime applies at all |

**Not** outstanding, which is the good news: no transfer risk assessment is needed.
GitHub and Cloudflare are both certified under the **UK Extension to the EU-US Data
Privacy Framework**, so the transfers are covered by UK adequacy regulations.
Verify both certifications are **live at the time of reliance** — a lapse silently
removes the basis.

---

## Deploying it (organiser-only, closed)

Two things must be created by a human with the right access. Neither can be
scripted from here.

### 1. A GitHub OAuth App

Org **Settings → Developer settings → OAuth Apps → New**:

| Field | Value |
|---|---|
| Application name | `Innovation Forum Workspace` |
| Homepage URL | your Pages URL |
| Authorization callback URL | `<pages-url>/auth/callback` |

Note the **Client ID**, generate a **Client secret**.

Scopes are requested at runtime and are deliberately minimal — `read:user` and
`read:org`. **Not `repo`**: the workspace never writes to a participant's
repository. They push with their own git client, which also means each person
carries their own API rate-limit budget rather than everyone sharing one token at
15:55 on the Friday.

### 2. A Cloudflare Pages project

Connect the repo, set the build output directory to `workspace/public`, and add
these under **Settings → Environment variables**:

| Variable | Type |
|---|---|
| `GITHUB_CLIENT_ID` | plain |
| `GITHUB_CLIENT_SECRET` | **encrypted** |
| `SESSION_SECRET` | **encrypted** — `openssl rand -base64 48` |
| `GITHUB_ORG` | plain — `Innovation-forum-Cambridgeshire` |

The last two must be marked secret. Note the contrast with the marketing site,
where every variable is `PUBLIC_` by design because those values genuinely are
public identifiers. **Here two of them are real secrets.**

---

## Tests

```bash
node --experimental-strip-types src/lib/session.test.mjs
node src/lib/countdown.test.mjs
```

**`session.test.mjs`** is the security test. It asserts that a session signed with
a different secret is rejected, that a **tampered payload carrying a valid old
signature** is rejected — the actual attack — that an expired-but-validly-signed
session is rejected, that malformed input does not throw, and that the cookie is
`HttpOnly`, `Secure` and `SameSite=Lax`.

`SameSite=Lax` rather than `Strict` is deliberate and is asserted: the OAuth
callback is a cross-site top-level navigation back from github.com, and `Strict`
drops the cookie on exactly that hop — producing a login that appears to succeed
and silently is not signed in.

**`countdown.test.mjs`** exists because **BST ends on Sunday 25 October 2026, the
day before the event starts.** A deadline written as "16:00" with no zone, or a
countdown built from a local-time string, is an hour wrong for the whole event —
in the direction that closes submissions early. The test asserts the deadline
renders as `16:00 GMT`, and that 24 October is still BST while 26 October is GMT.

The published rules must say **"16:00 GMT"**, not "16:00".
