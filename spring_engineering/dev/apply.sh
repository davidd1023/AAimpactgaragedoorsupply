#!/bin/sh
# Re-derive the calibration table from every reading and install it.
#
#   sh dev/apply.sh
#
# Kept as a script because the loop is routine: pull a batch, run this, look at
# the score. The table is never hand-edited.
set -e
cd "$(dirname "$0")/.."
node dev/derive.mjs --json | python3 dev/install.py
