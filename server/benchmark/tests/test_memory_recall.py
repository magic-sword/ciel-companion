import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('memory_recall', ROOT / 'server/benchmark/memory_recall.py')
mr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mr)


class Oracle:
    """Returns exactly the expected memories, marking past ones."""
    id = 'oracle'

    def __init__(self, suite):
        self.cases = {c['id']: c for c in suite['cases']}
        self.current = None

    def retrieve(self, memories, ctx):
        e = self.current['expect']
        return [mr.Item(i, 'auto') for i in e.get('relevant', [])] + [mr.Item(i, 'auto', past=True) for i in e.get('past', [])]


class Everything:
    """Pushes every stored memory, unmarked: maximal recall, but leaks and stale facts."""
    id = 'everything'

    def retrieve(self, memories, ctx):
        return [mr.Item(m.id, 'auto') for m in memories]


def run_with(retriever, suite):
    rows = []
    for case in suite['cases']:
        if isinstance(retriever, Oracle):
            retriever.current = case
        memories, ctx = mr.build_case(suite, case)
        rows.append(mr.score_case(case, memories, retriever.retrieve(memories, ctx)))
    return rows


class MemoryRecallTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = mr.load_suite()

    def test_suite_shape(self):
        abilities = {c['ability'] for c in self.suite['cases']}
        self.assertTrue({'extraction', 'multi_session', 'temporal', 'update', 'abstention', 'privacy', 'control'} <= abilities)
        self.assertEqual({1, 2, 3}, {c['stage'] for c in self.suite['cases']})

    def test_filler_is_distinct_and_ordered(self):
        case = next(c for c in self.suite['cases'] if c['id'] == 'note_beyond_cap')
        memories, _ = mr.build_case(self.suite, case)
        notes = [m for m in memories if m.kind == 'note']
        self.assertEqual(56, len(notes))
        self.assertEqual(len(notes), len({m.text for m in notes}))
        target = next(m for m in notes if m.id == 'n_guitar')
        self.assertEqual(55, sum(m.at > target.at for m in notes))

    def test_oracle_is_perfect(self):
        rows = run_with(Oracle(self.suite), self.suite)
        summary = mr.summarize(rows)['all']
        self.assertEqual(1.0, summary['recall_auto'])
        self.assertEqual(0, summary['forbidden_auto'])
        self.assertEqual(0, summary['stale_as_current'])

    def test_everything_is_caught_leaking(self):
        rows = {r['id']: r for r in run_with(Everything(), self.suite)}
        self.assertEqual(['n_interview'], rows['public_private_note']['forbidden_auto'])
        self.assertEqual(['n_aquarium'], rows['other_person_note']['forbidden_auto'])
        self.assertEqual(['p_w0_base'], rows['old_world_base']['forbidden_auto'])
        self.assertEqual(['p_old_base'], rows['base_destroyed']['stale_as_current'])
        self.assertEqual(1.0, rows['house_multi']['recall_auto'])
        # Recall is never applicable where nothing should be remembered.
        self.assertIsNone(rows['control_smalltalk']['recall_auto'])

    def test_current_method_matches_host_limits(self):
        current = mr.CurrentMethod()
        self.assertEqual(15, current.push_notes)
        self.assertEqual(50, current.max_notes)
        rows = {r['id']: r for r in run_with(current, self.suite)}
        self.assertEqual(1.0, rows['note_recent_direct']['recall_auto'])
        self.assertEqual(1.0, rows['like_sunset']['recall_auto'])
        # 25 newer notes: past the push window, still reachable by the recall tool.
        self.assertEqual(0.0, rows['note_deep']['recall_auto'])
        self.assertEqual(1.0, rows['note_deep']['recall_reach'])
        # 55 newer notes: dropped by the storage cap.
        self.assertEqual(0.0, rows['note_beyond_cap']['recall_reach'])
        # Diary and game memories never reach the conversation.
        for case in ('diary_song_recent', 'base_rest', 'village_found', 'house_multi', 'yesterday'):
            self.assertEqual(0.0, rows[case]['recall_reach'], case)
        self.assertEqual([], rows['public_private_note']['forbidden_auto'])
        self.assertEqual(0, rows['public_private_note']['auto_count'])

    def test_recall_method_uses_host_policy(self):
        rows = {r['id']: r for r in run_with(mr.RecallMethod(), self.suite)}
        # Words and dates alone already reach the diary, places of this world and time-scoped questions.
        for case in ('diary_song_recent', 'village_found', 'old_world_base', 'yesterday', 'note_beyond_cap'):
            self.assertEqual(1.0, rows[case]['recall_auto'], case)
        # The same eligibility as the host: nothing private, foreign or from another world.
        for case in ('public_private_note', 'other_person_note', 'old_world_base', 'abstain_sea'):
            self.assertEqual([], rows[case]['forbidden_auto'], case)
        self.assertEqual(0, rows['control_smalltalk']['auto_count'] - 10)   # no memory pushed into unrelated talk
        # Usage keys connect a rest to the base; given them, the base is recalled.
        keyed = mr.RecallMethod(keys={'ユウと森の横に作った拠点。ベッドとチェストがある': '休む、寝る、夜を越す'})
        self.assertEqual(1.0, {r['id']: r for r in run_with(keyed, self.suite)}['base_rest']['recall_auto'])

    def test_partial_recall_and_rank(self):
        case = next(c for c in self.suite['cases'] if c['id'] == 'house_multi')
        memories, _ = mr.build_case(self.suite, case)
        row = mr.score_case(case, memories, [mr.Item('g_farm', 'auto')])
        self.assertEqual(0.5, row['recall_auto'])
        self.assertEqual({'g_house': None, 'g_farm': 1}, row['ranks'])

    def test_compare_pairs_cases(self):
        base = mr.run(mr.CurrentMethod(), self.suite)
        rows = run_with(Everything(), self.suite)
        cand = dict(base, retriever='everything', cases=rows)
        result = mr.compare(base, cand)
        self.assertEqual(len(self.suite['cases']), result['paired'])
        self.assertGreater(result['recall_improved'], 0)
        self.assertGreater(result['new_leaks_or_stale'], 0)

    def test_unknown_ids_are_rejected(self):
        case = self.suite['cases'][0]
        memories, _ = mr.build_case(self.suite, case)
        with self.assertRaises(ValueError):
            mr.score_case(case, memories, [mr.Item('nope', 'auto')])


if __name__ == '__main__':
    unittest.main()
