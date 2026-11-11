import copy
import unittest
from target_candidates import TargetCandidates, explicit_axes


def definitions():
    fields = {axis+str(end+1): [axis, end] for axis in 'xyz' for end in range(2)}
    return {
        '1': {'arguments': {'type': 'object', 'properties': {
            **{f: {'type': 'integer'} for f in fields}, 'block': {'type': 'string'}},
            'required': [*fields, 'block'], 'additionalProperties': False},
            'target_binding': {'kind': 'axes', 'fields': fields}},
        '2': {'arguments': {'type': 'object', 'properties': {'selection_id': {'type': 'string'},
              'action': {'type': 'string'}}, 'required': ['selection_id', 'action']},
              'target_binding': {'kind': 'reference', 'argument': 'selection_id'}},
        '3': {'arguments': {'type': 'object', 'properties': {'x': {}, 'z': {}}, 'required': ['x', 'z']},
              'target_binding': {'kind': 'axes', 'point': True, 'fields': {'x': ['x', 0], 'z': ['z', 0]}}}}


class TargetsTest(unittest.TestCase):
    def test_exact_axes_signs_fullwidth_reversed_range_and_single_height(self):
        for text in ('X=-7〜-9、Y=64、Z=8〜10', 'Ｘ＝－７～－９、Ｙ＝６４、Ｚ＝８～１０',
                     'Xは-7から-9、Yは64、Zは8から10'):
            c = TargetCandidates('speech', text, {'selection_id': 'old'}, definitions())
            self.assertEqual(c.resolve('1', {'target_id': 'T1', 'block': 'oak_planks'}),
                             dict(x1=-9, x2=-7, y1=64, y2=64, z1=8, z2=10, block='oak_planks'))
            self.assertEqual(c.definitions['2']['target_ids'], [])
            self.assertEqual(c.definitions['3']['target_ids'], [])

    def test_missing_malformed_or_corrected_coordinates_cannot_fall_back_to_pointer(self):
        for text in ('X=5、Z=1', 'X=5、Y=64、Z=', 'X=5.5、Y=64、Z=1',
                     'X=5、Y=64、Z=1、いやX=6', 'X=5〜、Y=64、Z=1', 'X=5、Y=64〜65.5、Z=1',
                     'X=5e3、Y=64、Z=1', 'X1=5、Y=64、Z=1', 'X=5万、Y=64、Z=1'):
            c = TargetCandidates('s', text, {'selection_id': 'old'}, definitions())
            self.assertEqual(c.definitions['1']['target_ids'], [], text)
            self.assertEqual(c.definitions['2']['target_ids'], [], text)
            with self.assertRaises(ValueError):
                c.resolve('2', {'target_id': 'T1'})

    def test_pointer_snapshot_not_latest_and_binding_is_request_local(self):
        ref = {'selection_id': 'speech-target', 'points': [{'x': 5}], 'source': 'owner_gaze'}
        original = definitions()
        before = copy.deepcopy(original)
        first = TargetCandidates('first', 'ここへ', ref, original)
        ref['selection_id'] = 'later-target'
        ref['points'][0]['x'] = 99
        second = TargetCandidates('second', 'ここへ', ref, original)
        self.assertEqual(first.resolve('2', {'target_id': 'T1'})['selection_id'], 'speech-target')
        self.assertEqual(second.resolve('2', {'target_id': 'T1'})['selection_id'], 'later-target')
        self.assertEqual(first.targets[0]['points'][0]['x'], 5)
        self.assertEqual(original, before)
        with self.assertRaises(ValueError):
            first.resolve('2', {'target_id': 'later-target'})

    def test_no_reference_does_not_invent_coordinates(self):
        c = TargetCandidates('s', 'この辺に床を', None, definitions())
        self.assertEqual(c.targets, [])
        self.assertTrue(all(d['target_ids'] == [] for d in c.definitions.values()))

    def test_unrelated_english_word_is_not_an_axis(self):
        self.assertEqual(explicit_axes('explore the xyz blocks'), (False, {}))
