"""Перекрёстная проверка адресации: огибающая озвучки из слотов должна совпадать
со своим же синтезом лучше, чем с чужими. Ловит перепутанные записи."""
import os, sys, math, json, random, array
import mul, dub

d, ents = mul.entries(mul.ARC)
rep = {r['name']: r for r in json.load(open('apply_report.json', encoding='utf-8'))}
random.seed(7)
names = sys.argv[1:] or random.sample(sorted(rep), 12)


def envel(pcm, step=0.10):
    per = int(44100 * step); out = []
    for i in range(0, len(pcm) - per, per):
        out.append(math.sqrt(sum(float(x) * x for x in pcm[i:i + per]) / per))
    return out


def corr(a, b):
    n = min(len(a), len(b))
    if n < 5:
        return 0.0
    a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    va = math.sqrt(sum((x - ma) ** 2 for x in a)) or 1e-9
    vb = math.sqrt(sum((x - mb) ** 2 for x in b)) or 1e-9
    return sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (va * vb)


got, want = {}, {}
for nm in names:
    e = ents[nm]
    got[nm] = envel(dub.mp3_pcm(dub.unpad(mul.stream(d, e))))
    r = rep[nm]
    pcm = dub.trim(dub.read_pcm(os.path.join(dub.WAVD, nm + '.wav')))
    want[nm] = envel(dub.mp3_pcm(dub.encode(pcm, r['tempo'], r['gain'])))

print('  %-28s своя  лучшая чужая  вердикт' % 'реплика')
ok = 0
for nm in names:
    self_c = corr(got[nm], want[nm])
    others = sorted(((corr(got[nm], want[o]), o) for o in names if o != nm), reverse=True)
    best, who = others[0]
    good = self_c > 0.9 and self_c > best + 0.15
    ok += good
    print('  %-28s %.3f   %.3f (%s)  %s'
          % (nm, self_c, best, who[:22], 'да' if good else 'НЕТ'))
print('совпало: %d/%d' % (ok, len(names)))
