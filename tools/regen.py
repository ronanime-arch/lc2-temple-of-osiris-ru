"""Досинтез реплик, у которых в игре несколько карточек субтитров.

Раньше извлекалась только первая карточка, поэтому у 216 реплик озвучивалась
примерно треть текста. Здесь текст склеивается целиком (порядок карточек —
байтовый, он же порядок речи) и синтезируется заново.
"""
import os, re, json, shutil, threading, queue, time, subprocess, sys
import fish, build, mul, dub

HERE = dub.HERE
BACKUP = os.path.join(HERE, 'vo_wav_1card')
os.makedirs(BACKUP, exist_ok=True)
SPEAK = re.compile(r'^\s*[A-Za-zА-Яа-яЁё]+\s*:\s*')
TAG = re.compile(r'\[[^\]]*\]')
CPS = 12.7                      # измеренный темп синтеза, знаков в секунду
WORKERS = int(os.environ.get('WORKERS', '4'))


def clean(t):
    return SPEAK.sub('', TAG.sub('', t)).strip()


def to_wav(mp3, dst):
    r = subprocess.run([dub.FF, '-y', '-v', 'error', '-f', 'mp3', '-i', 'pipe:0',
                        '-ac', '1', '-ar', '44100', '-c:a', 'pcm_s16le', dst],
                       input=mp3, capture_output=True)
    return os.path.exists(dst) and os.path.getsize(dst) > 1000, r.stderr.decode('utf-8', 'replace')


def main(only=None):
    cards = json.load(open(os.path.join(HERE, 'cards.json'), encoding='utf-8'))
    lines = {l['name'].replace('.str_0', ''): l
             for l in json.load(open(os.path.join(HERE, 'vo_lines.json'), encoding='utf-8'))}
    _, ents = mul.entries(mul.BAK)
    todo = []
    for nm, v in sorted(cards.items()):
        cs = v.get('9', [])
        if len(cs) < 2:
            continue
        ch = (lines.get(nm, {}).get('char') or nm.rsplit('_', 1)[-1]).lower()
        if ch not in build.VOICES:
            continue
        full = ' '.join(clean(b) for t, b in cs)
        first = clean(cs[0][1])
        slot = ents[nm]['frames'] * 1152 / 44100.0
        speed = min(1.25, max(1.0, (len(full) / CPS) / slot))
        todo.append(dict(name=nm, char=ch, text=full, slot=round(slot, 2),
                         was=len(first), now=len(full), speed=round(speed, 3)))
    if only:
        todo = [t for t in todo if t['name'] in only]
    print('к досинтезу: %d реплик, знаков %d (было %d)'
          % (len(todo), sum(t['now'] for t in todo), sum(t['was'] for t in todo)), flush=True)

    q = queue.Queue()
    for t in todo:
        q.put(t)
    done, errs, lock = [], [], threading.Lock()
    t0 = time.time()

    def worker():
        while True:
            try:
                t = q.get_nowait()
            except queue.Empty:
                return
            dst = os.path.join(dub.WAVD, t['name'] + '.wav')
            bak = os.path.join(BACKUP, t['name'] + '.wav')
            if not os.path.exists(bak) and os.path.exists(dst):
                shutil.copy2(dst, bak)              # прежний односоставный вариант
            last, got = '', False
            for attempt in range(3):
                try:
                    mp3 = fish.tts(t['text'], build.VOICES[t['char']], speed=t['speed'],
                                   fmt='mp3', bitrate=128, sample_rate=44100)
                    inf = fish.mp3_info(mp3) or {}
                    ok, err = to_wav(mp3, dst)
                    if ok:
                        t['dur'] = inf.get('dur')
                        got = True
                        with lock:
                            done.append(t)
                            if len(done) % 25 == 0:
                                print('   %d/%d (%.1f мин)'
                                      % (len(done), len(todo), (time.time() - t0) / 60), flush=True)
                        break
                    last = err[:120]
                except Exception as ex:
                    last = '%s: %s' % (type(ex).__name__, ex)
                time.sleep(1.5 * (attempt + 1))
            if not got:
                with lock:
                    errs.append((t['name'], last))

    ths = [threading.Thread(target=worker) for _ in range(WORKERS)]
    [th.start() for th in ths]
    [th.join() for th in ths]
    json.dump(done, open(os.path.join(HERE, 'regen_report.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('синтезировано: %d за %.1f мин, ошибок: %d'
          % (len(done), (time.time() - t0) / 60, len(errs)))
    for nm, why in errs[:12]:
        print('   ОШИБКА %-26s %s' % (nm, why))
    long = [t for t in done if t.get('dur') and t['dur'] > t['slot']]
    print('длиннее слота (доберёт упаковщик): %d из %d' % (len(long), len(done)))


if __name__ == '__main__':
    main(set(sys.argv[1:]) or None)
