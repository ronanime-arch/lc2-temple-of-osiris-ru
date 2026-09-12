"""Minimal fish.audio client: voice search + TTS."""
import urllib.request, urllib.parse, json, os, ssl

HERE = os.path.dirname(os.path.abspath(__file__))
_kf = os.path.join(HERE, '.fishkey')
KEY = (os.environ.get('FISH_API_KEY')
       or (open(_kf).read().strip() if os.path.exists(_kf) else ''))
if not KEY:
    raise SystemExit('нет ключа: задайте FISH_API_KEY или положите его в tools/.fishkey')
API = 'https://api.fish.audio'
MODEL = os.environ.get('FISH_MODEL', 's2.1-pro-free')


def _req(url, data=None, headers=None, method=None):
    h = {'Authorization': 'Bearer ' + KEY}
    h.update(headers or {})
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    return urllib.request.urlopen(r, timeout=180)


def search(**params):
    url = API + '/model?' + urllib.parse.urlencode(params, doseq=True)
    return json.load(_req(url))


def tts(text, reference_id, speed=1.0, fmt='mp3', bitrate=128, sample_rate=44100,
        temperature=0.5, top_p=0.7, model=None):
    body = dict(text=text, reference_id=reference_id, format=fmt,
                mp3_bitrate=bitrate, sample_rate=sample_rate, chunk_length=300,
                normalize=True, latency='normal', prosody=dict(speed=speed, volume=0),
                temperature=temperature, top_p=top_p)
    data = json.dumps(body).encode('utf-8')
    resp = _req(API + '/v1/tts', data=data,
                headers={'Content-Type': 'application/json',
                         'model': model or MODEL})
    return resp.read()


BR = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
SR = [44100, 48000, 32000]
MODES = {0: 'stereo', 1: 'joint', 2: 'dual', 3: 'mono'}


def mp3_info(b):
    """Parse the first MPEG frame header and count frames."""
    i = 0
    frames = 0
    first = None
    while i < len(b) - 4:
        if b[i] == 0xFF and (b[i + 1] & 0xE6) == 0xE2:
            bi = (b[i + 2] >> 4) & 0xF
            sf = (b[i + 2] >> 2) & 3
            pad = (b[i + 2] >> 1) & 1
            mode = (b[i + 3] >> 6) & 3
            if BR[bi] and sf != 3:
                flen = int(144 * BR[bi] * 1000 / SR[sf]) + pad
                if first is None:
                    first = dict(bitrate=BR[bi], rate=SR[sf], mode=MODES[mode])
                frames += 1
                i += flen
                continue
        i += 1
    if first:
        first['frames'] = frames
        first['dur'] = round(frames * 1152 / first['rate'], 3)
        first['bytes'] = len(b)
    return first


if __name__ == '__main__':
    import sys
    r = search(page_size=14, page_number=int(sys.argv[1]) if len(sys.argv) > 1 else 1,
               language='ru', sort_by='like_count')
    for m in r['items']:
        print('%-30s langs=%-14s likes=%-6s id=%s'
              % (m.get('title', '')[:30], ','.join(m.get('languages') or []),
                 m.get('like_count'), m.get('_id')))
