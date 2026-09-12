"""Вшить русскую озвучку в bigfile_ENGLISH.000.tiger.

Меняются только байты MPEG-кадров внутри уже существующих 316-байтных слотов.
Заголовки чанков, cue-записи движка, заголовки банков, таблица TAFS и размеры
записей остаются байт в байт. Исходник всегда берётся из .bak.

    python apply.py 150_cs_010_          # всё, что начинается с префикса
    python apply.py --all                # все 977 синтезированных реплик
    python apply.py --restore            # вернуть оригинал
"""
import os, sys, shutil, struct, json, threading, queue, time, math
import mul, dub

REPORT = os.path.join(dub.HERE, 'apply_report.json')
WORKERS = int(os.environ.get('WORKERS', '8'))
COVER_MIN = float(os.environ.get('COVER_MIN', '0.40'))


def ensure_bak():
    if not os.path.exists(mul.BAK):
        shutil.copy2(mul.ARC, mul.BAK)
        print('создан резерв', mul.BAK)


def restore():
    ensure_bak()
    shutil.copy2(mul.BAK, mul.ARC)
    print('оригинал возвращён из резерва')


def plan(d, ents, names):
    """name -> список потоков, каждый — список смещений слотов с кадрами"""
    out = {}
    for nm in names:
        e = ents[nm]
        ch = mul.chunks(d, e)
        streams = []
        for si in range(mul.nstreams(d, e, ch)):
            sl = [o for o in mul.slots(d, e, si, ch) if mul.issync(d, o)]
            if sl:
                streams.append(sl)
        if streams:
            out[nm] = (e, streams)
    return out


def main(argv):
    if '--restore' in argv:
        restore(); return
    ensure_bak()
    d = open(mul.BAK, 'rb').read()
    _, ents = mul.entries(mul.BAK)
    have = {n for n in ents if os.path.exists(os.path.join(dub.WAVD, n + '.wav'))}
    if '--all' in argv:
        names = sorted(have)
    else:
        pre = [a.lower() for a in argv[1:] if not a.startswith('--')]
        names = sorted(n for n in have if any(n.lower().startswith(p) for p in pre))
    if not names:
        print('нечего вшивать'); return
    print('реплик к сборке: %d (поток за потоком, %d рабочих)' % (len(names), WORKERS), flush=True)

    tasks = plan(d, ents, names)
    buf = bytearray(d)
    lock = threading.Lock()
    q = queue.Queue()
    for nm in sorted(tasks):
        q.put(nm)
    res, errs, skipped_short = [], [], []
    t0 = time.time()

    def worker():
        while True:
            try:
                nm = q.get_nowait()
            except queue.Empty:
                return
            e, streams = tasks[nm]
            try:
                nslots = len(streams[0])
                orig = b''.join(d[o:o + mul.SLOT] for o in streams[0])
                tgt = dub.loud_rms(dub.mp3_pcm(dub.unpad(orig)))
                frames, info = dub.fit(nm, nslots, tgt)
                packed = dub.layout(frames, nslots)
                with lock:
                    for sl in streams:                      # стерео: то же в оба потока
                        for k, off in enumerate(sl):
                            if (k + 1) * mul.SLOT > len(packed):
                                break                       # поток длиннее нулевого
                            buf[off:off + mul.SLOT] = packed[k * mul.SLOT:(k + 1) * mul.SLOT]
                    info['streams'] = len(streams)
                    res.append(info)
                    n = len(res)
                    if n % 100 == 0:
                        print('   %d/%d  (%.1f мин)' % (n, len(tasks), (time.time() - t0) / 60), flush=True)
            except Exception as ex:
                with lock:
                    errs.append((nm, '%s: %s' % (type(ex).__name__, ex)))

    ths = [threading.Thread(target=worker) for _ in range(WORKERS)]
    [t.start() for t in ths]
    [t.join() for t in ths]

    open(mul.ARC, 'wb').write(bytes(buf))
    json.dump(res, open(REPORT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    sped = [r for r in res if r['tempo'] > 1.005]
    cut = [r for r in res if r['cut']]
    loud = [r for r in res if r['gain'] >= 3.99]
    print('вшито реплик: %d за %.1f мин; ошибок: %d' % (len(res), (time.time() - t0) / 60, len(errs)))
    print('   ускорено: %d (макс %.3f), обрезано: %d, на пределе усиления: %d'
          % (len(sped), max([r['tempo'] for r in res] or [1]), len(cut), len(loud)))
    for nm, why in errs[:10]:
        print('   ОШИБКА %-26s %s' % (nm, why))
    for r in sorted(cut, key=lambda r: -r['cut'])[:10]:
        print('   обрезано %-26s %d кадров (%.2f с) при бюджете %.2f с'
              % (r['name'], r['cut'], r['cut'] * 1152 / 44100.0, r['budget']))
    return res


if __name__ == '__main__':
    main(sys.argv)
