"""Regression: changing an image's byte length must relocate following entries."""
import struct
import tempfile
import unittest
from pathlib import Path

import caff


class CaffOffsetsTest(unittest.TestCase):
    def test_signed_key_preserves_editor_high_offset_field(self):
        key = 0xB093BB77
        archive = caff.Caff(b'CAFF'+b'\0'*10,key,b'\0'*36,
                           [caff.Entry('main.xml','main_xml',b'\xff'*4,b'\0'*4,True,33,b'\0'*8,b'contents')],b'')
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'signed.cmo3';caff.write(archive,target)
            restored=caff.read(target)
            self.assertEqual(restored.entries[0].pad1,b'\xff'*4)
            self.assertEqual(restored.entries[0].data,b'contents')

    def test_replacing_image_updates_absolute_offsets(self):
        key = 0x395229FF
        entries = [caff.Entry('image.png', 'image', b'\0'*4, b'\0'*4, False, 16, b'\0'*8, b'old'),
                   caff.Entry('main.xml', 'main_xml', b'\0'*4, b'\0'*4, True, 33, b'\0'*8, b'contents')]
        archive = caff.Caff(b'CAFF'+b'\0'*10, key, b'\0'*36, entries, b'\0\0')
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)/'test.cmo3'
            for image in (b'old', b'a much longer replacement image'):
                entries[0].data = image
                caff.write(archive, target)
                raw = target.read_bytes()
                restored = caff.read(target)
                for expected, actual in zip(entries, restored.entries):
                    offset = ((struct.unpack('>I',actual.pad1)[0]^key)<<32) | (struct.unpack('>I',actual.pad2)[0]^key)
                    stored = raw[offset:offset+len(expected.data)]
                    if actual.obfuscated: stored=bytes(v^(key&255) for v in stored)
                    self.assertEqual(stored, expected.data)
                    self.assertEqual(actual.data, expected.data)


if __name__ == '__main__': unittest.main()
