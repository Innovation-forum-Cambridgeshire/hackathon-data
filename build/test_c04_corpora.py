#!/usr/bin/env python3
"""Verify the c04 corpora and their schema contract.

Run:  python3 build/test_c04_corpora.py

Three classes of assertion, and they fail for different reasons:

  CONTRACT      the generators match what the catalogue promises
  SAFETY        the corpus does not contain things it must not contain
  TEACHABILITY  the exercise the challenge is built on is still present

The SAFETY block is the one that matters most here and is the reason this file
exists rather than relying on the shared test. c04 is the challenge where a
careless corpus does real harm: a withheld interest that leaks a hint of its
content defeats a statutory safeguard, and a live helpline number in a demo
dataset costs a real support service real time.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "generators"))

import yaml  # noqa: E402

import synthetic_abuse  # noqa: E402
import synthetic_register  # noqa: E402

CATALOGUE = Path(__file__).resolve().parent.parent / "catalogue" / "c04-safe-in-the-open.yml"
ROW_TOLERANCE = 0.20

# Contact values that are safe to publish: the Ofcom 0808 drama range and .invalid.
SAFE_CONTACT = re.compile(r"0808 |example\.invalid")


def main() -> int:
    failures: list[str] = []
    cat = yaml.safe_load(CATALOGUE.read_text())
    declared = {t["name"]: t for t in cat["gold_tables"]}

    tables = {**synthetic_register.generate(), **synthetic_abuse.generate()}

    # ---------- CONTRACT ----------
    if set(tables) != set(declared):
        failures.append(
            f"tables differ from catalogue: generated {sorted(tables)}, declared {sorted(declared)}"
        )

    for name, (header, rows) in tables.items():
        tbl = declared.get(name)
        if tbl is None:
            continue
        expected = [c["name"] for c in tbl["columns"]]
        if header != expected:
            failures.append(f"{name}: columns {header} != catalogue {expected}")
        approx = tbl.get("approx_rows")
        if isinstance(approx, int) and approx > 0:
            drift = abs(len(rows) - approx) / approx
            if drift > ROW_TOLERANCE:
                failures.append(f"{name}: {len(rows):,} rows vs declared ~{approx:,} ({drift:.0%})")

    for mod in (synthetic_register, synthetic_abuse):
        if mod.generate(mod.DEFAULT_SEED) != mod.generate(mod.DEFAULT_SEED):
            failures.append(f"{mod.__name__} is not deterministic for a fixed seed")

    # ---------- SAFETY ----------
    reg_header, reg_rows = tables["synthetic_councillor_register"]
    ri = {n: i for i, n in enumerate(reg_header)}

    withheld = [r for r in reg_rows if r[ri["withheld"]]]
    if not withheld:
        failures.append("no withheld interests — the s.32 case is absent from the corpus")

    # The load-bearing one. A withheld interest records THAT it exists and nothing
    # about what it is; any detail at all invites inference the Act exists to prevent.
    leaked = [r for r in withheld if r[ri["declaration_detail"]] is not None]
    if leaked:
        failures.append(
            f"{len(leaked)} withheld declarations carry a non-null detail — a withheld "
            f"interest must be genuinely absent, not redacted-looking or hinted at"
        )

    # Withheld rows must also not carry the real category, which would narrow it.
    cats = {r[ri["declaration_category"]] for r in withheld}
    if cats != {"Sensitive interest (withheld under s.32)"}:
        failures.append(f"withheld rows leak their category: {sorted(cats)}")

    sup_header, sup_rows = tables["support_directory"]
    si = {n: i for i, n in enumerate(sup_header)}
    unsafe = [r for r in sup_rows if not SAFE_CONTACT.search(str(r[si["contact_value"]]))]
    if unsafe:
        failures.append(
            f"{len(unsafe)} support routes carry a contact outside the safe ranges. "
            f"Every value must be Ofcom 0808 drama range or .invalid — a prototype WILL "
            f"dial one of these during a demo."
        )

    msg_header, msg_rows = tables["message_signals"]
    mi = {n: i for i, n in enumerate(msg_header)}

    # No real-person identifiers should ever appear in the message corpus.
    for col in ("sender_name", "sender_email", "sender_handle", "ip_address"):
        if col in msg_header:
            failures.append(f"message_signals carries {col!r} — c04 must not describe senders")

    # ---------- TEACHABILITY ----------
    flagged = [r for r in msg_rows if r[mi["is_flagged"]]]
    share = len(flagged) / len(msg_rows)
    if not 0.04 <= share <= 0.15:
        failures.append(
            f"flagged share {share:.1%} outside 4-15% — the class-imbalance lesson needs "
            f"rare positives, but not so rare the exercise is impossible"
        )

    # "Robust criticism" is the hard negative. Without it a classifier can learn
    # "negative sentiment = abusive", which in production suppresses legitimate
    # democratic scrutiny — a worse failure than missing a rude message.
    if not any(r[mi["category"]] == "Robust criticism" for r in msg_rows):
        failures.append("no 'Robust criticism' class — the hard negative is missing")

    crit = [r[mi["sentiment_score"]] for r in msg_rows if r[mi["category"]] == "Robust criticism"]
    flag = [r[mi["sentiment_score"]] for r in flagged]
    if crit and flag:
        overlap = min(max(crit), max(flag)) - max(min(crit), min(flag))
        if overlap <= 0.10:
            failures.append(
                f"sentiment overlap between flagged and robust-criticism is only {overlap:.2f} — "
                f"sentiment alone nearly separates the classes, making the exercise trivial"
            )

    if not any(r[mi["repeat_sender_count"]] > 5 for r in msg_rows):
        failures.append(
            "no persistent senders — persistence is a signal single-message "
            "classification cannot see, and the corpus should reward finding it"
        )

    if failures:
        print("c04 corpora FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        f"c04 corpora OK: {len(reg_rows):,} declarations ({len(withheld)} withheld, all "
        f"genuinely empty), {len(sup_rows)} support routes (all synthetic contacts), "
        f"{len(msg_rows):,} messages at {share:.1%} flagged with the hard negative present."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
