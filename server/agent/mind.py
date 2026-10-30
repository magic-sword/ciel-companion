# -*- coding: utf-8 -*-
"""シエルの心（CIEL_MODEL=pipeline のとき）：返事を作るたびに、会話の記録（conversation.Conversation）から文脈を組み立てる。

Realtime の組み立てでは、会話モデルが自分の会話をもう 1 つ持ち、そこへ話者の行・時刻・議事録の状態・心の状態を
system の項目として差し込んで合わせていた（記録が 2 つ。docs/attention-and-thinking-design-ja.md の 2 章）。
ここでは文字のモデルに毎回、次を渡す（LiveKit が持つ会話は、今回の発言と道具の呼び出しの分だけ使う）：
- 会話の指示（人物像・おしゃべり度など。いつも同じなので、キャッシュが効く）
- 記録の最近の発言（話者の名前付き。RECENT_TURNS 個まで）
- 今回の発言とその話者・覚えていること、今の時刻、議事録の状態、心の状態、今回だけの指示
黙るかどうかは、今までどおり返事の頭の [silent] で決める（ひかえめのとき。mode.drop_silent が読み上げない）。
呼ばれたかを名前で見る決まり（turns.py の _called）は、この組み立てでは使わない（発言をすべて心に渡す）。
"""
import logging

from livekit.agents import llm

import clock

log = logging.getLogger('ciel-agent.mind')

RECENT_TURNS = 40          # 記録から渡す最近の発言の数
TURN_CHARS = 1200          # 1 つの発言から渡す文字数


class Mind:
    def __init__(self, history, *, style=None, minutes=None, initiative=None, quiet_turn: str = '') -> None:
        self.history = history        # conversation.Conversation（唯一の記録）
        self.style = style            # mode.ConversationStyle
        self.minutes = minutes        # minutes.Minutes
        self.initiative = initiative  # initiative.Initiative（心の状態。段階 3 で記録に移す）
        self.quiet_turn = quiet_turn  # ひかえめのときの念押し（config/prompts/talk_quiet_turn.md）
        self.speaker_line: str | None = None   # 今回の発言の話者の 1 行（turns.py の speaker_parts が入れる）
        self.memory: str | None = None         # その人について覚えていること・関係（ひとり・身近な人のときだけ）
        self._state: str | None = None         # 最後に受け取った心の状態

    def build(self, chat_ctx: llm.ChatContext) -> llm.ChatContext:
        """LiveKit が渡した会話（会話の指示＋LiveKit が持つ発言＋今回の分）から、送る会話を作る"""
        items = list(chat_ctx.items)
        instructions = next((i for i in items if getattr(i, 'role', None) == 'system'), None)
        tail = _tail(items)
        tail_users = {_text(i) for i in tail if getattr(i, 'role', None) == 'user'}
        out = llm.ChatContext()
        if instructions is not None:
            out.items.append(instructions)
        for t in self._recent():
            text = t.text[:TURN_CHARS]
            if t.role == 'user':
                if any(u.endswith(text) for u in tail_users):
                    continue   # 今回の発言は、LiveKit の側の分（話者を添えたもの）を使う
                out.add_message(role='user', content=f'{t.name}：{text}')
            else:
                out.add_message(role='assistant', content=text)
        notes = self._notes()
        if notes:
            out.add_message(role='system', content=notes)
        out.items.extend(i for i in tail if i is not instructions)
        return out

    def _recent(self):
        if self.history is None:
            return []
        rows = [t for t in self.history.turns if t.ready.is_set() and t.text and t.role in ('user', 'assistant')]
        return rows[-RECENT_TURNS:]

    def _notes(self) -> str:
        """今回の返事のための補足（会話の後ろ、今回の発言の前に置く）"""
        lines = [clock.now_line()]
        if self.initiative is not None:
            note = self.initiative.state_note()
            if note is not None:
                self._state = note
            if self._state and self.style is not None and self.style.talk == 'chatty':
                lines.append(self._state)
        if self.minutes is not None:
            lines.append(self.minutes.context())
            note = self.minutes.take_note()
            if note:
                lines.append(note)
        if self.memory:
            lines.append(self.memory)
        if self.style is not None and self.style.talk == 'quiet' and self.quiet_turn:
            lines.append(self.quiet_turn)
        return '\n\n'.join(line for line in lines if line)


def _tail(items: list) -> list:
    """今回の分：最後のシエルの返事より後ろ（今回の発言・今回だけの指示・道具の呼び出しと結果）"""
    last = max((n for n, i in enumerate(items) if getattr(i, 'role', None) == 'assistant'), default=-1)
    return items[last + 1:]


def _text(item) -> str:
    return (getattr(item, 'text_content', None) or '').strip()
