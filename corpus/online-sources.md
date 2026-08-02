# Online sources - where the OS/2 documentation actually lives

A curated list of things worth knowing about, beyond what `../sources.md` needs for the toolchain.
This is *reference*, not a fetch list: `fetch-books.sh` and `fetch-edm2.sh` automate the two bulk
mirrors; everything else here you grab by hand when a task needs it.

**Every URL and archive.org identifier below was checked live** (HTTP 200) when this file was
written. Archives move and identifiers get renamed - if one 404s, search
`archive.org/advancedsearch.php` rather than assuming the material is gone.

**Rights:** all of it belongs to IBM or another rights holder. Download for your own reference;
see the rights note at the top of `../sources.md`. Nothing here is redistributable.

---

## 1. The bulk mirrors (automated)

| Source | What | Script |
|---|---|---|
| `komh.github.io/os2books` | IBM redbooks, technical references, *Undocumented OS/2*, Toolkit docs, programming FAQ, REXX, DBCS - as HTML/PDF/text | `fetch-books.sh` |
| `www.edm2.com` | The OS/2 developer wiki: per-function pages, driver internals, article archive (~12,300 pages) | `fetch-edm2.sh` |

EDM2 is live and has a working MediaWiki API. It is `[DOC]`-grade - community, secondary.

## 2. The Developer Connection and DDK - on archive.org

The DevCon CDs are the richest single source: the `.INF` programming books (`cpgref`, `pm1`-`pm5`,
`gpi1`-`gpi4`, `pddref`, `mmref`, `somref`, `wps*`, `rexxpg`), the DDK, and sample source. Extract
the `.INF` files and run them through `build-inf-text.sh`.

| Identifier | What |
|---|---|
| `IBMDeveloperConnectionForOS25CDs` | **DevCon for OS/2 Vol 12 (5 CDs)** - the largest set; start here |
| `IBMTheDeveloperConnectionForOS2Vol7` | DevCon for OS/2 Vol 7 |
| `IBMDeveloperConnectionForOS2Vol3` | DevCon for OS/2 Vol 3 |
| `IBMDevConR2V2` | DevCon Release 2 Volume 2 |
| `TheIBMDeveloperConnectionVol1` | DevCon Vol 1 |
| `cdrinc_The_Developer_Connection_Device_Driver_Kit_for_OS2_IBM` | **DevCon Device Driver Kit** - the PDD/IFS/GRADD/DISPLAY references |
| `IBMDDKit2004` | OS/2 Device Driver Development Kit, 2004 |
| `theos2warptoolkitforsoftwaredevelopers` | The OS/2 Warp Toolkit for Software Developers |
| `os2devmag` | IBM OS/2 Developer Magazine |
| `hobbes-os2-september-1999-walnut-creek-cd` | Hobbes archive snapshot on CD, Sept 1999 |

Use as `https://archive.org/details/<identifier>`.

## 3. The OS/2 Debugging Handbook - all four volumes

This matters if you use `tools/kdb_*`. It is a **four-volume** set, and Volume II is the one that
documents the debug kernel and dump formatter - i.e. the thing the KDB tooling in this kit drives.
Most people only ever find Volume I.

| Identifier | Volume |
|---|---|
| `sg244640` | I - Basic Skills and Diagnostic Techniques |
| `sg244641` | **II - Using the Debug Kernel and Dump Formatter** |
| `sg244642` (also `sg24464200`) | III - System Trace Reference |
| `sg244643` | IV - System Diagnostic Reference |

See `../recipes/kdb-reference.md` and `../recipes/setup-kdb-vm.md`.

## 4. Live community sites

| Site | What | Grade |
|---|---|---|
| `www.edm2.com` | Developer wiki, per-API pages | `[DOC]` |
| `hobbesarchive.com` | The Hobbes software/source archive - the successor site. The long-standing `hobbes.nmsu.edu` is **dead** (NMSU retired it); `hobbes.os-2.in` is a working mirror | varies |
| `www.os2museum.com` | Internals archaeology, boot/kernel behaviour, bug histories | `[DOC]` |
| `www.os2world.com` | Community forum and file archive | `[DOC]` |
| `trac.netlabs.org` | GCC/kLIBC, ports, source repositories | source |
| `komh.github.io/os2books` | Book mirror (see section 1) | `[DOC-IBM]` |

`os2museum.com` is unusually good on *why* something behaves as it does - often the only written
account of a kernel quirk. Still `[DOC]`: it is one person's research, not IBM's word.

## 5. Individual PDFs mirrored at komh

These are single files, fetchable directly from `https://komh.github.io/os2books/pdf/<file>`
(URL-encode the spaces). All verified present:

- `TCPIP Programming for OS2.pdf` - the sockets book
- `84X1434_OS2_Technical_Reference_Volume_1_Sep87.pdf`, `84X1440_..._Volume_2_Sep87.pdf` - the
  original 1987 OS/2 technical references
- `sg244719.pdf`, `sg244627.pdf` - Warp redbooks
- `thirded.pdf` - *OS/2 Warp Programming*, 3rd ed.
- `OS2_REXX.pdf` - REXX
- `inside_os2.pdf` - *Inside OS/2*
- `Surviving_warp_in_the_sea_of_windows.pdf`

Run any of them through `pdf-to-text.sh` to make them greppable.

## 5b. Scanned books on archive.org - fetch the OCR, not the PDF

Archive.org OCRs its scans and publishes the result as derivative files. Fetching those beats
downloading the PDF and OCRing it yourself: it is smaller, it is already done, and
`_page_numbers.json` gives you the book's **printed** page numbers, so a hit is citable as
"p.144" and checkable against the physical book.

`fetch-archive-book.sh <id> <name>` does all of it. Verified live:

| Identifier | Book | Notes |
|---|---|---|
| `os2presentationm0000petz` | Petzold, *OS/2 Presentation Manager Programming* (1994) | 934 pp, 18 ch. The PM tutorial. OCR text on 97% of leaves, 931 printed page numbers. `[DOC]` - third-party. |

```sh
./fetch-archive-book.sh os2presentationm0000petz petzold-pm-programming
./search.sh WinCreateStdWindow          # now includes it, graded third-party
```

Four things to know before trusting a result from a scan:

- **Not every `[[page N]]` was read off a page.** Archive.org *interpolates* a page number when it
  cannot find a folio on the leaf - 82 of this book's 931 are inferred from their neighbours.
  `djvu2txt.py` marks those `[[page N ~]]`. Cite a `~` page as approximate, or check it against the
  physical book. (They are usually right; they go wrong in runs, wherever a book restarts its
  numbering or inserts unnumbered plates.)
- **`[[page N]]` here is not `[[page N]]` from `pdf-to-text.sh`.** This script emits the book's
  *printed* page number; `pdf-to-text.sh` emits the *Nth page of the PDF*. Both land in
  `pdf_text/`. For a book with front matter the two differ by a constant offset - 32 in this one.
  Know which tool produced a file before citing a page from it.
- **Search case-insensitively and in fragments.** Hyphenation is broken across line ends, and the
  book's own typography survives into the text (headings are set in caps, so `WinCreateStdWindow`
  appears 145 times as written and twice as `WINCREATESTDWINDOW` - that is the book shouting, not
  OCR damage, but it defeats a case-sensitive grep either way). `search.sh` handles both already.
- **Some leaves have no text** (full-page figures, plates, scan failures). `<name>.coverage` lists
  them. A miss that lands there is not the book being silent.

Not every item can be fetched this way - a lending-only scan may withhold the OCR derivatives. The
script does **not** detect this in advance; it asks for the file and reports the failure. Do not
read a failed fetch as "restricted": a wrong identifier and a never-OCRed scan fail identically, and
the presence of an `_encrypted.pdf` does *not* imply the OCR is withheld (this very item publishes
both). Check the item's file list to tell them apart.

## 6. Not freely available

Worth knowing so you do not waste time looking:

- **The Ultimate OS/2 Programmer's Manual** (John Mueller, ~690 pages) - a commercial book. Not on
  archive.org under any identifier I could find. If you have a copy, `pdf-to-text.sh` extracts it
  well (~97% of pages carry a text layer).
- **IBM redbook `SG24-4640`** and siblings are on archive.org (section 3) but **not** on
  `redbooks.ibm.com` any more, and not in the komh `pdf/` directory - that URL 404s.
- **ArcaOS** is a current commercial product (`arcanoae.com`). Buy it; it is the recommended test
  target and ships the Toolkit and GCC/kLIBC.

## 7. Finding things yourself

archive.org's search API is the tool, and plain terms work better than field syntax:

```sh
curl -sS -G https://archive.org/advancedsearch.php \
  --data-urlencode 'q=os2 device driver kit' \
  --data-urlencode 'fl[]=identifier,title' \
  --data-urlencode 'rows=10' --data-urlencode 'output=json' | python3 -m json.tool
```

Then check a candidate before trusting it:

```sh
curl -sS https://archive.org/metadata/<identifier> | python3 -m json.tool | head -40
```

Two habits worth keeping: search for the **IBM order number** (`SG24-4641`, `84X1434`,
`GG24-3730`) as well as the title, and check `../sources.md` section 0 first - the machine you are on may
already have the thing you are about to download.
