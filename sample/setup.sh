#!/usr/bin/env bash
# Create the sample environment and register its Jupyter kernel.
#
#   ./sample/setup.sh
#
# Then build at least one challenge (see README.md) and open sample/notebooks/.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# Python 3.10 is the floor, and it is a SECURITY floor rather than a feature one.
# pyarrow dropped 3.9 at 22.0, and 23.0.1 is the version that fixes
# GHSA-rgxp-2hwp-jwgg — a use-after-free when reading an IPC file, on the exact
# path every notebook takes to read parquet.
#
# Checked here rather than left to pip, because pip's failure for this is
# "Could not find a version that satisfies the requirement pyarrow==23.0.1",
# which reads like a network or typo problem and sends people looking in the
# wrong place. Python 3.9 went end of life in October 2025.
PY="${PYTHON:-python3}"
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
  echo "✋ This environment needs Python 3.10 or newer."
  echo "   Found: $("$PY" -V 2>&1)"
  echo
  echo "   pyarrow 23.0.1 is required to fix a use-after-free when reading parquet"
  echo "   (GHSA-rgxp-2hwp-jwgg), and it does not build for 3.9."
  echo
  echo "   If you have a newer Python under another name:"
  echo "       PYTHON=python3.12 ./sample/setup.sh"
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Creating .venv with $("$PY" -V 2>&1) ..."
  "$PY" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

# Registered under a distinct name so it cannot be confused with a system kernel
# that happens to have a different pandas.
python -m ipykernel install --user --name if-hackathon --display-name "IF Hackathon" >/dev/null

echo
echo "Environment ready."
echo
echo "Next, build a challenge's data from the REPO ROOT:"
echo
echo "    python build/build.py build --challenge c03-beyond-the-mainframe \\"
echo "        --version v1 --out sample/data/c03-beyond-the-mainframe"
echo
echo "Then:  cd sample && .venv/bin/jupyter lab notebooks/"
