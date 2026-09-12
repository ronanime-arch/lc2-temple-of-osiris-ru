"""Весь ли текст вынут: сколько реплик (тегов [bXcY]) в блоке субтитров каждой записи
на каждый язык. Если для русского больше одной — мы потеряли часть текста."""
import re, collections, mul

d, ents = mul.entries(mul.BAK)
per_lang_counts = collections.Counter()
multi = []
langs = collections.Counter()
for nm, e in sorted(ents.items()):
    w = d[e['entry']:e['fsb']]
    i = w.find(b'ENIC')
    blk = w[i:] if i >= 0 else w
    j = blk.find(b'\xcd\xcd\xcd\xcd')
    txt = (blk[:j] if j > 0 else blk).decode('utf-8', 'replace')
    # запись языка: «<цифра>\r[теги]ТЕКСТ»
    parts = re.findall(r'(\d+)\r(\[[^\]]*\][^\r\x00]*)', txt)
    by = collections.defaultdict(list)
    for lg, body in parts:
        by[lg].append(body)
    for lg, bodies in by.items():
        langs[lg] += 1
        per_lang_counts[(lg, len(bodies))] += 1
        if len(bodies) > 1:
            multi.append((nm, lg, bodies))
print('записей: %d' % len(ents))
print('языков встречено: %s' % dict(langs))
print('\nсколько реплик на язык в одной записи:')
for (lg, n), c in sorted(per_lang_counts.items()):
    print('   язык %-2s : %d реплик(и) -> %d записей' % (lg, n, c))
print('\nзаписей, где у какого-то языка больше одной реплики: %d' % len(multi))
for nm, lg, bodies in multi[:10]:
    print('   %-26s язык %s:' % (nm, lg))
    for b in bodies:
        print('      %r' % b[:120])
