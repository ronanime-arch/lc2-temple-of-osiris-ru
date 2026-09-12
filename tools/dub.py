"""Русская озвучка Temple of Osiris: синтез -> MP3 -> слоты внутри bigfile.

Ключевое ограничение формата: каждый MPEG-кадр в архиве лежит в своём 316-байтном
слоте и обязан быть самодостаточным (main_data_begin = 0). Обычный LAME пользуется
бит-резервуаром — переносит часть данных кадра в предыдущий, — и в слотах такой
поток рассыпается. Поэтому кодируем с -reservoir 0 и проверяем каждый кадр.

Заголовки чанков, cue-записи движка, таблица архива и размеры записей не меняются:
переписываются только байты кадров внутри уже существующих слотов.
"""
import os, struct, subprocess, math, array, json, shutil
import mul

HERE = os.path.dirname(os.path.abspath(__file__))
WAVD = os.path.join(HERE, 'vo_wav')
FF = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'WinGet', 'Packages',
                  'Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe',
                  'ffmpeg-9.0.1-full_build', 'bin', 'ffmpeg.exe')
MAX_TEMPO = float(os.environ.get('MAX_TEMPO', '4.0'))
PEAK_CEIL = 1.8                   # предел пик*усиление до лимитера
MIN_TEMPO = 0.85                  # сильнее растягивать речь нельзя — тянется
SR = 44100
SPF = 1152                       # сэмплов в кадре


def run(args, stdin=None):
    p = subprocess.run(args, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.stdout, p.stderr.decode('utf-8', 'replace')


def read_pcm(path):
    """моно s16 44,1 кГц; размер берём по файлу — в заголовках синтеза он битый"""
    with open(path, 'rb') as fh:
        raw = fh.read()
    return array.array('h', raw[44:len(raw) - (len(raw) - 44) % 2])


def unpad(padded):
    """Слотовый поток -> непрерывный MP3 (выкидываем нули в хвостах слотов)."""
    out = bytearray()
    for k in range(0, len(padded) - 3, mul.SLOT):
        if mul.issync(padded, k):
            out += padded[k:k + mul.framelen(padded[k:k + 4])]
    return bytes(out)


def mp3_pcm(data):
    out, err = run([FF, '-v', 'error', '-f', 'mp3', '-i', 'pipe:0',
                    '-f', 's16le', '-ac', '1', '-ar', str(SR), 'pipe:1'], data)
    return array.array('h', out[:len(out) - len(out) % 2])


def rms(pcm, lo=0, hi=None):
    seg = pcm[lo:hi if hi is not None else len(pcm)]
    if not seg:
        return 0.0
    return math.sqrt(sum(float(x) * x for x in seg) / len(seg))


def loud_rms(pcm, thresh=300):
    """RMS только по звучащим окнам — не размывается тишиной по краям"""
    win = SR // 20
    tot, n = 0.0, 0
    for i in range(0, len(pcm) - win, win):
        s = sum(float(x) * x for x in pcm[i:i + win]) / win
        if math.sqrt(s) > thresh:
            tot += s; n += 1
    return math.sqrt(tot / n) if n else rms(pcm)


def trim(pcm, frac=0.04, floor=200.0, pad_ms=15):
    """Снять тишину и придыхание по краям.

    Порог берём от собственного пика реплики: у коротких выкриков синтез оставляет
    полсекунды затухающего выдоха, и фиксированный порог его не ловит. На обычных
    репликах это срезает 0,06 с — дыхание, не слова.
    """
    pk = max(max(pcm), -min(pcm)) if len(pcm) else 0
    thresh = max(floor, frac * pk)
    win = SR // 100
    lo = hi = None
    for i in range(0, len(pcm) - win, win):
        if rms(pcm, i, i + win) > thresh:
            if lo is None:
                lo = i
            hi = i + win
    if lo is None:
        return pcm
    pad = SR * pad_ms // 1000
    return pcm[max(0, lo - pad):min(len(pcm), hi + pad)]


def bursts(pcm, thresh=400, gap_ms=250):
    """Куски речи [(начало, конец)] в сэмплах: где актёр звучит, а где пауза."""
    win = SR // 100
    on = [rms(pcm, i, i + win) > thresh for i in range(0, len(pcm) - win, win)]
    need = gap_ms // 10
    out, i = [], 0
    while i < len(on):
        if not on[i]:
            i += 1
            continue
        j = last = i
        while j < len(on):
            if on[j]:
                last = j; j += 1
            elif j - last < need:
                j += 1
            else:
                break
        out.append((i * win, (last + 1) * win))
        i = j
    return out


def atempo_chain(tempo):
    """atempo умеет 0.5-2.0 за раз; большее набираем цепочкой."""
    out, t = [], tempo
    while t > 2.0:
        out.append(2.0); t /= 2.0
    while t < 0.5:
        out.append(0.5); t /= 0.5
    out.append(t)
    return ','.join('atempo=%.5f' % x for x in out)


def desilence(pcm, keep_ms=90, min_gap_ms=180, thresh=250):
    """Укоротить паузы внутри фразы: синтез любит тянуть их на запятых.

    Речь не трогаем — режется только тишина длиннее min_gap_ms, и то не насухо.
    """
    win = SR // 100
    loud = [rms(pcm, i, i + win) > thresh for i in range(0, len(pcm) - win, win)]
    keep = max(1, keep_ms // 10)
    out = array.array('h')
    i, n = 0, len(loud)
    while i < n:
        if loud[i]:
            j = i
            while j < n and loud[j]:
                j += 1
            out.extend(pcm[i * win:j * win])
            i = j
        else:
            j = i
            while j < n and not loud[j]:
                j += 1
            gap = j - i
            take = gap if gap * 10 <= min_gap_ms else keep
            out.extend(pcm[i * win:(i + take) * win])
            i = j
    out.extend(pcm[n * win:])
    return out


def encode(pcm, tempo=1.0, gain=1.0):
    af = []
    if abs(tempo - 1.0) > 0.001:
        af.append(atempo_chain(tempo))
    if abs(gain - 1.0) > 0.001:
        af.append('volume=%.4f' % gain)
    af.append('alimiter=limit=0.97:level=disabled')
    args = [FF, '-v', 'error', '-f', 's16le', '-ar', str(SR), '-ac', '1', '-i', 'pipe:0',
            '-af', ','.join(af), '-c:a', 'libmp3lame', '-b:a', '96k',
            '-reservoir', '0', '-original', '0', '-write_xing', '0',
            '-id3v2_version', '0', '-f', 'mp3', 'pipe:1']
    out, err = run(args, pcm.tobytes())
    if not out:
        raise RuntimeError('ffmpeg: ' + err[:200])
    return out


def split(mp3):
    """Кадры потока. Проверяем главное: 96 кбит/с, моно, 44,1 кГц, без резервуара."""
    out, i = [], 0
    while i + 4 <= len(mp3):
        if not mul.issync(mp3, i):
            i += 1                                   # хвост Info/ID3 в начале
            continue
        b = mp3[i:i + 4]
        if (b[2] >> 4) & 0xF != 7 or (b[2] >> 2) & 3 != 0:
            raise ValueError('кадр не 96 кбит/с 44,1 кГц на %d' % i)
        ln = mul.framelen(b)
        fr = bytearray(mp3[i:i + ln])
        if len(fr) < ln:
            break                                    # обрезанный хвост
        if mul.mdb(fr) != 0:
            raise ValueError('кадр на %d пользуется бит-резервуаром' % i)
        fr[3] = 0xC0                                 # как в файлах игры
        out.append(bytes(fr))
        i += ln
    return out


_SIL = None


def silent_frame():
    """Кадр тишины, выданный тем же кодировщиком — заполнитель пустых слотов."""
    global _SIL
    if _SIL is None:
        z = array.array('h', [0] * (SR // 2))
        fr = split(encode(z))
        _SIL = fr[len(fr) // 2]
    return _SIL


def layout(frames, nslots):
    """Кадры по слотам; хвост слота — нули, лишние слоты — тишина."""
    buf = bytearray()
    sil = silent_frame()
    for k in range(nslots):
        fr = frames[k] if k < len(frames) else sil
        if len(fr) > mul.SLOT:
            raise ValueError('кадр длиннее слота: %d' % len(fr))
        buf += fr + b'\x00' * (mul.SLOT - len(fr))
    return bytes(buf)


def prepare(name, target_rms=None):
    """Синтез: обрезанный PCM и усиление под громкость оригинала."""
    pcm = desilence(trim(read_pcm(os.path.join(WAVD, name + '.wav'))))
    gain = 1.0
    if target_rms:
        cur = loud_rms(pcm)
        if cur > 1:
            gain = min(4.0, max(0.25, target_rms / cur))
        # RMS синтеза втрое ниже английской дорожки, и подгонка по RMS загоняет
        # пики глубоко в лимитер. Ограничиваем: не больше ~5 дБ срезки на пиках.
        pk = max(max(pcm), -min(pcm)) / 32768.0 if len(pcm) else 1.0
        if pk > 0.01:
            gain = min(gain, PEAK_CEIL / pk)
    return pcm, gain


def fit_into(pcm, gain, nslots, cache=None):
    """Кадры реплики, уложенные ровно в nslots слотов.

    Темп подбираем так, чтобы фраза заняла окно целиком: короткую слегка растягиваем,
    длинную ускоряем. Пределы жёсткие — за ними речь звучит неестественно.
    """
    dur = len(pcm) / float(SR)
    win = nslots * SPF / float(SR)
    tempo = min(MAX_TEMPO, max(MIN_TEMPO, dur / win if win > 0.01 else 1.0))
    info = dict(slots=nslots, raw=round(dur, 3), window=round(win, 3))
    frames = []
    for attempt in range(5):
        key = round(tempo, 4)
        if cache is not None and key in cache:
            frames = cache[key]
        else:
            frames = split(encode(pcm, tempo, gain))
            if cache is not None:
                cache[key] = frames
        if len(frames) <= nslots:
            info.update(tempo=key, frames=len(frames), cut=0)
            return frames, info
        need = tempo * len(frames) / float(nslots) * 1.004
        if need > MAX_TEMPO:
            tempo = MAX_TEMPO
            key = round(tempo, 4)
            frames = (cache or {}).get(key) or split(encode(pcm, tempo, gain))
            if cache is not None:
                cache[key] = frames
            break
        tempo = need
    info.update(tempo=round(tempo, 4), frames=len(frames),
                cut=max(0, len(frames) - nslots))
    return frames[:nslots], info


def windows(en_pcm, nslots, thresh=None):
    """Окна под реплику: от начала каждого куска речи оригинала до начала следующего.

    Английский файл часто содержит одну и ту же фразу несколько раз подряд; чтобы
    русская озвучка звучала как оригинал, её нужно положить в каждый кусок.
    """
    if thresh is None:
        thresh = max(250.0, 0.12 * loud_rms(en_pcm))
    bs = bursts(en_pcm, thresh=thresh, gap_ms=300)
    if not bs:
        return [(0, nslots)]
    out = []
    for i, (a, b) in enumerate(bs):
        stop = bs[i + 1][0] if i + 1 < len(bs) else nslots * SPF
        s0, s1 = a // SPF, min(nslots, stop // SPF)
        if s1 - s0 >= 1:
            out.append((s0, s1))
    return out or [(0, nslots)]


def fit(name, nslots, target_rms=None, max_tempo=MAX_TEMPO):
    """Синтез -> кадры, уложенные в отведённое число слотов.

    Темп только ускоряется: короткую фразу не растягиваем, остаток слота — тишина.
    """
    pcm, gain = prepare(name, target_rms)
    budget = nslots * SPF / float(SR)
    dur = len(pcm) / float(SR)
    tempo = 1.0
    info = dict(name=name, slots=nslots, raw=round(dur, 3), budget=round(budget, 3),
                gain=round(gain, 3))
    frames = []
    for attempt in range(5):
        frames = split(encode(pcm, tempo, gain))
        if len(frames) <= nslots:
            info.update(tempo=round(tempo, 4), frames=len(frames), cut=0)
            return frames, info
        need = tempo * len(frames) / float(nslots) * 1.004
        if need > max_tempo:
            tempo = max_tempo
            frames = split(encode(pcm, tempo, gain))
            break
        tempo = need
    info.update(tempo=round(tempo, 4), frames=len(frames),
                cut=max(0, len(frames) - nslots))
    return frames[:nslots], info
