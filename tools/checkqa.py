"""Сравнить то, что выдала FMOD из нашего банка, с прямым декодом того же MP3.
Расхождение означает, что раскладка по слотам испортила поток."""
import os, sys, array, math, mul, dub, struct

def wav_pcm(p):
    raw = open(p, 'rb').read()
    i = raw.find(b'data')
    n = struct.unpack_from('<I', raw, i + 4)[0]
    return array.array('h', raw[i + 8:i + 8 + n - (n % 2)])

def env(pcm, step=0.25):
    per = int(44100 * step); out = []
    for i in range(0, len(pcm), per):
        c = pcm[i:i + per]
        if not c: break
        out.append(math.sqrt(sum(float(x) * x for x in c) / len(c)))
    return out

def bar(v):
    ch = ' .:-=+*#%@'; mx = max(v) or 1
    return ''.join(ch[min(9, int(9 * x / mx))] for x in v)

for nm in sys.argv[1:]:
    fsb = os.path.join('oracle', '4_ru_%s.fsb' % nm)
    dec = os.path.join('oracle', '4_ru_%s.decoded.wav' % nm)
    if not os.path.exists(dec):
        print('нет декода FMOD для', nm); continue
    b = open(fsb, 'rb').read()
    shdr = struct.unpack_from('<I', b, 8)[0]
    padded = b[48 + shdr:]
    ref = dub.mp3_pcm(dub.unpad(padded))          # тот же поток, декодер ffmpeg
    got = wav_pcm(dec)                            # то, что выдала FMOD игры
    n = min(len(ref), len(got))
    if n == 0:
        print('%-28s пусто' % nm); continue
    # выравниваем по задержке декодера: ищем лучший сдвиг в пределах 2000 сэмплов
    best, bo = None, 0
    for off in range(0, 2001, 1 if n < 1 else 100):
        m = min(n, len(ref) - off)
        if m < 1000: break
        d = sum((ref[off + i] - got[i]) ** 2 for i in range(0, m, 37))
        if best is None or d < best: best, bo = d, off
    m = min(len(ref) - bo, len(got))
    diff = math.sqrt(sum((ref[bo + i] - got[i]) ** 2 for i in range(0, m, 7)) / (m // 7))
    r = math.sqrt(sum(float(got[i]) ** 2 for i in range(0, m, 7)) / (m // 7))
    print('%-28s FMOD=%d сэмплов, ffmpeg=%d, сдвиг=%d  расхождение RMS=%.1f (%.2f%% от сигнала %.0f)'
          % (nm, len(got), len(ref), bo, diff, 100 * diff / (r or 1), r))
    print('   FMOD   %s' % bar(env(got)[:90]))
    print('   ffmpeg %s' % bar(env(ref)[:90]))
