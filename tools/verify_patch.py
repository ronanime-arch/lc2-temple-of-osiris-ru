"""Убедиться, что изменились только байты внутри отведённых слотов, и что
патченный архив по-прежнему разбирается точно так же, как оригинал."""
import mul, os

a = open(mul.BAK, 'rb').read()
b = open(mul.ARC, 'rb').read()
print('размер: резерв=%d  патч=%d  %s' % (len(a), len(b), 'совпадает' if len(a) == len(b) else 'РАЗНЫЙ'))
_, ents = mul.entries(mul.BAK)

allowed = set()
touched = {}
for nm, e in ents.items():
    ch = mul.chunks(a, e)
    for si in range(mul.nstreams(a, e, ch)):
        for o in mul.slots(a, e, si, ch):
            if mul.issync(a, o):
                allowed.add((o, o + mul.SLOT))
                touched[(o, o + mul.SLOT)] = nm
ranges = sorted(allowed)
import bisect
starts = [r[0] for r in ranges]

diff = 0
outside = []
names = set()
i = 0
n = len(a)
while i < n:
    if a[i] != b[i]:
        diff += 1
        k = bisect.bisect_right(starts, i) - 1
        if k >= 0 and ranges[k][0] <= i < ranges[k][1]:
            names.add(touched[ranges[k]])
        else:
            outside.append(i)
            if len(outside) > 5:
                break
        i = (ranges[k][1] if k >= 0 else i + 1)
        continue
    i += 1
print('различающихся участков внутри слотов: реплик %d -> %s' % (len(names), ', '.join(sorted(names))))
print('байтов, изменённых ВНЕ слотов: %d %s' % (len(outside), outside[:5]))

# и полная проверка модели на патченном файле
_, ents2 = mul.entries(mul.ARC)
bad = []
for nm, e in ents2.items():
    ch = mul.chunks(b, e)
    for si in range(mul.nstreams(b, e, ch)):
        sl = mul.slots(b, e, si, ch)
        buf = b''.join(b[o:o + mul.SLOT] for o in sl)
        good = sum(1 for k in range(0, len(buf), mul.SLOT) if mul.issync(buf, k))
        res = max([mul.mdb(buf[k:k + 8]) for k in range(0, len(buf), mul.SLOT)
                   if mul.issync(buf, k)] or [-1])
        if good != e['frames'] or res != 0:
            bad.append((nm, si, good, e['frames'], res))
print('разбор патченного архива: расхождений %d %s' % (len(bad), bad[:5]))
