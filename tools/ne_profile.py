#!/usr/bin/env python3
"""NE (New Executable) header profiler for OS/2 binaries.

Takes one or more binaries (or --list FILE naming them, one per line),
identifies MZ/ZM->NE/LX/LE/PE format, and for NE-OS/2 binaries deep-profiles:
segment attributes, relocation types, address types, imported modules.

Emits an aggregate report to stdout and writes ne_profile_result.json into the
current directory. Exits non-zero if every input failed to classify.
"""
import sys, os, struct, json, collections

# ---- NE segment flag bits ----
NESDATA     = 0x0001  # data (else code)
NESMOVE     = 0x0010  # movable
NESPURE     = 0x0020  # pure/shared
NESPRELOAD  = 0x0040  # preload (else load-on-call)
NESRONLY    = 0x0080  # read-only (data) / execute-only (code)
NESRELOC    = 0x0100  # has relocation records
NESDEBUG    = 0x0200
NESDISCARD  = 0x1000  # discardable (per some refs 0x1000; discard-prio in high nibble)
NES32BIT    = 0x2000  # 32-bit segment (USE32)

# reloc record: address-type byte
ADDR_TYPES = {0:'LOBYTE',2:'SEGMENT16',3:'FARADDR16_16',5:'OFFSET16',
              6:'FARADDR16_32?',8:'OFFSET16b?',0x0B:'FARADDR16_32',0x0D:'OFFSET32'}
# reloc record: type byte (low 2 bits), 0x04 = additive
RELOC_TYPES = {0:'INTERNALREF',1:'IMPORTORDINAL',2:'IMPORTNAME',3:'OSFIXUP'}
TARGET_OS = {0:'unknown',1:'OS/2',2:'Windows',3:'DOS4',4:'Win386',5:'BOSS'}

def read_pstr(buf, off):
    if off >= len(buf): return '', off
    n = buf[off]
    return buf[off+1:off+1+n].decode('latin1','replace'), off+1+n

def profile_ne(f, ne_off, size):
    hdr = f.read(64)  # read from ne_off
    if len(hdr) < 64: return None
    flags   = struct.unpack_from('<H', hdr, 0x0C)[0]
    segcnt  = struct.unpack_from('<H', hdr, 0x1C)[0]
    modref  = struct.unpack_from('<H', hdr, 0x1E)[0]
    segtab  = struct.unpack_from('<H', hdr, 0x22)[0]
    modreftab = struct.unpack_from('<H', hdr, 0x28)[0]
    impnames= struct.unpack_from('<H', hdr, 0x2A)[0]
    movcnt  = struct.unpack_from('<H', hdr, 0x30)[0]
    align   = struct.unpack_from('<H', hdr, 0x32)[0]
    tgtos   = hdr[0x36]
    align = align if align else 9  # default sector shift 512
    is_dll  = bool(flags & 0x8000)
    apptype = (flags >> 8) & 0x07  # 1=full,2=PM-compat,3=PM

    rec = {'format':'NE', 'targetos':TARGET_OS.get(tgtos,str(tgtos)),
           'is_dll':is_dll, 'apptype':apptype, 'segcount':segcnt,
           'modrefcount':modref, 'movable_entries':movcnt,
           'seg_attrs':collections.Counter(), 'reloc_types':collections.Counter(),
           'addr_types':collections.Counter(), 'imports':[], 'reloc_total':0,
           'code_segs':0, 'data_segs':0}

    # imported module names (via module ref table -> imported names table)
    try:
        f.seek(ne_off + impnames)
        imp_blob = f.read(4096)
        f.seek(ne_off + modreftab)
        refs = f.read(modref*2)
        names = []
        for i in range(modref):
            o = struct.unpack_from('<H', refs, i*2)[0]
            nm,_ = read_pstr(imp_blob, o)
            names.append(nm.upper())
        rec['imports'] = names
    except Exception:
        pass

    # segment table: 8 bytes each
    try:
        f.seek(ne_off + segtab)
        segs = f.read(segcnt*8)
    except Exception:
        return rec
    for i in range(segcnt):
        try:
            soff, slen, sflags, smin = struct.unpack_from('<HHHH', segs, i*8)
        except Exception:
            break
        if sflags & NESDATA: rec['data_segs'] += 1
        else: rec['code_segs'] += 1
        for bit,name in ((NESMOVE,'MOVABLE'),(NESPURE,'PURE'),(NESPRELOAD,'PRELOAD'),
                         (NESRONLY,'RD/EXEC-ONLY'),(NESDISCARD,'DISCARDABLE'),
                         (NES32BIT,'32BIT'),(NESRELOC,'HAS-RELOC')):
            if sflags & bit: rec['seg_attrs'][name]+=1
        # relocation records
        if (sflags & NESRELOC) and soff:
            data_pos = soff << align
            try:
                f.seek(data_pos + slen)
                cnt = struct.unpack_from('<H', f.read(2))[0]
                relocs = f.read(cnt*8)
                for r in range(cnt):
                    atype = relocs[r*8]
                    rtype = relocs[r*8+1]
                    rec['addr_types'][ADDR_TYPES.get(atype,'a%02x'%atype)]+=1
                    base = rtype & 0x03
                    rec['reloc_types'][RELOC_TYPES.get(base,'r%d'%base)]+=1
                    if rtype & 0x04: rec['reloc_types']['+ADDITIVE']+=1
                    rec['reloc_total']+=1
            except Exception:
                pass
    # make counters serializable
    rec['seg_attrs']=dict(rec['seg_attrs']); rec['reloc_types']=dict(rec['reloc_types'])
    rec['addr_types']=dict(rec['addr_types'])
    return rec

def classify(path):
    try:
        size = os.path.getsize(path)
        with open(path,'rb') as f:
            mz = f.read(2)
            if mz not in (b'MZ',b'ZM'):
                return {'format':'notMZ'}
            f.seek(0x3C); lfa = struct.unpack('<I', f.read(4))[0]
            if lfa==0 or lfa+2 > size: return {'format':'MZ-only'}
            f.seek(lfa); sig = f.read(2)
            if sig==b'NE':
                f.seek(lfa); return profile_ne(f, lfa, size)
            if sig==b'LX': return {'format':'LX'}
            if sig==b'LE': return {'format':'LE'}
            if sig==b'PE': return {'format':'PE'}
            return {'format':'sig:'+sig.decode('latin1','replace')}
    except Exception as e:
        return {'format':'ERR','err':str(e)}

USAGE = ("usage: ne_profile.py <binary> [binary ...]\n"
         "       ne_profile.py --list <file>   (one path per line, # comments ok)\n"
         "Writes an aggregate report to stdout and ne_profile_result.json "
         "in the current directory.")

def read_listfile(path):
    """Read a path list: one per line, blank lines and #-comments skipped."""
    try:
        with open(path, 'r', encoding='utf-8', errors='strict') as fh:
            lines = [l.strip() for l in fh]
    except (OSError, UnicodeDecodeError) as e:
        sys.exit(f"ne_profile.py: --list {path}: {e}")
    return [l for l in lines if l and not l.startswith('#')]

def collect_paths(argv):
    """Binaries are taken literally; a path list requires an explicit --list.

    Sniffing the argument to guess "is this a binary or a list?" was ambiguous
    (it silently shredded any non-MZ text file into one bogus path per line, and
    the outcome depended on the locale encoding), so the two modes are explicit.
    """
    if argv and argv[0] == '--list':
        if len(argv) != 2:
            sys.exit(USAGE)
        return read_listfile(argv[1])
    if any(a.startswith('--') for a in argv):
        sys.exit(USAGE)
    return list(argv)

def main():
    if len(sys.argv) < 2:
        sys.exit(USAGE)
    paths = collect_paths(sys.argv[1:])
    if not paths:
        sys.exit("ne_profile.py: no input files")
    fmt = collections.Counter()
    ne_os2 = []
    per_file = {}
    for p in paths:
        r = classify(p)
        if not r: continue
        f = r.get('format','?')
        if f=='NE':
            f = 'NE-'+r.get('targetos','?')
        fmt[f]+=1
        if r.get('format')=='NE' and r.get('targetos')=='OS/2':
            r['path']=p; ne_os2.append(r)
        per_file[p]=r

    # ---- aggregate over NE-OS/2 ----
    agg = {'count':len(ne_os2),'dll':0,'exe':0,
           'seg_attr_files':collections.Counter(),   # files having >=1 seg with attr
           'reloc_type_files':collections.Counter(), # files using reloc type
           'reloc_type_total':collections.Counter(), # total reloc records by type
           'addr_type_total':collections.Counter(),
           'import_files':collections.Counter(),     # files importing module
           'segcount_hist':collections.Counter(),
           'apptype':collections.Counter(),
           'single_seg':0,'has_movable':0,'has_discardable':0,'has_32bit':0,
           'has_osfixup':0,'has_importname':0}
    for r in ne_os2:
        agg['dll' if r['is_dll'] else 'exe']+=1
        agg['apptype'][r['apptype']]+=1
        sc=r['segcount']; agg['segcount_hist'][sc if sc<=8 else '9+']+=1
        if sc<=1: agg['single_seg']+=1
        for a in r['seg_attrs']: agg['seg_attr_files'][a]+=1
        if 'MOVABLE' in r['seg_attrs']: agg['has_movable']+=1
        if 'DISCARDABLE' in r['seg_attrs']: agg['has_discardable']+=1
        if '32BIT' in r['seg_attrs']: agg['has_32bit']+=1
        for t,c in r['reloc_types'].items():
            agg['reloc_type_files'][t]+=1; agg['reloc_type_total'][t]+=c
        if 'OSFIXUP' in r['reloc_types']: agg['has_osfixup']+=1
        if 'IMPORTNAME' in r['reloc_types']: agg['has_importname']+=1
        for t,c in r['addr_types'].items(): agg['addr_type_total'][t]+=c
        for m in set(r['imports']): agg['import_files'][m]+=1

    with open('ne_profile_result.json','w') as jf:
        json.dump({'fmt':dict(fmt),
                   'agg':{k:(dict(v) if isinstance(v,collections.Counter) else v) for k,v in agg.items()},
                   'ne_os2':ne_os2},
                  jf, indent=1)

    # ---- print report ----
    P=print
    P("="*70); P("FORMAT BREAKDOWN (%d files scanned)"%len(paths)); P("="*70)
    for k,v in fmt.most_common(): P("  %-14s %6d"%(k,v))
    P(); P("="*70); P("NE OS/2 DEEP PROFILE (n=%d)"%agg['count']); P("="*70)
    P("  EXE: %d   DLL: %d"%(agg['exe'],agg['dll']))
    P("  apptype (0=none 1=fullscr 2=PM-compat 3=PM): %s"%dict(agg['apptype']))
    P("  single-segment files: %d (%.0f%%)"%(agg['single_seg'],100*agg['single_seg']/max(1,agg['count'])))
    P("  seg-count histogram: %s"%dict(sorted(agg['segcount_hist'].items(),key=lambda x:str(x[0]))))
    def pct(n): return "%d (%.0f%%)"%(n,100*n/max(1,agg['count']))
    P("  files w/ MOVABLE seg:     %s"%pct(agg['has_movable']))
    P("  files w/ DISCARDABLE seg: %s"%pct(agg['has_discardable']))
    P("  files w/ 32BIT seg:       %s"%pct(agg['has_32bit']))
    P(); P("  --- RELOCATION TYPES (the loader-critical part) ---")
    P("  files using each reloc type:")
    for t,c in agg['reloc_type_files'].most_common(): P("     %-14s %s"%(t,pct(c)))
    P("  total reloc records by type:")
    for t,c in agg['reloc_type_total'].most_common(): P("     %-14s %d"%(t,c))
    P("  address types (total records):")
    for t,c in agg['addr_type_total'].most_common(): P("     %-14s %d"%(t,c))
    P(); P("  --- TOP IMPORTED MODULES (by # of files) ---")
    for m,c in agg['import_files'].most_common(25): P("     %-14s %s"%(m,pct(c)))
    P(); P("Wrote ne_profile_result.json")

    # Every input failed to classify -> report failure, don't imply success.
    if fmt['ERR'] == len(paths):
        P("ne_profile.py: no input could be classified", file=sys.stderr)
        return 1
    return 0

if __name__=='__main__': sys.exit(main() or 0)
