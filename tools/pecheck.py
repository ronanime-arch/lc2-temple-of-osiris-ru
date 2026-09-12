"""Static inspection of a PE file: headers, imports, suspicious strings. Nothing is executed."""
import struct, sys, re, os, datetime, hashlib

SUSPECT_DLL = ('wininet', 'winhttp', 'ws2_32', 'wsock32', 'urlmon', 'advapi32',
               'crypt32', 'shell32', 'netapi32', 'wtsapi32', 'psapi')
SUSPECT_API = (b'URLDownloadToFile', b'InternetOpen', b'WinExec', b'ShellExecute',
               b'CreateRemoteThread', b'WriteProcessMemory', b'VirtualAllocEx',
               b'RegSetValue', b'RegCreateKey', b'CreateService', b'WinHttpOpen',
               b'socket', b'connect', b'CryptEncrypt', b'SetWindowsHookEx')


def rva2off(rva, sections):
    for name, va, vsz, raw, rsz in sections:
        if va <= rva < va + max(vsz, rsz):
            return raw + (rva - va)
    return None


def analyse(path):
    d = open(path, 'rb').read()
    print('файл   :', os.path.basename(path), len(d), 'байт')
    print('sha256 :', hashlib.sha256(d).hexdigest())
    if d[:2] != b'MZ':
        print('не PE-файл')
        return
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    assert d[pe:pe + 4] == b'PE\0\0', 'битый PE-заголовок'
    machine, nsec, tstamp = struct.unpack_from('<HHI', d, pe + 4)
    optsz = struct.unpack_from('<H', d, pe + 20)[0]
    magic = struct.unpack_from('<H', d, pe + 24)[0]
    print('машина : %s, секций %d, собран %s UTC'
          % ({0x14c: 'x86', 0x8664: 'x64'}.get(machine, hex(machine)), nsec,
             datetime.datetime.utcfromtimestamp(tstamp).isoformat()))
    print('формат : %s' % {0x10b: 'PE32', 0x20b: 'PE32+'}.get(magic, hex(magic)))
    secoff = pe + 24 + optsz
    sections = []
    for i in range(nsec):
        o = secoff + i * 40
        nm = d[o:o + 8].rstrip(b'\0').decode('latin1')
        vsz, va, rsz, raw = struct.unpack_from('<IIII', d, o + 8)
        chars = struct.unpack_from('<I', d, o + 36)[0]
        sections.append((nm, va, vsz, raw, rsz))
        wx = ('W' if chars & 0x80000000 else '-') + ('X' if chars & 0x20000000 else '-')
        print('   секция %-8s raw=%-9d virt=%-9d %s' % (nm, rsz, vsz, wx))
    # import directory
    ddoff = pe + 24 + (96 if magic == 0x10b else 112)
    imp_rva, imp_sz = struct.unpack_from('<II', d, ddoff + 8)
    off = rva2off(imp_rva, sections)
    dlls = []
    if off:
        while True:
            ent = d[off:off + 20]
            if len(ent) < 20 or ent == b'\0' * 20:
                break
            name_rva = struct.unpack_from('<I', ent, 12)[0]
            no = rva2off(name_rva, sections)
            if no:
                nm = d[no:d.index(b'\0', no)].decode('latin1')
                dlls.append(nm)
            off += 20
    print('импорты: %d библиотек' % len(dlls))
    for nm in dlls:
        flag = '  <-- внимание' if nm.lower().split('.')[0] in SUSPECT_DLL else ''
        print('   %s%s' % (nm, flag))
    hits = sorted({m.group().decode('latin1')
                   for pat in SUSPECT_API for m in re.finditer(re.escape(pat), d)})
    print('подозрительные API в строках:', hits if hits else 'нет')
    urls = sorted({u.decode('latin1') for u in re.findall(rb'https?://[\x21-\x7e]{6,60}', d)})
    print('URL в файле:', urls[:10] if urls else 'нет')
    ips = sorted({u.decode('latin1') for u in
                  re.findall(rb'\b(?:\d{1,3}\.){3}\d{1,3}\b', d)})
    print('IP-адреса  :', ips[:10] if ips else 'нет')


for p in sys.argv[1:]:
    analyse(p)
    print('-' * 60)
