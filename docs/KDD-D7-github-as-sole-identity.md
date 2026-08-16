# D7 — GitHub as the sole identity provider, and dropping Supabase

**Status:** RECOMMENDED — reverses part of an earlier decision. Raised 2026-08-16.
**Decides:** where authentication and application state live.
**Supersedes:** the Supabase Auth (London) element of the workspace design.

---

## Why this is being revisited

Supabase Auth in London was chosen on 2026-08-16 for a good reason — UK data
residency. **The transfer research that came afterwards changed the picture**, and
it changed it in the opposite direction to the one everyone expected.

Verified in each vendor's own words:

| Vendor | UK Extension to the EU-US DPF | Consequence |
|---|---|---|
| **GitHub** | *"GitHub has certified… from the United Kingdom (and Gibraltar) in reliance on the UK Extension to the EU-U.S. DPF"* | **adequacy — no IDTA, no TRA** |
| **Cloudflare** | certified under the UK Extension | **adequacy — no IDTA, no TRA** |
| **Supabase** | **not registered**; relies on SCCs + UK Addendum | **IDTA + a full TRA required** |

The ICO's position is that *"you do not need to carry out a TRA if you are making
a transfer to any country covered by UK adequacy regulations"*, and **the UK
Extension is the UK's adequacy regulation for the US**.

So the component chosen *for* data residency is the only one in the stack that
creates a transfer assessment. London hosting does not change that: Supabase Inc
is a US entity with its own sub-processor chain, and the transfer is to the
organisation, not the datacentre.

---

## What Supabase was carrying, and where each piece goes instead

| Need | With Supabase | Without it |
|---|---|---|
| Identity | Supabase Auth (GitHub provider) | **GitHub OAuth** directly |
| Session | Supabase session | **signed cookie (JWT)** — no storage |
| Team membership | `teams`, `team_members` | **GitHub org Teams** — native |
| Team workspace | `repo_url` pointer | GitHub repos |
| Task board | `project_id` pointer | GitHub Projects |
| Submission | `submissions` table | **git tag / release** |
| Rubric | `criteria` table | `rubric/rubric.yml` — **already built** |
| Scores | `scores` table | files in the **private** organisers repo |
| Audit log | `audit_log` table | **git history** |

Two of those are better rather than merely equivalent:

**Git history *is* the append-only audit log.** The design review required scores
to be append-only for dispute defensibility. Git gives that for free and makes
tampering visible, which a database column does not.

**GitHub Issue Forms could be the judge UI.** Structured YAML forms with
validation, native, free, producing an issue in the private repo with full edit
history. That removes a custom scoring screen from the build entirely.

---

## What this gains

1. **Zero transfer risk assessments.** Both remaining processors are covered by UK
   adequacy.
2. **One fewer processor** on the register — and one fewer run through the Data
   Flow Register's 8-step onboarding, each of which needs an Art 28 DPA before
   go-live.
3. **No RLS security model.** The review's sharpest technical warning was that
   Supabase's anon key is public by design and *"one table with RLS disabled means
   the full participant list is world-readable"*. That entire class of risk
   disappears with the database.
4. **No email delivery.** The top-ranked event-day failure mode was Supabase's
   built-in mailer being rate-limited to a handful per hour, against ~100 logins
   at 09:00 on Monday. OAuth has no email step.
5. **No credential storage of any kind** — no passwords, no magic-link tokens.
6. **No project pausing and no backup gap.** Free Supabase pauses after ~7 days
   idle and has no automated backup; losing the scores table would have been
   unrecoverable. Git is replicated by every clone.
7. **Materially less to build** in the weeks that are actually available.

## What this loses — stated honestly

1. **No queryable database.** Reporting becomes GitHub API calls. Acceptable
   because `scripts/programme-report.py` already does exactly that, but any future
   need for ad-hoc querying means adding something back.
2. **Fixed shapes.** GitHub Teams and Projects model what they model. Anything
   that does not fit has no home — the fallback is **Cloudflare D1**, which is
   also covered by adequacy, so the escape hatch costs no new assessment.
3. **We cannot help a locked-out user.** Account recovery becomes GitHub's
   problem. That was equally true of Supabase email, and the mitigation is the
   same: the mandatory T-3 check-in where everyone logs in once.

## Risks and how they are handled

- **The OAuth client secret needs a server-side home.** Cloudflare Pages Functions
  support encrypted secrets — confirmed. This is the only server-side surface.
- **Pages Functions carry the cache-poisoning class** that disqualified the
  marketing site. Narrow here: the OAuth callback only, with
  `Cache-Control: private, no-store`. Everything else is client-rendered.
- **Single point of failure.** If GitHub is down nobody signs in — but the repos
  and boards are down too, so the event is stopped regardless. This adds no new
  failure mode; it removes one by deleting a second dependency.
- **API rate limits** for reading team and board state: 5,000/hour per user token,
  read via the signed-in user's own token so the budget is per-person rather than
  pooled. Cache aggressively during the event.

---

## Recommendation

**Adopt.** Drop Supabase entirely; GitHub OAuth is the sole identity provider and
GitHub is the system of record.

This only became the right answer once participants each held a GitHub account
(decided 2026-08-16). Before that, GitHub-only auth was impossible and Supabase
was the correct call. **It is a consequence of that decision, not a reversal of
the reasoning behind it.**

The workspace shrinks to: sign in with GitHub · see your team, your repository,
your board and the countdown · organisers see the roster and provisioning state.
Everything else is native GitHub.

## Consequences to action

- Remove Supabase from the processor onboarding queue (#90) — that item becomes
  **verify two DPF certifications are current**, not three assessments.
- The privacy notice still needs GitHub and Cloudflare added as recipients; it is
  a shorter list than planned but the amendment is still required (#92).
- The workspace data model in the plan is deleted rather than rewritten.
- Confirm GitHub's certification is **live on the DPF list at the time of
  reliance** — a lapsed certification silently removes the adequacy basis, so this
  is a check to repeat, not a fact to file.
