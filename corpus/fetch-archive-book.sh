#!/bin/sh
# fetch-archive-book.sh - turn a scanned archive.org book into greppable,
# page-citable text under $OS2DOCS/pdf_text/.
#
# Many OS/2 programming books exist only as archive.org scans. Archive.org
# already OCRs them and publishes the result as derivative files, so there is no
# reason to download a 44 MB PDF and OCR it again: fetch the OCR directly.
#
#   <id>_djvu.xml           OCR text WITH page + line structure  (what we want)
#   <id>_page_numbers.json  scan leaf -> the book's printed page number
#   <id>_djvu.txt           the same text, flattened, no page boundaries
#
# We take the XML because it preserves page boundaries, and the page-number map
# because it makes a hit citable as "book p.N" rather than "somewhere in a
# 900-page book". Output matches pdf-to-text.sh, so search.sh finds it with no
# extra configuration.
#
# Usage:
#   ./fetch-archive-book.sh <archive-id> [output-name]
#   ./fetch-archive-book.sh os2presentationm0000petz petzold-pm-programming
#
# Output:
#   $OS2DOCS/pdf_text/<name>.txt        full text, [[page N]] / [[leaf N]] markers
#   $OS2DOCS/pdf_text/<name>.coverage   per-leaf text/EMPTY map
#
# RIGHTS: a scanned book is somebody's copyrighted work, and being out of print
# is not a licence. Fetch it for your own reference, on your own machine. Do not
# re-host it and do not commit it into a project - $OS2DOCS is deliberately
# outside this repo. See ../sources.md.
#
# Some archive.org items are lending-only and withhold the OCR derivatives. This
# script does NOT detect that in advance - it asks for the file and reports the
# failure. Do not read a failed fetch as "restricted": it is equally likely to be
# a wrong identifier or an un-OCRed scan, and the script cannot tell you which.
# Note that the presence of an _encrypted.pdf does NOT imply the OCR is withheld
# (os2presentationm0000petz publishes both). If a fetch does turn out to be
# blocked, that is the answer - do not work around it.
#
# PROVENANCE: a commercial book is [DOC] - its author's reading of OS/2, not
# IBM's word. Corroborate against the IBM books before treating it as a
# contract. See ../corpus/README.md.
set -e

: "${OS2DOCS:=$HOME/os2docs}"
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

id=$1
[ -n "$id" ] || {
    echo "usage: fetch-archive-book.sh <archive-id> [output-name]" >&2
    echo "  e.g. fetch-archive-book.sh os2presentationm0000petz petzold-pm" >&2
    exit 2
}
# Sanitise the output name the way pdf-to-text.sh:70 does. Without this a name
# containing "/" or ".." writes outside $OS2DOCS and still reports success.
name=$(printf '%s' "${2:-$id}" | tr 'A-Z ' 'a-z_' | tr -cd 'a-z0-9._-')
name=$(printf '%s' "$name" | sed 's/^[.]*//')      # no leading dots -> no ".."
[ -n "$name" ] || { echo "output name is empty after sanitising" >&2; exit 2; }
[ "$name" = "${2:-$id}" ] || echo "  (output name sanitised to '$name')"

command -v curl >/dev/null 2>&1 || { echo "needs curl" >&2; exit 127; }
command -v python3 >/dev/null 2>&1 || { echo "needs python3" >&2; exit 127; }

out="$OS2DOCS/pdf_text"
mkdir -p "$out"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/archbook.XXXXXX")
trap 'rm -rf "$tmp"' EXIT INT TERM

base="https://archive.org/download/$id"
echo "item:   $id"
echo "output: $out/$name.txt"

# Fetch the OCR XML. -f so an HTTP error is an error and not a 200-byte file
# that later parses as "this book contains nothing".
printf '  fetching OCR text ... '
if ! curl -fsSL --retry 2 -o "$tmp/djvu.xml" "$base/${id}_djvu.xml"; then
    echo "FAILED"
    cat >&2 <<EOF

Could not fetch ${id}_djvu.xml.

That is a statement about the fetch, not about the book, and this script cannot
tell you which of these it was. Check them yourself, in order:
  - the identifier is right   https://archive.org/details/$id
  - the item has been OCRed at all - some scans have no _djvu.xml
  - the OCR derivatives are actually published (a lending-only item may withhold
    them). An _encrypted.pdf in the listing does NOT mean they are withheld.
The file list settles all three:
  curl -s https://archive.org/metadata/$id | python3 -m json.tool | grep name
EOF
    exit 1
fi
echo "$(wc -c < "$tmp/djvu.xml" | tr -d ' ') bytes"

# The printed-page map is optional: without it every marker degrades to
# [[leaf N]], which is still usable, just less precise.
printf '  fetching page numbers ... '
if curl -fsSL --retry 2 -o "$tmp/pages.json" "$base/${id}_page_numbers.json"; then
    echo "ok"
    pagearg="$tmp/pages.json"
else
    echo "absent (markers will be [[leaf N]])"
    pagearg=-
fi

echo "  converting ..."
python3 "$here/djvu2txt.py" "$tmp/djvu.xml" "$pagearg" "$out/$name.txt"

cat <<EOF

done: $out/$name.txt  ($(wc -l < "$out/$name.txt" | tr -d ' ') lines)

Search it with the rest of the corpus:
  ./search.sh WinCreateStdWindow

Citing a hit, by marker:
  [[page 144]]    printed page number READ off the page - cite it as p.144
  [[page 144 ~]]  archive.org INTERPOLATED this number; cite as approximate or
                  verify against the physical book first
  [[leaf 7]]      no printed number on that leaf - cite it as a leaf, not a page

Beware: files produced by pdf-to-text.sh live in the same directory and their
[[page N]] is the Nth page of a PDF, not a printed page number. The two are
offset by however much front matter a book has.
EOF
