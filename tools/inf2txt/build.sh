#!/bin/sh
# Build inf2txt: OS/2 INF/IPF -> text extractor, using fpGUI's docview parser
# (GUI-free driver). Writes ./inf2txt next to this script.
#
# Prereqs (Debian/Ubuntu):
#   sudo apt-get install --no-install-recommends \
#        fp-compiler fp-units-fcl fp-units-rtl fp-units-misc git
#
# LICENSING: fpGUI licenses per directory - its framework is modified-LGPL, but
# the docview units linked here are GPLv2 with no linking exception. The binary
# this script produces is therefore a GPLv2 combined work: free to use, but
# redistributable only under GPLv2 with corresponding source. See README.md.
set -e
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$here"

command -v fpc >/dev/null 2>&1 || {
    echo "build.sh: fpc not found - install Free Pascal (see prereqs above)" >&2
    exit 127
}

# fpGUI checkout: fetch it if absent rather than failing with a bare cd error.
if [ ! -d fpGUI ]; then
    command -v git >/dev/null 2>&1 || {
        echo "build.sh: need ./fpGUI, and git is not installed to fetch it." >&2
        echo "  git clone --depth 1 https://github.com/graemeg/fpGUI.git" >&2
        exit 127
    }
    echo "build.sh: fetching fpGUI (docview parser) ..."
    git clone --depth 1 https://github.com/graemeg/fpGUI.git fpGUI
fi

# Locate the FPC unit tree instead of hardcoding one version/arch: fpc -iV gives
# the version, -iTP/-iTO the target CPU/OS.
fpcver=$(fpc -iV)
fpctgt=$(fpc -iTP)-$(fpc -iTO)
UNITS=""
for cand in \
    "/usr/lib/$(uname -m)-linux-gnu/fpc/$fpcver/units/$fpctgt" \
    "/usr/lib/fpc/$fpcver/units/$fpctgt" \
    "/usr/local/lib/fpc/$fpcver/units/$fpctgt"
do
    [ -d "$cand" ] && { UNITS=$cand; break; }
done
[ -n "$UNITS" ] || {
    echo "build.sh: cannot find the FPC $fpcver unit tree for $fpctgt." >&2
    echo "  Looked under /usr/lib and /usr/local/lib; set UNITS= by hand if your" >&2
    echo "  distro puts them elsewhere." >&2
    exit 1
}

# -FU keeps the ~300 intermediate .o/.ppu files (22 MB) in a scratch dir instead
# of scattering them next to the source, where they would litter the checkout.
build="$here/.build"
mkdir -p "$build"

cd fpGUI
P=framework/src/main/pascal
FU_UNITS=$(find "$UNITS" -maxdepth 1 -type d | sed 's/^/-Fu/' | tr '\n' ' ')
FI=$(find framework docview -name '*.inc' -printf '%h\n' | sort -u | sed 's/^/-Fi/' | tr '\n' ' ')
fpc -Mobjfpc -O2 $FI $FU_UNITS \
  -Fudocview/src/main/pascal -Fudocview/src/main/pascal/richtext \
  -Fu$P -Fu$P/corelib -Fu$P/corelib/x11 -Fu$P/corelib/render -Fu$P/corelib/render/software -Fu$P/gui \
  -FU"$build" -FE.. ../inf2txt.pas

[ -x "$here/inf2txt" ] && echo "build.sh: built $here/inf2txt"
