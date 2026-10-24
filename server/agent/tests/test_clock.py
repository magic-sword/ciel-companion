"""The 'now' line and the exact time given to the conversation model (clock.py)."""
from datetime import datetime, timezone
import json
import unittest

import clock
from jst import JST


class ClockTests(unittest.TestCase):
    def test_line_has_date_weekday_band_and_season_in_japan_time(self):
        self.assertEqual(clock.now_line(datetime(2026, 10, 25, 21, 5, tzinfo=JST)), '[今：2026年10月25日（日）・夜・秋（日本時間）]')
        # 15:30 UTC is 0:30 the next day in Japan
        self.assertEqual(clock.now_line(datetime(2026, 12, 31, 15, 30, tzinfo=timezone.utc)),
                         '[今：2027年1月1日（金）・深夜・冬（日本時間）]')

    def test_bands_and_seasons(self):
        bands = {h: clock.band(h) for h in (0, 4, 5, 9, 10, 11, 12, 15, 16, 18, 19, 22, 23)}
        self.assertEqual(bands, {0: '深夜', 4: '深夜', 5: '朝', 9: '朝', 10: '午前', 11: '午前', 12: '昼', 15: '昼',
                                 16: '夕方', 18: '夕方', 19: '夜', 22: '夜', 23: '深夜'})
        self.assertEqual([clock.SEASONS[m] for m in (2, 3, 6, 9, 12)], ['冬', '春', '夏', '秋', '冬'])

    def test_exact_time_to_the_minute(self):
        t = clock.exact(datetime(2026, 10, 25, 9, 7, tzinfo=JST))
        self.assertEqual((t['date'], t['time'], t['band']), ('2026年10月25日（日）', '9時07分', '朝'))
        json.dumps(t, ensure_ascii=False)


if __name__ == '__main__':
    unittest.main()
