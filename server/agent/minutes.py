# -*- coding: utf-8 -*-
"""会議の議事録をとる（会話を止めない）。

- 始めと終わりは 3 つの口から：アプリの「議事録」のボタンと管理用のコマンド（minutes_admin.py）は、
  LiveKit のデータのメッセージ（topic ciel.minutes）で知らせる。声で頼まれたときは、会話モデルが道具
  （tools/minutes.py の start_minutes・finish_minutes）を呼ぶ。
- 始めた・終えたときは on_change で知らせる。agent.py が、シエルに一言告げさせ（config/prompts/minutes_voice.md）、
  アプリへ今の状態（ciel.event の minutes.state）を送る。
- 共通履歴（conversation.py）の開始・終了 ID と処理位置を持つ。独自の全文は持たない。
  時刻と話者は共通履歴のものを使い、シエルの発言も入れる（感情の印と [silent] は収集時に外す）。
- 長い会議では、10 分ごと（ROLL_SECONDS）に、それまでの議事録にその後の発言を合わせて作り直し、処理位置を進める。
  共通履歴の元発言は消さず、接続中の会話検索でも参照できる。
  終わったときは、残りの発言を合わせるだけなので待ち時間が短く、文字のモデルに渡す量も増えすぎない。
- 要約は別の文字のモデル（既定 gpt-5.4、CIEL_MINUTES_MODEL）。下書きを Discord の Webhook
  （CIEL_MINUTES_DISCORD_WEBHOOK。利用者だけが見るチャンネル）へ送る。
  自動で共有先へは出さない：利用者が確かめてから共有する（聞き間違い・外に出したくない発言が混ざることがあるため）。
- 送れなかったとき（Webhook が無い・失敗）だけ、下書きを data/minutes/ に保存する。
- 会話が終わるときにとっている途中なら、そこまでで終える。共通履歴は会話が終わると消える。
- 何を書くかは config/prompts/minutes.md。ログには会話も議事録の中身も出さない（行数・文字数だけ）。
"""
import asyncio
import json
import logging
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import openai
import requests
from livekit import rtc

import speakers
from conversation import Conversation, Turn

log = logging.getLogger('ciel-agent.minutes')

TOPIC = 'ciel.minutes'
MODEL = os.environ.get('CIEL_MINUTES_MODEL', 'gpt-5.4')
WEBHOOK = os.environ.get('CIEL_MINUTES_DISCORD_WEBHOOK', '')
SAVE_DIR = Path(__file__).resolve().parent / 'data' / 'minutes'
JST = timezone(timedelta(hours=9))
WEEKDAYS = '月火水木金土日'
MIN_LINES = 2           # これより少なければ、議事録にしない
ROLL_SECONDS = float(os.environ.get('CIEL_MINUTES_ROLL_SECONDS', '600'))   # 途中の議事録を作り直す間隔
DISCORD_LIMIT = 2000    # Discord のメッセージの本文の上限（文字）

# on_change に渡す出来事
STARTED, ALREADY, FINISHED, NOT_RECORDING = 'started', 'already', 'finished', 'not_recording'
PAST_QUEUED, PAST_PARTIAL = 'past_queued', 'past_partial'
STARTED_EARLIER, STARTED_PARTIAL = 'started_earlier', 'started_partial'
EMPTY, BUSY, INVALID_RANGE = 'empty', 'busy', 'invalid_range'

Line = Turn


@dataclass
class Meeting:
    """1 回の議事録（始めてから終えるまで）"""
    started: datetime
    cursor: int
    end_id: int | None = None
    summary: dict | None = None                       # 途中までの議事録（minutes.md の JSON）
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    timer: asyncio.Task | None = None
    closed: bool = False
    incomplete: bool = False
    snapshot: list[Line] | None = None  # 過去の議事録は依頼時の対象を固定する
    export_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


class Minutes:
    def __init__(self, book: speakers.SpeakerBook | None, instructions: str, history: Conversation) -> None:
        self.book = book
        self.instructions = instructions
        self.history = history
        self.meeting: Meeting | None = None   # とっていないときは None
        self.on_change: Callable[[str], None] | None = None   # 始めた・終えたとき（agent.py がつなぐ）
        self._tasks: set[asyncio.Task] = set()
        self._client = openai.AsyncOpenAI()

    @property
    def recording(self) -> bool:
        return self.meeting is not None

    def on_data(self, packet: rtc.DataPacket) -> None:
        if packet.topic != TOPIC:
            return
        try:
            action = json.loads(packet.data.decode('utf-8'))['action']
        except (ValueError, KeyError, TypeError) as ex:
            log.warning('議事録のメッセージを読めない: %s', ex)
            return
        if action == 'start':
            self.start()
        elif action == 'finish':
            self.finish()
        else:
            log.warning('議事録の知らない操作: %s', action)

    def _changed(self, what: str) -> None:
        if self.on_change is not None:
            try:
                self.on_change(what)
            except Exception:
                log.exception('議事録の知らせを送れない')

    def start(self, lookback_minutes: int = 0) -> str:
        if type(lookback_minutes) is not int or not 0 <= lookback_minutes <= 1440:
            return INVALID_RANGE
        if self.meeting is not None:
            log.info('議事録：もうとっている')
            self._changed(ALREADY)
            return ALREADY
        m = self.meeting = Meeting(datetime.now(JST), self.history.last_id)
        if lookback_minutes:
            cutoff = m.started.timestamp() - lookback_minutes * 60
            past = [t for t in self.history.turns if t.at >= cutoff]
            if past:
                m.started = datetime.fromtimestamp(past[0].at, JST)
                m.cursor = past[0].id - 1
            m.incomplete = self.history.dropped_through > 0 and (
                not self.history.turns or self.history.turns[0].at > cutoff)
        m.timer = asyncio.create_task(self._roll(m))
        log.info('議事録：とり始めた')
        status = STARTED_PARTIAL if m.incomplete else STARTED_EARLIER if lookback_minutes else STARTED
        self._changed(status)
        return status

    def summarize_past(self, last_minutes: int = 0, first_id: int = 0, last_id: int = 0) -> str:
        """開始し忘れた会話の下書きを作って送る。記録状態を切り替えない。"""
        if (any(type(v) is not int or v < 0 for v in (last_minutes, first_id, last_id))
                or last_minutes > 1440 or (last_minutes and (first_id or last_id))
                or (last_id and (last_id < first_id or last_id > self.history.last_id))
                or first_id > self.history.last_id):
            return INVALID_RANGE
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
        m = Meeting(datetime.fromtimestamp(rows[0].at, JST), rows[0].id - 1,
                    end_id=through, closed=True, incomplete=incomplete, snapshot=list(rows))
        task = asyncio.create_task(self._write(m, ended))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
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
        if m.timer is not None and not m.lock.locked():   # 途中の議事録を作っている最中なら、終わるのを待つ（_write が lock で待つ）
            m.timer.cancel()
        t = asyncio.create_task(self._write(m, datetime.now(JST)))
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        if announce:
            self._changed(FINISHED)
        return FINISHED

    async def flush(self) -> None:
        """会話が終わるとき：とっている途中なら、そこまでで議事録にする（もう誰もいないので、告げない）"""
        self.finish(announce=False)
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _roll(self, m: Meeting) -> None:
        """とっているあいだ、ROLL_SECONDS ごとに、途中までの議事録にその後の発言を合わせて作り直す"""
        while True:
            await asyncio.sleep(ROLL_SECONDS)
            async with m.lock:
                if m.closed:
                    return
                through = self.history.settled_through()
                m.incomplete |= m.cursor < self.history.dropped_through
                while not m.closed:
                    lines = self.history.between(m.cursor, through)[:100]
                    if len(lines) < MIN_LINES:
                        break
                    result = await self._summarize(m.started, datetime.now(JST), m.summary, lines)
                    if result is None:   # 作れなかったら次の機会（か終わり）に回す
                        break
                    m.summary = result
                    m.incomplete |= any(not t.ready.is_set() or t.clipped for t in lines)
                    m.cursor = lines[-1].id
                    log.info('議事録：途中までをまとめた（%d 行）', len(lines))
            if m.closed:
                return

    async def _summarize(self, started: datetime, ended: datetime, previous: dict | None, lines: list[Line]) -> dict | None:
        request = {'date': day(started), 'start': f'{started:%H:%M}', 'end': f'{ended:%H:%M}',
                   **({'previous': previous} if previous else {}),
                   'conversation': conversation(lines)}
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
        await self.history.wait_pending(m.cursor, m.end_id)
        async with m.lock:
            lines = m.snapshot if m.snapshot is not None else self.history.between(m.cursor, m.end_id)
            m.incomplete |= (m.snapshot is None and m.cursor < self.history.dropped_through) or any(
                not t.ready.is_set() or t.clipped or (
                    m.snapshot is not None and not t.text and t.id <= self.history.dropped_through)
                for t in lines)
            if m.summary is None and len(lines) < MIN_LINES and not m.incomplete:
                log.info('議事録：発言が %d 行だけなので、議事録にしない', len(lines))
                return
            # 長い会議の終了時も、一度にモデルへ渡す量を抑える。
            while len(lines) > 100:
                result = await self._summarize(m.started, ended, m.summary, lines[:100])
                if result is None:
                    break
                m.summary, m.cursor = result, lines[99].id
                lines = lines[100:]
            result = (await self._summarize(m.started, ended, m.summary, lines)
                      if 0 < len(lines) <= 100 else m.summary if not lines else None)
            if result is not None:
                text = render(result, m.started, ended)
            elif m.summary is not None:   # 途中までの議事録に、まとめられなかった発言をそのまま足す
                text = render(m.summary, m.started, ended) + render_raw(conversation(lines), heading='## まとめきれなかった発言')
            else:   # 発言をそのまま下書きとして残す
                text = render_raw(conversation(lines), m.started, ended)
            log.info('議事録：%d 行 → %d 字', len(lines), len(text))
            if m.incomplete:
                text += '\n※ 書き起こし未完了または履歴の保持上限により、一部の発言が欠けています。\n'
        name = f'minutes-{m.started:%Y%m%d-%H%M%S}-{m.export_id}.md'
        if WEBHOOK:
            try:
                await asyncio.to_thread(post_discord, WEBHOOK, text, name)
                log.info('議事録：下書きを Discord に送った')
                return
            except Exception as e:
                log.warning('議事録を Discord に送れない：%s', type(e).__name__)
        else:
            log.warning('議事録：CIEL_MINUTES_DISCORD_WEBHOOK が無い')
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        (SAVE_DIR / name).write_text(text, encoding='utf-8')
        log.info('議事録：下書きを data/minutes/%s に保存した', name)


def conversation(lines: list[Line]) -> list[dict]:
    return [{'id': t.id, 'time': f'{datetime.fromtimestamp(t.at, JST):%H:%M:%S}',
             'speaker': speaker_name(t), 'text': t.text if t.ready.is_set() else '（書き起こし未完了・内容不明）'}
            for t in lines if t.text or not t.ready.is_set()]


def day(at: datetime) -> str:
    """2026-10-16（金）の形（コンテナのロケールでは %a が英語になるので）"""
    return f'{at:%Y-%m-%d}（{WEEKDAYS[at.weekday()]}）'


def speaker_name(turn: Turn) -> str:
    """議事録での呼び名。話したあとで名乗った人は、その名前にする。名前の無い人は「参加者A」"""
    if turn.role == 'assistant':
        return 'シエル'
    if turn.speaker is None:
        return '参加者（不明）'
    return turn.name.replace('知らない人', '参加者', 1)


def render(result: dict, started: datetime, ended: datetime) -> str:
    """要約の JSON（config/prompts/minutes.md の形）を、Discord で読める Markdown にする"""
    def items(key: str) -> list[str]:
        return [s.strip() for s in result.get(key, []) if isinstance(s, str) and s.strip()]

    title = str(result.get('title') or '会議').strip()
    out = [f'# {title}', f'{day(started)} {started:%H:%M}〜{ended:%H:%M}']
    if attendees := items('attendees'):
        out.append('参加者：' + '、'.join(attendees))
    if summary := str(result.get('summary') or '').strip():
        out += ['', '## 概要', summary]
    topics = [t for t in result.get('topics', []) if isinstance(t, dict) and t.get('title')]
    if topics:
        out += ['', '## 話したこと']
        for t in topics:
            out.append(f'### {t["title"]}')
            out += [f'- {p}' for p in t.get('points', []) if isinstance(p, str) and p.strip()]
    if decisions := items('decisions'):
        out += ['', '## 決まったこと', *(f'- {d}' for d in decisions)]
    actions = [a for a in result.get('action_items', []) if isinstance(a, dict) and a.get('what')]
    if actions:
        out += ['', '## 宿題']
        for a in actions:
            who, due = str(a.get('who') or '').strip(), str(a.get('due') or '').strip()
            out.append(f'- {str(a["what"]).strip().rstrip("。")}' + (f'（{who}' if who else '（担当未定') + (f'、{due} まで）' if due else '）'))
    if questions := items('open_questions'):
        out += ['', '## 決まっていないこと', *(f'- {q}' for q in questions)]
    return '\n'.join(out) + '\n'


def render_raw(conversation: list[dict], started: datetime | None = None, ended: datetime | None = None,
               heading: str | None = None) -> str:
    """要約できなかったとき：発言をそのまま並べる（heading を渡すと、途中までの議事録の後ろに付ける節にする）"""
    if heading:
        out = ['', heading]
    else:
        out = ['# 会議の記録（要約できなかったので、発言をそのまま並べています）',
               f'{day(started)} {started:%H:%M}〜{ended:%H:%M}', '']
    out += [f'- {c["time"]} {c["speaker"]}：{c["text"]}' for c in conversation]
    return '\n'.join(out) + '\n'


def post_discord(url: str, text: str, filename: str) -> None:
    """下書きを Discord の Webhook へ送る。長いときは本文の頭だけ書いて、全文は Markdown のファイルで添付する。
    本文の @everyone などで通知が飛ばないように、メンションはすべて無効にする"""
    header = '📝 議事録の下書きです。内容を確かめてから共有してください。'
    payload = {'username': 'シエル', 'allowed_mentions': {'parse': []}}
    body = f'{header}\n\n{text}'
    if len(body) <= DISCORD_LIMIT:
        r = requests.post(url, json={**payload, 'content': body}, timeout=20)
    else:
        title = text.split('\n', 2)[:2]
        payload['content'] = '\n'.join([header, '', *title, '', '全文は添付のファイルです。'])[:DISCORD_LIMIT]
        r = requests.post(url, data={'payload_json': json.dumps(payload, ensure_ascii=False)},
                          files={'files[0]': (filename, text.encode('utf-8'), 'text/markdown')}, timeout=30)
    r.raise_for_status()
