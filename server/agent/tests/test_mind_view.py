import unittest

from mind_view import MindView
from recall import Idea


def idea(text='丸石で拠点を作ろう', score=4, weighted=4.1, turn=3):
    return Idea('suggest', '準備', text, ['役に立つ'], ['話がそれる'], score, weighted, turn, 0.0)


class MindViewTest(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.t = [0.0]
        self.view = MindView(self.sent.append, presence=lambda: 'solo', clock=lambda: self.t[0])

    def test_a_turn_goes_from_waiting_to_spoken(self):
        self.view.waiting(3, '夜になる前に何を準備したらいい？')
        self.view.waiting(3, '夜になる前に何を準備したらいい？')   # 待つ間の見直しは知らせない
        self.assertEqual(len(self.sent), 1)
        self.view.thinking(3, '夜になる前に何を準備したらいい？')
        self.view.thought(3, [idea(score=3, weighted=2.8), idea()], 6200.0)
        self.view.outcome(3, 'scheduled', threshold=3.5)
        self.view.outcome(3, 'spoken', threshold=3.5)
        s = self.sent[-1]
        self.assertEqual((s['type'], s['v'], s['presence'], s['threshold']), ('mind.ideas', 1, 'solo', 3.5))
        self.assertEqual([m['revision'] for m in self.sent], [1, 2, 3, 4, 5])
        card, = s['cards']
        self.assertEqual((card['turn'], card['phase'], card['chosen'], card['ms']), (3, 'spoken', 1, 6200.0))
        self.assertEqual(card['heard'], '夜になる前に何を準備したらいい？')
        self.assertEqual(card['ideas'][1], {'kind': 'suggest', 'text': '丸石で拠点を作ろう', 'pro': '役に立つ',
                                            'con': '話がそれる', 'score': 4, 'weighted': 4.1, 'level': 4.1})
        self.assertNotIn('at', card)

    def test_newest_cards_first_and_only_a_few_kept(self):
        for turn in range(1, 6):
            self.view.thinking(turn, f'発言{turn}')
        self.assertEqual([c['turn'] for c in self.sent[-1]['cards']], [5, 4, 3])

    def test_no_ideas_and_missing_weights(self):
        self.view.thinking(2, 'こんにちは')
        self.view.thought(2, [], 100.0)
        self.assertEqual(self.sent[-1]['cards'][0]['phase'], 'none')
        self.view.thinking(4, 'これ何？')
        self.view.thought(4, [idea(weighted=None, turn=4)], 100.0)
        self.assertEqual(self.sent[-1]['cards'][0]['ideas'][0]['weighted'], -1.0)
        self.view.outcome(99, 'dropped', 'low')   # 送っていない発言の結果は捨てる
        self.assertEqual(self.sent[-1]['cards'][0]['phase'], 'thought')

    def test_long_line_is_shortened(self):
        self.view.thinking(1, 'あ' * 100)
        self.assertEqual(len(self.sent[-1]['cards'][0]['heard']), 40)


if __name__ == '__main__':
    unittest.main()
