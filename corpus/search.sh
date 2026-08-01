#!/bin/sh
# search.sh - search the OS/2 documentation corpus in provenance order.
#
# Why this exists rather than "just grep": three ways an ad-hoc grep lies to you
# about OS/2 documentation, all of them silent.
#
#   1. Non-UTF-8 book text makes GNU grep treat the file as BINARY and print
#      nothing at all - no error, no "binary file matches". An empty result then
#      reads as "IBM never documented this", which is backwards. This script
#      always passes -a.
#   2. Searching one volume and concluding absence. The books are split
#      (gpi1..gpi4, pm1..pm5) and some volumes are front-matter stubs, so a miss
#      in the wrong volume looks identical to a real absence. This searches all
#      of them at once and reports which had hits.
#   3. Treating a community wiki hit as IBM's word. Sources here are searched and
#      LABELLED in provenance order, strongest first.
#   4. Case. Text recovered from typeset or scanned books is case-damaged: one
#      real book renders WinCreateStdWindow as "Wincreatestdwindow" and
#      DosAllocMem as "DOSAllocMem", so a case-sensitive grep for the canonical
#      spelling finds ZERO in a book that documents both. Searches here are
#      always -i.
#   5. Table layout. Much IBM reference material is laid out in box-drawn tables,
#      so a sentence is split across cell boundaries mid-phrase:
#         |Alphabetic     |Selects the first menu item with the         |
#         |character      |specified character as its mnemonic key.     |
#      Grepping the whole phrase finds nothing even though the book states it
#      plainly. Search a distinctive FRAGMENT (3-5 words that fit on one line),
#      then read the surrounding lines. This one nearly caused a correct IBM
#      citation to be recorded as unsourced.
#
# Usage:
#   ./search.sh <pattern> [more grep args]
#   ./search.sh -l <pattern>        # list matching files only
#   ./search.sh -c <pattern>        # counts per source only
#
# Corpus root: $OS2DOCS (default ~/os2docs). Missing sources are skipped with a
# note - the kit's own os2ref/ is always searched and needs no corpus.
set -e

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
kit=$(CDPATH= cd -- "$here/.." && pwd)     # normalized, so hits print as .../os2ref/x.md
: "${OS2DOCS:=$HOME/os2docs}"

[ $# -ge 1 ] || {
    echo "usage: search.sh <pattern> [grep args]" >&2
    echo "  searches os2ref/ then the IBM books then the community mirror" >&2
    exit 2
}
pat=$1; shift

# grep flags: -a is mandatory (see reason 1 above), -I skips real binaries,
# -n gives file:line so a finding can be cited.
GREP="grep -a -I -n -i"
ctx=${SEARCH_CONTEXT:-0}
[ "$ctx" -gt 0 ] 2>/dev/null && GREP="$GREP -C $ctx"

hits_total=0

section() {
    label=$1; provenance=$2; shift 2
    # Collect existing targets only.
    set -- "$@"
    found=""
    for t in "$@"; do [ -e "$t" ] && found="$found $t"; done
    if [ -z "$found" ]; then
        printf '\n--- %s [%s]\n    (not present - skipped)\n' "$label" "$provenance"
        return 0
    fi
    n=$($GREP -r "$pat" $found 2>/dev/null | wc -l | tr -d ' ')
    printf '\n--- %s [%s] - %s match(es)\n' "$label" "$provenance" "$n"
    if [ "$n" -gt 0 ]; then
        hits_total=$((hits_total + n))
        $GREP -r "$pat" $found 2>/dev/null | head -"${SEARCH_MAX:-40}"
        [ "$n" -gt "${SEARCH_MAX:-40}" ] && \
            printf '    ... %s more (raise SEARCH_MAX to see them)\n' \
                   "$((n - ${SEARCH_MAX:-40}))"
    fi
    return 0
}

echo "searching for: $pat"
echo "corpus root:   $OS2DOCS"

# 1. The kit's own reference first: already distilled, already provenance-tagged.
section "os2ref/ (this kit)" "verified, per-claim tags" "$kit/os2ref"

# 2. IBM primary sources: the books, extracted to text.
section "IBM books (inf_text)" "DOC-IBM" "$OS2DOCS/inf_text"

# 3. IBM redbooks / toolkit docs / undocumented-OS2 text, if mirrored.
section "IBM redbooks + toolkit text" "DOC-IBM" \
        "$OS2DOCS/os2books" "$OS2DOCS/komh.github.io"

# 3b. Text pulled out of PDF books (pdf-to-text.sh). Hits carry [[page N]]
#     markers above them, so a fact can be cited back to a page.
section "PDF books (pdf_text)" "DOC-IBM / third-party book" "$OS2DOCS/pdf_text"

# 4. Community: weaker. Never launder one of these into an IBM claim.
section "EDM2 wiki mirror" "DOC - community, secondary" "$OS2DOCS/edm2"

echo
echo "=== $hits_total match(es) across all present sources ==="
if [ "$hits_total" -eq 0 ]; then
    cat <<'EOF'

A zero result is NOT proof that OS/2 lacks the facility. Before concluding that:
  - try IBM's wording, not yours (e.g. "presentation space", not "canvas");
  - try the base name without a prefix ("OpenDC", not "DevOpenDC");
  - check the corpus is actually built:  ls $OS2DOCS/inf_text
  - a facility may be a WPS/SOM method or an IOCtl rather than a Win*/Dos* call.
See ../recipes/read-ibm-books.md and ../os2-app-dev-guide.md.
EOF
    exit 1
fi
