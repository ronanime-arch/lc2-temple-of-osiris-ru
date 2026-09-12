"""Опыт: русские слова в начале слота, оригинальная дорожка — в оставшихся слотах.
Так сохраняется невербальная игра (смех, рёв, вздохи), которую субтитр не подписывает.
"""
import os, sys, mul, dub

d, ents = mul.entries(mul.BAK)
for nm in sys.argv[1:]:
    e = ents[nm]
    ch = mul.chunks(d, e)
    sl = [o for o in mul.slots(d, e, 0, ch) if mul.issync(d, o)]
    orig = [d[o:o + mul.SLOT] for o in sl]
    tgt = dub.loud_rms(dub.mp3_pcm(dub.unpad(b''.join(orig))))
    frames, info = dub.fit(nm, len(sl), tgt)
    pro = d[e['fsb']:e['data']]
    sil = dub.silent_frame()

    def build(keep_tail):
        out = bytearray()
        for k in range(len(sl)):
            if k < len(frames):
                fr = frames[k]
                out += fr + b'\x00' * (mul.SLOT - len(fr))
            elif keep_tail:
                out += orig[k]
            else:
                out += sil + b'\x00' * (mul.SLOT - len(sil))
        return bytes(pro) + bytes(out)

    open('oracle/A_EN_%s.fsb' % nm, 'wb').write(bytes(pro) + b''.join(orig))
    open('oracle/B_RU_%s.fsb' % nm, 'wb').write(build(False))
    open('oracle/C_MIX_%s.fsb' % nm, 'wb').write(build(True))
    print('%-26s слот=%.2f с, русских кадров=%d из %d (%.2f с речи)'
          % (nm, len(sl) * 1152 / 44100, len(frames), len(sl), len(frames) * 1152 / 44100))
