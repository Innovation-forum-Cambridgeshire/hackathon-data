#!/usr/bin/env python3
"""Generator for `synthetic-register` and `support-routes` — challenge 04.

Produces two gold tables:

    synthetic_councillor_register   one row per member x declaration
    support_directory               one row per support/reporting route

WHY THIS IS SYNTHETIC, WHICH IS NOT THE SAME AS "WE COULD NOT GET THE REAL DATA"
--------------------------------------------------------------------------------
Registers of members' interests are genuinely public records and we could lawfully
read them. We decline to MIRROR them, which is a different decision.

Aggregating public records into a queryable dataset is a new processing operation
in its own right (Catt v UK, ECtHR 2019) — the fact that each item was already
public does not make the compiled whole equivalent. Councillors are data subjects
even when acting in public office, so Article 14 would apply to that compilation.
Since the challenge is about METHOD, and the method is identical against a
synthetic register, mirroring real people's declarations would take on a live data
protection obligation to buy exactly nothing.

Two traps that survive the switch to synthetic and are built into the shape here:

  1. WITHHELD INTERESTS ARE NOT MISSING DATA. Localism Act 2011 s.32 lets a
     sensitive interest be withheld from the published register — typically where
     disclosure would expose the member or someone connected to them to violence
     or intimidation. The register records THAT an interest exists without its
     detail. A team that treats a withheld row as a null to be imputed, or infers
     what it might contain, has done something the Act exists to prevent. So the
     corpus carries a `withheld` flag with a genuinely empty detail field, and
     never a hint of content behind it.

  2. THE REGISTER HOLDER IS NOT THE TOWN COUNCIL. Town and parish councils do not
     hold their own registers — the principal authority's Monitoring Officer does.
     For Huntingdon, St Ives and Ramsey that is Huntingdonshire District Council.
     The `register_held_by` column exists so this is visible in the data rather
     than being a fact somebody has to already know.

Usage:
    python build/generators/synthetic_register.py --out dist/gold --seed 20261026
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

DEFAULT_SEED = 20261026

N_MEMBERS = 1_400
DECLARATIONS_PER_MEMBER = 3  # ~4,200 rows, matching the declared grain

# A principal authority and the town/parish councils whose registers it holds.
# Deliberately mixed so the register_held_by column is not simply a copy of
# authority — that is the point being taught.
PRINCIPAL_AUTHORITY = "Huntingdonshire District Council"
AUTHORITIES = [
    ("Huntingdonshire District Council", PRINCIPAL_AUTHORITY),
    ("Huntingdon Town Council", PRINCIPAL_AUTHORITY),
    ("St Ives Town Council", PRINCIPAL_AUTHORITY),
    ("Ramsey Town Council", PRINCIPAL_AUTHORITY),
    ("Cambridgeshire County Council", "Cambridgeshire County Council"),
    ("South Cambridgeshire District Council", "South Cambridgeshire District Council"),
]

WARDS = [
    "Brampton", "Buckden", "Godmanchester", "Huntingdon North", "Huntingdon East",
    "Huntingdon West", "St Ives South", "St Ives East", "St Ives West", "Ramsey",
    "Warboys", "Somersham", "Sawtry", "Yaxley", "Fenstanton", "Hemingfords",
    "Little Paxton", "St Neots East", "St Neots Eynesbury", "Alconbury",
]

ROLES = ["Councillor", "Chair", "Vice-Chair", "Cabinet Member", "Committee Member", "Mayor"]
ROLE_WEIGHTS = [0.62, 0.07, 0.07, 0.08, 0.13, 0.03]

COMMITTEES = [
    "Planning", "Licensing", "Overview and Scrutiny", "Audit and Governance",
    "Employment", "Corporate Governance", "Health and Wellbeing", "Environment",
    "Finance", "Standards", "(none)",
]

# Categories follow the statutory disclosable pecuniary interests plus the common
# non-pecuniary registrable ones.
DECLARATION_CATEGORIES = [
    "Employment, office, trade or profession",
    "Sponsorship",
    "Contracts with the authority",
    "Land and property in the area",
    "Licences to occupy land",
    "Corporate tenancies",
    "Securities",
    "Membership of a body exercising public functions",
    "Membership of a charity or voluntary body",
    "Trade union membership",
    "Membership of a political party",
    "Directorship",
]

# Share of declarations lawfully withheld as sensitive interests (s.32).
WITHHELD_SHARE = 0.035

SUPPORT_CATEGORIES = [
    "Reporting abuse", "Police non-emergency", "Police emergency", "Legal advice",
    "Mental health support", "Standards complaint", "Online safety", "Peer support",
    "Employer HR route", "Advocacy", "Safeguarding referral", "Victim support",
]
SUPPORT_ORGS = [
    "Local Government Association", "Police and Crime Commissioner", "Monitoring Officer",
    "Standards Committee", "Samaritans", "Victim Support", "Mind", "Citizens Advice",
    "Cambridgeshire Constabulary", "Action Fraud", "Internet Watch Foundation",
    "Stop Hate UK", "Suzy Lamplugh Trust", "Protection Against Stalking",
    "National Cyber Security Centre",
]
CONTACT_TYPES = ["Telephone", "Online form", "Email", "In person", "24/7 helpline"]
COVERAGE = ["National", "Regional", "Local authority", "Force area"]


def build_register(rng: np.random.Generator) -> tuple[list[str], list[list]]:
    header = [
        "declaration_id", "member_id", "authority", "register_held_by", "ward", "role",
        "committee", "declaration_category", "declaration_detail", "withheld",
        "registered_date", "last_updated_date",
    ]
    rows: list[list] = []
    start = date(2023, 5, 1)  # a typical post-election register refresh

    auth_idx = rng.integers(0, len(AUTHORITIES), N_MEMBERS)
    wards = rng.choice(WARDS, N_MEMBERS)
    roles = rng.choice(ROLES, N_MEMBERS, p=ROLE_WEIGHTS)

    did = 0
    for m in range(N_MEMBERS):
        authority, held_by = AUTHORITIES[auth_idx[m]]
        member_id = f"M-{m + 1:05d}"
        n_dec = int(rng.integers(1, DECLARATIONS_PER_MEMBER * 2))
        for _ in range(n_dec):
            did += 1
            cat = rng.choice(DECLARATION_CATEGORIES)
            withheld = bool(rng.random() < WITHHELD_SHARE)

            # A withheld interest records THAT it exists and nothing about what it
            # is. The detail is genuinely empty — not redacted-looking, not a
            # placeholder that hints at a category, and never imputable. See the
            # module docstring on Localism Act 2011 s.32.
            if withheld:
                detail = None
                cat_out = "Sensitive interest (withheld under s.32)"
            else:
                cat_out = cat
                detail = f"{cat.split(',')[0]} declared in the register"

            reg = start + timedelta(days=int(rng.integers(0, 900)))
            upd = reg + timedelta(days=int(rng.integers(0, 400)))
            rows.append([
                f"D-{did:06d}", member_id, authority, held_by, wards[m], roles[m],
                str(rng.choice(COMMITTEES)), cat_out, detail, withheld, reg, upd,
            ])

    return header, rows


def build_support_directory(rng: np.random.Generator) -> tuple[list[str], list[list]]:
    """support_directory — every prototype must be able to point someone at help.

    Synthetic contact values on purpose. Publishing a directory of real helpline
    numbers in a hackathon corpus invites a prototype to dial one during a demo,
    and a support line answering a test call is a real cost to a real service.
    Teams wire the mechanism against these, and the mechanism is the assessable part.
    """
    header = [
        "route_id", "organisation", "category", "contact_type", "contact_value",
        "hours", "coverage", "is_emergency", "notes",
    ]
    rows: list[list] = []
    n = 180
    for i in range(n):
        org = str(rng.choice(SUPPORT_ORGS))
        cat = str(rng.choice(SUPPORT_CATEGORIES))
        ctype = str(rng.choice(CONTACT_TYPES))
        emergency = cat == "Police emergency"
        if ctype == "Telephone" or ctype == "24/7 helpline":
            # Ofcom 0808 range reserved for drama — never a live number.
            contact = f"0808 {rng.integers(100, 999)} {rng.integers(1000, 9999)}"
        elif ctype == "Email":
            contact = f"support{i + 1}@example.invalid"
        else:
            contact = f"https://example.invalid/{org.lower().replace(' ', '-')}"
        rows.append([
            f"R-{i + 1:04d}", org, cat, ctype, contact,
            "24/7" if ctype == "24/7 helpline" or emergency else "Mon-Fri 09:00-17:00",
            str(rng.choice(COVERAGE)), emergency,
            "SYNTHETIC contact details — never dial or email these in a demo.",
        ])
    return header, rows


def generate(seed: int = DEFAULT_SEED) -> dict[str, tuple[list[str], list[list]]]:
    rng = np.random.default_rng(seed)
    return {
        "synthetic_councillor_register": build_register(rng),
        "support_directory": build_support_directory(rng),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = p.parse_args()
    import pandas as pd

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, (header, rows) in generate(args.seed).items():
        pd.DataFrame(rows, columns=header).to_parquet(out / f"{name}.parquet", index=False)
        print(f"  {name}: {len(rows):,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
