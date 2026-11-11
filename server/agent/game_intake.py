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

STOP = re.compile(r'^(?:今の作業を)?(?:止まって|止めて|やめて|待って|中止して)(?:ください)?[。！!、\s]*(?:(?:その場で待ってください|こちらが頼むまで再開しないでください)[。\s、]*)*$')


class GameIntake:
    def __init__(self, runner, instructions, *, client=None, authorized=lambda: True):
        self.runner, self.instructions, self._client = runner, instructions, client
        self.authorized = authorized
        self._items = {}
        self._lock = asyncio.Lock()
        self._fast_stop = None
        self._generation = 0
        self._speech_reference = None
        self._reference_items = {}
        self._reference_tasks = set()

    async def _capture_references(self):
        env = self.runner.env
        if not env.playing() or not env.profile.get('reference_context'):
            return None
        if await asyncio.wait_for(env._refresh(), 2) is False:
            raise RuntimeError('Reference observation unavailable')
        return copy.deepcopy(env.state.get('references'))

    def on_user_state(self, event):
        if event.new_state == 'speaking':
            self._speech_reference = None
            return
        if getattr(event, 'old_state', None) != 'speaking' or event.new_state == 'speaking':
            return
        self._begin_reference_capture()

    def _begin_reference_capture(self):
        task = asyncio.create_task(self._capture_references())
        self._speech_reference = (time.monotonic(), task)
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
                                    examples=copy.deepcopy(env.meta[fn.id].get('ciel/triggers', [])[:3])))
        return {str(i): d for i, d in enumerate(definitions, 1)}

    async def _stop(self):
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
        item_id = getattr(event, 'item_id', None)
        if owner and item_id and getattr(event, 'is_final', False) and not STOP.fullmatch(event.transcript.strip()):
            if not self._speech_reference or time.monotonic()-self._speech_reference[0] >= 10:
                self._begin_reference_capture()
            captured_at, task = self._speech_reference
            if time.monotonic()-captured_at < 10:
                self._reference_items[item_id] = task
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
        if 'body' in payload:
            # Completed command arguments are not the destination of a new request.
            payload = {**payload, 'body': {k: v for k, v in payload['body'].items() if k != 'last'}}
        if payload['stage'] == 'arguments':
            payload = {**payload, 'required_operation': 'submit' if payload['capability']['kind'] == 'work' else 'execute'}
        request = uuid.uuid4().hex
        began = time.monotonic()
        remaining = max(.1, 20 - (began - started))
        content = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        debug_log.record('work_inference', id=request, model=models.model('mind'),
                         stage=payload['stage'], input_chars=len(content))
        try:
            options = models.options('mind', model=models.model('mind'), max_completion_tokens=600, timeout=remaining,
                messages=[{'role': 'system', 'content': self.instructions}, {'role': 'user', 'content': content}])
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
        # Capture once before model selection. Later pointer changes cannot retarget this request.
        references = None
        if env.profile.get('reference_context'):
            try:
                capture = self._reference_items.pop(request_id, None)
                references = await capture if capture else await self._capture_references()
            except Exception:
                return '指し示した対象の状態を確認できませんでした。'
        definitions = self._capabilities()
        epoch = getattr(env, '_connection_epoch', None)
        try:
            action = await self._infer({'stage': 'select', 'input': text,
                'capabilities': [{'id': i, 'description': d['description'],
                                  **({'reference_argument': d['reference_argument']} if d.get('reference_argument') else {}),
                                  **({'examples': d['examples']} if d.get('examples') else {})}
                                 for i, d in definitions.items()],
                'current': self.runner.status(), 'body': getattr(env, '_body', {}), 'references': references}, started)
            selected = None
            if action.get('operation') == 'select':
                selected = action.get('capability')
                if not isinstance(selected, str) or selected not in definitions:
                    raise ValueError('Unknown capability')
                definition = definitions[selected]
                debug_log.record('work_capability_selected', capability=definition['name'], capability_kind=definition['kind'],
                    version=hashlib.sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest()[:12])
                action = await self._infer({'stage': 'arguments', 'input': text, 'id': selected,
                    'capability': definition, 'current': self.runner.status(), 'body': getattr(env, '_body', {}),
                    'references': references if definition.get('reference_argument') else None}, started)
        except (ValueError, TypeError, KeyError, asyncio.TimeoutError):
            return '依頼の操作を確認できませんでした。'
        except Exception as e:
            debug_log.record('game_intake_error', error=type(e).__name__)
            return '作業の依頼を確認できませんでした。'
        op = action.get('operation')
        if generation != self._generation or not self.authorized():
            return '依頼の確認中に中止の指示があったため、作業を開始しませんでした。'
        if op == 'none':
            return None
        if op == 'clarify':
            return str(action.get('message') or 'どの作業をするか教えてください。')[:200]
        if op == 'status':
            return self.runner.status().get('message') or '今は作業中です。' if self.runner.work else '今は作業していません。'
        if op == 'cancel':
            r = await self._stop()
        elif op == 'answer' and action.get('action') in ('retry', 'cancel'):
            r = await self.runner.answer(action.get('decision_id'), action['action'])
        elif op in ('submit', 'execute') and selected is not None:
            # A delayed model response cannot acquire a new connection or changed definition.
            current = self._capabilities()
            if (not env.playing() or epoch != getattr(env, '_connection_epoch', None)
                    or current.get(selected) != definition):
                return '能力の状態が変わったため、操作を開始しませんでした。'
            if self.runner.body_step():
                return '今の作業を中止してから、新しい操作を依頼してください。'
            expected = 'submit' if definition['kind'] == 'work' else 'execute'
            for attempt in range(2):
                try:
                    if (action.get('operation') != expected
                            or action.get('capability', selected) not in (selected, definition['name'])):
                        raise ValueError('Wrong operation')
                    jsonschema.validate(action.get('arguments'), definition['arguments'])
                    if expected == 'submit':
                        jsonschema.validate(action.get('constraints'), definition['constraints'])
                    break
                except (ValueError, jsonschema.ValidationError):
                    if attempt or time.monotonic() - started >= 15:
                        return '操作の引数を確認できませんでした。'
                    try:
                        action = await self._infer({'stage': 'arguments', 'input': text, 'id': selected,
                            'capability': definition, 'current': self.runner.status(),
                            'references': references if definition.get('reference_argument') else None,
                            'correction': '引数と制約のschemaに従い、必須項目をすべて指定する。'}, started)
                    except (ValueError, TypeError, KeyError, asyncio.TimeoutError):
                        return '操作の引数を確認できませんでした。'
            if (generation != self._generation or not self.authorized() or not env.playing() or self.runner.body_step()
                    or epoch != getattr(env, '_connection_epoch', None) or self._capabilities().get(selected) != definition):
                return '操作の確認中に状態が変わったため、開始しませんでした。'
            if expected == 'execute':
                ref_arg = getattr(env, 'meta', {}).get(definition['name'], {}).get('ciel/reference_argument')
                if ref_arg and (not references or action['arguments'].get(ref_arg) != references.get('selection_id')):
                    return '指し示した対象を確認できません。指示棒で選び直してください。'
                r = await env.use(definition['name'], action['arguments'])
            else:
                seconds = action.get('seconds', 90)
                if type(seconds) is not int or not 1 <= seconds <= 120:
                    return '作業の条件を確認できませんでした。'
                remaining = seconds - (time.monotonic() - started)
                if remaining < 5:
                    return '依頼の確認に時間がかかったため、作業を開始しませんでした。'
                r = await self.runner.start(definition['name'], action['arguments'], constraints=action['constraints'],
                    title=str(action.get('title') or '')[:100], seconds=remaining, request_id=request_id)
        else:
            return '作業の依頼を確認できませんでした。'
        return r.get('message') or ('操作を受け付けました。' if r.get('task_id') or r.get('status') in ('started', 'accepted')
                                   else '操作を受け付けられませんでした。')

    async def close(self):
        for task in self._reference_tasks:
            task.cancel()
        await asyncio.gather(*self._reference_tasks, return_exceptions=True)
        if self._client is not None:
            await self._client.close()
