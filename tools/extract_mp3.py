"""Extract every English VO line from the Tiger bigfile as a plain .mp3."""
import struct, os, re, json

GAME = os.path.join('D:', os.sep, 'Games', 'Lara Croft - Temple of Osiris', 'Game')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vo_en')
os.makedirs(OUT, exist_ok=True)
d = open(os.path.join(GAME, 'bigfile_ENGLISH.000.tiger'), 'rb').read()
cnt = struct.unpack_from('<I', d, 0x0c)[0]
n = 0
total = 0
manifest = []
for i in range(cnt):
    h, loc, size, z1, z2, off = struct.unpack_from('<IIIIII', d, 0x34 + i * 24)
    fsb = d.find(b'FSB4', off, off + size)
    if fsb < 0:
        continue
    ns, shdrsize, datasize, ver, flags = struct.unpack_from('<IIIII', d, fsb + 4)
    p = fsb + 48
    name = d[p + 2:p + 32].split(b'\x00')[0].decode('latin1').replace('.str_0', '')
    lsamples, lcomp, lstart, lend, mode, freq = struct.unpack_from('<IIIIII', d, p + 32)
    start = p + shdrsize
    mp3 = d[start:start + lcomp]
    if mp3[:2] not in (b'\xff\xfb', b'\xff\xfa', b'\xff\xf3', b'\xff\xf2'):
        print('!! not an mp3 frame:', name, mp3[:4].hex())
    with open(os.path.join(OUT, name + '.mp3'), 'wb') as fh:
        fh.write(mp3)
    manifest.append(dict(name=name, hash=h, entry_off=off, entry_size=size,
                         fsb_rel=fsb - off, mp3_rel=start - off, mp3_len=lcomp,
                         samples=lsamples, freq=freq, dur=round(lsamples / freq, 3)))
    n += 1
    total += lcomp
print('extracted %d mp3 files, %.1f MB' % (n, total / 1e6))
json.dump(manifest, open(os.path.join(OUT, '_manifest.json'), 'w'), indent=1)
# bitrate stats
brs = [8 * m['mp3_len'] / m['dur'] / 1000 for m in manifest if m['dur'] > 0.5]
print('bitrate: min %.0f avg %.0f max %.0f kbps' % (min(brs), sum(brs) / len(brs), max(brs)))
