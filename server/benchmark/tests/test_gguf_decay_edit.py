import struct
import tempfile
import unittest
from pathlib import Path
from server.benchmark.gguf_decay_edit import shifted, verify_patches


class DecayEditTests(unittest.TestCase):
    def test_saved_shift_and_rejections(self):
        old = tuple(-4 + i/16 for i in range(32))
        for amount in (0.1, 0.25):
            saved = shifted(old, amount)
            self.assertEqual(saved, struct.unpack('<32f', struct.pack('<32f', *saved)))
            self.assertTrue(all(abs(v-u-amount) < 1e-5 for u,v in zip(old,saved)))
        for values, amount in [(old, -0.1), (old, 1), ([float('nan')]*32, .1), (old[:3], .1)]:
            with self.assertRaises(ValueError):
                shifted(values, amount)

    def test_verifies_unchanged_bytes_and_patch_contents(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d)/'base', Path(d)/'candidate'
            a.write_bytes(b'0123456789')
            b.write_bytes(b'012AB56789')
            patches = [(3, b'34', b'AB')]
            self.assertEqual(verify_patches(a,b,patches)['changed_bytes'], 2)
            for invalid in (b'X12AB56789', b'012AC56789', b'012AB56789X', b'012AB5678'):
                b.write_bytes(invalid)
                with self.assertRaises(ValueError):
                    verify_patches(a,b,patches)
            b.write_bytes(b'012AB56789')
            with self.assertRaises(ValueError):
                verify_patches(a,b,[(3,b'xx',b'AB')])
            with self.assertRaises(ValueError):
                verify_patches(a,b,patches+patches)
