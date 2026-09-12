"""Build FSB4 banks with FMOD's own FSBank and drop them into the archive entries.

The whole FSB (header + sample header + data) is replaced, so the frame layout is
produced by FMOD itself. Entry size stays the same, so the TAFS table is untouched.
"""
import os, struct, subprocess, shutil, sys, wave, array, math
import pack96

HERE = pack96.HERE
GAME = pack96.GAME
ARC = os.path.join(GAME, 'bigfile_ENGLISH.000.tiger')
BAK = ARC + '.bak'
PS32 = r'C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe'
BUILD = os.path.join(HERE, 'buildfsb4.ps1')
STAGE = os.path.join(HERE, 'fsb4stage')
os.makedirs(STAGE, exist_ok=True)


def entries(d):
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
        out[name] = dict(entry=off, size=size, fsb=fsb, wrapper=fsb - off,
                         total=48 + shdr + ds, ls=ls, lc=lc, slots=lc // 316)
    return out


def make_wav(name):
    """trim the synthesized take and write a clean mono 44.1k wav for FSBank"""
    src = os.path.join(HERE, 'vo_wav', name + '.wav')
    if not os.path.exists(src):
        return None
    pcm, sr = pack96.read_wav(src)
    pcm = pack96.trim(pcm, sr)
    dst = os.path.join(STAGE, name + '.wav')
    pack96.write_wav(dst, pcm, sr)
    return dst, len(pcm) / float(sr)


def build_fsb(wav, out, quality=30):
    r = subprocess.run([PS32, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', BUILD,
                        '-Wav', wav, '-Out', out, '-Quality', str(quality)],
                       capture_output=True, text=True)
    return os.path.exists(out), (r.stdout or '') + (r.stderr or '')


def main(names, match_flags=True):
    if not os.path.exists(BAK):
        shutil.copy2(ARC, BAK)
    d = open(BAK, 'rb').read()
    ents = entries(d)
    buf = bytearray(d)
    done, skipped = [], []
    for name in names:
        e = ents.get(name)
        if not e:
            skipped.append((name, 'нет такой записи'))
            continue
        mw = make_wav(name)
        if not mw:
            skipped.append((name, 'нет синтеза'))
            continue
        wav, dur = mw
        out = os.path.join(STAGE, name + '.fsb')
        if os.path.exists(out):
            os.remove(out)
        ok, log = build_fsb(wav, out)
        if not ok:
            skipped.append((name, 'FSBank не собрал: ' + log.strip()[:60]))
            continue
        blob = bytearray(open(out, 'rb').read())
        if match_flags:
            struct.pack_into('<I', blob, 20, 0x40)      # как в файлах игры
        room = e['size'] - e['wrapper']
        if len(blob) > room:
            skipped.append((name, 'не влезает: %d > %d' % (len(blob), room)))
            continue
        buf[e['fsb']:e['entry'] + e['size']] = bytes(blob) + b'\x00' * (room - len(blob))
        ls, lc = struct.unpack_from('<II', blob, 48 + 32)
        done.append((name, dur, ls // 1152, e['slots'], len(blob), room))
    open(ARC, 'wb').write(bytes(buf))
    print('вшито реплик: %d, пропущено: %d' % (len(done), len(skipped)))
    for n, dur, nf, slots, sz, room in done:
        print('   %-26s %.2f с, кадров %d (было %d), %d/%d байт' % (n, dur, nf, slots, sz, room))
    for n, why in skipped:
        print('   пропуск %-22s %s' % (n, why))


if __name__ == '__main__':
    names = sys.argv[1:]
    if not names:
        d = open(BAK, 'rb').read()
        names = sorted([n for n in entries(d) if n.lower().startswith('200_ow_010_')],
                       key=lambda s: s.lower())[:10]
    main(names)
