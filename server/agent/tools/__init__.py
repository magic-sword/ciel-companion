# -*- coding: utf-8 -*-
"""シエルの道具（function calling）。会話モデルが、必要なときに自分で呼んで、調べたり記録したりする。

- 覚えている人の一覧などを最初から指示に入れない。会話に関係する分だけを、必要になったときに道具で取りに来させる
  （指示が長くならず、会話に関係ない名前を急に出すこともない）。
- 道具を足すには：このフォルダにモジュールを作り、@function_tool の関数を TOOLS に並べ、下の TOOLS に加える。
  いつ使うかは config/prompts/ の Markdown で教える（関数の説明は短く、使い方の決まりはプロンプトに書く）。
- 道具の中では、会話の状態（話者の帳簿など）を context.userdata（State）から使う。
- 外部の MCP サーバーをつなぐときは、LiveKit Agents の AgentSession(mcp_servers=[...]) を使う（docs/decisions/tools-ja.md）。
"""
from dataclasses import dataclass

from speakers import SpeakerBook


@dataclass
class State:
    """道具から使う、この会話の状態（AgentSession の userdata）"""
    book: SpeakerBook | None = None
    notes: object | None = None   # notes.NoteTaker（覚えておくメモの記録係）
    minutes: object | None = None   # minutes.Minutes（会議の議事録の係）
    history: object | None = None   # conversation.Conversation（接続中だけの共通履歴）
    researcher: object | None = None   # web_research.WebResearcher（Web検索）
    initiative: object | None = None   # initiative.Initiative（シエルの内なる考え）
    song: object | None = None   # singing.SongListener（歌を聴く係）
    preamble: object | None = None   # emotion.PreambleCut（道具を呼んだ返事の前置きを止める）
    mouth: object | None = None   # mouth.Mouth（シエルを話させる入り口）


def cut_preamble(context) -> None:
    """道具を呼んだ返事の前置きを、読み上げている 1 文のあとで止める（あとから短い一言を言わせる道具が呼ぶ）"""
    cut = getattr(context.userdata, 'preamble', None)
    if cut is not None:
        cut.request(getattr(context, 'speech_handle', None))


from . import memory, minutes, people, conversation, research, thoughts, clock, singing  # noqa: E402  State の後に読む

TOOLS = [*people.TOOLS, *memory.TOOLS, *minutes.TOOLS, *conversation.TOOLS, *research.TOOLS, *thoughts.TOOLS, *clock.TOOLS,
         *singing.TOOLS]
