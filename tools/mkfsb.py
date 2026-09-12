"""Carve standalone .fsb files out of the archive, and build patched variants to test.

Each entry already contains a complete FSB4 (header + sample header + data), so a byte
slice is a valid bank the FMOD runtime can open on its own.
"""
import os, struct, sys
import pack96

OUT = os.path.join(pack96.HERE, 'oracle')
os.makedirs(OUT, exist_ok=True)
BAK = os.path.join(pack96.GAME, 'bigfile_ENGLISH.000.tiger.bak')


def banks():
    d = open(BAK, 'rb').read()
    cnt = struct.unpack_from('<I', d, 0x0c)[0]
    out = {}
    for i in range(cnt):
        h, loc, size, z1, z2, off = struct.unpack_from('<IIIIII', d, 0x34 + i * 24)
        fsb = d.find(b'FSB4', off, off + size)
        if fsb < 0:
            continue
        ns, shdr, ds, ver, fl = struct.unpack_from('<IIIII', d, fsb + 4)
        p = fsb + 48
        name = d[p + 2:p + 32].split(b'\x00')[0].decode('latin1').replace('.str_0', '')
        ls, lc = struct.unpack_from('<II', d, p + 32)
        out[name] = dict(blob=bytes(d[fsb:fsb + 48 + shdr + ds]), shdr=shdr, ds=ds,
                         ls=ls, lc=lc, slots=lc // 316, dataoff=48 + shdr)
    return out


def write(path, blob):
    open(path, 'wb').write(blob)
    return path


if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else '200_ow_010_010_lara'
    bk = banks()[name]
    print('%s: sampleHdr=%d dataSize=%d lengthCompressed=%d frames=%d'
          % (name, bk['shdr'], bk['ds'], bk['lc'], bk['slots']))

    # 1. the shipped bank, untouched -- proves the oracle works
    write(os.path.join(OUT, 'orig.fsb'), bk['blob'])

    # our russian frames for this line
    frs = pack96.frames(open(os.path.join(pack96.OUTD, name + '.mp3'), 'rb').read())
    print('наших кадров: %d (слотов в оригинале %d)' % (len(frs), bk['slots']))
    frs = frs[:bk['slots']]

    variants = {}
    # 2. fixed 316-byte slots  (what v3/probe did)
    v = bytearray()
    for f in frs:
        v += f + b'\x00' * (316 - len(f))
    while len(v) < bk['lc']:
        v += pack96.SILENT_SLOT
    variants['slots316'] = bytes(v[:bk['lc']])
    # 3. frames packed tight, zero tail
    v = bytearray(b''.join(frs))
    variants['tight'] = bytes(v[:bk['lc']]) + b'\x00' * max(0, bk['lc'] - len(v))
    # 4. tight + real LAME silence to fill
    sil = open(os.path.join(pack96.HERE, 'silence_frames.bin'), 'rb').read()
    v = bytearray(b''.join(frs))
    while len(v) < bk['lc']:
        v += sil
    variants['tight_silence'] = bytes(v[:bk['lc']])

    for tag, data in variants.items():
        blob = bytearray(bk['blob'])
        blob[bk['dataoff']:bk['dataoff'] + bk['lc']] = data
        write(os.path.join(OUT, tag + '.fsb'), bytes(blob))
        print('   собран %-14s %d байт' % (tag + '.fsb', len(blob)))
    print('готово ->', OUT)
