"""Звуковой поток Lara Croft and the Temple of Osiris внутри bigfile.

Одна запись архива устроена так:

    [обёртка ~9 КБ: субтитры на 8 языках]
    [FSB4: 48 б заголовок банка + 80 б заголовок сэмпла]   имя вида NAME.str_0
    [чанкованный поток]

Чанк: 16 байт заголовка — u32 размер полезной части, u32 тип,
8 байт магии 0xCD — затем сама полезная часть; всё вместе выровнено на 16 байт.
Между чанками попадаются 32-байтные cue-записи движка (вероятно, липсинк).

Поле «тип» — это номер потока. Обычная реплика моно: все чанки нулевого потока.
Семь реплик стерео: чанки потоков 0 и 1 чередуются, а первый чанк потока 1 начинается
со своего же 128-байтного заголовка FSB4 (NAME.str_1), который надо пропустить.
Полезная часть звукового чанка — MPEG-кадры, каждый в своём 316-байтном слоте.

Кадры **самодостаточны** (main_data_begin = 0), поэтому их можно менять по одному,
не трогая ни заголовки чанков, ни cue-записи, ни размер записи. Проверено на всех
983 записях: число кадров всегда равно lengthSamples/1152 и lengthCompressed/316.
"""
import struct, os

SLOT = 316
MAGIC = b'\xcd' * 8
HDR = 16                      # u32 size, u32 type, 8 байт магии
GAME = os.path.join('D:', os.sep, 'Games', 'Lara Croft - Temple of Osiris', 'Game')
ARC = os.path.join(GAME, 'bigfile_ENGLISH.000.tiger')
BAK = ARC + '.bak'


def entries(path=None):
    """name -> смещения записи и первого банка внутри архива"""
    d = open(path or ARC, 'rb').read()
    cnt = struct.unpack_from('<I', d, 0x0c)[0]
    out = {}
    for i in range(cnt):
        h, loc, size, z1, z2, off = struct.unpack_from('<IIIIII', d, 0x34 + i * 24)
        fsb = d.find(b'FSB4', off, off + size)
        if fsb < 0:
            continue
        ns, shdr, ds, ver, fl = struct.unpack_from('<IIIII', d, fsb + 4)
        p = fsb + 48
        raw = d[p + 2:p + 32].split(b'\x00')[0].decode('latin1')
        ls, lc = struct.unpack_from('<II', d, p + 32)
        out[raw.replace('.str_0', '')] = dict(
            idx=i, hash=h, entry=off, size=size, fsb=fsb, shdr=shdr, ds=ds,
            flags=fl, ls=ls, lc=lc, data=p + shdr, rawname=raw,
            frames=ls // 1152)
    return d, out


def chunks(d, e):
    """[(смещение полезной части, длина, тип)] по порядку в потоке."""
    base, end = e['data'], e['entry'] + e['size']
    out = []
    reach, i = base, base
    while True:
        m = d.find(MAGIC, i, end)
        if m < 0:
            break
        i = m + 8
        h = m - 8                                  # начало 16-байтного заголовка
        if h < base:
            continue
        size, typ = struct.unpack_from('<II', d, h)
        if (typ not in (0, 1) or size <= 0 or size % 4 or size > (1 << 16)
                or m + 8 + size > end or h < reach):
            continue                               # магия попалась внутри кадра
        out.append((m + 8, size, typ))
        reach = m + 8 + size
    return out


def spans(d, e, si=0, ch=None):
    """Звуковые участки потока si: [(абс. смещение, длина)] по порядку."""
    ch = ch if ch is not None else chunks(d, e)
    base = e['data']
    out = []
    if si == 0 and ch:
        lead = (ch[0][0] - HDR) - base             # хвост ведущего чанка не размечен
        while lead % SLOT:
            lead -= 1
        if lead > 0:
            out.append((base, lead))
    for off, ln, typ in ch:
        if typ != si:
            continue
        if d[off:off + 4] == b'FSB4':              # заголовок своего банка в начале
            skip = 48 + struct.unpack_from('<I', d, off + 8)[0]
            off, ln = off + skip, ln - skip
        if ln > 0:
            out.append((off, ln))
    return out


def nstreams(d, e, ch=None):
    ch = ch if ch is not None else chunks(d, e)
    return 1 + max([t for _, _, t in ch] or [0])


def slots(d, e, si=0, ch=None):
    """Абсолютные смещения 316-байтных слотов потока si, по порядку."""
    out = []
    for off, ln in spans(d, e, si, ch):
        k = 0
        while k + SLOT <= ln:
            out.append(off + k)
            k += SLOT
    return out


def stream(d, e, si=0, ch=None):
    """Непрерывный MPEG-поток потока si."""
    return b''.join(d[o:o + SLOT] for o in slots(d, e, si, ch))


def mdb(fr):
    """main_data_begin кадра: 0 => кадр самодостаточен"""
    return (fr[4] << 1) | (fr[5] >> 7)


def framelen(fr):
    return 314 if (fr[2] >> 1) & 1 else 313


def issync(b, k=0):
    return b[k] == 0xFF and (b[k + 1] & 0xE6) == 0xE2
