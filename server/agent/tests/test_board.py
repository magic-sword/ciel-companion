import unittest

import board


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class BoardTest(unittest.TestCase):
    def test_cards_move_and_old_ones_leave_the_list(self):
        clock = Clock()
        tasks = board.Board(clock)
        sent = []
        tasks.on_change = sent.append
        card = tasks.add('minutes', '会議の議事録をとる', board.RUNNING, 'listener', said='議事録開始して')
        clock.now += 30
        self.assertEqual(tasks.context(), '[今のタスク]\n#1 会議の議事録をとる：実行中（話の途中の頼みを聞く係が受けた・30 秒前から）')
        tasks.move(card, board.DONE, note='仕事用に送った')
        self.assertIn('：完了', tasks.context())
        self.assertIn('。仕事用に送った）', tasks.context())
        self.assertEqual(sent[-1]['cards'][0]['status'], board.DONE)
        clock.now += board.KEEP_SECONDS + 1
        self.assertIsNone(tasks.context())   # 終わって時間が経ったら一覧から外す
        self.assertEqual(sent[-1]['type'], 'board.state')

    def test_the_request_is_read_as_the_card(self):
        tasks = board.Board()
        card = tasks.add('minutes', '会議の議事録をとる', board.CHECKING, 'listener', said='議事録開始して')
        tasks.move(card, board.RUNNING)
        text = 'それで、議事録開始して。屋台を増やしたい'
        self.assertEqual(tasks.mark(text), 'それで、（→ #1 会議の議事録をとる：実行中）。屋台を増やしたい')
        self.assertEqual(tasks.strip(text), 'それで、。屋台を増やしたい')

    def test_find_and_remove(self):
        tasks = board.Board()
        old = tasks.add('minutes', 'A', board.DONE, 'ciel', ref='a')
        new = tasks.add('minutes', 'B', board.RUNNING, 'app', ref='b')
        self.assertIs(tasks.find('minutes'), new)
        self.assertIs(tasks.find('minutes', ref='a', statuses=(board.DONE,)), old)
        tasks.remove(new)
        self.assertIsNone(tasks.find('minutes'))


if __name__ == '__main__':
    unittest.main()
