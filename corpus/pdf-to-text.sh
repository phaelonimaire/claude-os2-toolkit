#!/bin/sh
# pdf-to-text.sh - make OS/2 PDF books searchable, with page numbers preserved.
#
# The OS/2 PDFs (redbooks, technical references, the big programmer's manuals)
# are the least usable part of a corpus: grep cannot read them, and the obvious
# workaround - splitting the PDF into per-page PDFs - is actively harmful. It
# produces hundreds of files that are STILL not greppable, and if the split
# rasterizes, it destroys whatever text layer the original had. (A 690-page
# manual on this pattern became 690 one-page PDFs, 636 MB, zero searchable text,
# while the original PDF had text on ~80% of its pages.)
#
# What actually helps: extract the text once, keep the page numbers so a hit can
# be cited, and report which pages had no text so a miss can be attributed to a
# gap rather than read as "the book does not cover it".
#
# Usage:
#   ./pdf-to-text.sh BOOK.pdf [MORE.pdf ...]
#   ./pdf-to-text.sh --chunk 100 BOOK.pdf     # also write 100-page chunk files
#   ./pdf-to-text.sh --ocr BOOK.pdf           # OCR the text-less pages (slow)
#   ./pdf-to-text.sh --scan DIR               # every PDF under DIR
#
# Output ($OS2DOCS defaults to ~/os2docs):
#   $OS2DOCS/pdf_text/<name>.txt              full text, [[page N]] markers
#   $OS2DOCS/pdf_text/<name>.coverage         per-page text/empty map
#   $OS2DOCS/pdf_text/<name>.pNNNN-NNNN.txt   chunks, with --chunk
#
# RIGHTS: converts PDFs you already have. Downloads nothing, and gives you no
# right to redistribute the output. See ../sources.md.
set -e

: "${OS2DOCS:=$HOME/os2docs}"
out="$OS2DOCS/pdf_text"
chunk=0
ocr=0
scan=""

command -v pdftotext >/dev/null 2>&1 || {
    echo "pdf-to-text.sh: needs pdftotext (apt install poppler-utils)" >&2; exit 127; }
command -v pdfinfo >/dev/null 2>&1 || {
    echo "pdf-to-text.sh: needs pdfinfo (apt install poppler-utils)" >&2; exit 127; }

while [ $# -gt 0 ]; do
    case $1 in
        --chunk) chunk=$2; shift 2 ;;
        --ocr)   ocr=1; shift ;;
        --scan)  scan=$2; shift 2 ;;
        --help|-h) sed -n '2,30p' "$0"; exit 0 ;;
        --*) echo "pdf-to-text.sh: unknown option $1" >&2; exit 2 ;;
        *) break ;;
    esac
done

if [ -n "$scan" ]; then
    [ -d "$scan" ] || { echo "pdf-to-text.sh: no such directory: $scan" >&2; exit 2; }
    set -- $(find "$scan" -type f -iname '*.pdf' | sort)
fi
[ $# -ge 1 ] || { echo "usage: pdf-to-text.sh [--chunk N] [--ocr] BOOK.pdf ..." >&2; exit 2; }

if [ "$ocr" = 1 ] && ! command -v tesseract >/dev/null 2>&1; then
    echo "pdf-to-text.sh: --ocr needs tesseract (apt install tesseract-ocr)" >&2
    exit 127
fi

mkdir -p "$out"

for pdf in "$@"; do
    [ -f "$pdf" ] || { echo "skip (not a file): $pdf" >&2; continue; }
    base=$(basename "$pdf"); stem=${base%.*}
    # Space-free, lowercase stem: these names get typed into grep commands.
    stem=$(printf '%s' "$stem" | tr 'A-Z ' 'a-z_' | tr -cd 'a-z0-9._-')
    dst="$out/$stem.txt"
    cov="$out/$stem.coverage"

    pages=$(pdfinfo "$pdf" 2>/dev/null | awk '/^Pages:/{print $2}')
    [ -n "$pages" ] || { echo "skip (unreadable PDF): $pdf" >&2; continue; }

    echo "$base  ($pages pages)"

    : > "$dst"; : > "$cov"
    withtext=0; empty=0; ocred=0
    pg=1
    while [ "$pg" -le "$pages" ]; do
        # -layout keeps tables and syntax blocks readable, which matters for
        # reference material far more than reflowed prose would.
        txt=$(pdftotext -layout -f "$pg" -l "$pg" "$pdf" - 2>/dev/null || true)
        n=$(printf '%s' "$txt" | tr -d '[:space:]' | wc -c | tr -d ' ')

        if [ "$n" -lt 200 ] && [ "$ocr" = 1 ]; then
            # Page is image-only: rasterize just this page and OCR it.
            tmp=$(mktemp -d)
            if pdftoppm -r 300 -f "$pg" -l "$pg" -gray -png "$pdf" "$tmp/p" 2>/dev/null; then
                img=$(find "$tmp" -name 'p*.png' | head -1)
                if [ -n "$img" ] && tesseract "$img" "$tmp/o" 2>/dev/null; then
                    txt=$(cat "$tmp/o.txt" 2>/dev/null || true)
                    n=$(printf '%s' "$txt" | tr -d '[:space:]' | wc -c | tr -d ' ')
                    [ "$n" -ge 200 ] && ocred=$((ocred + 1))
                fi
            fi
            rm -rf "$tmp"
        fi

        # An explicit marker, not pdftotext's form feed: a grep hit then carries
        # its page number, so a fact taken from here can be cited as "book p.N".
        printf '\n[[page %s]]\n' "$pg" >> "$dst"
        printf '%s\n' "$txt" >> "$dst"

        if [ "$n" -ge 200 ]; then
            withtext=$((withtext + 1)); printf '%s\ttext\t%s\n' "$pg" "$n" >> "$cov"
        else
            empty=$((empty + 1));       printf '%s\tempty\t%s\n' "$pg" "$n" >> "$cov"
        fi

        [ $((pg % 200)) -eq 0 ] && printf '  ... %s/%s pages\n' "$pg" "$pages"
        pg=$((pg + 1))
    done

    pct=$(( withtext * 100 / pages ))
    printf '  text on %s/%s pages (%s%%)' "$withtext" "$pages" "$pct"
    [ "$ocred" -gt 0 ] && printf ', %s recovered by OCR' "$ocred"
    printf '\n  -> %s\n' "$dst"

    if [ "$empty" -gt 0 ]; then
        printf '  %s page(s) yielded no text' "$empty"
        if [ "$ocr" = 1 ]; then
            printf ' even after OCR'
        else
            printf ' - re-run with --ocr to recover them'
        fi
        printf '. Page list: %s\n' "$cov"
        echo "  A search miss may fall in those pages: check before concluding the"
        echo "  book does not cover something."
    fi

    # Optional page-range chunks, for feeding a bounded slice to a reader.
    if [ "$chunk" -gt 0 ] 2>/dev/null; then
        rm -f "$out/$stem".p[0-9]*-[0-9]*.txt
        s=1
        while [ "$s" -le "$pages" ]; do
            e=$((s + chunk - 1)); [ "$e" -gt "$pages" ] && e=$pages
            f=$(printf '%s/%s.p%04d-%04d.txt' "$out" "$stem" "$s" "$e")
            awk -v s="$s" -v e="$e" '
                /^\[\[page [0-9]+\]\]$/ { match($0,/[0-9]+/); p=substr($0,RSTART,RLENGTH)+0 }
                p>=s && p<=e' "$dst" > "$f"
            s=$((e + 1))
        done
        printf '  chunks: %s file(s) of %s pages each\n' \
               "$(ls "$out/$stem".p[0-9]*-[0-9]*.txt 2>/dev/null | wc -l | tr -d ' ')" "$chunk"
    fi
done

echo
echo "corpus: $out"
echo "search it with:  ./search.sh <pattern>   (pdf_text is included)"
