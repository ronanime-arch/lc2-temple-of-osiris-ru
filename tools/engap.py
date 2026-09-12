"""Сколько английская речь занимает от своего слота — чтобы отделить «слот с запасом»
от настоящего расхождения с русской озвучкой."""
import os, json, threading, queue, statistics
import mul, dub

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
        pcm = dub.mp3_pcm(dub.unpad(mul.stream(d, e)))
        tr = dub.trim(pcm)
        with lock:
            out[nm] = dict(slot=len(pcm) / 44100.0, en=len(tr) / 44100.0)
            if len(out) % 150 == 0:
                print('   %d/%d' % (len(out), len(rep)), flush=True)


ths = [threading.Thread(target=worker) for _ in range(10)]
[t.start() for t in ths]
[t.join() for t in ths]
json.dump(out, open('engap.json', 'w'), indent=0)

st = json.load(open('speechstats.json', encoding='utf-8'))
rows = []
for x in st:
    o = out[x['name']]
    ru = min(x['trimmed'] / (x['tempo'] or 1), x['budget'])
    rows.append((x['name'], o['slot'], o['en'], ru, x['cut']))
print('\nанглийская речь от слота: медиана %.2f' % statistics.median(r[2] / r[1] for r in rows))
print('русская речь от английской: медиана %.2f' % statistics.median(r[3] / (r[2] or 1) for r in rows))
short = [r for r in rows if r[3] < 0.75 * r[2]]
print('\nрусская короче английской речи более чем на 25 %%: %d реплик' % len(short))
for r in sorted(short, key=lambda t: t[3] / (t[2] or 1))[:14]:
    print('   %-28s слот=%5.2f  англ=%5.2f  рус=%5.2f  (%.0f %% от англ)'
          % (r[0], r[1], r[2], r[3], 100 * r[3] / (r[2] or 1)))
json.dump([{'name': r[0], 'slot': r[1], 'en': r[2], 'ru': r[3], 'cut': r[4]} for r in rows],
          open('gapstats.json', 'w'), indent=0)
