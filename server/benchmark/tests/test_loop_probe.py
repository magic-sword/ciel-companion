import copy
import unittest
from pathlib import Path
from server.benchmark.weight_space import load_suite
from server.benchmark.loop_probe import signals, metrics


class LoopProbeTests(unittest.TestCase):
    def setUp(self):
        self.suite = load_suite(Path(__file__).parents[1] / 'weight_space/failure-loop-suite.json')
        self.case = self.suite['cases'][2]

    def row(self, texts):
        return dict(status='ok', turns=[dict(index=i, status='ok', response=[{'content': t}])
                                       for i, t in enumerate(texts)])

    def test_same_question_across_turns_and_seed_is_detected(self):
        totals, turns = metrics(self.case, self.row(['原木は何に使うの？']*5))
        self.assertEqual(totals['loop_candidate_turns'][0], 5)
        self.assertEqual(totals['loop_candidate_longest_run'][0], 5)
        self.assertEqual(turns[0]['metrics']['loop_seed_question_echoes'][0], 1)

    def test_paraphrase_and_omitted_object(self):
        for text in ['木材の使い道を教えて。', '何を作りたい？', '何に使うの？']:
            self.assertTrue(signals(self.case, 0, text)['question_candidates'])

    def test_new_topic_question_can_repeat_outside_target_regex(self):
        totals, turns = metrics(self.case, self.row(['その小説、どんな物語なんですか？']*2+['7日です。']*3))
        self.assertEqual(totals['loop_candidate_turns'][0], 0)
        self.assertEqual(totals['loop_reasked_turns'][0], 1)
        self.assertEqual(turns[1]['evidence']['reasked_questions'], ['その小説、どんな物語なんですか？'])

    def test_acknowledgement_not_a_question(self):
        self.assertFalse(signals(self.case, 0, '原木の用途はもう聞かないよ。')['question_candidates'])

    def test_recovery_and_relapse_are_not_averaged_away(self):
        totals, _ = metrics(self.case, self.row(['何に使うの？', '何を作るの？', '24時間だよ。', '使い道を教えて。', 'またね。']))
        self.assertEqual(totals['loop_candidate_turns'][0], 3)
        self.assertEqual(totals['loop_candidate_longest_run'][0], 2)

    def test_requested_repeat_is_control_not_failure(self):
        case = self.suite['cases'][3]
        totals, turns = metrics(case, self.row(['原木は何に使うの？']*2+['またね。']))
        self.assertEqual(totals['loop_candidate_turns'][0], 0)
        self.assertEqual(turns[0]['metrics']['loop_question_candidate'][1], 'neutral')

    def test_incomplete_not_perfect(self):
        totals, _ = metrics(self.case, self.row(['24時間だよ。']))
        self.assertIsNone(totals['loop_candidate_turns'][0])

    def test_semantic_continuation_can_be_reviewed_when_regex_misses(self):
        from server.benchmark.progress import score_report
        case = self.suite['cases'][3]
        row = self.row(['何に使うの？', '何に使うの？', 'その家のイメージを聞かせてください。'])
        row.update(id=case['id'], category=case['category'], repeat=0, messages=[], calls=[])
        report = dict(trials=[row])
        _, review = score_report(report, self.suite)
        review['evaluator'] = 'test-reviewer-v1'
        item = review['items'][2]
        item['loop_labels']['stale_task_continuation'] = 1
        with self.assertRaises(ValueError): score_report(report, self.suite, review)
        item['loop_evidence']['stale_task_continuation'] = '終了要求後も家のイメージを質問している。'
        scored, _ = score_report(report, self.suite, review)
        self.assertEqual(scored['observations'][-1]['metrics']['review_loop_stale_task_continuation']['value'], 1)
        self.assertIsNone(scored['observations'][-1]['metrics']['review_loop_unwanted_question']['value'])

    def test_success_control_has_same_probes(self):
        self.assertEqual(self.suite['cases'][0]['dialogue'], self.suite['cases'][1]['dialogue'])

    def test_invalid_probe_rejected(self):
        # Validate regex configuration using a temporary suite, not live output.
        import json
        import tempfile
        suite = copy.deepcopy(self.suite)
        suite['cases'][0]['loop_probe']['question_pattern'] = ''
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'suite.json'
            path.write_text(json.dumps(suite), encoding='utf-8')
            with self.assertRaises(ValueError): load_suite(path)
