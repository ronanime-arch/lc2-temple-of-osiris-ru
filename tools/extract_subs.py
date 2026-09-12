"""Extract per-line VO metadata + embedded multilingual subtitles from the ENGLISH bigfile."""
import struct, os, re, json, collections, csv

GAME = os.path.join('D:', os.sep, 'Games', 'Lara Croft - Temple of Osiris', 'Game')
OUT = os.path.dirname(os.path.abspath(__file__))
d = open(os.path.join(GAME, 'bigfile_ENGLISH.000.tiger'), 'rb').read()
cnt = struct.unpack_from('<I', d, 0x0c)[0]
ents = [struct.unpack_from('<IIIIII', d, 0x34 + i * 24) for i in range(cnt)]

LANGS = {0: 'english', 1: 'french', 2: 'german', 3: 'italian', 4: 'spanish',
         5: 'japanese', 6: 'portuguese', 7: 'l7', 8: 'l8', 9: 'russian',
         10: 'l10', 11: 'l11', 12: 'l12'}
PAIR = re.compile(rb'(?:^|\r)(\d{1,2})\r(\[[^\]\r]*\])?([^\r]*)')

rows = []
for (h, loc, size, z1, z2, off) in ents:
    fsb = d.find(b'FSB4', off, off + size)
    if fsb < 0:
        continue
    head = d[off:fsb]
    ns, shdrsize, datasize, ver, flags = struct.unpack_from('<IIIII', d, fsb + 4)
    p = fsb + 48
    name = d[p + 2:p + 32].split(b'\x00')[0].decode('latin1')
    lsamples, lcomp, lstart, lend, mode, freq = struct.unpack_from('<IIIIII', d, p + 32)
    dur = lsamples / freq if freq else 0
    # subtitle blob: from the first "0\r[" marker to the end of the wrapper
    start = head.find(b'0\r[')
    subs = {}
    tags = {}
    if start >= 0:
        blob = head[start:].rstrip(b'\x00')
        blob = blob.split(b'\x00')[0]
        for m in PAIR.finditer(blob):
            idx = int(m.group(1))
            tag = (m.group(2) or b'').decode('utf-8', 'replace')
            txt = m.group(3).decode('utf-8', 'replace').strip()
            lang = LANGS.get(idx, 'l%d' % idx)
            if txt:
                subs[lang] = txt
                tags[lang] = tag
    rows.append(dict(name=name, dur=round(dur, 3), size=size, comp=lcomp,
                     char=name.lower().split('.str')[0].split('_')[-1],
                     cat=name.lower().split('_')[1] if '_' in name else '',
                     en=subs.get('english', ''), ru=subs.get('russian', ''),
                     tag_en=tags.get('english', ''), tag_ru=tags.get('russian', ''),
                     nlangs=len(subs)))

print('entries with FSB:', len(rows))
withru = [r for r in rows if r['ru']]
withen = [r for r in rows if r['en']]
print('with English subtitle text: %d' % len(withen))
print('with Russian subtitle text: %d' % len(withru))
print('lines with no text at all: %d' % len([r for r in rows if not r['en'] and not r['ru']]))
print('avg languages per line:', round(sum(r['nlangs'] for r in rows) / len(rows), 2))

ru_chars = sum(len(re.sub(r'\[[^\]]*\]', '', r['ru'])) for r in withru)
en_chars = sum(len(re.sub(r'\[[^\]]*\]', '', r['en'])) for r in withen)
print('Russian characters (subtitle text): %d' % ru_chars)
print('English characters: %d' % en_chars)
print('ru/en char ratio: %.2f' % (ru_chars / en_chars if en_chars else 0))

print()
print('per character (speaker):')
by = collections.defaultdict(lambda: [0, 0.0, 0])
for r in rows:
    b = by[r['char']]
    b[0] += 1
    b[1] += r['dur']
    b[2] += len(r['ru'])
for c, (n, s, ch) in sorted(by.items(), key=lambda kv: -kv[1][1]):
    print('  %-10s lines=%4d  audio=%6.1f s  ru_chars=%6d' % (c, n, s, ch))

print()
print('samples:')
for r in rows[:6]:
    print('  %-32s %5.2fs  EN: %s' % (r['name'], r['dur'], r['en'][:70]))
    print('  %-32s        RU: %s' % ('', r['ru'][:70]))

nosub = [r for r in rows if not r['ru']]
print()
print('lines missing Russian text: %d' % len(nosub))
for r in nosub[:10]:
    print('   ', r['name'], round(r['dur'], 2), '| EN:', r['en'][:60])

with open(os.path.join(OUT, 'vo_lines.json'), 'w', encoding='utf-8') as fh:
    json.dump(rows, fh, ensure_ascii=False, indent=1)
with open(os.path.join(OUT, 'vo_lines.csv'), 'w', encoding='utf-8-sig', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print('wrote vo_lines.json / vo_lines.csv')
