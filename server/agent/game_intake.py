"""One work decision per user item; independent of the voice pipeline and game planner."""
import asyncio
import json
import re
import time
import uuid
import debug_log
import models

STOP = re.compile(r'^(?:今の作業を)?(?:止まって|止めて|やめて|待って|中止して)(?:ください)?[。！!、\s]*(?:(?:その場で待ってください|こちらが頼むまで再開しないでください)[。\s、]*)*$')


class GameIntake:
    def __init__(self, runner, instructions, *, client=None):
        self.runner, self.instructions, self._client = runner, instructions, client
        self._items = {}
        self._lock = asyncio.Lock()
        self._fast_stop = None
        self._generation = 0

    def on_transcribed(self, event, owner=True):
        if owner and getattr(event, 'is_final', False) and STOP.fullmatch(event.transcript.strip()):
            self._generation += 1
            self._fast_stop = asyncio.create_task(self.runner.stop())

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

    async def _handle(self, text, request_id, *, repair=None, began=None, generation=None):
        generation = self._generation if generation is None else generation
        if STOP.fullmatch(text.strip()):
            fast, self._fast_stop = self._fast_stop, None
            r = await fast if fast is not None else await self.runner.stop()
            return r.get('message') or '停止を確認できません。'
        env = self.runner.env
        if not env.playing():
            return None
        if self._client is None:
            self._client = models.create_client('mind')
        started = time.monotonic() if began is None else began
        request = uuid.uuid4().hex
        generation_started = time.monotonic()
        debug_log.record('work_inference', id=request, model=models.model('mind'))
        try:
            options = models.options('mind', model=models.model('mind'), max_completion_tokens=600, timeout=20,
                messages=[{'role': 'system', 'content': self.instructions}, {'role': 'user', 'content': json.dumps({
                    'input': text, 'capabilities': (env.profile.get('work') or {}).get('capabilities', []),
                    'current': self.runner.status(), 'correction': repair}, ensure_ascii=False)}])
            response = await asyncio.wait_for(self._client.chat.completions.create(**options), max(.1, 20 - (time.monotonic() - started)))
            models.record('mind', models.model('mind'), getattr(response, 'usage', None))
            action = json.loads(response.choices[0].message.content or '')
            if not isinstance(action, dict):
                raise ValueError('Expected object')
        except (ValueError, TypeError, KeyError, asyncio.TimeoutError):
            return '作業の依頼を確認できませんでした。対象と数を教えてください。'
        except Exception as e:
            debug_log.record('game_intake_error', error=type(e).__name__)
            return '作業の依頼を確認できませんでした。'
        finally:
            debug_log.record('model_response', role='game_intake', id=request, seconds=round(time.monotonic()-generation_started, 3))
        op = action.get('operation')
        debug_log.record('work_decision', operation=op, capability=action.get('capability'))
        if generation != self._generation:
            return '依頼の確認中に中止の指示があったため、作業を開始しませんでした。'
        if op == 'none':
            return None
        if op == 'clarify':
            return str(action.get('message') or 'どの作業をするか教えてください。')[:200]
        if op == 'status':
            return self.runner.status().get('message') or '今は作業中です。' if self.runner.work else '今は作業していません。'
        if op == 'cancel':
            r = await self.runner.stop()
        elif op == 'answer' and action.get('action') in ('retry', 'cancel'):
            r = await self.runner.answer(action.get('decision_id'), action['action'])
        elif op == 'submit':
            seconds = action.get('seconds', 90)
            if type(seconds) is not int or not 1 <= seconds <= 120 or not isinstance(action.get('arguments'), dict) or not isinstance(action.get('constraints'), dict):
                return '作業の条件を確認できませんでした。'
            remaining = seconds - (time.monotonic() - started)
            if remaining < 5:
                return '依頼の確認に時間がかかったため、作業を開始しませんでした。'
            r = await self.runner.start(action.get('capability'), action['arguments'], constraints=action['constraints'],
                title=str(action.get('title') or '')[:100], seconds=remaining, request_id=request_id)
            if r.get('reason') == 'invalid_request' and repair is None and time.monotonic() - started < 15:
                return await self._handle(text, request_id, repair={'previous': action,
                    'error': 'invalid_request: 能力の引数と制約のschemaを確認し、必須項目をすべて指定して修正する。'},
                    began=started, generation=generation)
        else:
            return '作業の依頼を確認できませんでした。'
        return r.get('message') or ('作業を受け付けました。' if r.get('task_id') else '作業を受け付けられませんでした。')

    async def close(self):
        if self._client is not None:
            await self._client.close()
