"""Decode what is actually sitting in the archive slots and report on the audio."""
import struct, os, sys, subprocess, wave, math, array, json

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join('D:', os.sep, 'Games', 'Lara Croft - Temple of Osiris', 'Game')
FF = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'WinGet', 'Packages',
                  'Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe',
                  'ffmpeg-9.0.1-full_build', 'bin', 'ffmpeg.exe')
TMP = os.path.join(HERE, 'verify_tmp')
os.makedirs(TMP, exist_ok=True)


def slots(path):
    d = open(path, 'rb').read()
    cnt = struct.unpack_from('<I', d, 0x0c)[0]
    out = {}
    for i in range(cnt):
        h, loc, size, z1, z2, off = struct.unpack_from('<IIIIII', d, 0x34 + i * 24)
        fsb = d.find(b'FSB4', off, off + size)
        if fsb < 0:
            continue
        ns, shdrsize, datasize, ver, flags = struct.unpack_from('<IIIII', d, fsb + 4)
        p = fsb + 48
        name = d[p + 2:p + 32].split(b'\x00')[0].decode('latin1').replace('.str_0', '')
        ls, lc = struct.unpack_from('<II', d, p + 32)
        out[name] = (bytes(d[p + shdrsize:p + shdrsize + lc]), ls, lc)
    return out


def decode(mp3_bytes, tag):
    src = os.path.join(TMP, tag + '.mp3')
    dst = os.path.join(TMP, tag + '.wav')
    open(src, 'wb').write(mp3_bytes)
    r = subprocess.run([FF, '-y', '-v', 'error', '-i', src, '-ac', '1', '-ar', '44100', dst],
                       capture_output=True, text=True)
    err = r.stderr.strip()
    if not os.path.exists(dst):
        return None, err
    w = wave.open(dst, 'rb')
    n = w.getnframes()
    pcm = array.array('h', w.readframes(n))
    w.close()
    return pcm, err


def profile(pcm, step=0.25):
    """RMS per quarter-second, as a coarse loudness map."""
    per = int(44100 * step)
    out = []
    for i in range(0, len(pcm), per):
        chunk = pcm[i:i + per]
        if not chunk:
            break
        rms = math.sqrt(sum(float(x) * x for x in chunk) / len(chunk))
        out.append(rms)
    return out


def bar(vals):
    ch = ' .:-=+*#%@'
    mx = max(vals) or 1
    return ''.join(ch[min(9, int(9 * v / mx))] for v in vals)


names = sys.argv[1:] or ['200_ow_010_010_lara', '150_cs_010_030_isis']
cur = slots(os.path.join(GAME, 'bigfile_ENGLISH.000.tiger'))
orig = slots(os.path.join(GAME, 'bigfile_ENGLISH.000.tiger.bak'))
for nm in names:
    for label, src in (('SHIPPED ', orig), ('PATCHED ', cur)):
        if nm not in src:
            print(label, nm, 'not found')
            continue
        data, ls, lc = src[nm]
        pcm, err = decode(data, label.strip() + '_' + nm)
        slot_s = ls / 44100.0
        if pcm is None:
            print('%s %-26s DECODE FAILED: %s' % (label, nm, err[:120]))
            continue
        dur = len(pcm) / 44100.0
        p = profile(pcm)
        speech = sum(1 for v in p if v > 300) * 0.25
        print('%s %-26s slot=%5.2fs decoded=%5.2fs speech≈%4.2fs peak=%5d %s'
              % (label, nm, slot_s, dur, speech, max(abs(x) for x in pcm) if pcm else 0,
                 ('ERR:' + err[:60]) if err else ''))
        print('           %s' % bar(p[:100]))
