# Participant workspace

Sign in with GitHub · see your team, your repository, your board · countdown to the
submission deadline.

**Status: built, not deployed, and not open to participants.** See "Before this can
go live" — one of those items is a hard blocker, not a formality.

---

## What it is

A static site plus six Cloudflare Pages Functions. **There is no database.**

```
public/index.html               sign-in page
public/workspace/index.html     the workspace shell
public/workspace/app.css        design layer — IF palette, square corners, Barlow
public/workspace/app.js         sign-in state, hash routing, the panels
public/workspace/notebook-view.js  .ipynb -> DOM, builds nodes and never markup
public/fonts/                   Barlow, Barlow Condensed, IBM Plex Mono (self-hosted)
functions/auth/login.ts         redirect to GitHub
functions/auth/callback.ts      exchange code, check org membership, issue session
functions/auth/logout.ts        clear session
functions/api/me.ts             who am I, which team, when is the deadline
functions/api/notebooks.ts      the catalogue of worked examples
functions/api/notebook/[id].ts  one notebook, fetched and stripped server-side
src/lib/session.ts              HMAC-signed cookie
src/lib/countdown.ts            event timing, UTC in and Europe/London out
src/lib/notebooks.ts            the allowlist — the only paths that can be fetched
src/lib/notebook-shape.ts       what the browser is allowed to be given
src/lib/config.ts               fail closed on a misconfigured deploy
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

## The worked examples

The reason a participant opens the workspace at all: the six notebooks in
`sample/notebooks/`, readable in place, with the challenge running this week
listed first.

**The pages never contact GitHub.** `/api/notebook/:id` fetches the file
server-side and hands over a normalised structure. The obvious build — fetching
`raw.githubusercontent.com` from the page — would hand GitHub the participant's
IP address and this origin as a Referer on every notebook opened, which is the
same thing the avatar was removed for, and it would need `connect-src` widened
in `public/_headers`. Fetching in the Function keeps the pages at zero
third-party requests.

**Three controls, and none of them relies on the next one working:**

| | |
|---|---|
| `src/lib/notebooks.ts` | A fixed list of six ids. A request's id is *resolved against* it and never used to build a URL, so a bad id is a 404 with no outbound request — the difference between an allowlist and sanitising an SSRF |
| `src/lib/notebook-shape.ts` | Drops `text/html`, `application/javascript` and SVG **server-side**, so the browser never receives them. Verified against all six notebooks: every HTML output has a `text/plain` alternative — the pandas ASCII table — so refusing HTML costs nothing |
| `public/workspace/notebook-view.js` | Builds nodes with `createElement`/`textContent`. No `innerHTML`, no markup strings, so there is no escaping step to get wrong |

Both halves are tested: `notebook-shape.test.mjs` asserts the dangerous payload
does not appear *anywhere* in the wire output, and `notebook-markdown.test.mjs`
asserts which URLs may become an `href` — including `java\tscript:`, which a
`startsWith` check does not catch.

### Editing, rather than reading

The workspace does not run participant code, and should not start. The buttons
open a copy elsewhere:

* **github.dev** — a full VS Code in the browser, free, no quota.
* **Codespaces** — also runs the code, on the participant's own free monthly
  hours. Same principle as not requesting the `repo` scope: everyone carries
  their own budget rather than sharing one of ours at 15:55 on the Friday.

An in-browser kernel (JupyterLite/Pyodide) was considered and rejected: it needs
`script-src 'unsafe-eval'` on an origin that holds a session cookie, and tens of
megabytes of WASM, to do worse what github.dev does for free.

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
| `NOTEBOOKS_REF` | plain, **optional** — which ref the worked examples are read from. Defaults to `main`. Set it to a tag before the event so what a participant reads on the Friday is what they read on the Monday, and so a push to `main` cannot change a document people are being judged against |

`GITHUB_CLIENT_SECRET` and `SESSION_SECRET` must be marked secret. Note the contrast with the marketing site,
where every variable is `PUBLIC_` by design because those values genuinely are
public identifiers. **Here two of them are real secrets.**

---

## Tests

```bash
npm test
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
