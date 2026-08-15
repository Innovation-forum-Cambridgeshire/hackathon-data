#!/usr/bin/env python3
"""Generator for `synthetic-abuse` — challenge 04, the message corpus.

Produces one gold table:

    message_signals   one row per message

WHAT THIS DELIBERATELY DOES NOT CONTAIN
----------------------------------------
No real messages, and no realistic abuse.

The first is a legal requirement. Republishing real social content would breach
platform terms and risks Protection from Harassment Act 1997, Defamation Act 2013
and misuse of private information — none of which a UK GDPR lawful basis cures.
That is settled and is why c04 became a synthetic challenge.

The second is a choice, and it is worth stating because it is not the obvious one.
A corpus of convincingly abusive text would make the classification exercise feel
more authentic. It would also be a file of ready-made harassment, published
anonymously and permanently under CC0, mirrored by anyone who wants it. The
technique the challenge teaches — classification under class imbalance, and the
asymmetric cost of the two error types — needs SEPARABLE SIGNAL, not genuine
hostility. So messages are assembled from neutral, obviously-templated fragments,
and the severe categories are represented STRUCTURALLY (short, flagged, high
urgency) rather than graphically.

A team that wants to see how their method behaves on real language should evaluate
it on their own consented collection inside the DPIA. That is exactly the boundary
the challenge brief already draws.

WHY SIGNALS AND NOT RAW TEXT AS THE PRIMARY TABLE
--------------------------------------------------
The table is `message_signals`, not `messages`. It carries the derived features a
triage system would actually act on — urgency, target role, channel, whether a
named individual is referenced — alongside a short synthetic `text` column for
teams that want to run a tokeniser end to end. This keeps the centre of gravity on
"what would you do with this signal", which is the assessable part, rather than on
prompting people to fine-tune a model on abuse.

THE CLASS BALANCE IS THE POINT
-------------------------------
Roughly 8% of messages are flagged. That is deliberate and it is the trap: a
classifier that predicts "never abusive" scores 92% accuracy and is worthless. The
notebook for this challenge exists to make that visible on the first read.

Usage:
    python build/generators/synthetic_abuse.py --out dist/gold --seed 20261026
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

DEFAULT_SEED = 20261026

N_MESSAGES = 24_000
WINDOW_DAYS = 180
WINDOW_END = datetime(2026, 9, 30, 23, 59, 0)

# Share of messages that are genuinely flagged. Low on purpose — see the docstring.
ABUSIVE_SHARE = 0.08

CHANNELS = ["Public comment", "Direct message", "Email", "Forum post", "Contact form"]
CHANNEL_WEIGHTS = [0.34, 0.18, 0.24, 0.14, 0.10]

TARGET_ROLES = ["Councillor", "Chair", "Cabinet Member", "Mayor", "Committee Member", "Officer"]

# Categories a triage system would separate. "Robust criticism" is present and is
# NOT abusive — it is the hard negative, and a classifier that suppresses it has
# suppressed legitimate democratic scrutiny, which is a worse failure than missing
# a rude message.
CATEGORIES = [
    ("Routine correspondence", False),
    ("Service request", False),
    ("Robust criticism", False),
    ("Persistent contact", True),
    ("Personal abuse", True),
    ("Threatening language", True),
    ("Targeted campaign", True),
]

# Obviously-synthetic fragments. Neutral by construction: the separability comes
# from combination and metadata, not from hostility in the words.
OPENERS = [
    "Regarding the recent decision", "About the planning application",
    "Following the committee meeting", "In response to the consultation",
    "Concerning the budget proposal", "After reading the published minutes",
]
BODIES_NEUTRAL = [
    "I would like to understand the reasoning.",
    "Could you clarify the timeline please.",
    "Residents on my street have questions.",
    "I disagree with this and here is why.",
    "This does not reflect what was consulted on.",
    "Please can you point me to the evidence.",
]
BODIES_CRITICAL = [
    "This is a poor decision and I think it should be reversed.",
    "The process was not transparent and I want it reviewed.",
    "I have lost confidence in how this was handled.",
    "You have not answered the question that was asked.",
]
# Flagged messages are marked by STRUCTURE and metadata, not by content. These
# stay deliberately bland: severity lives in `urgency`, `repeat_sender_count` and
# `references_named_individual`, which is where a triage system reads it anyway.
BODIES_FLAGGED = [
    "[synthetic flagged message - category A]",
    "[synthetic flagged message - category B]",
    "[synthetic flagged message - category C]",
    "[synthetic flagged message - repeated contact]",
]


def generate(seed: int = DEFAULT_SEED) -> dict[str, tuple[list[str], list[list]]]:
    rng = np.random.default_rng(seed)

    header = [
        "message_id", "received_at", "channel", "target_role", "category",
        "is_flagged", "urgency", "word_count", "repeat_sender_count",
        "references_named_individual", "sentiment_score", "text",
    ]
    rows: list[list] = []

    cat_names = [c[0] for c in CATEGORIES]
    cat_flag = dict(CATEGORIES)
    # Weighted so the flagged classes together land near ABUSIVE_SHARE.
    weights = np.array([0.40, 0.28, 0.24, 0.026, 0.026, 0.014, 0.014])
    weights = weights / weights.sum()

    start = WINDOW_END - timedelta(days=WINDOW_DAYS)
    for i in range(N_MESSAGES):
        cat = str(rng.choice(cat_names, p=weights))
        flagged = cat_flag[cat]

        received = start + timedelta(
            seconds=int(rng.integers(0, WINDOW_DAYS * 24 * 3600))
        )

        if flagged:
            body = str(rng.choice(BODIES_FLAGGED))
            urgency = str(rng.choice(["medium", "high", "high", "critical"]))
            repeats = int(rng.integers(2, 40))
            named = bool(rng.random() < 0.72)
            sentiment = float(round(rng.uniform(-1.0, -0.35), 3))
        elif cat == "Robust criticism":
            body = str(rng.choice(BODIES_CRITICAL))
            urgency = str(rng.choice(["low", "medium"]))
            repeats = int(rng.integers(1, 4))
            named = bool(rng.random() < 0.22)
            # Overlaps the flagged range on purpose: sentiment ALONE must not
            # separate the classes, or the exercise is trivial and teaches nothing.
            sentiment = float(round(rng.uniform(-0.6, 0.05), 3))
        else:
            body = str(rng.choice(BODIES_NEUTRAL))
            urgency = "low"
            repeats = int(rng.integers(1, 3))
            named = bool(rng.random() < 0.06)
            sentiment = float(round(rng.uniform(-0.15, 0.75), 3))

        text = f"{rng.choice(OPENERS)}. {body}"
        rows.append([
            f"MSG-{i + 1:06d}", received, str(rng.choice(CHANNELS, p=CHANNEL_WEIGHTS)),
            str(rng.choice(TARGET_ROLES)), cat, flagged, urgency,
            len(text.split()), repeats, named, sentiment, text,
        ])

    return {"message_signals": (header, rows)}


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
