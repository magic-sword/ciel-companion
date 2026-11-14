"""One work decision per user item; independent of the voice pipeline and game planner."""
import asyncio
import copy
import hashlib
import json
import re
import time
import uuid
import debug_log
import models
import jsonschema
from target_candidates import TargetCandidates

STOP = re.compile(r'^(?:今の作業を)?(?:止まって|止めて|やめて|待って|中止して)(?:ください)?[。！!、\s]*(?:(?:その場で待ってください|こちらが頼むまで再開しないでください)[。\s、]*)*$')


def decision_schema(payload):
    def obj(properties,required=None):
        return {'type':'object','additionalProperties':False,'properties':properties,'required':required or list(properties)}
    alternatives=[obj({'operation':{'const':v}})for v in ('none','cancel','status')]
    alternatives.append(obj({'operation':{'const':'clarify'},'message':{'type':'string'}}))
    if payload['stage']=='select':
        complete_axes={'x','y','z'}<={t.get('axis')for t in payload.get('targets',[])}
        for capability in payload['capabilities']:
            for variant in capability.get('variants')or[None]:
                properties={'operation':{'const':'select'},'capability':{'const':capability['id']}}
                if variant:properties['variant']={'const':variant['id']}
                modes=['new'];draft=payload.get('draft')
                if (draft and not complete_axes and (draft.get('capability')==capability['id']or(draft.get('capability')is None and capability.get('variants')))
                        and (draft.get('variant')in(None,variant['id']if variant else None))):
                    modes=['continue']
                if payload.get('previous_request')and not complete_axes:modes.append('repeat')
                properties['draft_action']={'enum':modes}
                alternatives.append(obj(properties))
        current=payload.get('current',{})
        decision=(current.get('decision')or{}).get('decision_id')
        if current.get('state')=='needs_decision'and decision:
            actions=(current.get('decision')or{}).get('actions')or['retry','cancel']
            plain=[a for a in actions if a in('retry','cancel')]
            if plain:
                alternatives.append(obj({'operation':{'const':'answer'},'decision_id':{'const':decision},'action':{'enum':plain}}))
            if 'reply' in actions:
                # The body asked the owner; the reply carries the owner's own words to it.
                alternatives.append(obj({'operation':{'const':'answer'},'decision_id':{'const':decision},'action':{'const':'reply'},
                                         'message':{'type':'string','minLength':1,'maxLength':2000}}))
        if current.get('state')=='running':
            alternatives.append(obj({'operation':{'const':'tell'},'message':{'type':'string','minLength':1,'maxLength':2000}}))
    else:
        definition=payload['capability']
        if payload.get('confirmed_request'):
            # Selection has established the request's meaning and required
            # source fields are present. Geometry belongs to preparation.
            alternatives=[]
        properties={'operation':{'const':payload['required_operation']},'arguments':definition['arguments']}
        if definition['kind']=='work':
            properties.update(constraints=definition['constraints'],title={'type':'string'},seconds={'type':'integer','minimum':1,'maximum':120})
        alternatives.append(obj(properties))
    return {'anyOf':alternatives}


def available_variants(definition,mentions,source_roles=None):
    ranged_height=any(m['axis']=='y'and m['range'][0]!=m['range'][1]for m in mentions)
    labelled=set(source_roles or {})
    variants=definition.get('preparation',{}).get('variants',{})
    # If all service-declared height roles are explicit, only offer variants
    # that can represent those roles. The model still decides the user's intent.
    labelled_heights=not ranged_height and any(v.get('required_height_mentions')
        and len(labelled)>=v['required_height_mentions'] and labelled<=set(v.get('roles',[]))for v in variants.values())
    return [{'id':key,'description':v['description']}for key,v in definition.get('preparation',{}).get('variants',{}).items()
            if not(ranged_height and v.get('required_height_mentions'))
            and not(labelled_heights and not labelled<=set(v.get('roles',[])))]


class GameIntake:
    LOCAL_TEMPERATURE = 0

    def __init__(self, runner, instructions, *, client=None, authorized=lambda: True, select_instructions=None, draft_instructions=''):
        self.runner, self.instructions, self._client = runner, instructions, client
        self.select_instructions = select_instructions or instructions
        self.draft_instructions = draft_instructions
        self.authorized = authorized
        self._items = {}
        self._lock = asyncio.Lock()
        self._fast_stop = None
        self._generation = 0
        self._speech_reference = None
        self._reference_items = {}
        self._reference_tasks = set()
        self._speech_item = None
        self._draft = None
        self._previous = None
        self._current_item = None
        runner.intake = self

    async def _capture_references(self):
        env = self.runner.env
        if not env.playing() or not env.profile.get('reference_context'):
            return None
        epoch = getattr(env, '_connection_epoch', None)
        if await asyncio.wait_for(env._refresh(), 2) is False or epoch != getattr(env, '_connection_epoch', None):
            raise RuntimeError('Reference observation unavailable')
        return copy.deepcopy(env.state.get('references'))

    def on_user_state(self, event):
        if event.new_state == 'speaking':
            self._speech_reference = None
            self._speech_item = None
            return
        if getattr(event, 'old_state', None) != 'speaking' or event.new_state == 'speaking':
            return
        self._begin_reference_capture()

    def _begin_reference_capture(self):
        task = asyncio.create_task(self._capture_references())
        self._speech_reference = (time.monotonic(), task)
        self._speech_item = None
        self._reference_tasks.add(task)
        def finished(t):
            self._reference_tasks.discard(t)
            if not t.cancelled():
                t.exception()  # Observed again by the matching input; do not leave an orphan warning.
        task.add_done_callback(finished)

    def _capabilities(self):
        """Only owner-invoked work and body actions; schemas stay out of the selection prompt."""
        env = self.runner.env
        definitions = [dict(kind='work', name=d['name'], description=d.get('description', ''),
                            arguments=copy.deepcopy(d.get('arguments', {})),
                            constraints=copy.deepcopy(d.get('constraints', {})),
                            **({'preparation': copy.deepcopy(d['preparation'])} if d.get('preparation') else {}),
                            **({'handoff': copy.deepcopy(d['handoff'])} if d.get('handoff') else {}),
                            interpretation=d.get('interpretation', ''))
                       for d in (env.profile.get('work') or {}).get('capabilities', [])]
        for fn in getattr(env, 'tools', []):
            if getattr(env, 'meta', {}).get(fn.id, {}).get('ciel/role') != 'act':
                continue
            schema = copy.deepcopy(fn.info.raw_schema)
            schema['parameters']['additionalProperties'] = False
            definitions.append(dict(kind='tool', name=fn.id, description=schema.get('description', ''),
                                    arguments=schema['parameters'],
                                    reference_argument=env.meta[fn.id].get('ciel/reference_argument'),
                                    target_binding=copy.deepcopy(env.meta[fn.id].get('ciel/target_binding')),
                                    examples=copy.deepcopy(env.meta[fn.id].get('ciel/triggers', [])[:3])))
        return {str(i): d for i, d in enumerate(definitions, 1)}

    async def _stop(self):
        self._draft = None
        if self.runner.body_step():
            return await self.runner.stop()
        env = self.runner.env
        name = env.profile.get('stop_tool')
        if env.playing() and name and getattr(env, 'meta', {}).get(name, {}).get('ciel/stops'):
            result = await env.use(name, {})
            if not result.get('message') and result.get('status') in ('stopped', 'stopping'):
                result = {**result, 'message': '停止しました。' if result['status'] == 'stopped'
                          else '停止を依頼しました。停止の確認を待っています。'}
            return result
        return await self.runner.stop()

    def on_transcribed(self, event, owner=True):
        if not owner:
            self._draft = None
        item_id = getattr(event, 'item_id', None)
        if owner and item_id and getattr(event, 'is_final', False) and not STOP.fullmatch(event.transcript.strip()):
            if (not self._speech_reference or time.monotonic()-self._speech_reference[0] >= 10
                    or self._speech_item not in (None, item_id)):
                self._begin_reference_capture()
            captured_at, task = self._speech_reference
            if time.monotonic()-captured_at < 10:
                self._speech_item = item_id
                self._reference_items[item_id] = (task, getattr(self.runner.env, '_connection_epoch', None))
                while len(self._reference_items)>16:
                    del self._reference_items[next(iter(self._reference_items))]
        if owner and getattr(event, 'is_final', False) and STOP.fullmatch(event.transcript.strip()):
            self._generation += 1
            self._fast_stop = asyncio.create_task(self._stop())

    async def handle(self, item):
        async with self._lock:
            key = item.id
            if key in self._items:
                return self._items[key]
            result = await self._handle(item.text_content or '', key)
            self._items[key] = result
            if len(self._items) > 128:
                del self._items[next(iter(self._items))]
            return result

    async def _infer(self, payload, started):
        if payload['stage']=='arguments':
            # Intent and ownership are checked outside argument generation.
            payload={k:v for k,v in payload.items()if k not in ('current','body')}
            payload['capability']={k:v for k,v in payload['capability'].items()
                if k in ('kind','name','arguments','constraints','interpretation','reference_argument','target_ids')}
        if 'current'in payload:
            payload={**payload,'current':{k:v for k,v in payload['current'].items()
                if k in ('state','capability','message','decision','remaining_ms','reason','status')}}
        if 'body' in payload:
            # Completed command arguments are not the destination of a new request.
            payload = {**payload, 'body': {k: bool(v) for k, v in payload['body'].items() if k in ('current','pending','blocked')}}
        if payload['stage'] == 'arguments':
            payload = {**payload, 'required_operation': 'submit' if payload['capability']['kind'] == 'work' else 'execute'}
        request = uuid.uuid4().hex
        began = time.monotonic()
        remaining = max(.1, 20 - (began - started))
        content = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        instructions=self.select_instructions if payload['stage']=='select'else self.instructions
        if payload['stage']=='select'and payload.get('draft'):
            instructions+='\n'+self.draft_instructions
        debug_log.record('work_inference', id=request, model=models.model('mind'),
                         stage=payload['stage'], input_chars=len(content),
                         temperature=self.LOCAL_TEMPERATURE if models.is_local('mind')else None)
        try:
            options = models.options('mind', model=models.model('mind'), max_completion_tokens=600, timeout=remaining,
                messages=[{'role': 'system', 'content': instructions},
                          {'role': 'user', 'content': content}])
            options['response_format']=({'type':'json_schema','json_schema':{'name':'game_decision','schema':decision_schema(payload)}}
                if models.is_local('mind') else {'type':'json_object'})
            if models.is_local('mind'):options['temperature']=self.LOCAL_TEMPERATURE
            response = await asyncio.wait_for(self._client.chat.completions.create(**options), remaining)
            models.record('mind', models.model('mind'), getattr(response, 'usage', None))
            action = json.loads(response.choices[0].message.content or '')
            if not isinstance(action, dict):
                raise ValueError('Expected object')
            debug_log.record('work_decision', stage=payload['stage'], operation=action.get('operation'),
                             capability=action.get('capability'))
            return action
        finally:
            debug_log.record('model_response', role='game_intake', stage=payload['stage'], id=request,
                             seconds=round(time.monotonic()-began, 3))

    async def _handle(self, text, request_id):
        generation = self._generation
        if not self.authorized():
            return None
        if STOP.fullmatch(text.strip()):
            fast, self._fast_stop = self._fast_stop, None
            r = await fast if fast is not None else await self._stop()
            return r.get('message') or '停止を確認できません。'
        env = self.runner.env
        if not env.playing():
            return None
        if self._client is None:
            self._client = models.create_client('mind')
        started = time.monotonic()
        self._current_item = request_id
        epoch = getattr(env, '_connection_epoch', None)
        draft = self._draft
        source = None
        draft_revision = 1
        selected_variant = None
        confirmed_request = False
        if draft and (draft['expires'] <= started or draft['epoch'] != epoch):
            self._draft = draft = None
        # Capture once before model selection. Later pointer changes cannot retarget this request.
        references = None
        if env.profile.get('reference_context'):
            try:
                capture = self._reference_items.pop(request_id, None)
                if capture:
                    task, capture_epoch = capture
                    references = await task
                    if capture_epoch != getattr(env, '_connection_epoch', None):
                        raise RuntimeError('Reference connection changed')
                else:
                    references = await self._capture_references()
            except Exception:
                return '指し示した対象の状態を確認できませんでした。'
        definitions = self._capabilities()
        targets = TargetCandidates(request_id, text, references, definitions)
        exposed = targets.definitions
        complete_coordinates={'x','y','z'}<={m['axis']for m in targets.mentions}
        # Bound targets replace raw references on the new contract; other games keep
        # their existing opaque reference contract.
        model_references = None if targets.bindings else references
        epoch = getattr(env, '_connection_epoch', None)
        try:
            action = await self._infer({'stage': 'select', 'input': text,
                'capabilities': [{'id': i, 'description': d['description'],
                                  **({'reference_argument': d['reference_argument']} if d.get('reference_argument') else {}),
                                  **({'target_ids': d['target_ids']} if 'target_ids' in d and not definitions[i].get('preparation') else {}),
                                  **({'variants': available_variants(definitions[i],targets.mentions,targets.role_candidates.get(i))}
                                     if definitions[i].get('preparation',{}).get('variants') else {}),
                                  **({'examples': d['examples']} if d.get('examples') else {})}
                                 for i, d in exposed.items() if d.get('target_ids') != []],
                'current': self.runner.status(), 'body': getattr(env, '_body', {}),
                'targets': targets.targets, 'references': model_references,
                **({'draft': {'input': draft['text'], 'question': draft['question'],
                    'capability':draft.get('capability'),'variant':draft.get('variant')}} if draft and not complete_coordinates else {}),
                **({'previous_request': self._previous['text']} if self._previous and self._previous['epoch'] == epoch and not complete_coordinates else {})}, started)
            selected = None
            if action.get('operation') == 'select':
                selected = action.get('capability')
                selected_variant = action.get('variant')
                if not isinstance(selected, str) or selected not in definitions:
                    raise ValueError('Unknown capability')
                definition = definitions[selected]
                source = draft if action.get('draft_action') == 'continue' else self._previous if action.get('draft_action') == 'repeat' else None
                if action.get('draft_action') in ('continue', 'repeat'):
                    if not source or source['epoch'] != epoch:
                        return '引き継ぐ依頼を確認できません。範囲と材料を指定してください。'
                    if action['draft_action']=='repeat' and source.get('spec'):
                        references={'source':'previous_work','confirmed_spec':copy.deepcopy(source['spec']),'summary':source.get('summary','')}
                    else:
                        text = source['text'] + '\n補足：' + text if action['draft_action'] == 'continue' else source['text']
                        references = copy.deepcopy(source['references'])
                    targets = TargetCandidates(request_id, text, references, definitions)
                    exposed = targets.definitions
                    if source is draft:
                        request_id = draft['request_id']
                        draft_revision = draft['revision'] + 1
                self._draft = None
                variants = definition.get('preparation', {}).get('variants')
                if variants:
                    variant = variants.get(action.get('variant'))
                    if variant is None:
                        return '施工の種類を確認できませんでした。'
                    confirmed_request = True
                    narrowed = copy.deepcopy(definitions)
                    narrowed[selected]['preparation'].update(intent_schema=variant['schema'], roles=variant['roles'],
                        required_axes=variant.get('required_axes',[]),required_height_mentions=variant.get('required_height_mentions',0),
                        reference_axes=variant.get('reference_axes',[]))
                    targets = TargetCandidates(request_id, text, references, narrowed)
                    exposed = targets.definitions
                model_definition = exposed[selected]
                if model_definition.get('missing_fields'):
                    labels={'block':'施工に使う材質','clear_blocks':'取り除く材質','ground/top':'残す地面と上限のY座標',
                            'coordinate_roles':'編集範囲の最終のX/Y/Z一組（保存範囲は分けて）'}
                    question='、'.join(labels.get(k,k.upper()+'座標')for k in model_definition['missing_fields'])+'を指定してください。'
                    self._draft={'text':text,'references':copy.deepcopy(references),'epoch':epoch,
                        'capability':selected,'variant':selected_variant,
                        'expires':min(started+60,source['expires']if source is draft and draft else started+60),
                        'started':source['started']if source is draft and draft else started,'question':question,
                        'request_id':request_id,'revision':draft_revision}
                    return question
                if model_definition.get('target_ids') == []:
                    return '今回の対象を特定できません。座標を一組で指定するか、指示棒で選び直してください。'
                debug_log.record('work_capability_selected', capability=definition['name'], capability_kind=definition['kind'],
                    version=hashlib.sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest()[:12])
                handoff = definition.get('handoff')
                if handoff:
                    if handoff.get('version') != 1 or definition['kind'] != 'work':
                        raise ValueError('Unsupported handoff')
                    # Intent was decided by the model. Preserve the original request,
                    # including constraints; the service owns its interpretation.
                    action = {'operation': 'submit', 'arguments': {handoff['argument']: text},
                              'constraints': copy.deepcopy(handoff['constraints']),
                              'seconds': handoff['seconds'], 'title': text[:100]}
                else:
                    action = await self._infer({'stage': 'arguments', 'input': text, 'id': selected,
                        'confirmed_request':confirmed_request,
                        'capability': model_definition, 'current': self.runner.status(), 'body': getattr(env, '_body', {}),
                        'targets': targets.targets,
                        'references': model_references if definition.get('reference_argument') else None}, started)
        except (ValueError, TypeError, KeyError, asyncio.TimeoutError):
            return '依頼の操作を確認できませんでした。'
        except Exception as e:
            debug_log.record('game_intake_error', error=type(e).__name__)
            return '作業の依頼を確認できませんでした。'
        op = action.get('operation')
        if generation != self._generation or not self.authorized():
            return '依頼の確認中に中止の指示があったため、作業を開始しませんでした。'
        if op == 'none':
            self._draft = None
            return None
        if op == 'clarify':
            question = str(action.get('message') or 'どの作業をするか教えてください。')[:200]
            self._draft = {'text': text, 'references': copy.deepcopy(references), 'epoch': epoch,
                           'capability':selected,'variant':selected_variant,
                           'expires': min(started + 60, source['expires'] if source is draft and draft else started + 60),
                           'started': source['started'] if source is draft and draft else started, 'question': question,
                           'request_id': request_id, 'revision': draft_revision}
            return question
        if op == 'status':
            return self.runner.status().get('message') or '今は作業中です。' if self.runner.work else '今は作業していません。'
        if op == 'cancel':
            r = await self._stop()
        elif op == 'answer' and action.get('action') in ('retry', 'cancel'):
            r = await self.runner.answer(action.get('decision_id'), action['action'])
        elif op == 'answer' and action.get('action') == 'reply':
            r = await self.runner.answer(action.get('decision_id'), 'reply', str(action.get('message') or text)[:2000])
        elif op == 'tell':
            r = await self.runner.tell(str(action.get('message') or text)[:2000])
        elif op in ('submit', 'execute') and selected is not None:
            # A delayed model response cannot acquire a new connection or changed definition.
            current = self._capabilities()
            if (not env.playing() or epoch != getattr(env, '_connection_epoch', None)
                    or current.get(selected) != definition):
                return '能力の状態が変わったため、操作を開始しませんでした。'
            if self.runner.body_step():
                return '今の作業を中止してから、新しい操作を依頼してください。'
            expected = 'submit' if definition['kind'] == 'work' else 'execute'
            def clarify_spec():
                question='施工範囲と保存範囲を区別して、最終の座標一組を指定してください。'
                self._draft={'text':text,'references':copy.deepcopy(references),'epoch':epoch,
                    'capability':selected,'variant':selected_variant,
                    'expires':min(started+60,draft['expires']if source is draft and draft else started+60),
                    'started':draft['started']if source is draft and draft else started,'question':question,
                    'request_id':request_id,'revision':draft_revision}
                return question
            for attempt in range(2):
                try:
                    if (action.get('operation') != expected
                            or action.get('capability', selected) not in (selected, definition['name'])):
                        raise ValueError('Wrong operation')
                    jsonschema.validate(action.get('arguments'), model_definition['arguments'])
                    resolved = targets.resolve(selected, action['arguments'])
                    if not definition.get('preparation'):
                        jsonschema.validate(resolved, definition['arguments'])
                    if expected == 'submit':
                        jsonschema.validate(action.get('constraints'), definition['constraints'])
                    break
                except (ValueError, jsonschema.ValidationError):
                    if attempt or time.monotonic() - started >= 15:
                        return clarify_spec()if definition.get('preparation')else '操作の引数を確認できませんでした。'
                    try:
                        action = await self._infer({'stage': 'arguments', 'input': text, 'id': selected,
                            'confirmed_request':confirmed_request,
                            'capability': model_definition, 'current': self.runner.status(),
                            'targets': targets.targets,
                            'references': model_references if definition.get('reference_argument') else None,
                            'correction': '引数と制約のschemaに従う。定義にない項目・不要な空配列・同じ候補の二重使用を追加しない。'}, started)
                    except (ValueError, TypeError, KeyError, asyncio.TimeoutError):
                        return clarify_spec()if definition.get('preparation')else '操作の引数を確認できませんでした。'
            if (generation != self._generation or not self.authorized() or not env.playing() or self.runner.body_step()
                    or epoch != getattr(env, '_connection_epoch', None) or self._capabilities().get(selected) != definition):
                return '操作の確認中に状態が変わったため、開始しませんでした。'
            if expected == 'execute':
                ref_arg = getattr(env, 'meta', {}).get(definition['name'], {}).get('ciel/reference_argument')
                if ref_arg and (not references or resolved.get(ref_arg) != references.get('selection_id')):
                    return '指し示した対象を確認できません。指示棒で選び直してください。'
                r = await env.use(definition['name'], resolved)
            else:
                seconds = action.get('seconds', 90)
                if type(seconds) is not int or not 1 <= seconds <= 120:
                    return '作業の条件を確認できませんでした。'
                origin = draft['started'] if draft and source is draft else started
                remaining = seconds - (time.monotonic() - origin)
                if remaining < 5:
                    return '依頼の確認に時間がかかったため、作業を開始しませんでした。'
                if definition.get('preparation'):
                    prep = definition['preparation']
                    if prep.get('version') != 1 or not prep.get('tool'):
                        return '施工の準備方式に対応していません。サービスの更新が必要です。'
                    if source is draft and draft and time.monotonic() >= draft['expires']:
                        return '確認待ちの有効期限が切れました。範囲と材料を改めて指定してください。'
                    try:
                        r = await asyncio.wait_for(env.use(prep['tool'], {
                            'request_id': request_id, 'draft_revision': draft_revision, 'spec': resolved}), max(.1, min(6, remaining)))
                    except Exception:
                        return '施工の準備状態を確認できないため、開始していません。'
                    if (generation != self._generation or not self.authorized() or epoch != getattr(env, '_connection_epoch', None)
                            or self._capabilities().get(selected) != definition):
                        return '準備中に状態が変わったため、作業を開始しませんでした。'
                    if r.get('status') != 'ready' or not r.get('plan_id'):
                        if r.get('status') == 'needs_clarification':
                            question = str(r.get('message') or '施工の範囲と条件を改めて指定してください。')[:200]
                            self._draft = {'text': text, 'references': copy.deepcopy(references), 'epoch': epoch,
                                'capability':selected,'variant':selected_variant,
                                'expires': min(started + 60, draft['expires'] if source is draft and draft else started + 60),
                                'started': origin, 'question': question, 'request_id': request_id, 'revision': draft_revision}
                            return question
                        reason = r.get('reason', 'preparation_error')
                        why = env.profile.get('reasons', {}).get(reason, reason)
                        debug_log.record('work_preparation_refused', reason=reason)
                        return r.get('message') or f'施工を開始していません。{why}。'
                    resolved = {prep['result_argument']: r['plan_id']}
                    remaining = seconds - (time.monotonic() - origin)
                    if remaining < 5:
                        return '施工の確認に時間がかかったため、開始していません。'
                    self._previous = {'text': text, 'references': copy.deepcopy(references), 'epoch': epoch,
                                      'spec':copy.deepcopy(r.get('spec')), 'summary':r.get('summary','')}
                r = await self.runner.start(definition['name'], resolved, constraints=action['constraints'],
                    title=str(action.get('title') or '')[:100], seconds=remaining, request_id=request_id)
        else:
            return '作業の依頼を確認できませんでした。'
        return r.get('message') or ('操作を受け付けました。' if r.get('task_id') or r.get('status') in ('started', 'accepted')
                                   else '操作を受け付けられませんでした。')

    async def close(self):
        self._draft = self._previous = None
        for task in self._reference_tasks:
            task.cancel()
        await asyncio.gather(*self._reference_tasks, return_exceptions=True)
        if self._client is not None:
            await self._client.close()
