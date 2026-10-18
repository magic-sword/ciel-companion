"""LiveKit のイベントを共通履歴へ一度だけ取り込む。通常の返答処理とは独立する。"""
import asyncio
import logging

import emotion
import speakers


log = logging.getLogger('ciel-agent.conversation')


class ConversationRecorder:
    def __init__(self, history, replies, note_taker=None):
        self.history, self.replies, self.note_taker = history, replies, note_taker
        self._final_texts: dict[str, str] = {}
        self._tasks: set[asyncio.Task] = set()

    def on_transcribed(self, ev) -> None:
        if not ev.is_final:
            return
        if ev.item_id:
            # 続くユーザー会話項目に、実際の発言開始時刻が付く。
            self._final_texts[ev.item_id] = ev.transcript
            if len(self._final_texts) > 100:
                self._final_texts.pop(next(iter(self._final_texts)))
            return
        self._record_final(ev.transcript, ev.created_at, None)

    def on_item(self, ev) -> None:
        item = ev.item
        # 会話開始・エージェント切り替えの AgentHandoff に role は無い。
        if getattr(item, 'type', None) != 'message':
            return
        if item.role == 'user' and item.id in self._final_texts:
            self._record_final(self._final_texts.pop(item.id), item.created_at,
                               item.metrics.get('started_speaking_at'), item.id)
        if item.role == 'assistant':
            text = emotion.strip_tags(item.text_content or '').replace('[silent]', '').strip()
            if text and not self._has_source(item.id):
                turn = self.history.reserve(item.created_at, 'assistant')
                turn.source_id = item.id
                self.history.complete(turn, text)

    def _has_source(self, source_id) -> bool:
        return bool(source_id and any(t.source_id == source_id for t in self.history.turns))

    def _record_final(self, text, at, started_at, source_id=None) -> None:
        if self._has_source(source_id):
            return
        segment = self.replies.take_segment(started_at)
        turn = segment.turn if segment is not None and segment.turn is not None else self.history.reserve(at)
        turn.source_id = source_id
        task = asyncio.create_task(self._record_user(text, segment, turn))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _record_user(self, text, segment, turn) -> None:
        try:
            j = await self.replies.speaker_of(segment)
        except Exception:
            j = None
            log.warning('会話履歴：話者の判定を取得できない')
        self.history.complete(turn, text, j.sp if j else None,
                              speakers.SpeakerBook.label(j), j.sure if j else False)
        if self.note_taker is not None:
            self.note_taker.on_turn(turn)

    async def flush(self) -> None:
        await asyncio.gather(*list(self._tasks), return_exceptions=True)
