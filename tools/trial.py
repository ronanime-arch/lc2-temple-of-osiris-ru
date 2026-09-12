"""Собрать банк с русской озвучкой одной реплики и отдать оракулу — без правки игры."""
import os, sys, struct, json, mul, dub

d, ents = mul.entries()
names = sys.argv[1:] or ['200_ow_010_010_lara']
os.makedirs('oracle', exist_ok=True)
for i, nm in enumerate(names):
    e = ents[nm]
    ch = mul.chunks(d, e)
    sl = [o for o in mul.slots(d, e, 0, ch) if mul.issync(d, o)]
    orig = b''.join(d[o:o + mul.SLOT] for o in mul.slots(d, e, 0, ch))
    tgt = dub.loud_rms(dub.mp3_pcm(dub.unpad(orig)))
    frames, info = dub.fit(nm, len(sl), tgt)
    new = dub.layout(frames, len(sl))
    blob = bytearray(d[e['fsb']:e['data']]) + bytearray(orig)
    blob[e['data'] - e['fsb']:e['data'] - e['fsb'] + len(new)] = new
    out = os.path.join('oracle', '4_ru_%s.fsb' % nm)
    open(out, 'wb').write(bytes(blob))
    print('%-28s слотов=%d кадров=%d темп=%.3f усиление=%.2f  синтез %.2f с -> бюджет %.2f с  обрезано=%d'
          % (nm, len(sl), info['frames'], info['tempo'], info['gain'],
             info['raw'], info['budget'], info['cut']))
    print('   RMS оригинала=%.0f' % tgt)
