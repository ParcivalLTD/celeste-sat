#!/bin/bash
# get_drat_trim.sh -- download and build drat-trim (the DRAT proof checker tools/certify.py uses)
# into build/drat-trim/, and check that its source is the one results/certificates/ was made with.
#
#   bash tools/get_drat_trim.sh && export PATH="$PWD/build/drat-trim:$PATH"
#
# CBMC and CaDiCaL come from the package manager (Ubuntu/WSL: sudo apt install -y cbmc cadical).
set -e
cd "$(dirname "$0")/.."
EXPECTED=d834b649f437e091597f5347f259b9f681087f89ca0844d0cee250a1a1a0c2ee   # drat-trim.c, "Last edit: April 21, 2024"
mkdir -p build/drat-trim
cd build/drat-trim
curl -sSfLO https://raw.githubusercontent.com/marijnheule/drat-trim/master/drat-trim.c
GOT=$(sha256sum drat-trim.c | cut -d' ' -f1)
if [ "$GOT" != "$EXPECTED" ]; then
    echo "warning: drat-trim.c has changed upstream (sha256 $GOT); record the new one in results/certificates/versions.txt"
fi
gcc -O2 -o drat-trim drat-trim.c
echo "built $PWD/drat-trim"
