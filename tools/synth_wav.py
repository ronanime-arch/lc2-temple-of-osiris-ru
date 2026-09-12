"""Re-synthesize the whole VO set as WAV (no lossy intermediate)."""
import os, json, time, threading, queue
import fish
from build import VOICES, clean, HERE

OUT = os.path.join(HERE, 'vo_wav')
os.makedirs(OUT, exist_ok=True)
WORKERS = int(os.environ.get('WORKERS', '6'))

lines = json.load(open(os.path.join(HERE, 'vo_lines.json'), encoding='utf-8'))
lines = [l for l in lines if l['ru'] and l['char'] in VOICES]
todo = [l for l in lines
        if not os.path.exists(os.path.join(OUT, l['name'].replace('.str_0', '') + '.wav'))]
print('total %d, remaining %d' % (len(lines), len(todo)), flush=True)

q = queue.Queue()
for l in todo:
    q.put(l)
lock = threading.Lock()
done = [0]
t0 = time.time()


def worker():
    while True:
        try:
            l = q.get_nowait()
        except queue.Empty:
            return
        name = l['name'].replace('.str_0', '')
        for attempt in range(3):
            try:
                audio = fish.tts(clean(l['ru']), VOICES[l['char']], speed=1.0,
                                 fmt='wav', sample_rate=44100, temperature=0.5)
                open(os.path.join(OUT, name + '.wav'), 'wb').write(audio)
                break
            except Exception as e:
                with lock:
                    print('  !! %s %s' % (name, str(e)[:60]), flush=True)
                time.sleep(2 + attempt * 3)
        with lock:
            done[0] += 1
            if done[0] % 50 == 0:
                el = time.time() - t0
                print('%4d/%d  eta %.0f min'
                      % (done[0], len(todo), (len(todo) - done[0]) / max(done[0] / el, .01) / 60),
                      flush=True)


ths = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
[t.start() for t in ths]
[t.join() for t in ths]
print('done in %.1f min' % ((time.time() - t0) / 60), flush=True)
