"""Parallel synthesis of the whole VO set via fish.audio."""
import os, json, time, threading, queue, sys
import fish
from build import VOICES, BITRATE, MAX_SPEED, clean, frames_of, RU, HERE

WORKERS = int(os.environ.get('WORKERS', '6'))

lines = json.load(open(os.path.join(HERE, 'vo_lines.json'), encoding='utf-8'))
lines = [l for l in lines if l['ru'] and l['char'] in VOICES]
lines.sort(key=lambda l: l['name'].lower())
todo = [l for l in lines
        if not os.path.exists(os.path.join(RU, l['name'].replace('.str_0', '') + '.mp3'))]
print('total %d, remaining %d, workers %d' % (len(lines), len(todo), WORKERS), flush=True)

q = queue.Queue()
for l in todo:
    q.put(l)
lock = threading.Lock()
log = []
done = [0]
t0 = time.time()


def worker():
    while True:
        try:
            l = q.get_nowait()
        except queue.Empty:
            return
        name = l['name'].replace('.str_0', '')
        text = clean(l['ru'])
        slot = l['dur']
        speed, audio, dur = 1.0, None, None
        for attempt in range(3):
            try:
                audio = fish.tts(text, VOICES[l['char']], speed=speed,
                                 bitrate=BITRATE, temperature=0.5)
            except Exception as e:
                with lock:
                    print('  !! %s %s' % (name, str(e)[:70]), flush=True)
                time.sleep(2 + attempt * 3)
                audio = None
                continue
            dur = len(frames_of(audio)) * 1152 / 44100.0
            if dur <= slot or speed >= MAX_SPEED:
                break
            speed = min(MAX_SPEED, round(speed * dur / slot, 3))
        if audio:
            open(os.path.join(RU, name + '.mp3'), 'wb').write(audio)
            with lock:
                log.append(dict(name=name, char=l['char'], slot=round(slot, 2),
                                dur=round(dur, 2), speed=speed, text=text))
        with lock:
            done[0] += 1
            if done[0] % 25 == 0:
                el = time.time() - t0
                print('%4d/%d  %.1f/min  eta %.0f min'
                      % (done[0], len(todo), done[0] / el * 60,
                         (len(todo) - done[0]) / max(done[0] / el, 0.01) / 60), flush=True)
        q.task_done()


ths = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
[t.start() for t in ths]
[t.join() for t in ths]
json.dump(log, open(os.path.join(HERE, 'synth_log_par.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
over = [x for x in log if x['dur'] > x['slot'] + 0.05]
print('finished %d in %.1f min; over slot: %d' % (len(log), (time.time() - t0) / 60, len(over)),
      flush=True)
