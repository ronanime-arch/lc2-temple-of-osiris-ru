"""Build FSB4 banks that are metadata-identical to the shipped ones.

Same sample name, same frame count, same lengthCompressed, same byte size -- only the
audio content differs. The bank itself is produced by FMOD's own FSBank.
"""
import os, struct, subprocess, shutil, sys, array
import pack96

HERE = pack96.HERE
GAME = pack96.GAME
ARC = os.path.join(GAME, 'bigfile_ENGLISH.000.tiger')
BAK = ARC + '.bak'
PS32 = r'C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe'
BUILD = os.path.join(HERE, 'buildfsb4.ps1')
STAGE = os.path.join(HERE, 'fsb4stage')
os.makedirs(STAGE, exist_ok=True)
FF = None
try:
    import verify
    FF = verify.FF
except Exception:
    pass


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
        raw = d[p + 2:p + 32]
        name = raw.split(b'\x00')[0].decode('latin1')
        ls, lc = struct.unpack_from('<II', d, p + 32)
        out[name.replace('.str_0', '')] = dict(
            entry=off, size=size, fsb=fsb, wrapper=fsb - off, rawname=raw,
            total=48 + shdr + ds, ls=ls, lc=lc, frames=ls // 1152, flags=fl,
            blob=bytes(d[fsb:fsb + 48 + shdr + ds]))
    return out


def speech(name, target_s):
    """trimmed take, tempo-fitted to target_s if needed, as a PCM array"""
    src = os.path.join(HERE, 'vo_wav', name + '.wav')
    pcm, sr = pack96.read_wav(src)
    pcm = pack96.trim(pcm, sr)
    dur = len(pcm) / float(sr)
    if dur > target_s and FF:
        tempo = min(1.6, dur / target_s * 1.01)
        a = os.path.join(STAGE, '_in.wav')
        b = os.path.join(STAGE, '_out.wav')
        pack96.write_wav(a, pcm, sr)
        subprocess.run([FF, '-y', '-v', 'error', '-i', a, '-af', 'atempo=%.4f' % tempo,
                        '-ac', '1', '-ar', '44100', b], capture_output=True)
        if os.path.exists(b):
            pcm, sr = pack96.read_wav(b)
    return pcm


def exact_wav(name, pcm, nsamples):
    out = array.array('h', pcm[:nsamples])
    if len(out) < nsamples:
        out.extend([0] * (nsamples - len(out)))
    path = os.path.join(STAGE, name + '.wav')
    pack96.write_wav(path, out, 44100)
    return path


def build(wav, out, quality=30):
    if os.path.exists(out):
        os.remove(out)
    subprocess.run([PS32, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', BUILD,
                    '-Wav', wav, '-Out', out, '-Quality', str(quality)],
                   capture_output=True, text=True)
    return os.path.exists(out)


def main(names):
    if not os.path.exists(BAK):
        shutil.copy2(ARC, BAK)
    d = open(BAK, 'rb').read()
    ents = entries(d)
    buf = bytearray(d)
    ok, bad = [], []
    for name in names:
        e = ents.get(name)
        if not e or not os.path.exists(os.path.join(HERE, 'vo_wav', name + '.wav')):
            bad.append((name, 'нет записи или синтеза'))
            continue
        target_frames = e['frames']
        pcm = speech(name, target_frames * 1152 / 44100.0)
        nsamples = target_frames * 1152
        blob = None
        for attempt in range(3):
            wav = exact_wav(name, pcm, nsamples)
            out = os.path.join(STAGE, name + '.fsb')
            if not build(wav, out):
                break
            b = bytearray(open(out, 'rb').read())
            got = struct.unpack_from('<I', b, 48 + 32)[0] // 1152
            if got == target_frames:
                blob = b
                break
            nsamples -= (got - target_frames) * 1152      # компенсируем задержку кодера
            if nsamples <= 0:
                break
        if blob is None:
            bad.append((name, 'не удалось попасть в %d кадров' % target_frames))
            continue
        # весь пролог (заголовок банка + заголовок сэмпла) берём из оригинала,
        # чтобы запись отличалась только звуковыми данными
        prologue = len(e['blob']) - e['lc']
        if len(blob) >= prologue:
            blob[:prologue] = e['blob'][:prologue]
        ls, lc = struct.unpack_from('<II', blob, 48 + 32)
        same = (ls == e['ls'] and lc == e['lc'] and len(blob) == len(e['blob']))
        room = e['size'] - e['wrapper']
        if len(blob) > room:
            bad.append((name, 'не влезает'))
            continue
        buf[e['fsb']:e['entry'] + e['size']] = bytes(blob) + b'\x00' * (room - len(blob))
        ok.append((name, ls // 1152, e['frames'], lc, e['lc'], len(blob), len(e['blob']), same))
    open(ARC, 'wb').write(bytes(buf))
    print('вшито: %d, не вышло: %d' % (len(ok), len(bad)))
    for n, f1, f2, lc1, lc2, s1, s2, same in ok:
        print('   %-26s кадров %d/%d  lc %d/%d  размер %d/%d  %s'
              % (n, f1, f2, lc1, lc2, s1, s2, 'идентично' if same else 'ОТЛИЧАЕТСЯ'))
    for n, why in bad:
        print('   пропуск %-22s %s' % (n, why))


if __name__ == '__main__':
    names = sys.argv[1:]
    if not names:
        d = open(BAK, 'rb').read()
        names = sorted([n for n in entries(d) if n.lower().startswith('200_ow_010_')],
                       key=lambda s: s.lower())[:10]
    main(names)
