import asyncio
import unittest
from unittest.mock import patch

from server.benchmark import drivers
from server.benchmark.report import metrics
from server.benchmark.run import load_tasks
from server.benchmark.world import achieved


class Runner:
    def __init__(self):
        self.work = {'state': 'running', 'decision': None}
        self.calls = []

    async def answer(self, decision_id, action, message=None):
        self.calls.append(('answer', decision_id, action, message))
        self.work = {'state': 'running', 'decision': None}

    async def tell(self, message):
        self.calls.append(('tell', message))


class ScriptedOwnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_the_owner_answers_each_question_once_and_speaks_when_a_command_first_appears(self):
        events, runner = [], Runner()
        task = {'owner': {'reply': 'Shear them.', 'say': [{'after_command': '!chooseOption', 'text': 'Keep the sheep.'}]}}
        owner = drivers.ScriptedOwner(task, runner, lambda kind, **data: events.append({'kind': kind, **data}))
        with patch.object(drivers, 'OWNER_DELAY', 0):
            loop = asyncio.create_task(owner.run())
            runner.work = {'state': 'needs_decision', 'decision': {'decision_id': 'q', 'kind': 'question', 'message': 'Kill or shear?'}}
            await asyncio.sleep(0.7)
            owner.activity({'command': '!chooseOption'})
            await asyncio.sleep(0.7)
            owner.activity({'command': '!chooseOption'})
            await asyncio.sleep(0.7)
            loop.cancel()
        self.assertEqual(runner.calls, [('answer', 'q', 'reply', 'Shear them.'), ('tell', 'Keep the sheep.')])
        counted = metrics(events)
        self.assertEqual((counted['owner_questions'], counted['owner_says']), (1, 1))

    def test_a_task_without_a_script_still_gets_an_answer(self):
        self.assertEqual(drivers.ScriptedOwner({}, Runner(), print).reply, drivers.DEFAULT_REPLY)

    def test_keeping_the_sheep_is_part_of_the_goal(self):
        task = next(t for t in load_tasks() if t['id'] == 'long_dirt_shelter_keep_sheep')
        initial = {'goal_blocks': [False] * 101, 'mobs': {'sheep': 3}}
        built = {'goal_blocks': [True] * 101}
        self.assertTrue(achieved(task, initial, {**built, 'mobs': {'sheep': 3}}))
        self.assertFalse(achieved(task, initial, {**built, 'mobs': {'sheep': 2}}))


if __name__ == '__main__':
    unittest.main()
