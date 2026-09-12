"""Сборка патча русской озвучки из пары «оригинал + пропатченный архив».

Патч не содержит ни одного байта оригинальной игры: в него попадают только те
участки, которые отличаются, то есть MPEG-кадры синтезированной русской речи
внутри уже существующих 316-байтных слотов.

Смещения хранятся НЕ от начала файла, а от начала записи TAFS, к которой они
относятся, и запись ищется по её хешу. Если в другой сборке игры таблица TAFS
собрана иначе (другой набор DLC — другие смещения), патч всё равно встанет:
установщик заново находит запись по хешу и прибавляет дельту.

Формат (little-endian):

    "LC2RU1" | u32 версия=1 | u32 записей
    u32 sha_src[8] | u32 sha_dst[8]          — SHA-256 исходника и результата
    на запись: u32 хеш | u32 размер записи | u32 участков
        на участок: u32 дельта_от_начала_записи | u32 длина | байты

    python makepatch.py <оригинал.tiger> <пропатченный.tiger> <патч.lc2p>
"""
import sys, os, struct, hashlib

GAP = 64          # участки ближе этого склеиваем — дешевле, чем новый заголовок


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.digest()


def entries(d):
    """хеш -> (смещение записи, размер) из таблицы TAFS"""
    cnt = struct.unpack_from('<I', d, 0x0c)[0]
    out = []
    for i in range(cnt):
        h, loc, size, z1, z2, off = struct.unpack_from('<IIIIII', d, 0x34 + i * 24)
        out.append((h, off, size))
    return out


def runs(a, b, lo, hi):
    """список (смещение, длина) отличающихся участков в пределах [lo, hi)"""
    out = []
    i = lo
    cur = None
    while i < hi:
        if a[i] != b[i]:
            if cur is None:
                cur = [i, i + 1]
            elif i - cur[1] <= GAP:
                cur[1] = i + 1
            else:
                out.append(cur); cur = [i, i + 1]
        i += 1
    if cur:
        out.append(cur)
    return out


def main(src, dst, out):
    a = open(src, 'rb').read()
    b = open(dst, 'rb').read()
    if len(a) != len(b):
        raise SystemExit('размеры не совпадают: %d и %d — это не наш патч' % (len(a), len(b)))

    ents = entries(a)
    covered = 0
    recs = []
    for h, off, size in ents:
        rs = runs(a, b, off, min(off + size, len(a)))
        if not rs:
            continue
        payload = b''.join(struct.pack('<II', s - off, e - s) + b[s:e] for s, e in rs)
        recs.append(struct.pack('<III', h, size, len(rs)) + payload)
        covered += sum(e - s for s, e in rs)

    # ничего не должно меняться вне записей: таблица, выравнивание, хвост
    total = sum(1 for i in range(len(a)) if a[i] != b[i])
    inside = 0
    for h, off, size in ents:
        for s, e in runs(a, b, off, min(off + size, len(a))):
            inside += sum(1 for i in range(s, e) if a[i] != b[i])
    if inside != total:
        raise SystemExit('%d изменённых байт вне записей TAFS — патч небезопасен'
                         % (total - inside))

    head = b'LC2RU1' + struct.pack('<II', 1, len(recs)) + sha(src) + sha(dst)
    with open(out, 'wb') as f:
        f.write(head)
        for r in recs:
            f.write(r)
    print('записей в патче: %d' % len(recs))
    print('изменённых байт: %d (%.1f МБ), все внутри записей' % (total, total / 1048576))
    print('размер патча:    %d (%.1f МБ)' % (os.path.getsize(out), os.path.getsize(out) / 1048576))
    print('SHA-256 исходника:  %s' % sha(src).hex())
    print('SHA-256 результата: %s' % sha(dst).hex())


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
