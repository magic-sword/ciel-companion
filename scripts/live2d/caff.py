"""CAFF（Cubism Editor の .cmo3 / .can3 のコンテナ）の読み書き。

形式は、オープンソースの Rust 実装 https://github.com/vtubing/caff-archive（MIT）の仕様を参照した。
CAFF 自体はLive2Dの非公開形式なので、書き込んだファイルが Cubism Editor で開けるかは、必ず実機で確かめる。
元のファイルは Git の履歴から復元できるようにしてから書き換えること。

構造（数値はビッグエンディアン）
  ヘッダ  'CAFF'(4) + archive_version(3) + format_id(4) + format_version(3) + key(u32)
          + 36バイト（pad・プレビュー画像の情報・pad）         ＝ 54 バイト（実ファイルで確認）
  本体    entry_count(u32 ^ key) → メタデータ × entry_count → 各ファイルのバイト列 → 残り(trailing)
  メタデータ  file_name・tag（1バイトの長さ ^ key8 ＋ 文字 ^ key8）、pad(4)、pad(4)、
              file_size(u32 ^ key)、is_obfuscated(u8 ^ key8)、compression(u8 ^ key8)、pad(8)
  ファイル本体  is_obfuscated が真なら、1バイトずつ ^ key8
"""
import struct


class Entry:
    def __init__(self, name, tag, pad1, pad2, obfuscated, compression, pad3, data):
        self.name = name
        self.tag = tag
        self.pad1, self.pad2, self.pad3 = pad1, pad2, pad3
        self.obfuscated = obfuscated
        self.compression = compression
        self.data = data  # 難読化を解いた、圧縮されたままのバイト列


class Caff:
    def __init__(self, header_prefix, key, header_rest, entries, trailing):
        self.header_prefix = header_prefix   # 'CAFF'..format_version (14 bytes)
        self.key = key
        self.header_rest = header_rest       # 36 bytes
        self.entries = entries
        self.trailing = trailing


def _xor_bytes(b, k8):
    return bytes(x ^ k8 for x in b)


def read(path):
    raw = open(path, 'rb').read()
    if raw[:4] != b'CAFF':
        raise ValueError('not a CAFF file')
    pos = 0
    header_prefix = raw[0:14]  # 実ファイルでは鍵の後ろ36バイトを、そのまま保持する
    key = struct.unpack('>I', raw[14:18])[0]
    header_rest = raw[18:54]
    pos = 54
    k8 = key & 0xFF

    def u32():
        nonlocal pos
        v = struct.unpack('>I', raw[pos:pos + 4])[0] ^ key
        pos += 4
        return v

    def u8():
        nonlocal pos
        v = raw[pos] ^ k8
        pos += 1
        return v

    def string():
        nonlocal pos
        n = u8()
        if n & 0x80:
            raise ValueError('varint not supported')
        s = _xor_bytes(raw[pos:pos + n], k8)
        pos += n
        return s.decode('utf-8')

    count = u32()
    metas = []
    for _ in range(count):
        name = string()
        tag = string()
        pad1 = raw[pos:pos + 4]; pos += 4
        pad2 = raw[pos:pos + 4]; pos += 4
        size = u32()
        obf = bool(u8())
        comp = u8()
        pad3 = raw[pos:pos + 8]; pos += 8
        metas.append((name, tag, pad1, pad2, size, obf, comp, pad3))
    entries = []
    for name, tag, pad1, pad2, size, obf, comp, pad3 in metas:
        chunk = raw[pos:pos + size]
        pos += size
        data = _xor_bytes(chunk, k8) if obf else chunk
        entries.append(Entry(name, tag, pad1, pad2, obf, comp, pad3, data))
    trailing = raw[pos:]
    return Caff(header_prefix, key, header_rest, entries, trailing)


def write(caff, path):
    key = caff.key
    k8 = key & 0xFF
    out = bytearray()
    out += caff.header_prefix
    out += struct.pack('>I', key)
    out += caff.header_rest
    out += struct.pack('>I', len(caff.entries) ^ key)

    def string(s):
        b = s.encode('utf-8')
        if len(b) >= 0x80:
            raise ValueError('string too long')
        out.append(len(b) ^ k8)
        out.extend(_xor_bytes(b, k8))

    for e in caff.entries:
        string(e.name)
        string(e.tag)
        out += e.pad1
        out += e.pad2
        out += struct.pack('>I', len(e.data) ^ key)
        out.append((1 if e.obfuscated else 0) ^ k8)
        out.append(e.compression ^ k8)
        out += e.pad3
    for e in caff.entries:
        out += _xor_bytes(e.data, k8) if e.obfuscated else e.data
    out += caff.trailing
    open(path, 'wb').write(bytes(out))
