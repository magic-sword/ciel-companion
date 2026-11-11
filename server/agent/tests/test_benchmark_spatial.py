import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from benchmark.spatial import spatial_outcome, validate_spatial
from benchmark.run import load_tasks


class SpatialOracleTest(unittest.TestCase):
    def test_all_fixtures_valid(self):
        tasks=[t for t in load_tasks() if t.get('spatial')]
        self.assertEqual(len(tasks),28)
        for task in tasks:
            validate_spatial(task)

    def test_claim_stale_completion_and_outside_changes_cannot_pass(self):
        spec={'skill':'build_region'}
        state={'spatial_expected':[True,True],'spatial_preserved':[True]}
        body={'last':{'skill':'build_region','since':2000,'phase':'succeeded'}}
        self.assertEqual(spatial_outcome(spec,state,body,1),('passed','blocks_verified'))
        self.assertIsNone(spatial_outcome(spec,state,body,3))
        state['spatial_expected']=[True,False]
        self.assertEqual(spatial_outcome(spec,state,body,1)[1],'false_completion')
        state['spatial_preserved']=[False]
        self.assertEqual(spatial_outcome(spec,state,body,1)[1],'outside_or_protected_changed')

    def test_refusal_requires_unchanged_world_and_matching_reason(self):
        spec={'skill':'build_region','expected_reason':'missing_materials'}
        state={'spatial_expected':[True],'spatial_preserved':[True]}
        body={'last':{'skill':'build_region','since':2000,'phase':'failed','result':{'reason':'missing_materials'}}}
        self.assertEqual(spatial_outcome(spec,state,body,1)[0],'passed')
        body['last']['result']['reason']='no_path'
        self.assertEqual(spatial_outcome(spec,state,body,1)[0],'failed')
        body['current']={'skill':'build_region'}
        self.assertIsNone(spatial_outcome(spec,state,body,1))

    def test_pointing_claim_requires_arrival_or_collected_item(self):
        body={'last':{'skill':'pointed_action','since':2000,'phase':'succeeded'}}
        state={'spatial_expected':[True],'spatial_preserved':[True],'position':[0,64,0],'inventory':{}}
        spec={'skill':'pointed_action','arrival':[12,64,0]}
        self.assertEqual(spatial_outcome(spec,state,body,1)[1],'wrong_destination')
        state['position']=[12,64,0]
        self.assertEqual(spatial_outcome(spec,state,body,1)[0],'passed')
        spec={'skill':'pointed_action','recovered':'crafting_table'}
        self.assertEqual(spatial_outcome(spec,state,body,1)[1],'item_not_recovered')
        state['inventory']['crafting_table']=1
        self.assertEqual(spatial_outcome(spec,state,body,1)[0],'passed')
