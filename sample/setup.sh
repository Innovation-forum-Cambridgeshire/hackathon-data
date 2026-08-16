#!/usr/bin/env bash
# Create the sample environment and register its Jupyter kernel.
#
#   ./sample/setup.sh
#
# Then build at least one challenge (see README.md) and open sample/notebooks/.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if [ ! -d .venv ]; then
  echo "Creating .venv ..."
  python3 -m venv .venv
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
