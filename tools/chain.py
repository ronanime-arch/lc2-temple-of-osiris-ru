"""Recover the exact frame offsets of the shipped audio with a constrained walk.

The shipped stream and our re-encode are both 96 kbps CBR / 44.1 kHz / mono, so the
frame-length sequence (313/314) is deterministic and identical. That lets us validate
candidate headers hard enough to reject the garbage syncs sitting in the padding.
"""
import os, struct, collections, sys

GAME = os.path.join('D:', os.sep, 'Games', 'Lara Croft - Temple of Osiris', 'Game')
BAK = os.path.join(GAME, 'bigfile_ENGLISH.000.tiger.bak')
MAXGAP = 64


def is_hdr(d, i):
    """valid MPEG1 layer III, 96 kbps, 44.1 kHz, mono -> frame length"""
    if i + 4 > len(d) or d[i] != 0xFF or (d[i + 1] & 0xE6) != 0xE2:
        return 0
    if (d[i + 2] >> 4) & 0xF != 7:          # 96 kbps
        return 0
    if (d[i + 2] >> 2) & 3 != 0:            # 44.1 kHz
        return 0
    if (d[i + 3] >> 6) & 3 != 3:            # mono
        return 0
    return 314 if (d[i + 2] >> 1) & 1 else 313


def walk(d, start, lc, nframes):
    """Follow the frame chain, requiring each candidate to be corroborated by the next."""
    offs = []
    i = start
    end = start + lc
    while len(offs) < nframes:
        ln = is_hdr(d, i)
        if not ln:
            break
        offs.append((i - start, ln))
        nxt = None
        for g in range(0, MAXGAP + 1):
            q = i + ln + g
            if q + 4 > end:
                break
            l2 = is_hdr(d, q)
            if not l2:
                continue
            # corroborate: the frame after q must also start with a header nearby,
            # unless q is the final frame of the slot
            good = (len(offs) + 1 >= nframes)
            if not good:
                for g2 in range(0, MAXGAP + 1):
                    if is_hdr(d, q + l2 + g2):
                        good = True
                        break
            if good:
                nxt = q
                break
        if nxt is None:
            break
        i = nxt
    return offs


def entries():
    d = open(BAK, 'rb').read()
    cnt = struct.unpack_from('<I', d, 0x0c)[0]
    out = []
    for k in range(cnt):
        h, loc, size, z1, z2, off = struct.unpack_from('<IIIIII', d, 0x34 + k * 24)
        fsb = d.find(b'FSB4', off, off + size)
        if fsb < 0:
            continue
        ns, shdr, ds, ver, fl = struct.unpack_from('<IIIII', d, fsb + 4)
        p = fsb + 48
        name = d[p + 2:p + 32].split(b'\x00')[0].decode('latin1').replace('.str_0', '')
        ls, lc = struct.unpack_from('<II', d, p + 32)
        out.append(dict(name=name, data=p + shdr, lc=lc, nframes=ls // 1152))
    return d, out


if __name__ == '__main__':
    d, ents = entries()
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    full = short = 0
    dist = collections.Counter()
    samples = []
    for e in ents[:limit]:
        offs = walk(d, e['data'], e['lc'], e['nframes'])
        pct = 100.0 * len(offs) / e['nframes']
        dist[round(pct / 10) * 10] += 1
        if len(offs) == e['nframes']:
            full += 1
        else:
            short += 1
            if len(samples) < 5:
                samples.append((e['name'], len(offs), e['nframes']))
    print('entries probed: %d | complete chains: %d | short: %d' % (limit, full, short))
    print('coverage histogram (%% of frames found):', sorted(dist.items()))
    for s in samples:
        print('   short: %-28s %d/%d' % s)
    # detail on the first entry
    e = ents[0]
    offs = walk(d, e['data'], e['lc'], e['nframes'])
    if offs:
        gaps = [offs[i + 1][0] - (offs[i][0] + offs[i][1]) for i in range(len(offs) - 1)]
        print('%s: %d/%d frames, last ends at %d of %d'
              % (e['name'], len(offs), e['nframes'], offs[-1][0] + offs[-1][1], e['lc']))
        print('   gaps:', collections.Counter(gaps).most_common(6))
