#!/usr/bin/env python3
"""djvu2txt.py - archive.org `_djvu.xml` -> page-marked plain text.

Markers, in decreasing order of how much you may trust them:

  [[page 144]]     the book's printed page number, READ off the page by OCR
  [[page 144 ~]]   a printed page number archive.org INTERPOLATED - it found no
                   folio on this leaf and inferred the number from its
                   neighbours. Usually right; wrong for a whole run wherever the
                   book restarts numbering or inserts unnumbered plates.
  [[leaf 7]]       a scan leaf with no page number at all - cover, front matter

The `~` exists because the alternative is a citation that looks checkable and
isn't. Cite a `~` page as approximate, or check it against the physical book
before relying on it. For this reason a bare `[[page N]]` is a stronger claim
than `pdf-to-text.sh` can make: that script's `[[page N]]` is the Nth page of a
PDF, which for any book with front matter is NOT the printed page number.

Also writes `<out>.coverage` - one line per leaf, `text` or `EMPTY`. Scanned
books have text-less leaves (plates, full-page figures, scanning failures), and
a search miss that lands in one is not evidence the book is silent.

Output is written to a temporary file and renamed into place only after the
whole XML parses. A truncated download or an interrupt therefore leaves NO
output rather than a short book that reads as a complete one.

Usage:
    djvu2txt.py <_djvu.xml> <_page_numbers.json|-> <out.txt>
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

USAGE = "usage: djvu2txt.py <_djvu.xml> <_page_numbers.json|-> <out.txt>"

# "..._0142.djvu" -> 142. Each OBJECT names its own leaf, which beats trusting
# the enumeration order to match the separate page-number file.
USEMAP_NUM = re.compile(r"_(\d+)\.djvu$")


def load_page_numbers(path):
    """leafNum -> (label, interpolated?).

    A label whose confidence/pageProb/wordConf are ALL null was not read off the
    page; archive.org filled it in. Keeping that distinction is the whole point.
    """
    printed = {}
    if not path:
        return printed, 0
    try:
        with open(path) as fh:
            pages = json.load(fh).get("pages", [])
        total = len(pages)                    # ALL leaves, not just labelled ones
        for p in pages:
            label = p.get("pageNumber")
            if not label:
                continue
            interpolated = (p.get("confidence") is None
                            and p.get("pageProb") is None
                            and p.get("wordConf") is None)
            printed[p["leafNum"]] = (label, interpolated)
    except Exception as exc:                  # malformed JSON, unexpected shape
        print("djvu2txt: no usable page numbers (%s: %s); using [[leaf N]] throughout"
              % (type(exc).__name__, exc), file=sys.stderr)
        return {}, 0
    return printed, total


def marker_for(leaf, printed):
    entry = printed.get(leaf)
    if entry is None:
        return "[[leaf %d]]" % leaf
    label, interpolated = entry
    return "[[page %s ~]]" % label if interpolated else "[[page %s]]" % label


def convert(xml_path, pagenum_path, out_path):
    printed, total_entries = load_page_numbers(pagenum_path)

    root, ext = os.path.splitext(out_path)    # splitext, NOT rsplit('.') - a dot
    cov_path = root + ".coverage"             # in a DIRECTORY name must not count
    tmp_out = out_path + ".part"
    tmp_cov = cov_path + ".part"

    leaf = 0
    with_text = 0
    empty = []
    interpolated = 0
    drift = []

    try:
        with open(tmp_out, "w", encoding="utf-8") as out, \
             open(tmp_cov, "w", encoding="utf-8") as cov:
            # iterparse + clear(): these run to tens of megabytes, and holding
            # the whole tree costs far more than the text it yields.
            for _event, elem in ET.iterparse(xml_path, events=("end",)):
                if not elem.tag.endswith("OBJECT"):   # endswith: tolerate a namespace
                    continue
                leaf += 1

                # Cross-check the positional counter against the leaf number the
                # page itself carries. If a derive ever omits an OBJECT these
                # diverge, and every label from that point on would be shifted.
                m = USEMAP_NUM.search(elem.get("usemap") or "")
                if m and int(m.group(1)) != leaf:
                    drift.append((leaf, int(m.group(1))))

                lines = []
                for line in elem.iter():
                    if not line.tag.endswith("LINE"):
                        continue
                    words = [w.text for w in line.iter()
                             if w.tag.endswith("WORD") and w.text]
                    if words:
                        lines.append(" ".join(words))
                elem.clear()

                marker = marker_for(leaf, printed)
                if marker.endswith(" ~]]"):
                    interpolated += 1
                out.write("\n%s\n" % marker)
                if lines:
                    out.write("\n".join(lines) + "\n")
                    with_text += 1
                else:
                    empty.append(marker)
                cov.write("%s\t%s\n" % (marker, "text" if lines else "EMPTY"))

        if leaf == 0:
            print("djvu2txt: no pages found in %s - is it really a _djvu.xml?"
                  % xml_path, file=sys.stderr)
            return 1

        # Only now is the output a whole book. Rename is atomic on POSIX.
        os.replace(tmp_out, out_path)
        os.replace(tmp_cov, cov_path)
    finally:
        for t in (tmp_out, tmp_cov):
            if os.path.exists(t):
                os.unlink(t)

    print("  %d leaves, text on %d (%d%%), %d printed page numbers"
          % (leaf, with_text, with_text * 100 // leaf, len(printed)))
    if interpolated:
        print("  %d of those were INTERPOLATED by archive.org, not read off the"
              % interpolated)
        print("  page - they are marked [[page N ~]]. Treat as approximate.")
    if total_entries and leaf != total_entries:
        # Compare against ALL entries, not the labelled subset - most books have
        # unlabelled front matter, so comparing to len(printed) cries wolf every
        # time. A real mismatch here means the two derivatives disagree about how
        # many leaves the book has, which puts every label in doubt.
        print("  WARNING: %d leaves in the XML vs %d in the page-number file."
              % (leaf, total_entries), file=sys.stderr)
        print("  The two derivatives disagree; page labels may be shifted.",
              file=sys.stderr)
    if drift:
        first = drift[0]
        print("  WARNING: leaf numbering drifts from the scan's own numbering at"
              " position %d (scan says %d), %d leaf/leaves affected."
              % (first[0], first[1], len(drift)), file=sys.stderr)
        print("  Page labels after that point are probably shifted. Do not cite"
              " them.", file=sys.stderr)
    if empty:
        shown = " ".join(empty[:8]) + (" ..." if len(empty) > 8 else "")
        print("  no text on %d leaf/leaves: %s" % (len(empty), shown))
        print("  A search miss may fall in those. Check <name>.coverage before")
        print("  concluding the book does not cover something.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(USAGE)
    sys.exit(convert(sys.argv[1],
                     None if sys.argv[2] == "-" else sys.argv[2],
                     sys.argv[3]))
