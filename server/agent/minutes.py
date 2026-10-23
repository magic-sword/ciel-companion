# -*- coding: utf-8 -*-
"""会話のまとめをとる（会議の議事録・目標と計画・調べもののまとめ など。会話を止めない）。

- まとめの種類はテンプレート（config/summaries/。summaries/templates.py）。見出しは決まった種類（summaries/kinds.py）を組み合わせる。
- 始めと終わりは 3 つの口から：アプリ（topic ciel.minutes）と管理用のコマンド（minutes_admin.py）、
  声で頼まれたときは会話モデルが道具（tools/minutes.py の start_minutes・finish_minutes）を呼ぶ。
- 始めた・終えたときは on_change で知らせる。agent.py が、シエルに一言告げさせ（config/prompts/minutes_voice.md）、
  アプリへ記録中か（ciel.event の minutes.state）を送る。
- ライブ：とっているあいだ、新しい発言がたまったら（summaries/live.py）軽いモデルで差分だけを作り
  （config/prompts/minutes_live.md）、ID の付いた項目の一覧（summaries/state.py）に当てる。
  変わるたびに on_state でアプリのパネルへ今の中身を送る（ciel.summary。packets で分けて送る）。
- 清書：終えたら、強いモデル（既定 gpt-5.4、CIEL_MINUTES_MODEL）が、ライブの一覧と発言から下書きに仕上げる
  （config/prompts/minutes.md）。発言が全部残っていて多すぎなければ全部を見直し、多ければ続きだけを合わせる。
- 共通履歴（conversation.py）の開始・終了 ID と処理位置を持つ。独自の全文は持たない。
- 下書きは Discord の Webhook（CIEL_MINUTES_DISCORD_WEBHOOK。利用者だけが見るチャンネル）へ送る（summaries/export.py）。
  自動で共有先へは出さない：利用者が確かめてから共有する（聞き間違い・外に出したくない発言が混ざることがあるため）。
- 送れなかったとき（Webhook が無い・失敗）だけ、下書きを data/minutes/ に保存する。
- 会話が終わるときにとっている途中なら、そこまでで終える。共通履歴は会話が終わると消える。
- ログには会話もまとめの中身も出さない（行数・文字数だけ）。決めたことは docs/decisions/meeting-minutes-ja.md。
"""
import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import openai
from livekit import rtc

import speakers
from conversation import Conversation, Turn
from jst import JST
from summaries import live
from summaries import templates as summary_templates
from summaries.export import post_discord, render_raw
from summaries.state import SummaryState, day
from summaries.templates import Template

log = logging.getLogger('ciel-agent.minutes')

TOPIC = 'ciel.minutes'
MODEL = os.environ.get('CIEL_MINUTES_MODEL', 'gpt-5.4')
WEBHOOK = os.environ.get('CIEL_MINUTES_DISCORD_WEBHOOK', '')
SAVE_DIR = Path(__file__).resolve().parent / 'data' / 'minutes'
RECENT_EXPORTS = 5
DRAFT_CACHE_CHARS = 40_000
READ_CHARS = 6000
MIN_LINES = 2           # これより少なければ、まとめにしない
FINAL_FULL_LINES = 400  # 清書で発言を全部見直す上限（これより多ければ、ライブの一覧に続きだけを合わせる）
FINAL_FULL_CHARS = 60_000
FINAL_CHUNK = 100       # 続きを合わせるとき、一度にモデルへ渡す発言の数
PART_CHARS = 2000       # アプリへ送る 1 つのデータのメッセージの文字数（LiveKit の上限に余裕を持たせる）

# on_change に渡す出来事
STARTED, ALREADY, FINISHED, NOT_RECORDING = 'started', 'already', 'finished', 'not_recording'
PAST_QUEUED, PAST_PARTIAL = 'past_queued', 'past_partial'
STARTED_EARLIER, STARTED_PARTIAL = 'started_earlier', 'started_partial'
EMPTY, BUSY, INVALID_RANGE, UNKNOWN_TEMPLATE = 'empty', 'busy', 'invalid_range', 'unknown_template'

Line = Turn


@dataclass
class Meeting:
    """1 回のまとめ（始めてから終えるまで）"""
    template: Template
    started: datetime
    first_id: int                                     # この発言 ID より後がまとめの対象
    cursor: int = -1                                  # ライブの一覧に反映した最後の発言 ID
    end_id: int | None = None
    state: SummaryState | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    timer: asyncio.Task | None = None
    closed: bool = False
    incomplete: bool = False
    snapshot: list[Line] | None = None  # 過去のまとめは依頼時の対象を固定する
    export_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    summarized_turn_count: int = 0
    stage: str = 'recording'
    ended: datetime | None = None
    draft: str | None = None
    draft_clipped: bool = False
    error: str | None = None
    updated_at: float = field(default_factory=time.monotonic)   # 前のライブの更新（time.monotonic。更新の間隔を決める）
    updated_wall: float | None = None                          # 前のライブの更新（アプリに「何秒前」と出す）
    research_seen: int = 0                                     # ライブに渡した調べた記録の最後の ID
    pending_shown: int = -1                                    # アプリに知らせた、まだ反映していない発言の数

    def __post_init__(self) -> None:
        if self.cursor < 0:
            self.cursor = self.first_id
        if self.state is None:
            self.state = SummaryState(self.template)


class Minutes:
    def __init__(self, book: speakers.SpeakerBook | None, instructions: str, history: Conversation,
                 live_instructions: str = '', templates: dict[str, Template] | None = None) -> None:
        self.book = book
        self.instructions = instructions
        self.live_instructions = live_instructions
        self.history = history
        self.templates = templates if templates is not None else summary_templates.load()
        self.meeting: Meeting | None = None   # とっていないときは None
        self.on_change: Callable[[str], None] | None = None   # 始めた・終えたとき（agent.py がつなぐ）
        self.on_state: Callable[[dict], None] | None = None   # まとめの中身が変わったとき（アプリのパネル）
        self.on_progress: Callable[[dict], None] | None = None   # まだ反映していない発言の数が変わったとき
        self._tasks: set[asyncio.Task] = set()
        self._exports: list[Meeting] = []  # この接続で作成した直近5件。終了後も結果を照会できる
        self._shown: Meeting | None = None   # アプリのパネルに出しているまとめ（終えたあとも結果を見せる）
        self._client = openai.AsyncOpenAI()

    @property
    def recording(self) -> bool:
        return self.meeting is not None

    def status(self) -> dict:
        """会話モデルへ渡す事実だけ。まとめや会話の本文は含めない。"""
        m = self.meeting
        rows = self.history.between(m.cursor) if m is not None else []
        return {
            'recording': self.recording,
            'meeting_id': m.export_id if m is not None else None,
            'template': m.template.name if m is not None else None,
            'processing': any(not t.done() for t in self._tasks),
            'started_at': m.started.isoformat() if m is not None else None,
            'summarized_turn_count': m.summarized_turn_count if m is not None else 0,
            'has_summary': m is not None and m.state.has_content(),
            'ready_turn_count': sum(t.ready.is_set() and bool(t.text) for t in rows),
            'pending_turn_count': sum(not t.ready.is_set() for t in rows),
            'incomplete': m is not None and (m.incomplete or m.first_id < self.history.dropped_through
                                           or any(t.clipped for t in rows)),
            'latest_export': self._export_status(self._exports[-1]) if self._exports else None,
            'recent_exports': [{'meeting_id': e.export_id, 'stage': e.stage} for e in self._exports],
        }

    def context(self) -> str:
        # 毎回は参照先だけ。件数・内容・送信結果は道具で同じ状態を読む。
        latest = self._exports[-1] if self._exports else None
        m = self.meeting
        return '[議事録状態]\n' + json.dumps({
            'recording': self.recording,
            'meeting_id': m.export_id if m is not None else None,
            'template': m.template.name if m is not None else None,
            'template_label': (m or latest).template.label if (m or latest) is not None else None,
            'latest_export': {'meeting_id': latest.export_id, 'stage': latest.stage} if latest else None,
        }, ensure_ascii=False)

    @staticmethod
    def _export_status(m: Meeting) -> dict:
        return {'meeting_id': m.export_id, 'template': m.template.name, 'stage': m.stage,
                'started_at': m.started.isoformat(), 'ended_at': m.ended.isoformat() if m.ended else None,
                'incomplete': m.incomplete, 'draft_available': m.draft is not None,
                'error': m.error}

    def read(self, meeting_id: str = '') -> dict:
        """本文は要求時だけ、有界で返す。新しい要約や外部への送信はしない。"""
        candidates = ([self.meeting] if self.meeting is not None else []) + list(reversed(self._exports))
        m = next((m for m in candidates if not meeting_id or m.export_id == meeting_id), None)
        if m is None:
            return {'status': 'not_found', 'scope': 'current_session', 'meeting_id': meeting_id or None}
        result = {'status': 'ok', 'scope': 'current_session', **self._export_status(m),
                  'summary_through_id': m.cursor if m.state.has_content() else None}
        if m.draft is not None:
            return {**result, 'draft': m.draft[:READ_CHARS],
                    'content_clipped': m.draft_clipped or len(m.draft) > READ_CHARS}
        summary = m.state.render(m.started, m.ended or datetime.now(JST)) if m.state.has_content() else ''
        budget = max(0, READ_CHARS - min(len(summary), READ_CHARS))
        rows = m.snapshot if m.snapshot is not None else self.history.between(m.cursor, m.end_id)
        usable = [t for t in rows if t.text or not t.ready.is_set()]
        selected = usable[-8:]
        recent = []
        for t in selected:
            if budget <= 0:
                break
            text = t.text[:min(1800, budget)] if t.ready.is_set() else ''
            recent.append({'id': t.id, 'speaker': speaker_name(t), 'text': text,
                           'pending': not t.ready.is_set(), 'text_clipped': t.clipped or len(text) < len(t.text)})
            budget -= len(text)
        return {**result, 'summary': summary[:READ_CHARS], 'recent_turns': recent,
                'unprocessed_turn_count': len(usable),
                'content_clipped': len(summary) > READ_CHARS or len(recent) < len(usable)
                                   or any(t['text_clipped'] for t in recent),
                'incomplete': m.incomplete or (m.snapshot is None and m.first_id < self.history.dropped_through)}

    # ---- アプリのパネルへ ----

    def app_state(self, m: Meeting) -> dict:
        return {'v': 1, 'type': 'summary.state', 'meeting_id': m.export_id, 'recording': m is self.meeting,
                'stage': m.stage, 'template': m.template.name, 'label': m.template.label,
                'started_at': m.started.timestamp(), 'updated_at': m.updated_wall or 0.0,
                'pending_turns': max(m.pending_shown, 0), **m.state.for_app()}

    def templates_event(self) -> dict:
        """アプリの「まとめをとる」の選び先（会話の始めに一度送る）"""
        names = [summary_templates.DEFAULT] + sorted(n for n in self.templates if n != summary_templates.DEFAULT)
        return {'v': 1, 'type': 'summary.templates',
                'templates': [{'name': n, 'label': self.templates[n].label, 'description': self.templates[n].description}
                              for n in names]}

    def _publish(self, m: Meeting) -> None:
        if self.on_state is None or (m is not self.meeting and m is not self._shown):
            return
        self._shown = m
        try:
            self.on_state(self.app_state(m))
        except Exception:
            log.exception('まとめをアプリへ送れない')

    def _progress(self, m: Meeting, pending: int) -> None:
        if pending == m.pending_shown:
            return
        m.pending_shown = pending
        if self.on_progress is not None:
            try:
                self.on_progress({'v': 1, 'type': 'summary.progress', 'meeting_id': m.export_id, 'pending_turns': pending})
            except Exception:
                log.exception('まとめの進み具合をアプリへ送れない')

    # ---- 始め・終わり ----

    def on_data(self, packet: rtc.DataPacket) -> None:
        if packet.topic != TOPIC:
            return
        try:
            msg = json.loads(packet.data.decode('utf-8'))
            action = msg['action']
        except (ValueError, KeyError, TypeError) as ex:
            log.warning('議事録のメッセージを読めない: %s', ex)
            return
        if action == 'start':
            template = msg.get('template') or summary_templates.DEFAULT
            if self.start(template=template if isinstance(template, str) else '') == UNKNOWN_TEMPLATE:
                log.warning('まとめの知らないテンプレート')
        elif action == 'finish':
            self.finish()
        elif action == 'refresh':
            self.refresh()
        else:
            log.warning('議事録の知らない操作: %s', action)

    def _changed(self, what: str) -> None:
        if self.on_change is not None:
            try:
                self.on_change(what)
            except Exception:
                log.exception('議事録の知らせを送れない')

    def start(self, lookback_minutes: int = 0, template: str = summary_templates.DEFAULT) -> str:
        if type(lookback_minutes) is not int or not 0 <= lookback_minutes <= 1440:
            return INVALID_RANGE
        if template not in self.templates:
            return UNKNOWN_TEMPLATE
        if self.meeting is not None:
            log.info('議事録：もうとっている')
            self._changed(ALREADY)
            return ALREADY
        m = self.meeting = Meeting(self.templates[template], datetime.now(JST), self.history.last_id)
        if lookback_minutes:
            cutoff = m.started.timestamp() - lookback_minutes * 60
            past = [t for t in self.history.turns if t.at >= cutoff]
            if past:
                m.started = datetime.fromtimestamp(past[0].at, JST)
                m.first_id = m.cursor = past[0].id - 1
            m.incomplete = self.history.dropped_through > 0 and (
                not self.history.turns or self.history.turns[0].at > cutoff)
        m.timer = asyncio.create_task(self._live(m))
        log.info('議事録：とり始めた（%s）', m.template.name)
        status = STARTED_PARTIAL if m.incomplete else STARTED_EARLIER if lookback_minutes else STARTED
        self._changed(status)
        self._publish(m)
        return status

    def summarize_past(self, last_minutes: int = 0, first_id: int = 0, last_id: int = 0,
                       template: str = summary_templates.DEFAULT) -> str:
        """開始し忘れた会話の下書きを作って送る。記録状態を切り替えない。"""
        if (any(type(v) is not int or v < 0 for v in (last_minutes, first_id, last_id))
                or last_minutes > 1440 or (last_minutes and (first_id or last_id))
                or (last_id and (last_id < first_id or last_id > self.history.last_id))
                or first_id > self.history.last_id):
            return INVALID_RANGE
        if template not in self.templates:
            return UNKNOWN_TEMPLATE
        if self.recording:
            return ALREADY
        if any(not task.done() for task in self._tasks):
            return BUSY
        ended = datetime.now(JST)
        through = last_id or self.history.last_id
        cutoff = ended.timestamp() - last_minutes * 60 if last_minutes else None
        rows = [t for t in self.history.between(max(0, first_id - 1), through)
                if (cutoff is None or t.at >= cutoff) and (t.text or not t.ready.is_set())]
        if len(rows) < MIN_LINES:
            return EMPTY
        incomplete = self.history.dropped_through > 0 and (
            (cutoff is not None and (not self.history.turns or self.history.turns[0].at > cutoff))
            or (cutoff is None and first_id <= self.history.dropped_through))
        m = Meeting(self.templates[template], datetime.fromtimestamp(rows[0].at, JST), rows[0].id - 1,
                    end_id=through, closed=True, incomplete=incomplete, snapshot=list(rows))
        self._queue_export(m, ended)
        status = PAST_PARTIAL if incomplete else PAST_QUEUED
        self._changed(status)
        return status

    def finish(self, announce: bool = True) -> str:
        m = self.meeting
        if m is None:
            log.info('議事録：とっていない')
            if announce:
                self._changed(NOT_RECORDING)
            return NOT_RECORDING
        self.meeting, m.closed = None, True
        m.end_id = self.history.last_id  # この時点で予約済みの、書き起こし待ちの発言も対象
        log.info('議事録：終了を受け付けた（終了ID %d）', m.end_id)
        if m.timer is not None and not m.lock.locked():   # ライブの更新の最中なら、終わるのを待つ（_write が lock で待つ）
            m.timer.cancel()
        self._shown = m
        self._queue_export(m, datetime.now(JST))
        if announce:
            self._changed(FINISHED)
        return FINISHED

    def refresh(self) -> None:
        """アプリの「今すぐ更新」。新しい発言が 1 つでもあれば、待たずにライブの一覧を更新する"""
        m = self.meeting
        if m is None:
            return
        task = asyncio.create_task(self._update(m, force=True))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def flush(self) -> None:
        """会話が終わるとき：とっている途中なら、そこまでで議事録にする（もう誰もいないので、告げない）"""
        self.finish(announce=False)
        await asyncio.gather(*self._tasks, return_exceptions=True)

    # ---- ライブ ----

    async def _live(self, m: Meeting) -> None:
        """とっているあいだ、新しい発言を見に行き、たまったら一覧を更新する（summaries/live.py）"""
        while not m.closed:
            await asyncio.sleep(live.LIVE_POLL_SECONDS)
            if m.closed:
                return
            try:
                await self._update(m)
            except Exception:
                log.exception('議事録：ライブの更新に失敗')

    async def _update(self, m: Meeting, force: bool = False) -> bool:
        if m.closed or m.lock.locked():
            return False
        through = self.history.settled_through()
        rows = [t for t in self.history.between(m.cursor, through) if t.text or not t.ready.is_set()]
        self._progress(m, len(rows))
        if not live.due(len(rows), time.monotonic() - m.updated_at, force):
            return False
        async with m.lock:
            if m.closed:
                return False
            lines = self.history.between(m.cursor, through)[:live.LIVE_MAX_LINES]
            m.updated_at = time.monotonic()   # 作れなかったときも、すぐには呼び直さない
            research = self._research(m, after=m.research_seen)
            result = await self._live_update(m, lines, research) if conversation(lines) else {}
            if result is None:
                return False
            changed = m.state.apply(result)
            m.summarized_turn_count += sum(bool(t.text) or not t.ready.is_set() for t in lines)
            m.incomplete |= any(not t.ready.is_set() or t.clipped for t in lines) or m.cursor < self.history.dropped_through
            m.cursor = lines[-1].id
            m.research_seen = max([r['id'] for r in research], default=m.research_seen)
            m.updated_wall = time.time()
            log.info('議事録：ライブを更新した（%d 行、変わった項目 %d）', len(lines), changed)
        pending = [t for t in self.history.between(m.cursor, self.history.settled_through()) if t.text]
        m.pending_shown = len(pending)
        self._publish(m)
        return True

    def _research(self, m: Meeting, after: int = 0) -> list[dict]:
        """このまとめを始めてから調べた記録（出典の URL は、発見の項目の出典にしてよいものとして覚える）"""
        records = [r for r in self.history.research.records
                   if r.id > after and r.status == 'completed' and r.requested_at >= m.started.timestamp()]
        for r in records:
            m.state.allowed_urls.update(s['url'] for s in r.sources)
        return [{'id': r.id, 'question': r.question, 'summary': r.summary[:1500],
                 'sources': [{'title': s['title'], 'url': s['url']} for s in r.sources]} for r in records[-5:]]

    async def _live_update(self, m: Meeting, lines: list[Line], research: list[dict]) -> dict | None:
        now = datetime.now(JST)
        request = {'date': day(m.started), 'now': f'{now:%H:%M}', 'template': m.template.for_model(),
                   'state': m.state.for_model(), 'conversation': conversation(lines),
                   **({'research': research} if research else {})}
        try:
            r = await self._client.chat.completions.create(
                model=live.LIVE_MODEL, reasoning_effort='low', response_format={'type': 'json_object'},
                messages=[{'role': 'system', 'content': self.live_instructions},
                          {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)}])
            return json.loads(r.choices[0].message.content or '{}')
        except Exception as e:   # 作れなくても、会話は続ける（次の機会か、終わりの清書に回す）
            log.warning('議事録：ライブの差分を作れない：%s', type(e).__name__)
            return None

    # ---- 清書・送る ----

    def _queue_export(self, m: Meeting, ended: datetime) -> None:
        m.ended, m.stage = ended, 'queued'
        self._exports.append(m)
        self._exports = self._exports[-RECENT_EXPORTS:]
        task = asyncio.create_task(self._export(m, ended))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        self._publish(m)

    async def _export(self, m: Meeting, ended: datetime) -> None:
        m.stage = 'building'
        self._publish(m)
        try:
            await self._write(m, ended)
        except asyncio.CancelledError:
            m.stage, m.error = 'failed', 'CancelledError'
            raise
        except Exception as e:
            m.stage, m.error = 'failed', type(e).__name__
            log.warning('議事録：作成・保存に失敗 id=%s error=%s', m.export_id, m.error)
        finally:
            m.snapshot = None
            log.info('議事録：処理結果 id=%s stage=%s', m.export_id, m.stage)
            self._publish(m)

    async def _summarize(self, started: datetime, ended: datetime, draft: dict | None, lines: list[Line],
                         template: Template | None = None, draft_through: int = 0,
                         research: list[dict] | None = None) -> dict | None:
        template = template or self.templates[summary_templates.DEFAULT]
        request = {'date': day(started), 'start': f'{started:%H:%M}', 'end': f'{ended:%H:%M}',
                   'template': template.for_model(),
                   **({'draft': draft, 'draft_through_id': draft_through} if draft else {}),
                   'conversation': conversation(lines),
                   **({'research': research} if research else {})}
        try:
            r = await self._client.chat.completions.create(
                model=MODEL, reasoning_effort='medium', response_format={'type': 'json_object'},
                messages=[{'role': 'system', 'content': self.instructions},
                          {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)}])
            return json.loads(r.choices[0].message.content or '{}')
        except Exception as e:   # 要約できなくても、会話は続ける
            log.warning('議事録を要約できない：%s', type(e).__name__)
            return None

    async def _write(self, m: Meeting, ended: datetime) -> None:
        await self.history.wait_pending(m.first_id, m.end_id)
        async with m.lock:
            research = self._research(m) if m.snapshot is None else []
            if m.snapshot is not None:
                lines, full = m.snapshot, True
            else:
                everything = self.history.between(m.first_id, m.end_id)
                # 発言が全部残っていて多すぎなければ、全部を見直す（ライブは軽いモデルの下書きなので）
                full = (m.first_id >= self.history.dropped_through and len(everything) <= FINAL_FULL_LINES
                        and sum(len(t.text) for t in everything) <= FINAL_FULL_CHARS)
                lines = everything if full else self.history.between(m.cursor, m.end_id)
            m.incomplete |= (m.snapshot is None and m.first_id < self.history.dropped_through) or any(
                not t.ready.is_set() or t.clipped or (
                    m.snapshot is not None and not t.text and t.id <= self.history.dropped_through)
                for t in lines)
            usable = [t for t in lines if t.text or not t.ready.is_set()]
            if not m.state.has_content() and len(usable) < MIN_LINES and not m.incomplete:
                m.stage = 'empty'
                log.info('議事録：発言が %d 行だけなので、議事録にしない', len(usable))
                return
            # 多すぎるときは、ライブの一覧に続きを少しずつ合わせる
            while not full and len(lines) > FINAL_CHUNK:
                result = await self._summarize(m.started, ended, m.state.for_model(), lines[:FINAL_CHUNK],
                                               m.template, m.cursor, research)
                if result is None:
                    break
                m.state.replace(result)
                m.cursor, lines = lines[FINAL_CHUNK - 1].id, lines[FINAL_CHUNK:]
            draft = m.state.for_model() if m.state.has_content() else None
            result = (await self._summarize(m.started, ended, draft, lines, m.template, m.cursor, research)
                      if lines and (full or len(lines) <= FINAL_CHUNK) else None)
            rest = [t for t in lines if t.id > m.cursor]   # ライブの一覧に入っていない発言
            if result is not None:
                m.state.replace(result)
                text = m.state.render(m.started, ended)
            elif m.state.has_content():   # 途中までの一覧に、まとめられなかった発言をそのまま足す
                text = m.state.render(m.started, ended) + (
                    render_raw(conversation(rest), heading='## まとめきれなかった発言') if conversation(rest) else '')
            else:   # 発言をそのまま下書きとして残す
                text = render_raw(conversation(lines), m.started, ended)
            log.info('議事録：%d 行 → %d 字', len(lines), len(text))
            if m.incomplete:
                text += '\n※ 書き起こし未完了または履歴の保持上限により、一部の発言が欠けています。\n'
            m.draft, m.draft_clipped = text[:DRAFT_CACHE_CHARS], len(text) > DRAFT_CACHE_CHARS
        name = f'{m.template.name}-{m.started:%Y%m%d-%H%M%S}-{m.export_id}.md'
        if WEBHOOK:
            try:
                await asyncio.to_thread(post_discord, WEBHOOK, text, name, m.template.label)
                m.stage = 'sent'
                log.info('議事録：下書きを Discord に送った')
                return
            except Exception as e:
                log.warning('議事録を Discord に送れない：%s', type(e).__name__)
        else:
            log.warning('議事録：CIEL_MINUTES_DISCORD_WEBHOOK が無い')
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        (SAVE_DIR / name).write_text(text, encoding='utf-8')
        m.stage = 'saved_locally'
        log.info('議事録：下書きを data/minutes/%s に保存した', name)


def packets(state: dict, seq: int) -> list[dict]:
    """アプリへ送るまとめの中身を、データのメッセージの大きさに収まるよう分ける（topic ciel.summary）。
    アプリは seq ごとに parts 個そろったら、つないで読む"""
    text = json.dumps(state, ensure_ascii=False)
    parts = [text[i:i + PART_CHARS] for i in range(0, len(text), PART_CHARS)] or ['']
    return [{'v': 1, 'type': 'summary.part', 'seq': seq, 'part': i, 'parts': len(parts), 'text': p}
            for i, p in enumerate(parts)]


def conversation(lines: list[Line]) -> list[dict]:
    return [{'id': t.id, 'time': f'{datetime.fromtimestamp(t.at, JST):%H:%M:%S}',
             'speaker': speaker_name(t), 'text': t.text if t.ready.is_set() else '（書き起こし未完了・内容不明）'}
            for t in lines if t.text or not t.ready.is_set()]


def speaker_name(turn: Turn) -> str:
    """まとめでの呼び名。話したあとで名乗った人は、その名前にする。名前の無い人は「参加者A」"""
    if turn.role == 'assistant':
        return 'シエル'
    if turn.speaker is None:
        return '参加者（不明）'
    return turn.name.replace('知らない人', '参加者', 1)
