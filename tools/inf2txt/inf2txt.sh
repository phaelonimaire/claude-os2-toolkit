#!/bin/sh
# usage: inf2txt.sh <path-to-inf>   -> clean UTF-8 plain text on stdout
#
# The IPF text inside an .INF is stored in an IBM PC code page (CP850 for the
# OS/2 programming books; CP437 for some older material), NOT in UTF-8. Emitted
# raw, the high bytes make the output look like ISO-8859 to `file`, and GNU grep
# then classifies it as *binary* and silently prints nothing at all -- no error,
# no "binary file matches". A verification grep that returns empty is then read
# as "IBM does not document this", which is exactly backwards.
#
# So we transcode to UTF-8 here. Override the source code page with
# INF2TXT_CP=CP437 (etc.) if a book converts wrongly.
set -e
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

[ $# -ge 1 ] || { echo "usage: inf2txt.sh <path-to-inf>" >&2; exit 2; }
[ -r "$1" ]  || { echo "inf2txt.sh: cannot read '$1'" >&2; exit 2; }
[ -x "$dir/inf2txt" ] || {
    echo "inf2txt.sh: $dir/inf2txt not built - run $dir/build.sh first" >&2
    exit 127
}

: "${INF2TXT_CP:=CP850}"

# Probe once, up front: a mid-pipeline fallback is not possible because the
# failing iconv would already have consumed stdin. -c drops any unconvertible
# byte rather than aborting, so a bad byte cannot silently truncate a book.
if command -v iconv >/dev/null 2>&1 &&
   printf '' | iconv -f "$INF2TXT_CP" -t UTF-8 >/dev/null 2>&1; then
    conv="iconv -c -f $INF2TXT_CP -t UTF-8//TRANSLIT"
else
    conv="cat"
    echo "inf2txt.sh: warning: iconv unavailable or '$INF2TXT_CP' unsupported;" >&2
    echo "  output stays in the source code page -- you MUST use 'grep -a'" >&2
fi

# Note: the exit status of this pipeline is the last stage's, not inf2txt's; the
# -x check above is the portable guard (set -o pipefail is not POSIX sh).
"$dir/inf2txt" "$1" \
 | sed -E 's/<[^>]*>//g' \
 | sed -E 's/[ \t]+$//' \
 | cat -s \
 | $conv
