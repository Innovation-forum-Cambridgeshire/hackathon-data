# Setup

Everything that can be scripted is scripted. This covers the parts that need a browser,
and why the platform choices are what they are.

---

## The shape

| Plane | Where | Who touches it | Cost |
|---|---|---|---|
| **Participants** | Public GitHub repo + **Releases** | ~100 external people, no accounts | £0 — no bandwidth quota |
| **Organisers** | **GitHub Projects** + private repo | The programme team | £0 — unlimited private repos |
| **Build** | **GitHub Actions** | CI | £0 — unlimited minutes on public repos |
| **Edge** | Cloudflare Worker | Nobody, it just runs | £0 — free tier |

One platform for everything except the edge. Total: **£0**.

The governing principle: **anonymous access is the only model that scales to ~100 external
participants with zero onboarding.** Every failure mode in the alternatives — guest
invites, licences, credential distribution, a support queue on day one — is a symptom of
requiring identity.

---

## Why not Azure DevOps

Azure DevOps was the first choice for the organiser plane and was dropped for a hard
blocker, not a preference. Recording it so nobody spends the afternoon rediscovering it.

**Creating an Azure DevOps organisation on a work account requires linking an Azure
subscription for billing.** Verified in the browser 2026-08-15: the signup form offers no
"none" option and refuses with

> You need to be an owner or contributor on the subscription to set up billing.

Yavin holds no role on either R1X subscription — Keith Brown is sole Owner of both
(`2ed3ad81…` billed personally, `269b5f4f…` billed to R1X). The plain `/signup/` route
enforces the same rule.

**To be fair to it: linking a subscription would not have cost anything.** The free tier
persists — 5 Basic users, unlimited Stakeholders, unlimited private repos. This was a
*permissions* blocker, not a cost one. But taking a dependency on another person at step
one, for a programme with a hard October date, was the wrong trade.

Three further facts made the decision easy rather than reluctant:

1. **Public Azure DevOps projects are retired.** New ones cannot be created and existing
   ones convert to private in 2027. Microsoft's own documented migration path is *to
   GitHub*. So Azure DevOps could never have hosted anything participant-facing.
2. **Azure Artifacts is 2 GiB free and authenticated** — it cannot serve the data payload.
   GitHub Releases has no total-size cap and no bandwidth quota.
3. **Private ADO projects need that same subscription link to get free pipeline minutes**,
   whereas GitHub Actions is free and unlimited on public repos.

GitHub Projects gives boards, iterations, custom fields and roadmap views for free, with
no 5-user cap, sitting next to the data and the CI.

---

## 1. GitHub — one-off

```bash
brew install gh              # not installed on this Mac as of 2026-08-15
gh auth login
gh auth refresh -s project,read:project    # Projects v2 needs its own scope
```

That extra scope is easy to miss — without it the project steps fail with a permissions
error while everything else succeeds.

## 2. Public participant repo

```bash
./scripts/setup-github.sh --dry-run
./scripts/setup-github.sh
```

Creates the public `Innovation-forum-Cambridgeshire/hackathon-data`, sets options, adds
triage labels for participant-reported data problems, and pushes this scaffold.

> The org already exists and had no public repos — verified 2026-08-15. It is outside the
> R1X tenant, r1x.co.uk already has access, and it is owned by an organisation rather than
> an individual, which avoids the continuity problem a personal account would carry.

## 3. Organiser plane

```bash
./scripts/setup-github-project.sh --dry-run
./scripts/setup-github-project.sh
```

Creates the private `hackathon-organisers` repo, a **Hackathon Programme** project board,
and issues for the six delivery epics, the three open decisions (D2–D4) and the two
standing governance rules — each added to the board.

Split by audience, not by wrapping everything in auth: the participant repo is public so
every tool works with no credentials; judging rubrics, scores, DPIA papers and
sponsor-confidential material live in the private one.

## 4. Cloudflare Worker — the bit that makes browsers work

### Why it is not optional

GitHub release asset URLs are a 302 to an S3 blob. **CORS pre-flight does not follow
redirects, and the blob sends no `Access-Control-Allow-Origin`.** So every browser-based
tool fails against a raw release URL — DuckDB-WASM, Observable, any JS charting library.
That is exactly the zero-install path the programme promises to non-coders.

The Worker terminates the pre-flight itself, follows the redirect server-side, and
re-emits the bytes with CORS. It also forwards Range requests, so DuckDB reads one column
of a remote parquet instead of downloading the file, and caches at the edge to absorb the
event-morning spike.

It also gives branded, stable URLs — nothing participants bookmark names the hosting
account, so the org underneath can change without breaking a link.

```bash
cd worker
npx wrangler login
npx wrangler deploy
```

Needs the `inno-forum.co.uk` zone in Cloudflare. If DNS is elsewhere, move the zone or
point a `data` CNAME at the Worker route.

### Acceptance test — from a real browser, not curl

`curl` does not enforce CORS, so it passes whether or not the Worker is working. Open
devtools on a page on a **different** origin:

```js
fetch('https://data.inno-forum.co.uk/manifest.json')
  .then(r => r.json()).then(console.log)
```

JSON back means the participant plane works.

## 5. First release

```bash
pip install -r build/requirements.txt
python build/build.py validate --challenge c03-beyond-the-mainframe
python build/build.py build --challenge c03-beyond-the-mainframe --version v2026-10-01 --out dist/
```

Then **Actions → Build and publish challenge data → Run workflow**, `dry_run` ticked the
first time. Versions are immutable — the workflow refuses to overwrite an existing tag,
because judging must be reproducible against a frozen corpus.

---

## What blocks what

| Blocker | Blocks | Owner |
|---|---|---|
| **D4 licence review** (AHDB, Copernicus, DERI) | Mirroring any third-party bytes | Not a technical task |
| `gh` not installed | Both setup scripts | `brew install gh` |
| Cloudflare zone access | Worker deploy, all browser tooling | Whoever holds inno-forum.co.uk DNS |
| Sponsor contact | Challenge 03 data | Programme |

**Nothing is blocked on Keith or on an Azure subscription.** That was the point.

The build runs today with D4 outstanding: it publishes the catalogue, manifest and
documents, and mirrors only the two CC0 synthetic datasets we author ourselves. Correct
behaviour, not a degraded mode.
