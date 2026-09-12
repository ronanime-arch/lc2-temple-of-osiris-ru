"""Recover the true frame chain in the shipped FSB data with dynamic programming."""
import os, struct, collections, sys
import verify

BR = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
MAXGAP = 96


def headers(d):
    """positions of plausible MPEG1-L3 / 44.1 kHz / mono frame headers"""
    out = {}
    for i in range(len(d) - 4):
        if d[i] != 0xFF or (d[i + 1] & 0xE6) != 0xE2:
            continue
        bi = (d[i + 2] >> 4) & 0xF
        sf = (d[i + 2] >> 2) & 3
        pad = (d[i + 2] >> 1) & 1
        if BR[bi] == 0 or sf != 0:
            continue
        if (d[i + 3] >> 6) & 3 != 3:          # mono only
            continue
        out[i] = (int(144 * BR[bi] * 1000 / 44100) + pad, BR[bi])
    return out


def chain(d, nframes):
    """longest frame chain starting at 0, gaps <= MAXGAP"""
    h = headers(d)
    pos = sorted(h)
    idx = {p: k for k, p in enumerate(pos)}
    best = {}
    order = sorted(pos, reverse=True)
    nxt = {}
    for p in order:
        ln = h[p][0]
        b = 1
        n = None
        lo = p + ln
        for q in pos[idx[p] + 1:]:
            if q < lo:
                continue
            if q > lo + MAXGAP:
                break
            if best.get(q, 0) + 1 > b:
                b = best[q] + 1
                n = q
        best[p] = b
        nxt[p] = n
    if 0 not in best:
        return None, h
    out = []
    p = 0
    while p is not None:
        out.append(p)
        p = nxt.get(p)
    return out, h


def report(name):
    orig = verify.slots(os.path.join(verify.GAME, 'bigfile_ENGLISH.000.tiger.bak'))
    d, ls, lc = orig[name]
    nf = ls // 1152
    ch, h = chain(d, nf)
    print('%s: expect %d frames in %d bytes (%.3f B/frame)' % (name, nf, lc, lc / nf))
    print('   candidate headers: %d | chain length: %d' % (len(h), len(ch) if ch else 0))
    if not ch:
        return
    gaps = []
    for a, b in zip(ch, ch[1:]):
        gaps.append(b - (a + h[a][0]))
    print('   gap histogram:', collections.Counter(gaps).most_common(8))
    print('   first 24 gaps:', gaps[:24])
    print('   bitrates:', collections.Counter(h[p][1] for p in ch).most_common(5))
    tail = lc - (ch[-1] + h[ch[-1]][0])
    print('   bytes after last frame: %d' % tail)
    tight = b''.join(d[p:p + h[p][0]] for p in ch)
    pcm, err = verify.decode(tight, 'chain_' + name)
    if pcm:
        print('   tight decode: %.2f s (slot %.2f s) peak %d %s'
              % (len(pcm) / 44100, ls / 44100, max(abs(x) for x in pcm), err[:60]))
        print('   ', verify.bar(verify.profile(pcm)[:60]))


for nm in (sys.argv[1:] or ['200_ow_010_010_lara', '150_cs_010_030_isis']):
    report(nm)
