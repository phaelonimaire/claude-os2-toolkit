#!/bin/sh
# fetch-edm2.sh - mirror the EDM2 developer wiki as greppable wikitext.
#
# EDM2 (edm2.com) is the OS/2 developer wiki: per-function pages, driver
# internals, and article archives that fill gaps the IBM books leave. It is
# [DOC]-grade - community, secondary. Useful for corroboration and for finding
# IBM's own terminology, never as a substitute for IBM's word.
#
# This enumerates pages through the MediaWiki API and fetches each one's raw
# wikitext (action=raw), which is smaller and far more greppable than rendered
# HTML. Resumable: existing files are skipped, so re-run after an interruption.
#
# Usage:
#   ./fetch-edm2.sh            # enumerate + fetch everything missing
#   ./fetch-edm2.sh --list     # only rebuild the page list, fetch nothing
#
# Output: $OS2DOCS/edm2/<Page_Title>.wiki   (OS2DOCS defaults to ~/os2docs)
#
# RIGHTS: EDM2 declares no machine-readable content licence (its API returns an
# empty rightsinfo). Mirror it for your own reference; do not redistribute the
# mirror or fold it into a published project. Be polite: this rate-limits itself,
# so leave that in place.
set -e

: "${OS2DOCS:=$HOME/os2docs}"
api=https://www.edm2.com/api.php
raw=https://www.edm2.com/index.php
out="$OS2DOCS/edm2"
list="$OS2DOCS/edm2_pages.txt"
delay=${EDM2_DELAY:-0.3}

command -v curl >/dev/null 2>&1 || { echo "fetch-edm2.sh: needs curl" >&2; exit 127; }
command -v python3 >/dev/null 2>&1 || { echo "fetch-edm2.sh: needs python3" >&2; exit 127; }

mkdir -p "$out"

# --- enumerate every page in the main namespace, following continuation ---
if [ ! -s "$list" ] || [ "$1" = "--list" ]; then
    echo "enumerating pages via the MediaWiki API ..."
    python3 - "$api" "$list" <<'PY'
import json, sys, urllib.parse, urllib.request
api, out = sys.argv[1], sys.argv[2]
titles, cont, page = [], None, 0
while True:
    q = {"action": "query", "list": "allpages", "aplimit": "500",
         "apnamespace": "0", "format": "json"}
    if cont:
        q["apcontinue"] = cont
    with urllib.request.urlopen(api + "?" + urllib.parse.urlencode(q), timeout=60) as r:
        d = json.load(r)
    batch = d.get("query", {}).get("allpages", [])
    titles += [p["title"] for p in batch]
    page += 1
    print("  batch %d: +%d (total %d)" % (page, len(batch), len(titles)))
    cont = d.get("continue", {}).get("apcontinue")
    if not cont:
        break
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(titles) + "\n")
print("  wrote %d titles to %s" % (len(titles), out))
PY
    [ "$1" = "--list" ] && exit 0
fi

total=$(wc -l < "$list" | tr -d ' ')
echo "fetching $total page(s) into $out (existing files skipped)"

n=0; got=0; skip=0; fail=0
while IFS= read -r title; do
    [ -n "$title" ] || continue
    n=$((n + 1))
    # Filename-safe: path separators and shell-hostile characters only.
    safe=$(printf '%s' "$title" | tr ' /' '__' | tr -d '\\:*?"<>|')
    dst="$out/$safe.wiki"
    if [ -s "$dst" ]; then
        skip=$((skip + 1))
        continue
    fi
    enc=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$title")
    if curl -sS -f --max-time 45 -o "$dst.tmp" \
            "$raw?title=$enc&action=raw" 2>/dev/null && [ -s "$dst.tmp" ]; then
        mv "$dst.tmp" "$dst"
        got=$((got + 1))
    else
        # Never leave a zero-byte file: it would be skipped as "already fetched"
        # on the next run and become a permanent silent hole in the mirror.
        rm -f "$dst.tmp"
        fail=$((fail + 1))
    fi
    [ $((n % 100)) -eq 0 ] && echo "  $n/$total  fetched=$got skipped=$skip failed=$fail"
    sleep "$delay"
done < "$list"

echo
echo "done: $got fetched, $skip already present, $fail failed, of $total"
echo "corpus: $out  ($(du -sh "$out" 2>/dev/null | cut -f1))"
[ "$fail" -gt 0 ] && echo "  re-run to retry the $fail failure(s)"
exit 0
