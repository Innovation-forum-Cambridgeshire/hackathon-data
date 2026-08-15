#!/usr/bin/env python3
"""Verify the CSV twin encoding contract.

Run:  python3 build/test_csv_contract.py

These two rules are the difference between a participant trusting the data and
quietly drawing a wrong conclusion from it, so they are asserted rather than
assumed. Both failure modes are silent — the file still opens, it is just wrong.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build import CSV_ENCODING, write_csv  # noqa: E402

# A real Cambridgeshire-shaped row: an accented place name and both a date and a
# datetime whose day and month are both <= 12, so a locale mix-up stays plausible.
HEADER = ["place", "observed_on", "recorded_at", "value"]
ROW = ["Saint-Yves café", date(2026, 4, 3), datetime(2026, 4, 3, 14, 30, 0), 12.5]


def main() -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        path = write_csv(Path(td) / "gold" / "sample.csv", HEADER, [ROW])
        raw = path.read_bytes()
        text = raw.decode(CSV_ENCODING)

        if not raw.startswith(b"\xef\xbb\xbf"):
            failures.append("no UTF-8 BOM — Excel will read this as Windows-1252")

        if "Saint-Yves café" not in text:
            failures.append("accented text did not survive the round trip")

        if "2026-04-03" not in text:
            failures.append("date is not ISO-8601")

        if "2026-04-03T14:30:00" not in text:
            failures.append("datetime is not ISO-8601")

        for ambiguous in ("03/04", "04/03", "3/4/2026", "4/3/2026"):
            if ambiguous in text:
                failures.append(f"ambiguous locale-dependent date present: {ambiguous!r}")

        # The writer must create its own parent directory — the transform stage
        # should not have to know to mkdir before every table.
        if not path.exists():
            failures.append("write_csv did not create the file")

    if failures:
        print("CSV contract FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("CSV contract OK: UTF-8 BOM present, dates ISO-8601, accents intact.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
