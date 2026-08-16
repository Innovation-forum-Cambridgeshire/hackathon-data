"""Value-based fingerprinting for generated corpora.

WHAT THE DETERMINISM GUARANTEE ACTUALLY IS
-------------------------------------------
Stated loosely it was "same seed, same bytes". Testing the numpy 1.26 -> 2.2
upgrade showed that is two different claims with two different answers:

  SAME SEED, SAME VALUES         holds across library versions. Verified on all
                                 13 tables across numpy 1.26.4 and 2.2.6: every
                                 number, string and null identical.

  SAME SEED, SAME BYTES          holds only within a PINNED environment. Parquet
                                 embeds its writer version, so the same frame
                                 written by pyarrow 21 and 23 produces different
                                 files with identical contents.

Only the first matters for fairness. Judging happens against the DOWNLOADED
release asset — a fixed file — so two teams always see the same bytes regardless.
Value-identity is what lets anyone rebuild a release and confirm the corpus was
what it claimed to be.

Byte-identity is still worth having, because it makes "did this rebuild produce
the same thing" a one-line shasum instead of a frame comparison. That is a real
reason the pins in sample/requirements.txt and build/requirements.txt matter
beyond the security advisories that forced them up.

WHY NOT JUST COMPARE THE ROW LISTS
-----------------------------------
`generate(seed) == generate(seed)` is fine within one process, and the tests
still do it. It is NOT safe across environments, and neither is hashing
`repr(rows)`: NumPy 2 changed scalar repr (NEP 51), so `repr(np.float64(1.5))`
is `'np.float64(1.5)'` there and `'1.5'` on 1.x. A repr-based hash reports five
of thirteen tables as changed when nothing about the data moved — which is
exactly what happened, and cost an hour of chasing an RNG bug that did not exist.

`fingerprint()` normalises the value and ignores its Python type.
"""

from __future__ import annotations

import hashlib
from typing import Iterable, Sequence


def canonical(value) -> str:
    """One value, as a type-independent string.

    Floats go through %.10g: enough precision to catch a real change, loose
    enough to ignore the last-bit noise that differs between BLAS builds and
    would otherwise make this fire on a machine change rather than a data change.
    """
    if value is None:
        return "N"
    if isinstance(value, bool):        # before the float branch — bool is an int
        return "b1" if value else "b0"
    try:
        return "f%.10g" % float(value)
    except (TypeError, ValueError):
        return "s%s" % (value,)


def fingerprint(rows: Iterable[Sequence]) -> str:
    """A stable digest of a table's VALUES, independent of Python types."""
    acc = hashlib.sha256()
    for row in rows:
        acc.update("|".join(canonical(v) for v in row).encode("utf-8"))
        acc.update(b"\n")
    return acc.hexdigest()[:16]


def fingerprint_tables(tables: dict[str, tuple[list, list]]) -> dict[str, str]:
    """{table_name: fingerprint} for a generator's full output."""
    return {name: fingerprint(rows) for name, (_header, rows) in tables.items()}
