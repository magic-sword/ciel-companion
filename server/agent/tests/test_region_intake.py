import copy
import json
import time
from unittest.mock import patch
import unittest
from target_candidates import TargetCandidates, coordinate_mentions
import test_game_intake
from livekit.agents import llm
from game_intake import decision_schema,available_variants
import jsonschema


PREPARATION = {'version': 1, 'tool': 'minecraft_prepare_region', 'result_argument': 'plan_id',
    'target_binding': {'kind': 'region_roles'}, 'intent_schema': {
        'type': 'object', 'additionalProperties': False, 'required': ['operation', 'on_protected'],
        'properties': {'operation': {'enum': ['clear', 'floor', 'wall', 'backfill', 'level']},
            'block': {'type': 'string'}, 'on_protected': {'const': 'stop_before_edit'}}}}


def definitions():
    return {'1': {'kind': 'work', 'name': 'minecraft.edit_region', 'arguments': {}, 'preparation': PREPARATION}}


def intent(operation='clear', **roles):
    return {'operation': operation, 'on_protected': 'stop_before_edit', 'target_roles': roles}


class RegionRolesTest(unittest.TestCase):
    def test_confirmed_complete_intent_requires_a_spec_for_game_preparation(self):
        payload={'stage':'arguments','required_operation':'submit','confirmed_request':True,
            'capability':{'kind':'work','arguments':{'type':'object'},'constraints':{'type':'object'}}}
        schema=decision_schema(payload)
        jsonschema.validate({'operation':'submit','arguments':{},'constraints':{},'title':'work','seconds':90},schema)
        for value in ({'operation':'none'},{'operation':'clarify','message':'Which range?'}):
            with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(value,schema)
        jsonschema.validate({'operation':'none'},decision_schema({**payload,'confirmed_request':False}))
        jsonschema.validate({'operation':'clarify','message':'Which range?'},decision_schema({**payload,'confirmed_request':False}))

    def test_preserve_schema_inherits_the_only_explicit_edit_axes(self):
        defs=definitions();defs['1']['preparation']=copy.deepcopy(PREPARATION)
        defs['1']['preparation']['required_axes']=['x','y','z']
        c=TargetCandidates('one','X=4〜5、Y=64、Z=0〜1の土を除去。Y=63の地面は残す',None,defs)
        role=c.definitions['1']['arguments']['properties']['target_roles']['properties']['preserve']['items']
        self.assertEqual(set(role['properties']),{'y'})

    def test_explicit_service_height_roles_only_offer_variants_that_can_bind_them(self):
        definition={'preparation':{'variants':{
            'range':{'description':'range','roles':['edit','preserve']},
            'heights':{'description':'heights','required_height_mentions':2,'roles':['edit','ground','top']}}}}
        mentions=coordinate_mentions('上限Y=64、X=-23〜-21、地面Y=62、Z=-5〜-3')
        self.assertEqual([v['id']for v in available_variants(definition,mentions,{'top':['C1'],'ground':['C3']})],['heights'])
        self.assertEqual(len(available_variants(definition,mentions,{'ground':['C3']})),2)

    def test_ranged_height_does_not_offer_a_variant_requiring_single_heights(self):
        definition={'preparation':{'variants':{'range':{'description':'range'},
            'heights':{'description':'heights','required_height_mentions':2}}}}
        self.assertEqual([v['id']for v in available_variants(definition,coordinate_mentions('Y=64〜65、地面Y=63'))],['range'])
        self.assertEqual(len(available_variants(definition,coordinate_mentions('地面Y=63、上限Y=65'))),2)

    def test_declared_height_labels_prevent_reversed_ground_and_top(self):
        defs=definitions();defs['1']['preparation']=copy.deepcopy(PREPARATION)
        defs['1']['preparation']['role_prefixes']={'ground':['地面'],'top':['上限']}
        c=TargetCandidates('one','上限Y=64、X=-23〜-21、地面Y=62、Z=-5〜-3',None,defs)
        roles=c.definitions['1']['arguments']['properties']['target_roles']['properties']
        self.assertEqual(roles['ground']['enum'],['C3'])
        self.assertEqual(roles['top']['enum'],['C1'])
        with self.assertRaises(ValueError):
            c.resolve('1',intent('level',edit={'x':'C2','z':'C4'},ground='C1',top='C3'))
        result=c.resolve('1',intent('level',edit={'x':'C2','z':'C4'},ground='C3',top='C1'))
        self.assertEqual(result['level']['ground_y'],62)

    def test_schema_requires_variant_and_keeps_select_separate_from_submit(self):
        payload={'stage':'select','capabilities':[{'id':'1','variants':[{'id':'floor'}]}]}
        schema=decision_schema({**payload,'draft':{'input':'original request'}})
        jsonschema.validate({'operation':'select','capability':'1','variant':'floor','draft_action':'continue'},schema)
        for value in ({'operation':'select','capability':'1'}, {'operation':'submit','arguments':{}}):
            with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(value,schema)
        for value in ({'operation':'select','capability':'1','variant':'floor','draft_action':'continue'},
                      {'operation':'answer','decision_id':'invented','action':'retry'}):
            with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(value,decision_schema(payload))
        complete={**payload,'draft':{'input':'old','capability':'1','variant':'floor'},'targets':[{'axis':a}for a in 'xyz']}
        action={'operation':'select','capability':'1','variant':'floor','draft_action':'new'}
        jsonschema.validate(action,decision_schema(complete))
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate({**action,'draft_action':'continue'},decision_schema(complete))

    def test_material_choices_are_bound_to_source_and_longest_alias(self):
        defs=definitions();prep=copy.deepcopy(PREPARATION);defs['1']['preparation']=prep
        prep['source_values']={'block':{'stone':['石','stone'],'cobblestone':['丸石','cobblestone']}}
        prep['intent_schema']['required'].append('block')
        c=TargetCandidates('one','X=4、Y=64、Z=0に床を敷いて',None,defs)
        self.assertIn('block',c.definitions['1']['missing_fields'])
        c=TargetCandidates('one','X=4、Y=64、Z=0に丸石の床を敷いて',None,defs)
        self.assertEqual(c.definitions['1']['arguments']['properties']['block']['enum'],['cobblestone'])

    def test_correction_cannot_invent_a_preserved_height(self):
        defs=definitions();prep=copy.deepcopy(PREPARATION);defs['1']['preparation']=prep
        prep.update(required_axes=['x','y','z'],source_roles={'preserve':['残し','保護']})
        c=TargetCandidates('one','X=4、Y=64、Z=0、いやY=65に床を作って',None,defs)
        self.assertIn('coordinate_roles',c.definitions['1']['missing_fields'])
        self.assertNotIn('preserve',c.definitions['1']['arguments']['properties']['target_roles']['properties'])
        c=TargetCandidates('one','X=4、Y=64、Z=0を除去、Y=63は残してください',None,defs)
        self.assertIn('preserve',c.definitions['1']['arguments']['properties']['target_roles']['properties'])
        with self.assertRaises(ValueError):coordinate_mentions('X=4、Y=64、Z=0、いや65')

    def test_pointed_level_keeps_opaque_selection_until_game_validation(self):
        mentions=coordinate_mentions('選んだ2点のX/Z範囲を、地面Y=63を残し上限Y=65まで')
        self.assertEqual([m['range']for m in mentions],[[63,63],[65,65]])
        c=TargetCandidates('one','地面Y=63、上限Y=65',{'selection_id':'opaque','points':[]},definitions())
        r=c.resolve('1',intent('level',reference='P1',ground='C1',top='C2'))
        self.assertEqual(r['selection_id'],'opaque')
        self.assertEqual(r['level'],{'ground_y':63,'top_y':65})

    def test_height_roles_cannot_be_reused_as_edit_or_preserve_axes(self):
        defs=definitions();prep=copy.deepcopy(PREPARATION);defs['1']['preparation']=prep
        prep.update(required_axes=['x','z'],required_height_mentions=2)
        c=TargetCandidates('one','X=4〜6、Z=0〜1、地面Y=63、上限Y=65',None,defs)
        schema=c.definitions['1']['arguments'];roles=schema['properties']['target_roles']
        self.assertEqual(set(roles['required']),{'edit','ground','top'})
        self.assertNotIn('y',roles['properties']['edit']['properties'])
        self.assertNotIn('preserve',roles['properties'])
        jsonschema.validate(intent('level',edit={'x':'C1','z':'C2'},ground='C3',top='C4'),schema)

    def test_repeat_uses_confirmed_goal_and_rejects_new_coordinates_or_material(self):
        defs=definitions();defs['1']['preparation']=copy.deepcopy(PREPARATION)
        defs['1']['preparation']['allow_repeat']=True
        goal={'operation':'floor','region':dict(x1=4,x2=6,y1=64,y2=64,z1=0,z2=2),'block':'stone','on_protected':'stop_before_edit'}
        ref={'confirmed_spec':goal}
        defs['2']={'kind':'tool','name':'pointer_move','arguments':{'type':'object','properties':{}},
                   'target_binding':{'kind':'reference','argument':'selection_id'}}
        c=TargetCandidates('two','続きを進めて',ref,defs)
        self.assertEqual(c.definitions['2']['target_ids'],[])
        self.assertEqual(c.resolve('1',{**intent('floor',previous='R1'),'block':'stone'}),goal)
        with self.assertRaises(ValueError):c.resolve('1',{**intent('floor',previous='R1'),'block':'glass'})
        c=TargetCandidates('two','X=9へ続きを進めて',ref,defs)
        with self.assertRaises(ValueError):c.resolve('1',{**intent('floor',previous='R1'),'block':'stone'})

    def test_dimensions_are_source_bound_and_ascii_x_is_not_an_extra_axis(self):
        c=TargetCandidates('one','X=4〜5、Y=64、Z=0〜1に3x3の床',None,definitions())
        r=c.resolve('1',intent('floor',edit={'x':'C1','y':'C2','z':'C3'},dimensions='D1'))
        self.assertEqual(r['expected_dimensions'],[3,3])
        self.assertEqual(len(c.mentions),3)
        with self.assertRaises(ValueError):c.resolve('1',intent('floor',edit={'x':'C1','y':'C2','z':'C3'}))
    def test_edit_and_preserved_ground_share_axis_without_overwriting(self):
        c = TargetCandidates('one', 'X=4〜6、Y=64〜65、Z=0〜1の土を除去。Y=63は残す。', None, definitions())
        r = c.resolve('1', intent(edit={'x': 'C1', 'y': 'C2', 'z': 'C3'}, preserve=[{'y': 'C4'}]))
        self.assertEqual(r['region'], dict(x1=4, x2=6, y1=64, y2=65, z1=0, z2=1))
        self.assertEqual(r['preserve_regions'][0]['y1'], 63)

    def test_dropped_or_reused_values_and_wrong_axes_are_rejected(self):
        c = TargetCandidates('one', 'X=4〜6、Y=64〜65、Z=0〜1。Y=63を保存', None, definitions())
        for roles in ({'edit': {'x': 'C1', 'y': 'C2', 'z': 'C3'}},
                      {'edit': {'x': 'C1', 'y': 'C3', 'z': 'C2'}, 'preserve': [{'y': 'C4'}]},
                      {'edit': {'x': 'C1', 'y': 'C2', 'z': 'C3'}, 'preserve': [{'y': 'C2'}]}):
            with self.assertRaises(ValueError): c.resolve('1', intent(**roles))

    def test_level_binds_ground_and_top_and_does_not_add_one_in_model(self):
        c = TargetCandidates('one', 'X=4〜6、Z=0〜1、地面Y=63、上限Y=65', None, definitions())
        r = c.resolve('1', intent('level', edit={'x': 'C1', 'z': 'C2'}, ground='C3', top='C4'))
        self.assertEqual(r['level'], dict(x1=4, x2=6, z1=0, z2=1, ground_y=63, top_y=65))

    def test_invalid_numbers_missing_coordinates_and_pointer_substitution_fail(self):
        for text in ('X=5.5、Y=64、Z=0', 'X=5e3、Y=64、Z=0', 'X=5〜、Y=64、Z=0', 'X=5、Z=0'):
            c = TargetCandidates('one', text, {'selection_id': 'old', 'points': []}, definitions())
            with self.assertRaises(ValueError): c.resolve('1', intent(edit={'x': 'C1', 'y': 'C2', 'z': 'C3'}))
        c = TargetCandidates('one', 'X=5、Y=64、Z=0', {'selection_id': 'old'}, definitions())
        with self.assertRaises(ValueError): c.resolve('1', intent(reference='P1'))


class PreparedIntakeTest(unittest.IsolatedAsyncioTestCase):
    setUp = test_game_intake.IntakeTest.setUp
    sequence = test_game_intake.IntakeTest.sequence
    def prepared(self):
        self.runner.env.profile['work']['capabilities'] = [{
            'name': 'minecraft.edit_region', 'description': '整地・床・壁・埋め戻し',
            'arguments': {'type': 'object', 'required': ['plan_id'], 'properties': {'plan_id': {'type': 'string'}}},
            'constraints': {'type': 'object', 'required': ['failure_policy'], 'properties': {'failure_policy': {'const': 'stop'}}},
            'preparation': copy.deepcopy(PREPARATION)}]
        self.runner.env.use.return_value = {'status': 'ready', 'plan_id': 'prepared-only'}

    def action(self, **roles):
        return {'operation': 'submit', 'arguments': intent(**roles), 'constraints': {'failure_policy': 'stop'}, 'seconds': 90}

    async def test_prepares_bound_spec_then_submits_opaque_result_once(self):
        self.prepared()
        self.sequence({'operation': 'select', 'capability': '1'}, self.action(edit={'x': 'C1', 'y': 'C2', 'z': 'C3'}, preserve=[{'y': 'C4'}]))
        item = llm.ChatMessage(role='user', content=['X=4〜6、Y=64〜65、Z=0〜1の土を除去。Y=63は残す。'])
        await self.intake.handle(item)
        await self.intake.handle(item)
        self.runner.env.use.assert_awaited_once()
        self.assertEqual(self.runner.env.use.await_args.args[1]['spec']['region']['z2'], 1)
        self.runner.start.assert_awaited_once_with('minecraft.edit_region', {'plan_id': 'prepared-only'},
            constraints={'failure_policy': 'stop'}, title='', seconds=unittest.mock.ANY, request_id=item.id)

    def variants(self):
        self.prepared()
        prep=self.runner.env.profile['work']['capabilities'][0]['preparation']
        schema=copy.deepcopy(PREPARATION['intent_schema'])
        schema['properties']['clear_blocks']={'type':'array','items':{'type':'string'}}
        schema['required'].append('clear_blocks')
        prep['source_values']={'clear_blocks':{'dirt':['土'],'stone':['石']}}
        prep['allow_repeat']=True
        prep['variants']={op:{'schema':{**copy.deepcopy(schema),'properties':{**schema['properties'],'operation':{'const':op}}},
            'description':op,'roles':['edit','ground','top'],'required_axes':['x','z']if op=='level'else['x','y','z'],
            'required_height_mentions':2 if op=='level'else 0}for op in ('clear','level')}

    async def test_selected_colloquial_and_quoted_requests_reach_game_validation(self):
        self.variants()
        for text in ('X=4、Y=64、Z=0の土を整地してほしいな',
                     'X=4、Y=64、Z=0の土を整地しておくれる',
                     '「X=4、Y=64、Z=0の土を除去」でお願いします'):
            with self.subTest(text=text):
                self.runner.env.use.reset_mock();self.runner.start.reset_mock()
                action=self.action(edit={'x':'C1','y':'C2','z':'C3'})
                action['arguments']['clear_blocks']=['dirt']
                self.sequence({'operation':'select','capability':'1','variant':'clear','draft_action':'new'},action)
                await self.intake.handle(llm.ChatMessage(role='user',content=[text]))
                spec=self.runner.env.use.await_args.args[1]['spec']
                self.assertEqual(spec['region'],dict(x1=4,x2=4,y1=64,y2=64,z1=0,z2=0))
                self.runner.start.assert_awaited_once()

    async def test_live_requests_without_a_region_ask_for_missing_fields(self):
        self.variants()
        for text in ('この辺に家立てたいから、この辺を整地してほしいな','この辺りを整地しておくれる'):
            self.sequence({'operation':'select','capability':'1','variant':'level','draft_action':'new'})
            reply=await self.intake.handle(llm.ChatMessage(role='user',content=[text]))
            self.assertIn('指定してください',reply)
            self.assertIn('X座標',reply)
            self.assertEqual(self.intake._draft['text'],text)
        self.runner.env.use.assert_not_awaited();self.runner.start.assert_not_awaited()

    async def test_non_request_decisions_never_prepare_submit_or_answer(self):
        self.variants()
        for text in ('X=4、Y=64、Z=0の土は除去しないでください',
                     '「X=4、Y=64、Z=0の土を除去して」は例です',
                     '土を整地して。ただし今は実行しないで',
                     '石の床って作れるの？'):
            self.sequence({'operation':'none'})
            self.assertIsNone(await self.intake.handle(llm.ChatMessage(role='user',content=[text])))
            self.assertIsNone(self.intake._draft)
        self.sequence({'operation':'clarify','message':'施工を始める依頼ですか？'})
        self.assertIn('依頼ですか',await self.intake.handle(llm.ChatMessage(role='user',content=['ここ、整地かなあ'])))
        self.runner.env.use.assert_not_awaited();self.runner.start.assert_not_awaited();self.runner.answer.assert_not_awaited()

    async def test_colloquial_repeat_keeps_the_confirmed_spec(self):
        self.variants()
        spec={'operation':'clear','on_protected':'stop_before_edit','clear_blocks':['dirt'],
            'region':dict(x1=4,x2=4,y1=64,y2=64,z1=0,z2=0)}
        self.intake._previous={'text':'X=4、Y=64、Z=0の土を除去してほしいな',
            'references':None,'epoch':1,'spec':spec,'summary':''}
        action=self.action(previous='R1');action['arguments']['clear_blocks']=['dirt']
        self.sequence({'operation':'select','capability':'1','variant':'clear','draft_action':'repeat'},action)
        await self.intake.handle(llm.ChatMessage(role='user',content=['さっきの続き、お願いできるかな']))
        self.assertEqual(self.runner.env.use.await_args.args[1]['spec'],spec)
        self.runner.start.assert_awaited_once()

    async def test_local_structured_intake_has_explicit_repeatable_sampling(self):
        self.sequence({'operation':'none'})
        with patch('game_intake.models.is_local',return_value=True):
            await self.intake._infer({'stage':'select','capabilities':[]},time.monotonic())
        self.assertEqual(self.create.await_args.kwargs['temperature'],0)
        self.assertEqual(self.create.await_args.kwargs['response_format']['type'],'json_schema')

    async def test_unassigned_correction_is_a_question_and_complete_replacement_can_start(self):
        self.prepared()
        wrong=self.action(edit={'x':'C1','y':'C4','z':'C3'})
        self.sequence({'operation':'select','capability':'1'},wrong,wrong)
        reply=await self.intake.handle(llm.ChatMessage(role='user',content=['X=4〜5、Y=64、Z=0〜1、いやY=65に石の床を作って']))
        self.assertIn('指定',reply);self.runner.start.assert_not_awaited()
        self.assertIsNotNone(self.intake._draft)
        self.sequence({'operation':'select','capability':'1','draft_action':'new'},self.action(edit={'x':'C1','y':'C2','z':'C3'}))
        await self.intake.handle(llm.ChatMessage(role='user',content=['X=4〜5、Y=65、Z=0〜1の土を除去して']))
        self.runner.start.assert_awaited_once()
        replacement=json.loads(self.create.await_args_list[-2].kwargs['messages'][1]['content'])
        self.assertNotIn('draft',replacement)

    async def test_clarification_followup_keeps_prior_coordinates(self):
        self.prepared()
        self.intake.draft_instructions='Use the confirmed answer without asking again'
        self.sequence({'operation': 'clarify', 'message': '高さYはいくつですか？'})
        await self.intake.handle(llm.ChatMessage(role='user', content=['X=4〜6、Z=0〜1を土で埋めて']))
        self.sequence({'operation': 'select', 'capability': '1', 'draft_action': 'continue'},
                      self.action(edit={'x': 'C1', 'z': 'C2', 'y': 'C3'}))
        await self.intake.handle(llm.ChatMessage(role='user', content=['Y=64です']))
        self.assertEqual(self.runner.env.use.await_args.args[1]['spec']['region'], dict(x1=4,x2=6,z1=0,z2=1,y1=64,y2=64))
        prompts=[call.kwargs['messages'][0]['content']for call in self.create.await_args_list]
        self.assertEqual(prompts,[self.intake.select_instructions,
            self.intake.select_instructions+'\n'+self.intake.draft_instructions,self.intake.instructions])

    async def test_refused_preparation_and_reconnect_never_submit(self):
        self.prepared()
        for reconnect in (False, True):
            async def prepare(*_):
                if reconnect: self.runner.env._connection_epoch += 1
                return {'status': 'refused', 'reason': 'protected_block'}
            self.runner.env.use.side_effect = prepare
            self.sequence({'operation': 'select', 'capability': '1'}, self.action(edit={'x':'C1','y':'C2','z':'C3'}))
            await self.intake.handle(llm.ChatMessage(role='user', content=['X=4〜6、Y=64、Z=0〜1を除去して']))
        self.runner.start.assert_not_awaited()

    async def test_draft_expiry_stop_and_other_speaker_cannot_resume(self):
        self.prepared()
        self.sequence({'operation':'clarify','message':'高さを教えてください'})
        await self.intake.handle(llm.ChatMessage(role='user', content=['X=4〜6、Z=0〜1に床を作って']))
        self.intake.on_transcribed(type('Event',(),{})(), owner=False)
        self.assertIsNone(self.intake._draft)
        self.sequence({'operation':'select','capability':'1','draft_action':'continue'})
        await self.intake.handle(llm.ChatMessage(role='user', content=['Y=64']))
        self.runner.start.assert_not_awaited()
