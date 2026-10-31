"""Curiosity: Ciel researches what she is curious about by herself, and tells what she found."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

import board
import curiosity
from initiative import Initiative, Thought


def thought(**kw):
    return Thought(kw.pop('text', 'オリオン座の撮り方が気になる'), kw.pop('kind', 'research'), kw.pop('motivation', 4.0),
                   query=kw.pop('query', 'スマートフォンでオリオン座をきれいに撮る設定'), **kw)


def make(result=None, talk='normal'):
    researcher = SimpleNamespace(search=AsyncMock(return_value=result or {
        'status': 'completed', 'summary': '夜景モードで三脚を使う[1]', 'sources': [{'title': '星空撮影の入門'}]}),
        _lock=asyncio.Lock())
    say = Mock()
    c = curiosity.Curiosity(researcher, board.Board(), say, 'FOUND', style=SimpleNamespace(talk=talk))
    return c, researcher, say


class CuriosityTests(unittest.IsolatedAsyncioTestCase):
    async def test_researches_and_tells_what_she_found(self):
        c, researcher, say = make()
        t = thought()
        self.assertTrue(c.offer(t))
        await c._task
        researcher.search.assert_awaited_once_with('スマートフォンでオリオン座をきれいに撮る設定', f'self-{t.id}', None)
        self.assertEqual([(x.kind, x.status) for x in c.board.cards], [('research', board.DONE)])
        text = say.call_args.args[0]
        self.assertTrue(text.startswith('FOUND'))
        self.assertIn('夜景モードで三脚を使う', text)
        self.assertIn('星空撮影の入門', text)
        self.assertTrue(t.expressed)
        self.assertFalse(t.researching)

    async def test_what_she_learned_goes_to_the_thinker(self):
        c, _, _ = make()
        c.learned = Mock()
        self.assertTrue(c.offer(thought()))
        await c._task
        c.learned.assert_called_once_with('スマートフォンでオリオン座をきれいに撮る設定', '夜景モードで三脚を使う[1]')

    async def test_failure_is_not_told_and_not_retried(self):
        c, _, say = make({'status': 'failed'})
        t = thought()
        self.assertTrue(c.offer(t))
        await c._task
        say.assert_not_called()
        self.assertEqual(c.board.cards[0].status, board.FAILED)
        self.assertEqual(t.query, '')
        self.assertFalse(t.expressed)
        self.assertLess(t.motivation, 4.0)

    async def test_declines(self):
        c, _, _ = make(talk='quiet')
        self.assertFalse(c.offer(thought()))                    # meetings
        c, researcher, _ = make()
        self.assertFalse(c.offer(thought(motivation=3.0)))      # not curious enough
        self.assertFalse(c.offer(thought(query='')))            # nothing to search
        self.assertFalse(c.offer(thought(kind='question')))     # asking the user, not the web
        async with researcher._lock:                            # a requested search is running
            self.assertFalse(c.offer(thought()))

    async def test_one_research_per_topic(self):
        c, _, _ = make()
        self.assertTrue(c.offer(thought(topic='プラネタリウム')))
        await c._task
        self.assertFalse(c.offer(thought(text='投影機の会社が知りたい', topic='プラネタリウム')))
        self.assertTrue(c.offer(thought(text='流星群の見頃が気になる', topic='流星群')))
        await c._task

    async def test_hourly_cap(self):
        c, _, _ = make()
        now = [0.0]
        c._clock = lambda: now[0]
        for _ in range(curiosity.PER_HOUR):
            self.assertTrue(c.offer(thought()))
            await c._task
        self.assertFalse(c.offer(thought()))
        now[0] = 3600.0
        self.assertTrue(c.offer(thought()))
        await c._task

    async def test_initiative_hands_research_thoughts_over_instead_of_a_want_card(self):
        c, _, _ = make()
        i = Initiative(SimpleNamespace(), SimpleNamespace(talk='normal'), 'NUDGE', instructions='THINK')
        i.board, i.curious = c.board, c
        t = thought(created=100.0)
        ask = Thought('どんなカメラで撮ったのかな', 'question', 4.0, created=100.0)
        i.thoughts = [t, ask]
        i.sync_board(100.0)
        self.assertTrue(t.researching)
        self.assertEqual([(x.kind, x.title) for x in c.board.cards], [('thought', 'どんなカメラで撮ったのかな（相手に聞きたいこと）')])
        await c._task
        self.assertEqual(sorted((x.kind, x.status) for x in c.board.cards), [('research', board.DONE), ('thought', board.WANT)])


if __name__ == '__main__':
    unittest.main()
