#!/bin/sh
# fetch-books.sh - mirror the komh.github.io/os2books collection.
#
# That site republishes IBM OS/2 documentation as HTML/PDF/text: the Warp
# redbooks (GG24-37xx), "Undocumented OS/2", Toolkit documentation, the
# programming FAQ, the REXX and DBCS books. It is [DOC-IBM] material - IBM's own
# words - in a form you can grep without an INF extractor.
#
# Complementary to build-inf-text.sh, not a replacement: the .INF books carry
# the per-function reference, these carry the narrative and the redbooks.
#
# Usage:
#   ./fetch-books.sh            # mirror the default tree list
#   ./fetch-books.sh gg243730   # just one tree
#
# Output: $OS2DOCS/os2books/...  (OS2DOCS defaults to ~/os2docs)
#
# RIGHTS: this is IBM's documentation, republished by a third party. Mirror it
# for your own reference. Do not redistribute it or bundle it into a published
# project. See ../sources.md.
set -e

: "${OS2DOCS:=$HOME/os2docs}"
base=https://komh.github.io/os2books
out="$OS2DOCS/os2books"

command -v wget >/dev/null 2>&1 || { echo "fetch-books.sh: needs wget" >&2; exit 127; }

# Default trees. Each is fetched with its own timeout so one slow or missing
# tree cannot stall the whole run.
if [ $# -gt 0 ]; then
    TREES="$*"
else
    TREES="gg243730 gg243731 gg243732 gg243774 os2undoc os2tk45 progfaq prcp
           rexx firewall smp dbcs/os2dbcs dbcs/open32j dbcs/im32 dbcs/xprmos2
           txt pdf"
fi

mkdir -p "$out"
cd "$out"
echo "mirroring into $out"

ok=0; bad=0
for d in $TREES; do
    printf '>>> %-20s ' "$d"
    if timeout "${BOOKS_TIMEOUT:-300}" wget -e robots=off -r -np -nH --cut-dirs=1 \
         -q -A 'html,htm,txt,png,gif,pdf,inf' "$base/$d/" 2>/dev/null; then
        echo "ok"; ok=$((ok + 1))
    else
        rc=$?
        # wget exits 8 on server 404s for optional trees; report, do not abort.
        echo "incomplete (rc=$rc)"; bad=$((bad + 1))
    fi
done

echo
echo "done: $ok tree(s) ok, $bad incomplete"
echo "  html: $(find "$out" -iname '*.htm*' 2>/dev/null | wc -l | tr -d ' ')"
echo "  pdf:  $(find "$out" -iname '*.pdf' 2>/dev/null | wc -l | tr -d ' ')"
echo "  text: $(find "$out" -iname '*.txt' 2>/dev/null | wc -l | tr -d ' ')"
echo "  size: $(du -sh "$out" 2>/dev/null | cut -f1)"
echo
echo "PDFs are not greppable as-is. If you need to search them, convert first:"
echo "  for f in \$(find \"$out\" -name '*.pdf'); do pdftotext \"\$f\" \"\${f%.pdf}.txt\"; done"
exit 0
