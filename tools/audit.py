"""Проверка модели потока на всех записях архива."""
import os, json, mul

d, ents = mul.entries()
print('записей с FSB4: %d' % len(ents))
bad, rep, multi = [], {}, []
for nm, e in sorted(ents.items()):
    try:
        sl = mul.slots(d, e)
        ns = mul.nstreams(d, e)
    except Exception as ex:
        bad.append((nm, 'разбор: %s' % ex)); continue
    if ns > 1:
        multi.append(nm)
    buf = b''.join(d[o:o + mul.SLOT] for o in sl)
    good = sum(1 for k in range(0, len(buf), mul.SLOT) if mul.issync(buf, k))
    res = max([mul.mdb(buf[k:k + 8]) for k in range(0, len(buf), mul.SLOT)
               if mul.issync(buf, k)] or [-1])
    long = max([mul.framelen(buf[k:k + 4]) for k in range(0, len(buf), mul.SLOT)
                if mul.issync(buf, k)] or [0])
    ok = (good == e['frames'] and res == 0 and e['lc'] == e['frames'] * mul.SLOT
          and long <= mul.SLOT)
    if not ok:
        bad.append((nm, 'кадров %d/%d mdb=%d lc=%d/%d maxlen=%d'
                    % (good, e['frames'], res, e['lc'], e['frames'] * mul.SLOT, long)))
    rep[nm] = dict(frames=e['frames'], dur=round(e['frames'] * 1152 / 44100.0, 3),
                   streams=ns, slots=len(sl), entry=e['entry'], size=e['size'])
print('записей с двумя потоками: %d  %s' % (len(multi), ', '.join(multi)))
print('расхождений: %d' % len(bad))
for nm, why in bad[:15]:
    print('   %-28s %s' % (nm, why))
json.dump(rep, open('budget.json', 'w'), indent=0)
print('суммарно слотов: %.1f мин' % (sum(v['dur'] for v in rep.values()) / 60))
