"""Сколько кусков речи в каждом английском файле и что даст раскладка «в каждый кусок»."""
import json, threading, queue, statistics, mul, dub

d, ents = mul.entries(mul.BAK)
rep = {r['name']: r for r in json.load(open('apply_report.json', encoding='utf-8'))}
q = queue.Queue()
for nm in rep:
    q.put(nm)
out, lock = {}, threading.Lock()


def worker():
    while True:
        try:
            nm = q.get_nowait()
        except queue.Empty:
            return
        e = ents[nm]
        sl = [o for o in mul.slots(d, e) if mul.issync(d, o)]
        en = dub.mp3_pcm(dub.unpad(b''.join(d[o:o + mul.SLOT] for o in sl)))
        wins = dub.windows(en, len(sl))
        with lock:
            out[nm] = [(a, b) for a, b in wins]


ths = [threading.Thread(target=worker) for _ in range(10)]
[t.start() for t in ths]
[t.join() for t in ths]
json.dump(out, open('windows.json', 'w'), indent=0)

multi = {k: v for k, v in out.items() if len(v) > 1}
print('реплик всего: %d' % len(out))
print('с одним куском речи (уже озвучены целиком): %d' % (len(out) - len(multi)))
print('с двумя и более кусками: %d' % len(multi))
hist = {}
for v in out.values():
    hist[len(v)] = hist.get(len(v), 0) + 1
print('распределение по числу кусков: %s' % dict(sorted(hist.items())))
# сколько тишины вернём: слоты вторых и далее окон
gain = sum(sum(b - a for a, b in v[1:]) for v in multi.values()) * 1152 / 44100.0
now = sum(rep[k]['frames'] for k in out) * 1152 / 44100.0
tot = sum(len(mul.slots(d, ents[k])) for k in out) * 1152 / 44100.0
print('\nсейчас русской речи %.1f мин из %.1f мин слотов' % (now / 60, tot / 60))
print('раскладка «в каждый кусок» добавит до %.1f мин озвучки' % (gain / 60))
