"""Synthesize Russian VO with fish.audio and inject it into the game's Tiger archive.

Usage:
  python build.py synth <count|all> [prefix]   -- synthesize into vo_ru/
  python build.py inject                        -- patch bigfile_ENGLISH.000.tiger in place
"""
import struct, os, re, json, sys, time, shutil, collections
import fish

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join('D:', os.sep, 'Games', 'Lara Croft - Temple of Osiris', 'Game')
ARC = os.path.join(GAME, 'bigfile_ENGLISH.000.tiger')
BAK = ARC + '.bak'
RU = os.path.join(HERE, 'vo_ru')
os.makedirs(RU, exist_ok=True)

VOICES = {
    'lara':   '2a1036d645634680b3cc69aeeb60375b',   # Спокойный женский голос
    'isis':   '9dc10492c7d84ac0b8297cce1186f234',   # Нежный женский голос
    'carter': '6ada82e315e648b6a30a2e2210844cbf',   # Дерзкий Парень
    'set':    '7312c38557eb4fb384e3874e8e9cea67',   # Мужской Профессиональный213
    'horus':  'e43aaac9114549edbfbfa1e4b861ed49',   # Парень
    'osiris': 'ad345871bcbd4ab0af5f3af9940287d2',   # Игровой Рассказчик
}
BITRATE = 64          # keeps every line inside the original byte slot
MAX_SPEED = 1.25

TAG = re.compile(r'\[[^\]]*\]')
SPEAK = re.compile(r'^\s*[A-Za-zА-Яа-яЁё]+\s*:\s*')


def clean(t):
    return SPEAK.sub('', TAG.sub('', t)).strip()


def frames_of(b):
    """Return [(offset, length)] of MPEG frames, skipping any leading junk."""
    BR = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
    SR = [44100, 48000, 32000]
    out = []
    i = 0
    while i < len(b) - 4:
        if b[i] == 0xFF and (b[i + 1] & 0xE6) == 0xE2:
            bi = (b[i + 2] >> 4) & 0xF
            sf = (b[i + 2] >> 2) & 3
            pad = (b[i + 2] >> 1) & 1
            if BR[bi] and sf != 3:
                fl = int(144 * BR[bi] * 1000 / SR[sf]) + pad
                out.append((i, fl))
                i += fl
                continue
        i += 1
    return out


def pack_mpeg(b):
    """Re-emit the frames 4-byte aligned, the way the shipped FSB data is laid out."""
    out = bytearray()
    n = 0
    for off, ln in frames_of(b):
        out += b[off:off + ln]
        out += b'\x00' * ((-len(out)) & 3)
        n += 1
    return bytes(out), n


def entries():
    d = open(ARC, 'rb').read()
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
        out[name] = dict(entry=off, size=size, fsb=fsb, shdr=p, data=p + shdrsize,
                         budget=datasize, samples=ls, comp=lc, dur=ls / 44100.0)
    return d, out


def do_synth(limit, prefix):
    lines = json.load(open(os.path.join(HERE, 'vo_lines.json'), encoding='utf-8'))
    lines = [l for l in lines if l['ru'] and l['char'] in VOICES]
    if prefix:
        lines = [l for l in lines if l['name'].lower().startswith(prefix.lower())]
    lines.sort(key=lambda l: l['name'].lower())
    if limit != 'all':
        lines = lines[:int(limit)]
    log = []
    t0 = time.time()
    for k, l in enumerate(lines, 1):
        name = l['name'].replace('.str_0', '')
        dst = os.path.join(RU, name + '.mp3')
        if os.path.exists(dst):
            continue
        text = clean(l['ru'])
        slot = l['dur']
        speed, audio, dur = 1.0, None, None
        for attempt in range(3):
            try:
                audio = fish.tts(text, VOICES[l['char']], speed=speed,
                                 bitrate=BITRATE, temperature=0.5)
            except Exception as e:
                print('  !! %s %s' % (name, str(e)[:80]))
                time.sleep(3)
                continue
            fr = frames_of(audio)
            dur = len(fr) * 1152 / 44100.0
            if dur <= slot or speed >= MAX_SPEED:
                break
            speed = min(MAX_SPEED, round(speed * dur / slot, 3))
        if audio is None:
            continue
        open(dst, 'wb').write(audio)
        log.append(dict(name=name, char=l['char'], slot=round(slot, 2),
                        dur=round(dur, 2), speed=speed, bytes=len(audio),
                        over=round(dur - slot, 2), text=text))
        print('%4d/%d  %-30s slot=%5.2f new=%5.2f speed=%.2f %s'
              % (k, len(lines), name, slot, dur, speed,
                 'OVER' if dur > slot + 0.05 else ''))
    json.dump(log, open(os.path.join(HERE, 'synth_log.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('done in %.1f min, %d files' % ((time.time() - t0) / 60, len(log)))


def do_inject():
    if not os.path.exists(BAK):
        print('backing up ->', BAK)
        shutil.copy2(ARC, BAK)
    d, ents = entries()
    buf = bytearray(d)
    done = skipped = 0
    report = []
    for fn in sorted(os.listdir(RU)):
        if not fn.endswith('.mp3'):
            continue
        name = fn[:-4]
        path = os.path.join(RU, fn)
        if time.time() - os.path.getmtime(path) < 10:
            print('  .. skipping %s (still being written)' % name)
            continue
        e = ents.get(name) or ents.get(name + '.str_0')
        if not e:
            print('  ?? no entry for', name)
            continue
        raw = open(path, 'rb').read()
        stream, nframes = pack_mpeg(raw)
        if len(stream) > e['budget']:
            print('  !! %s too big: %d > %d' % (name, len(stream), e['budget']))
            skipped += 1
            continue
        samples = nframes * 1152
        buf[e['data']:e['data'] + e['budget']] = stream + b'\x00' * (e['budget'] - len(stream))
        struct.pack_into('<II', buf, e['shdr'] + 32, samples, len(stream))
        struct.pack_into('<I', buf, e['entry'] + 8, samples)
        done += 1
        report.append(dict(name=name, old=round(e['dur'], 2),
                           new=round(samples / 44100.0, 2), bytes=len(stream),
                           budget=e['budget']))
    open(ARC, 'wb').write(bytes(buf))
    print('injected %d lines, skipped %d -> %s' % (done, skipped, ARC))
    for r in report:
        print('   %-30s %5.2fs -> %5.2fs  (%d/%d B)'
              % (r['name'], r['old'], r['new'], r['bytes'], r['budget']))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'synth'
    if cmd == 'synth':
        do_synth(sys.argv[2] if len(sys.argv) > 2 else '5',
                 sys.argv[3] if len(sys.argv) > 3 else '')
    elif cmd == 'inject':
        do_inject()
