import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmark.distractors import attach, configuration, generate


class DistractorTest(unittest.IsolatedAsyncioTestCase):
    def test_bounded_unique_nested_inventory(self):
        all_defs = generate(100)
        self.assertEqual(len({d['name'] for d in all_defs}), 100)
        self.assertEqual(generate(10), all_defs[:10])
        for value in (-1, 101, True):
            with self.assertRaises(ValueError):
                generate(value)
        self.assertEqual(configuration({}), configuration({'CIEL_BENCH_DISTRACTORS': '0'}))

    async def test_surfaces_and_no_world_effect(self):
        for surface in ('work', 'catalog', 'both'):
            with self.subTest(surface=surface):
                profile = {'work': {'capabilities': [{'name': 'minecraft.obtain_item'}]}}
                original_profile = copy.deepcopy(profile)
                original = AsyncMock(return_value={'status': 'ok'})
                env = SimpleNamespace(profile=profile, tools=[], meta={}, _call=original,
                                      _wrap=lambda name, description, schema: name)
                records = []
                config = configuration({'CIEL_BENCH_DISTRACTORS': '10', 'CIEL_BENCH_DISTRACTOR_SURFACE': surface})
                attach(env, config, lambda kind, **kw: records.append((kind, kw)))
                self.assertEqual(profile, original_profile)
                self.assertEqual(len(env.tools), 0 if surface == 'work' else 10)
                self.assertEqual(len(env.profile['work']['capabilities']), 1 if surface == 'catalog' else 11)
                result = await env._call('minecraft_work_submit', {'capability': generate(10)[0]['name']})
                self.assertEqual(result['reason'], 'benchmark_distractor')
                original.assert_not_called()
                await env._call('minecraft_come_here', {})
                original.assert_awaited_once_with('minecraft_come_here', {})
                self.assertEqual(records[0][0], 'benchmark_distractors')
                self.assertEqual(records[1][0], 'benchmark_distractor_call')

    def test_collision_fails_before_mutation(self):
        env = SimpleNamespace(profile={'work': {'capabilities': generate(1)}}, tools=[], meta={})
        with self.assertRaises(ValueError):
            attach(env, configuration({'CIEL_BENCH_DISTRACTORS': '1'}), lambda *a, **kw: None)


if __name__ == '__main__':
    unittest.main()
