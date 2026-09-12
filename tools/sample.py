"""Выборочная проверка: собрать банки прямо из патченного архива (как это делает движок)."""
import os, sys, mul
d, ents = mul.entries(mul.ARC)
for nm in sys.argv[1:]:
    e = ents[nm]
    ch = mul.chunks(d, e)
    blob = d[e['fsb']:e['data']] + mul.stream(d, e, 0, ch)
    open(os.path.join('oracle', '%s.fsb' % nm), 'wb').write(blob)
    print('%-28s потоков=%d кадров=%d слотов=%d'
          % (nm, mul.nstreams(d, e, ch), e['frames'], len(mul.slots(d, e, 0, ch))))
