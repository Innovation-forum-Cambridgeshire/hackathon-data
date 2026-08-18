#!/usr/bin/env python3
"""Data quality assurance for the five hackathon challenge corpora.

    python quality/run_assurance.py                       # sample/data, full report
    python quality/run_assurance.py --data-root /tmp/ci    # a CI build
    python quality/run_assurance.py --update-baseline      # accept the current profile

See quality/README.md for what is checked and why.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "quality"))

# GX prints a per-metric progress bar that turns CI logs into thousands of lines
# of carriage returns. Off by default; -v puts it back.
os.environ.setdefault("GX_PROGRESS_BARS", "False")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--data-root", type=Path, default=REPO_ROOT / "sample" / "data",
        help="directory holding <challenge>/gold/*.parquet (default: sample/data)",
    )
    p.add_argument(
        "--out", type=Path, default=REPO_ROOT / "quality" / "out",
        help="where the report is written (default: quality/out)",
    )
    p.add_argument(
        "--update-baseline", action="store_true",
        help="overwrite the committed profile baseline with the current corpus",
    )
    p.add_argument(
        "--allow-known-findings", action="store_true",
        help="exit 0 even if the only failures are those recorded in quality/FINDINGS.md",
    )
    p.add_argument(
        "--vendor", action="store_true",
        help="fetch the CDN assets Data Docs would otherwise load from six external "
             "origins, so the report renders offline and emits no third-party requests",
    )
    p.add_argument("--no-docs", action="store_true", help="skip the HTML report")
    p.add_argument("-v", "--verbose", action="store_true", help="show GX progress bars")
    args = p.parse_args()

    if not args.data_root.exists():
        print(
            f"error: no data at {args.data_root}\n"
            f"The corpus is generated, not committed. Build it first:\n"
            f"    python build/build.py build --challenge c01-one-farm-one-picture "
            f"--version v1 --out {args.data_root}\n"
            f"or run sample/setup.sh for all five.",
            file=sys.stderr,
        )
        return 2

    from assurance.run import run
    from assurance.report import write_report, print_summary

    website_css = REPO_ROOT.parent / "website_" / "src" / "styles" / "global.css"

    result = run(
        repo_root=REPO_ROOT,
        data_root=args.data_root,
        out_dir=args.out,
        update_baseline=args.update_baseline,
        website_css=website_css if website_css.exists() else None,
        progress_bars=args.verbose,
    )

    if not args.no_docs:
        write_report(REPO_ROOT, args.out, result, vendor=args.vendor)

    print_summary(result, args.out)

    if result.success:
        return 0
    if args.allow_known_findings:
        from assurance.report import only_known_findings

        known, unknown = only_known_findings(REPO_ROOT, result)
        if not unknown:
            print(
                f"\n{len(known)} known finding(s) from quality/FINDINGS.md, nothing new. "
                f"Exiting 0 because --allow-known-findings was given."
            )
            return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
