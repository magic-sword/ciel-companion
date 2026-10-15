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


from . import people  # noqa: E402  State の後に読む

TOOLS = [*people.TOOLS]
