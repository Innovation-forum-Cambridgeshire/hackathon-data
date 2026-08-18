# D6 — Minimum age, and what it does to the safeguarding perimeter

**Status:** OPEN — needs a decision. Raised 2026-08-16.
**Decides:** the minimum participant age, and therefore whether the children's
regulatory regime applies at all.
**Blocks:** safeguarding sign-off · the DBS position (#86) · the workspace gates
(#88) · registration opening.

---

## The question as asked

> Can the age be increased so safeguarding can be removed?

**Yes — mostly, and it is the single largest simplification available to this
programme.** But "removed" overstates it, and the cost is not administrative.
It is the audience.

---

## Where the load actually comes from

Every one of these triggers on **under 18**, not on 17 specifically:

| Regime | Trigger | What it costs today |
|---|---|---|
| Regulated activity / DBS | a child is under 18 | enhanced DBS + barred-list for mentors and crew — and the **supervision exemption is removed on 1 Sept 2026**, before the event (#86) |
| ICO Children's Code | service likely accessed by under-18s | 15 standards, mandatory DPIA, default high privacy, profiling off |
| OSA children's risk duties | children are users | children's access assessment + children's risk assessment |
| Safeguarding policy | admits minors | parental consent, emergency contacts, ratios, DSL, media consent, moderation rota |

**The whole apparatus exists for a single year of age range.** The published
range is 17–65; the only minors it admits are 17-year-olds.

## What raising to 18 removes

All four rows above. Concretely: no parental consent forms, no emergency-contact
handling, no DSL, no supervision ratios, no DBS for mentors, no Children's Code
assessment, no children's risk assessment, and the moderation requirement drops
to ordinary conduct management.

It also removes the `is_minor` field from the workspace entirely, which was the
field with the worst blast radius if row-level security ever slipped.

## What raising to 18 does NOT remove

Stating these plainly because "safeguarding removed" is the version of this that
gets repeated and it is not accurate:

- **OSA illegal-content duties remain.** They attach to a user-to-user service
  regardless of the users' ages. Smaller than the children's duties, not zero.
- **Adults can be at risk too.** Safeguarding of adults at risk under the Care
  Act 2014 is a separate and lighter regime, but a code of conduct, a reporting
  route and a named person are still needed.
- **The Art 28 gap is untouched.** The IF↔R1X processor agreement does not exist
  and is unrelated to age.
- **DPIA is still required** for the workspace — novel processing and systematic
  monitoring qualify on their own.

## What it costs, and this is the real decision

The event record reads:

> `H03 · Beyond the Mainframe · 26–30 Oct 2026 · "October half-term — returning
> students, data and computing focus"`

**The date was chosen for students.** October half-term is a schools and college
break. An 18+ rule keeps the date and discards the reason for it.

It also cuts against the published position twice over: the site says "open to
all ages", and the stated intent is inclusivity — which is why the 65 upper limit
is being removed as likely Equality Act 2010 exposure. Raising the floor to 18
narrows at the other end.

So the question is not really "can we remove safeguarding". It is:

> **Is this event for students, or not?**

If it is, the safeguarding apparatus is the cost of the audience and needs
building. If it is not, the half-term timing needs revisiting too.

---

## Options

**A · 18+ across the programme.** Cleanest legally, cheapest to run. Abandons the
student audience and the rationale for half-term scheduling. Contradicts the
published "all ages" claim and the inclusivity aim.

**B · 18+ for Challenge 03 only, 17+ from Challenge 04.** Removes the entire
children's regime from the event that is ten weeks away with no safeguarding
apparatus in place, while keeping the under-18 pathway as a deliberate later
capability rather than a quietly abandoned aim. Requires per-event age rules in
the copy and in the workspace, and honest framing so it does not read as a
permanent narrowing.

**C · Keep 17+ and build the apparatus.** Honours the audience and the published
position. Needs, before 26 October: DBS position resolved under the 1 Sept rules,
a named DSL, ratios, parental consent process, a moderation rota, a Children's
Code assessment, and safeguarding-adviser sign-off. All of it is unstarted and
several parts need people who have not been appointed.

**D · All ages with an accompanying adult.** Solves the GitHub account problem —
the adult holds the account — but **enlarges** safeguarding rather than reducing
it. The current policy is written for 17-year-olds; admitting young children needs
a different risk assessment, ratios, insurance and venue position. The under-13
must never *be* the account user, which is a fine line to hold in practice.

---

## Recommendation

**Option B**, and framed as a phasing decision rather than an exclusion.

The reasoning is timing, not principle. Challenge 03 is ten weeks out, the entire
Event-delivery epic is unstarted, and the DBS change lands on 1 September with
enhanced checks taking two to eight weeks. Option C is the right long-run answer
and cannot be delivered safely by 26 October from a standing start.

Option B buys the year needed to build the apparatus properly for Challenge 04
(March 2027) — which is also when a wider age range would first be genuinely
usable, because by then a DSL, ratios and a moderation rota could actually exist.

**If Option B is taken, two things must follow or it is dishonest:** the half-term
framing for Challenge 03 should be dropped from the marketing, and the under-18
pathway should get a named owner and a date rather than becoming permanent
attrition.

---

## Consequences to action once decided

- Age wording currently disagrees in **three** places: site copy says "all ages",
  Participant T&Cs say "17 to 65", Privacy Policy says "17 to 65". All three must
  end up saying the same thing.
- The **65 upper limit goes regardless of this decision** — an upper age limit on
  a service is likely Equality Act 2010 exposure and is not defensible.
- Legal documents are generated: edit the Word masters in `01 Legal & Compliance/`
  and `02 Event & Participant/`, then re-run `scripts/legal-from-docx.py`.
