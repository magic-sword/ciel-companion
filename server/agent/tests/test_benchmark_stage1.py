import copy
import sys
import unittest
import tempfile
import importlib.util
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from benchmark.audit import score,state_hash
from benchmark.stage1 import KINDS,fixture
from benchmark.spatial import validate_spatial,evaluate_spatial
from benchmark.pointing import validate_capture
from benchmark.policy import Progress
from benchmark.run import Trace
from benchmark.stage1_intake import goal_spec,scenarios


class Stage1FixtureTest(unittest.TestCase):
    def test_pointer_requires_top_face_even_when_coordinates_match(self):
        actual=dict(x=1,y=64,z=2,face=[1,0,0])
        with self.assertRaisesRegex(RuntimeError,'wrong fixture face'):
            validate_capture(actual,[1,64,2],[0,1,0])
        validate_capture({**actual,'face':[0,1,0]},[1,64,2],[0,1,0])

    def test_fresh_acceptance_inputs_are_distinct_bounded_and_balanced(self):
        path=Path(__file__).resolve().parents[3]/'scripts/server/minecraft-stage1-fresh.py'
        module_spec=importlib.util.spec_from_file_location('fresh_intake_inputs',path)
        module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
        fresh=module.fresh_cases()
        self.assertEqual(len(fresh),24);self.assertEqual(len({c['id']for c in fresh}),24)
        self.assertEqual([sum(c['group']==g for c in fresh)for g in range(6)],[4]*6)
        previous={text for c in scenarios()for text in c['turns']}
        self.assertFalse(previous&{text for c in fresh for text in c['turns']})
        for case in fresh:
            self.assertEqual(case['split'],'holdout')
            goal=case['expected']or{}
            if 'region'in goal:
                r=goal['region'];volume=1
                for axis in 'xyz':
                    self.assertLessEqual(r[axis+'1'],r[axis+'2']);volume*=r[axis+'2']-r[axis+'1']+1
                self.assertLessEqual(volume,64)
        self.assertEqual(len(module.FROZEN_SOURCE_SHA256),64)

    def test_expired_selection_and_protection_overlap_have_distinct_refusals(self):
        cases={c['id']:c for c in scenarios()}
        self.assertEqual(cases['g5-5']['refusal'],'selection_expired')
        self.assertEqual(cases['g6-7']['refusal'],'protected_overlap')

    def test_level_and_explicit_ground_preservation_are_the_same_goal(self):
        level={'operation':'level','level':dict(x1=4,x2=5,z1=0,z2=1,ground_y=63,top_y=64),'clear_blocks':['dirt']}
        clear={'operation':'clear','region':dict(x1=4,x2=5,z1=0,z2=1,y1=64,y2=64),
               'preserve_regions':[dict(x1=4,x2=5,z1=0,z2=1,y1=63,y2=63)],'clear_blocks':['dirt']}
        self.assertEqual(goal_spec(level),goal_spec(clear))
        self.assertEqual(goal_spec({**clear,'preserve_regions':clear['preserve_regions']*2}),goal_spec(clear))
        wrong=copy.deepcopy(level);wrong['level']['ground_y']=62
        self.assertNotEqual(goal_spec(wrong),goal_spec(clear))
        self.assertEqual(len(scenarios()),48)
        self.assertEqual(len({c['id']for c in scenarios()}),48)
        self.assertEqual(sum(c['split']=='holdout'for c in scenarios()),24)

    def test_unrelated_travel_and_inventory_do_not_keep_construction_alive(self):
        task=fixture('floor',11)
        initial={'inventory':{},'position':[0,64,0]}
        progress=Progress(initial,task)
        progress.observe({'inventory':{'dirt':64},'position':[-20,64,0]},20)
        self.assertEqual(progress.last_progress,0)
        progress.observe({'inventory':{},'position':[3,64,0]},21)
        self.assertEqual(progress.last_progress,21)

    def test_two_complete_distinct_layouts_and_bounded_targets(self):
        for kind in KINDS:
            a,b,c,d=(fixture(kind,seed)for seed in (11,29,47,65))
            validate_spatial(a);validate_spatial(b);validate_spatial(c);validate_spatial(d)
            self.assertNotEqual(a['spatial'],b['spatial'])
            self.assertNotEqual(b['spatial'],c['spatial'])
            self.assertNotEqual(c['spatial'],d['spatial'])
            for t in (a,b,c,d):
                r=t['region_spec']['region']
                self.assertLessEqual((r['x2']-r['x1']+1)*(r['y2']-r['y1']+1)*(r['z2']-r['z1']+1),64)
                self.assertEqual(len({tuple(v[:3]) for v in t['spatial']['expected']}),len(t['spatial']['expected']))


class ConstructionDeadlineTest(unittest.IsolatedAsyncioTestCase):
    async def test_preparation_without_a_single_edit_cannot_avoid_the_deadline(self):
        task=fixture('floor',11);now=[0]
        state={'inventory':{},'position':[0,64,0],'health':20,'deaths':0,
               'spatial_expected':[False]*64,'spatial_preserved':[True]*len(task['spatial']['preserve'])}
        async def sleep(seconds):now[0]+=seconds
        with tempfile.TemporaryDirectory()as folder:
            trace=Trace(Path(folder)/'trace.jsonl')
            async def submit(_):
                trace('game_call',id='prepare',name='minecraft_prepare_region',arguments={})
                trace('game_result',id='prepare',name='minecraft_prepare_region',result={'status':'ready'})
            driver=SimpleNamespace(submit=submit,events=lambda:[],goal_state={},report_complete=lambda _:False)
            result=await evaluate_spatial(task,SimpleNamespace(snapshot=lambda _:state),driver,trace,state,
                seconds=None,max_llm=100,max_calls=100,poll=1,clock=lambda:now[0],sleep=sleep,observe=lambda:{'body':{}})
        self.assertEqual((result['reason'],result['elapsed_seconds']),('first_edit_timeout',30))
        self.assertEqual(result['first_observation_seconds'],0)


class AuditFaultTest(unittest.TestCase):
    def setUp(self):
        self.task={'spatial':{'expected':[[0,64,0,'oak_planks']],'preserve':[[1,64,0,'chest']]}}
        self.states=['minecraft:air','minecraft:chest|contents']
        self.initial={'version':1,'id':'test','bounds':[0,64,0,1,64,0],'states':self.states,'sha256':state_hash(self.states)}
        self.events=[{'id':'test','sequence':1,'position':[0,64,0],'actor':'Ciel_Debug','cause':'place'}]
        self.final={'version':1,'id':'test','complete':True,'error':'','sequence':1,
            'initial_sha256':state_hash(self.states),'final_sha256':state_hash(['minecraft:oak_planks',self.states[1]]),
            'changes':[{'position':[0,64,0],'before':'minecraft:air','after':'minecraft:oak_planks'}]}

    def test_independent_snapshot_and_event_log_agree(self):
        self.assertTrue(score(self.task,self.initial,self.final,self.events)['passed'])

    def test_temporary_destruction_of_restored_protected_cell_fails(self):
        events=self.events+[{'id':'test','sequence':2,'position':[1,64,0],'actor':'Ciel_Debug','cause':'break'},
                            {'id':'test','sequence':3,'position':[1,64,0],'actor':'Ciel_Debug','cause':'place'}]
        self.final['sequence']=3
        result=score(self.task,self.initial,self.final,events)
        self.assertFalse(result['passed']);self.assertEqual(len(result['violations']),2)

    def test_missing_log_sequence_snapshot_or_complete_flag_is_error(self):
        for change in ({'sequence':2},{'initial_sha256':'bad'},{'complete':False},{'final_sha256':'bad'}):
            with self.assertRaises(ValueError):score(self.task,self.initial,{**self.final,**change},self.events)
        with self.assertRaises(ValueError):score(self.task,self.initial,self.final,[{**self.events[0],'sequence':2}])
        self.final['sequence']=0
        with self.assertRaises(ValueError):score(self.task,self.initial,self.final,[])

    def test_noop_claim_wrong_height_and_changed_container_fail(self):
        self.final['changes']=[];self.final['final_sha256']=self.initial['sha256']
        self.assertFalse(score(self.task,self.initial,self.final,self.events)['passed'])
        self.final['changes']=[{'position':[1,64,0],'before':self.states[1],'after':'minecraft:chest|empty'}]
        self.final['final_sha256']=state_hash(['minecraft:air','minecraft:chest|empty'])
        self.assertFalse(score(self.task,self.initial,self.final,self.events)['passed'])

    def test_refusal_is_not_allowed_to_partially_build(self):
        self.task['spatial']['expected_reason']='missing_materials'
        self.assertFalse(score(self.task,self.initial,self.final,self.events)['passed'])
