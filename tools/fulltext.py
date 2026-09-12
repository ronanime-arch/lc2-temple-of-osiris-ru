"""Полное извлечение субтитров: карточки лежат ПО ВСЕЙ записи, между звуковыми
чанками, с тегом вида [b1c3d3.4] — d — это тайминг показа. Раньше брался только
первый блок перед банком, поэтому у длинных реплик терялось продолжение.
"""
import struct, re, json, collections, mul

CARD = re.compile(r'(\d)\r(\[b[0-9a-zA-Z.]*\])([^\r\x00]{1,400})')
d = open(mul.BAK, 'rb').read()
cnt = struct.unpack_from('<I', d, 0x0c)[0]
_, ents = mul.entries(mul.BAK)
by_off = {e['entry']: nm for nm, e in ents.items()}

out = {}
for i in range(cnt):
    h, loc, size, z1, z2, off = struct.unpack_from('<IIIIII', d, 0x34 + i * 24)
    nm = by_off.get(off)
    if not nm:
        continue
    txt = d[off:off + size].decode('utf-8', 'replace')
    cards = collections.defaultdict(list)
    for lg, tag, body in CARD.findall(txt):
        cards[lg].append((tag, body))
    out[nm] = {lg: v for lg, v in cards.items()}

json.dump(out, open('cards.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
n = collections.Counter(len(v.get('9', [])) for v in out.values())
print('русских карточек на реплику: %s' % dict(sorted(n.items())))
multi = [k for k, v in out.items() if len(v.get('9', [])) > 1]
print('реплик с несколькими карточками: %d из %d' % (len(multi), len(out)))


def spoken(body):
    b = re.sub(r'^\s*[^:]{0,22}:', '', body)
    return re.sub(r'\s+', ' ', b).strip()


old = new = 0
for nm, v in out.items():
    cs = v.get('9', [])
    if cs:
        old += len(spoken(cs[0][1]))
        new += len(' '.join(spoken(b) for t, b in cs))
print('\nрусского текста: было извлечено %d знаков, на самом деле %d (+%.0f%%)'
      % (old, new, 100.0 * (new - old) / max(1, old)))
en_old = en_new = 0
for nm, v in out.items():
    cs = v.get('0', [])
    if cs:
        en_old += len(spoken(cs[0][1]))
        en_new += len(' '.join(spoken(b) for t, b in cs))
print('английского: первый блок %d знаков, все карточки %d' % (en_old, en_new))
