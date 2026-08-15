# Setup — Azure DevOps + GitHub

Everything that can be scripted is scripted. This document covers the parts that
genuinely need a browser, and explains why the work is split across two platforms
rather than one.

---

## Why the split

| Plane | Platform | Who touches it | Why |
|---|---|---|---|
| **Participants** | Public GitHub repo + Releases | ~100 external people, no accounts | Anonymous access is the only model that scales to a hundred strangers with zero onboarding |
| **Organisers** | Azure DevOps (Boards + private Repos) | ≤5 people | Free for 5 Basic users, unlimited private repos, proper work tracking |
| **Edge** | Cloudflare Worker | Nobody — it just runs | GitHub release assets are not browser-fetchable; see below |

The temptation is to put everything in Azure DevOps. Four verified facts say don't:

1. **Public Azure DevOps projects are retired.** New ones cannot be created, and existing
   ones convert to private in 2027. Microsoft's own documented migration path for them is
   *to GitHub*. So Azure DevOps cannot host anything participant-facing.
2. **Private projects need an Azure subscription link to get free pipeline minutes.**
   Yavin holds no role on either R1X subscription — Keith Brown is sole Owner. Putting the
   build there reintroduces exactly the dependency this design was shaped to avoid.
3. **Azure Artifacts is capped at 2 GiB free and is authenticated.** It cannot serve the
   data payload. GitHub Releases has *no* total-size cap and *no* bandwidth quota.
4. **GitHub Actions is free and unlimited on public repos** — no form, no subscription,
   no waiting.

So Azure DevOps earns its place for Boards and confidential repos, which is genuinely what
its free tier is good at. The build lives next to the Releases it publishes to.

---

## 1. Azure DevOps — organiser plane

### 1a. Create the organisation (browser, one-off)

**This cannot be scripted.** Azure DevOps auto-provisions your user profile on first
sign-in; until then the API returns `VSS011031: There is no profile for the authenticated
user in the system` — verified on this account 2026-08-15, meaning no org exists yet.

1. Open <https://dev.azure.com> and sign in as `yavin.owens@r1x.co.uk`
2. Create an organisation — suggested name `innovation-forum`
3. Region: **UK South** (keeps programme data in-region)

You do **not** need an Azure subscription for this, and you do **not** need Keith. Org
creation is free and available to any Entra user. The subscription only becomes relevant
if you later want Microsoft-hosted pipeline minutes — which this design avoids needing.

### 1b. Run the setup script

```bash
az login
az extension add --name azure-devops        # done already on this Mac
./scripts/setup-azure-devops.sh --org innovation-forum --dry-run   # preview
./scripts/setup-azure-devops.sh --org innovation-forum             # apply
```

Creates a private project, two private repos (`hackathon-organisers`,
`hackathon-sponsors`), seven iterations matching the delivery plan, and Boards items for
every epic and open decision — including **D5**, the parallelism/subscription issue, so it
is tracked rather than rediscovered.

Idempotent: re-running skips anything that already exists.

### 1c. Add people

Free tier is **5 Basic users**, plus **unlimited Stakeholders**. Stakeholders can view and
edit work items but not code — right for sponsors and non-technical programme staff, and
they don't consume a Basic seat.

---

## 2. GitHub — participant plane

### 2a. Prerequisite

```bash
brew install gh && gh auth login    # gh is NOT currently installed on this Mac
```

### 2b. Create and push

```bash
./scripts/setup-github.sh --dry-run
./scripts/setup-github.sh
```

Creates the public `Innovation-forum-Cambridgeshire/hackathon-data` repo, sets sensible
options, adds triage labels for participant-reported data problems, and pushes this
scaffold.

> The org already exists and currently has no public repos — verified 2026-08-15. This
> resolves decision **D1**: it is outside the R1X tenant, r1x.co.uk already has access,
> and it is owned by an organisation rather than an individual, which is what the
> architecture doc recommended over a personal account.

---

## 3. Cloudflare Worker — the bit that makes browsers work

### Why it is not optional

GitHub release asset URLs are a 302 to an S3 blob. CORS pre-flight does not follow
redirects, and the blob sends no `Access-Control-Allow-Origin`. So **every browser-based
tool fails against a raw release URL** — DuckDB-WASM, Observable, any JS charting library.
That is precisely the zero-install path the programme promises to non-coders.

The Worker terminates the pre-flight itself, follows the redirect server-side, and
re-emits the bytes with CORS. It also forwards Range requests, so DuckDB reads one column
of a remote parquet instead of downloading the whole file.

Two things it gives you for free:

- **Branded, stable URLs.** Nothing participants bookmark ever names the hosting account,
  so the GitHub org underneath can change without breaking a link.
- **Edge caching**, which absorbs the event-morning spike.

### Deploy

```bash
cd worker
npx wrangler login
npx wrangler deploy
```

Needs the `inno-forum.co.uk` zone in the Cloudflare account. If DNS is elsewhere, either
move the zone or point a `data` CNAME at the Worker route.

### Acceptance test — do this from a real browser, not curl

`curl` does not enforce CORS, so it will pass whether or not the Worker is doing its job.
Open the devtools console on any page on a **different** origin and run:

```js
fetch('https://data.inno-forum.co.uk/manifest.json')
  .then(r => r.json()).then(console.log)
```

If that returns JSON, the participant plane works. If it throws a CORS error, the Worker
is not in the path.

---

## 4. First release

```bash
pip install -r build/requirements.txt
python build/build.py validate --challenge c03-beyond-the-mainframe
python build/build.py build --challenge c03-beyond-the-mainframe --version v2026-10-01 --out dist/
```

Then via GitHub Actions: **Actions → Build and publish challenge data → Run workflow**,
leaving `dry_run` ticked the first time.

Versions are immutable — the workflow refuses to overwrite an existing tag, because
judging must be reproducible against a frozen corpus.

---

## 5. What blocks what

| Blocker | Blocks | Owner |
|---|---|---|
| **D4 licence review** (AHDB, Copernicus, DERI) | Mirroring any third-party bytes | Not a technical task — needs deciding |
| Azure DevOps org creation | Boards, organiser repos | Yavin, browser, ~5 minutes |
| `gh` not installed | Creating the public repo | `brew install gh` |
| Cloudflare zone access | Worker deploy, browser tooling | Whoever holds inno-forum.co.uk DNS |
| Sponsor contact (C03) | Challenge 03 data | Programme |

Note what is *not* on this list: **nothing is blocked on Keith or on an Azure
subscription.** That was deliberate.

The build already runs today with D4 outstanding — it publishes the catalogue, manifest
and documents, and mirrors only the synthetic datasets we author ourselves under CC0.
That is correct behaviour, not a degraded mode.
