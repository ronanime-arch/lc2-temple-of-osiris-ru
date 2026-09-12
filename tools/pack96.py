"""WAV -> trimmed, tempo-fitted, 96 kbps CBR mono MP3 laid out the way the game stores it.

The shipped container puts every MPEG frame in a fixed 316-byte slot:
lengthcompressed / frame_count == 316.000 for all 983 entries. We reproduce that
exactly and leave every metadata field untouched.
"""
import os, sys, struct, wave, array, math, subprocess, json, threading, queue, time
import verify

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = verify.GAME
FF = verify.FF
WAVD = os.path.join(HERE, 'vo_wav')
OUTD = os.path.join(HERE, 'vo96')
TMPD = os.path.join(HERE, 'tmp96')
for p in (OUTD, TMPD):
    os.makedirs(p, exist_ok=True)

SLOT = 316
FRAME_NOPAD = 313
FRAME_PAD = 314
# 96 kbps / 44.1 kHz / mono frame with all-zero side info -> decodes to silence
SILENT = bytes([0xFF, 0xFB, 0x70, 0xC0]) + b'\x00' * (FRAME_NOPAD - 4)
SILENT_SLOT = SILENT + b'\x00' * (SLOT - FRAME_NOPAD)
MAX_TEMPO = 1.30


def read_wav(path):
    w = wave.open(path, 'rb')
    ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    pcm = array.array('h', w.readframes(n))
    w.close()
    if ch == 2:
        pcm = array.array('h', [(pcm[i] + pcm[i + 1]) // 2 for i in range(0, len(pcm) - 1, 2)])
    return pcm, sr


def trim(pcm, sr, thresh=250, pad_ms=25):
    win = max(1, sr // 100)
    lo, hi = None, None
    for i in range(0, len(pcm) - win, win):
        seg = pcm[i:i + win]
        rms = math.sqrt(sum(float(x) * x for x in seg) / len(seg))
        if rms > thresh:
            if lo is None:
                lo = i
            hi = i + win
    if lo is None:
        return pcm
    pad = sr * pad_ms // 1000
    return pcm[max(0, lo - pad):min(len(pcm), hi + pad)]


def write_wav(path, pcm, sr=44100):
    w = wave.open(path, 'wb')
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes(pcm.tobytes())
    w.close()


def encode(src_wav, dst_mp3, tempo):
    af = 'atempo=%.4f' % tempo if tempo > 1.001 else 'anull'
    r = subprocess.run([FF, '-y', '-v', 'error', '-i', src_wav, '-af', af,
                        '-ac', '1', '-ar', '44100', '-c:a', 'libmp3lame',
                        '-b:a', '96k', '-write_xing', '0', '-id3v2_version', '0',
                        dst_mp3], capture_output=True, text=True)
    return r.stderr.strip()


def frames(b):
    """Frames of a contiguous 96k/44.1/mono CBR stream."""
    out = []
    i = 0
    while i + 4 <= len(b):
        if b[i] != 0xFF or (b[i + 1] & 0xE6) != 0xE2:
            break
        pad = (b[i + 2] >> 1) & 1
        ln = FRAME_PAD if pad else FRAME_NOPAD
        fr = bytearray(b[i:i + ln])
        fr[3] = 0xC0          # match the shipped frames byte for byte
        out.append(bytes(fr))
        i += ln
    return out


def slotify(frs, nslots):
    out = bytearray()
    for f in frs[:nslots]:
        out += f + b'\x00' * (SLOT - len(f))
    while len(out) < nslots * SLOT:
        out += SILENT_SLOT
    return bytes(out)


def targets():
    """name -> (data offset in archive, lengthcompressed, slot count)"""
    d = open(os.path.join(GAME, 'bigfile_ENGLISH.000.tiger.bak'), 'rb').read()
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
        out[name] = dict(data=p + shdr, lc=lc, slots=lc // SLOT)
    return d, out


def build_one(name, tgt):
    src = os.path.join(WAVD, name + '.wav')
    if not os.path.exists(src):
        return None
    pcm, sr = read_wav(src)
    pcm = trim(pcm, sr)
    dur = len(pcm) / float(sr)
    slot_s = tgt['slots'] * 1152 / 44100.0
    tempo = 1.0
    if dur > slot_s:
        tempo = min(MAX_TEMPO, dur / slot_s * 1.01)
    tw = os.path.join(TMPD, name + '.wav')
    tm = os.path.join(OUTD, name + '.mp3')
    write_wav(tw, pcm, sr)
    err = encode(tw, tm, tempo)
    os.remove(tw)
    if not os.path.exists(tm):
        return dict(name=name, error=err[:80])
    frs = frames(open(tm, 'rb').read())
    return dict(name=name, slots=tgt['slots'], frames=len(frs), tempo=round(tempo, 3),
                raw_s=round(dur, 2), slot_s=round(slot_s, 2),
                fitted_s=round(min(len(frs), tgt['slots']) * 1152 / 44100.0, 2),
                cut=max(0, len(frs) - tgt['slots']))


def main():
    d, tgts = targets()
    names = [n for n in tgts if os.path.exists(os.path.join(WAVD, n + '.wav'))]
    print('lines with audio: %d / %d' % (len(names), len(tgts)), flush=True)
    q = queue.Queue()
    for n in names:
        q.put(n)
    res = []
    lock = threading.Lock()
    t0 = time.time()

    def worker():
        while True:
            try:
                n = q.get_nowait()
            except queue.Empty:
                return
            r = build_one(n, tgts[n])
            with lock:
                if r:
                    res.append(r)
                if len(res) % 100 == 0:
                    print('  %d/%d' % (len(res), len(names)), flush=True)

    ths = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    json.dump(res, open(os.path.join(HERE, 'pack96.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    bad = [r for r in res if r.get('error')]
    cut = [r for r in res if r.get('cut')]
    sped = [r for r in res if r.get('tempo', 1) > 1.001]
    print('encoded %d in %.1f min | errors %d | tempo-fitted %d | still truncated %d'
          % (len(res), (time.time() - t0) / 60, len(bad), len(sped), len(cut)), flush=True)
    for r in cut[:8]:
        print('   cut %-28s %d frames > %d slots' % (r['name'], r['frames'], r['slots']))


if __name__ == '__main__':
    main()
