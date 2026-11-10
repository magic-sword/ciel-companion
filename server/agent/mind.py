# -*- coding: utf-8 -*-
"""シエルの小脳と心（CIEL_MODEL=pipeline のとき）。返事を作るたびに、会話の記録（conversation.Conversation）から文脈を組み立てる。

Realtime の組み立てでは、会話モデルが自分の会話をもう 1 つ持ち、そこへ話者の行・時刻・議事録の状態・心の状態を
system の項目として差し込んで合わせていた（記録が 2 つ。docs/conversation/conversation-pipeline-ja.md の 2 章）。
ここでは、LiveKit が持つ会話からは今回の分（今回の発言・今回だけの指示・道具の呼び出し）だけを使い、ほかは記録から作る。

返事は 2 つの係で作る（研究 Talker-Reasoner の形。速く話す係と、裏で考える係を分ける）。
- 小脳（すぐの返事）：ふつうの発言に返す。短い指示（人物像・話し方・config/prompts/talker.md）と、心が書いた「今のまとめ」と、
  最近の発言だけを読み、道具は持たない。黙るときは [silent]。
- 心（考える番）：全部の指示と道具で返す。どちらで返すかはコードが決める（route）：頼みごとの言葉がある・長く話した・何人も話した・
  ひかえめで名前を呼ばれた・議事録や歌の知らせ・道具の結果を受けた続き。小脳に「考えるべきか」を [think] で言わせる作りは、
  2 回の試験で一度も [think] を出さず、議事録を頼まれて道具なしで「準備しますね」と答えたのでやめた（2026-10-30）。
- 今のまとめ：心が、発言が増えたら（summaries/live.py と同じ決め方）会話を読み直して書く（config/prompts/mind_brief.md）。
  小脳は最近の発言しか読まないので、会話全体の流れはここで伝える。
"""
import asyncio
import json
import logging
import re
import time
from datetime import datetime

import openai
from livekit.agents import llm

import clock
import debug_log
import models
import tools as toolbox
from tools.goals import GOAL_TOOLS
from jst import JST
from summaries import live

log = logging.getLogger('ciel-agent.mind')

TALKER_TURNS = 16          # 小脳に渡す最近の発言の数
DEEP_TURNS = 40            # 心に渡す最近の発言の数
TURN_CHARS = 1200          # 1 つの発言から渡す文字数
BRIEF_TURNS = 60           # 今のまとめを書くときに渡す発言の数（前に書いてからの分）
BRIEF_TIMEOUT = 20.0
DEEP_WHY = ('minutes', 'song', 'enrolled', 'initiative', 'research', 'comment', 'game', 'image')   # 心が返事を作る、口（mouth.py）の why
LONG_SECONDS = 10.0        # これだけ長く話したら、心が考えて返す
LONG_CHARS = 80
# 「シエル」。文字起こしの聞き間違いも含める（gpt-realtime-whisper は名前のヒントを渡せず「シェル」「シェアル」になった。2026-10-30）
NAME = re.compile(r'シエル|しえる|シェル|シェアル|チエル|ciel|\bCL\b', re.IGNORECASE)
# 道具が要る頼みごとの言葉（議事録・調べもの・時刻・名前・覚えていること・歌）。あれば心が返す
REQUEST = re.compile(r'録|まとめ|調べ|検索|何時|時間を|名前|覚えて|忘れて|歌')
# 議事録を始める・終える頼みの言葉。今回の発言（付箋になった分を除く）に無ければ、議事録を動かす道具を心に渡さない
MINUTES_ASK = re.compile(r'録|まとめ|終わ|終了|止め|ストップ|送って')
MINUTES_MOVES = ('start_minutes', 'finish_minutes', 'summarize_past_minutes')
# 目的の道具のうち、相手の発言で呼ぶもの（育つ例文の印）・体を動かすもの。係の知らせで心が呼ぶ道具（小さな目標・心に任せた段を
# 終える）は除く。ゲームの道具は、ゲームの決まりの役目（act・look・know）で決める（game_env.py）。体を動かす頼みの言葉も
# ゲームの決まり（route_words）にある。「ついてきて」は短いので、小脳に行くと、道具を持たない小脳が「はーい」と言うだけになる
GOAL_ASKED = frozenset(GOAL_TOOLS)
GOAL_MOVING = GOAL_ASKED - {'game_task_status'}
GOAL_ONE = GOAL_MOVING
# 小脳が体の動きを約束した言い方（シエル自身の口ぐせなので、相手の言い方よりそろっている）。約束しても小脳は道具を持たないので、
# 話し終えたら心が続きをする（「すぐに渡しますね」と言うだけで渡さなかった。2026-11-07）
PROMISE = re.compile(r'(渡し|作り|作って|集め|集めて|取って|取り|掘り|掘って|探し|探して|持って|置き|置いて|拾い|拾って|降り|向かい|ついていき|ついて行き|そっちに行き|行き|あげ|止まり|待ち)(ます|ますね|ますよ|ましょう|きます|おきます|いきます|るのです|ますのです)')
STALL_GAP = 30.0   # 言葉だけで止まったと心に知らせるのは、この秒数に 1 回まで
FILLER = re.compile(r'[\s、。，．,.!?！？…ー〜あえうっんそだは]+')
BRIEF_LABELS = (('topic', '話題'), ('flow', '流れ'), ('decided', '決まったこと'), ('open', 'まだ決まっていないこと'),
                ('people', '人'), ('say', 'シエルが言いたいこと'))


class Mind:
    def __init__(self, history, *, style=None, minutes=None, initiative=None, quiet_turn: str = '',
                 brief_instructions: str = '', client=None, board=None, body=None, eyes=None,
                 self_image: str = '') -> None:
        self.history = history        # conversation.Conversation（唯一の記録）
        self.style = style            # mode.ConversationStyle
        self.minutes = minutes        # minutes.Minutes
        self.board = board            # board.Board（頼まれたこと・していることの付箋。今どうなっているかはここで読む）
        self.initiative = initiative  # initiative.Initiative（心の状態。段階 3 で記録に移す）
        self.body = body              # game_env.GameEnv（ゲームの体。つなぐ先があるときだけ）
        self.goals = None             # goals.GoalRunner（長い目的の係。agent.py が置く）
        self.eyes = eyes              # eyes.Eyes（見せてもらった画像）
        # シエル自身の姿の絵（data URL）。指示のすぐ後ろにいつも置き、自分の姿を絵としても知っているようにする。
        # 毎回同じ始まりなので、OpenAI のキャッシュで安くなる。画像を見せたときだけ添えると、関係ない画像にも
        # 自分を探しにいくおそれがあった（ユーザーの方針。2026-11-06）
        self.self_image = self_image
        self.quiet_turn = quiet_turn  # ひかえめのときの念押し（config/prompts/talk_quiet_turn.md）
        self.brief_instructions = brief_instructions   # config/prompts/mind_brief.md
        self._client = client
        self.brief: str | None = None    # 今のまとめ（心が書く）
        self._brief_raw: dict = {}
        self._brief_through = 0          # 今のまとめに使った最後の発言 ID
        self._brief_at = time.monotonic()
        self._briefing: asyncio.Task | None = None
        self._deep = False               # 次の返事は心が作る
        self.reply_origin = ''
        self._next_origin = ''
        self.from_comment = False        # 今の返事（と、その道具の結果の続き）は配信のコメントへの返事
        self.waiting = None              # まだ言っていない知らせ（why → 指示）を返す（mouth.Mouth.waiting）
        self.handed: str | None = None   # 今の返事に添えた知らせの why（言い終えたら agent.py が口から外す）
        self._state: str | None = None   # 最後に受け取った心の状態（initiative）
        self._task: asyncio.Task | None = None
        # 遊んでいるあいだの振り分けの 2 段目（router.Router。道具ごとのきっかけとの意味の近さ）。agent.py が置く
        self.router = None
        self.is_owner = lambda: True      # 今の発言が持ち主のものか（育つ例文は持ち主の発言だけ。agent.py が置く）
        self.last_why: str | None = None  # 最後に心へ回した理由（semantic なら、道具を使わなければ小脳の例文にする）
        self.semantic_tool: str | None = None   # 意味で心へ回したときの、いちばん近いきっかけの道具
        self._promised: str | None = None # 小脳が体の動きを約束だけした発言（心が道具でやったら、その道具の例文にする）
        self.on_promise = None            # 呼ぶと、心に約束の続きをさせる（agent.py が置く。口の why 'game'）
        self.on_stalled = None            # 呼ぶと、断られた体の道具の次の手を心にさせる（agent.py が置く。口の why 'game'）
        self._nudged: set[str] = set()    # 言葉だけで止まったと心に知らせた道具の呼び出し（同じものは 1 度だけ）
        self._nudged_at = -STALL_GAP      # 最後に知らせた時刻（知らせた返事でまた止まっても、続けて知らせない）

    @property
    def client(self):
        if self._client is None:
            self._client = models.create_client('brief')
        return self._client

    # ---- 小脳と心の振り分け ----

    def on_say(self, why: str) -> None:
        """口が返事を頼む直前（mouth.Mouth.before_say）。議事録・歌の知らせ・声の登録の一言は、心が作る"""
        self.from_comment = why == 'comment'
        self._next_origin = why
        if why in DEEP_WHY:
            self._deep = True

    def route(self, chat_ctx: llm.ChatContext, turn: dict | None = None) -> str:
        """この返事を心（'mind'）と小脳（'talker'）のどちらが作るか（コードで決める）。turn は turns.py の pipeline_turn"""
        tail = _tail(list(chat_ctx.items))
        self.last_why = self.semantic_tool = None
        if any(getattr(i, 'type', None) == 'function_call_output' for i in tail):
            self.reply_origin = 'tool_result'
            return 'mind'   # 道具の結果を受けた続き
        self.reply_origin = self._next_origin or 'reply'
        self._next_origin = ''
        if self._deep:
            self._deep = False
            return 'mind'
        self.from_comment = False   # 声の発言への返事（口を通さない）
        text = _user_text(tail)
        if not text:
            return 'talker'   # 自分から話しかける・タッチなど、相手の発言の無い返事
        # 付箋になった頼みは、頼みごととして数えない。同じ発言に残った「議事録開始して」で心に回し続け、
        # 議事録をとっている心が終了の頼みと取り違えて終わらせた（2026-10-30）
        rest = self._strip(text)
        # 頼みだけの発言かは、最後の発言で見る。黙って聞いた前の発言も今回の分に残るので、全部で見ると
        # 「賛成です。…（→ 付箋）」が頼みだけにならず、心が前の発言に返した（2026-10-31）
        latest = next((_text(i) for i in reversed(tail) if _is_user(i) and _text(i)), '')
        latest_rest = self._strip(latest)
        if latest_rest != latest and not FILLER.sub('', latest_rest):
            # 頼みだけの発言で、付箋になった（「あ、議事録開始して」）。返事はせず、議事録係の知らせだけを言う。
            # 心が「議事録、とりながら進めていますよ」と返し、そのあと知らせも言って 2 回になった（2026-10-30）
            debug_log.record('mind_route', why='on_board')
            return 'skip'
        # ひかえめ（会議）では、どの発言も心が受ける。黙るか答えるかの見極めは、短い指示の小脳では人どうしの話に
        # 1 回に 3 度口をはさみ、全部の指示と会話の流れを読む心では口をはさまなかった（2026-10-30、bench_compare.py）。
        # 黙る返事は声にならないので、心で受けても遅れは気にならない
        quiet = self.style is not None and self.style.talk == 'quiet'
        why = ('image' if self.eyes is not None and self.eyes.wants(rest)
               else 'notice' if self._waiting()
               else 'request' if REQUEST.search(rest)
               else 'game' if self._game_ask(rest)
               else 'long' if (turn or {}).get('seconds', 0.0) >= LONG_SECONDS or len(text) >= LONG_CHARS
               else 'people' if not quiet and self._speakers_since_ciel() >= 2
               else 'named' if quiet and NAME.search(text)
               else 'quiet' if quiet
               else None)
        self.last_why = why
        if why is None:
            return 'talker'
        log.info('心：考えて返す（%s）', why)
        debug_log.record('mind_route', why=why)
        return 'mind'

    def playing(self) -> bool:
        """体を受け持っていて、ゲームの中にいる"""
        return self.body is not None and self.body.playing()

    def _game_ask(self, text: str) -> bool:
        words = getattr(self.body, 'route_words', None) if self._body_linked() else None
        return bool(words is not None and words.search(text))

    def _ids(self, *roles: str) -> frozenset:
        return self.body.tool_ids(*roles) if self.body is not None else frozenset()

    def game_calls(self) -> frozenset:
        """相手の発言で呼ぶゲームの道具（育つ例文の印）"""
        return self._ids('act', 'look', 'know') | GOAL_ASKED

    def moving_calls(self) -> frozenset:
        """体を動かす頼みの道具（意味で心へ回したのに使わなければ、回しすぎ）"""
        return self._ids('act') | GOAL_MOVING

    def one_call_tools(self) -> frozenset:
        """1 つの返事で 1 つだけ通す道具（one_body_call）"""
        return self._ids('act') | GOAL_ONE

    async def second_look(self, chat_ctx: llm.ChatContext) -> str:
        """1 段目で小脳に決まった発言を、遊んでいるあいだだけ、道具ごとのきっかけとの意味の近さで見直す（router.py）。
        決まった言葉に「欲しい」「ピッケル」が無く、「石のピッケルが欲しいな」が道具の無い小脳へ回り、
        「渡しますね」と言うだけだった（2026-11-07）"""
        if models.LOCAL_TEST and self.playing() and latest_user_text(chat_ctx):
            self.last_why = 'local_game'
            return 'mind'  # 埋め込み API を使わず、ゲームの頼みを道具のある心へ渡す
        if self.router is None or not self.playing():
            return 'talker'
        text = latest_user_text(chat_ctx)
        tool = await self.router.wants_mind(self._strip(text)) if text else None
        if tool is None:
            return 'talker'
        self.last_why, self.semantic_tool = 'semantic', tool
        log.info('心：考えて返す（semantic・%s）', tool)
        debug_log.record('mind_route', why='semantic', tool=tool)
        return 'mind'

    def after_reply(self, chat_ctx: llm.ChatContext, who: str, text: str, calls: list[str], done: bool) -> None:
        """返事のあと：振り分けの例文を育て、小脳が体の動きを約束だけしたら心に続きをさせる"""
        if done and self.eyes is not None:
            self.eyes.reply_finished()
        if self.router is None or not self.playing() or not done:
            return
        if who == 'mind' and not calls and self.on_stalled is not None and time.monotonic() - self._nudged_at >= STALL_GAP:
            stalled = self._stalled(chat_ctx)
            if stalled is not None:
                # 体の道具が始めずに断られ（次の手つき）、心が道具を呼ばずに言葉だけで返した。「丸石を集めてから作るのです」と
                # 言って何も始めず、「始めてる？」に「まだ始めていない」と答えた（2026-11-07）。指示文だけでは止まらないので、
                # コードで 1 度だけ心に続きをさせる
                name, result = stalled
                self._nudged_at = time.monotonic()
                debug_log.record('mind_route', why='stalled', tool=name, reason=result.get('reason'))
                self.on_stalled(name, result)
        said = latest_user_text(chat_ctx)
        asked = self.game_calls()
        game = [c for c in calls if c in asked]
        if who == 'mind' and game:
            if self._promised:   # 小脳が約束だけした発言を、心が道具でやった：取りこぼしの例文
                self._learn(self._promised, game[0], 'promise')
                self._promised = None
            elif said and self.is_owner():
                self._learn(said, game[0], 'tool')
        elif (who == 'mind' and self.last_why == 'semantic' and self.semantic_tool in self.moving_calls() and said
              and self.is_owner() and '[silent]' not in text):
            # 体を動かす頼みに近いとして心へ回したのに、道具を使わなかった：回しすぎ。見る・進み具合・知識の頼みは、
            # 心が様子から道具なしで答えることもあるので、小脳の例文にしない
            self._learn(said, None, 'no_tool')
        elif who == 'talker' and said and PROMISE.search(text):
            # 小脳が「渡しますね」と約束だけした：話し終えたら、心が道具で続きをする（取りこぼしの受け皿）
            self._promised = said if self.is_owner() else None
            debug_log.record('mind_route', why='promise', said=said[:60], text=text[:80])
            if self.on_promise is not None:
                self.on_promise(said, text)

    def _stalled(self, chat_ctx: llm.ChatContext) -> tuple[str, dict] | None:
        """この返事の直前の道具の結果のうち、体を動かす道具が始めずに断られ、次の手（next）があるもの。まだ知らせていなければ"""
        acts = self._ids('act')
        for item in reversed(list(chat_ctx.items)):
            if isinstance(item, llm.FunctionCall):
                continue
            if not isinstance(item, llm.FunctionCallOutput):
                return None   # この返事の道具の結果は、ここまで
            if item.name not in acts or item.call_id in self._nudged:
                continue
            try:
                result = json.loads(item.output)
            except (TypeError, ValueError):
                continue
            if isinstance(result, dict) and result.get('status') == 'error' and result.get('next'):
                self._nudged.add(item.call_id)
                return item.name, result
        return None

    def _learn(self, text: str, tool: str | None, source: str) -> None:
        task = asyncio.create_task(self.router.learn(self._strip(text), tool, source))
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    def tools_for(self, chat_ctx: llm.ChatContext, tools: list) -> list:
        """心に渡す道具。議事録を始める・終える道具は、今回の発言に頼みの言葉があるときだけ渡す（付箋になった頼みは除く）。
        付箋で状態を渡しても、長い話のあとの「予算は去年と同じくらい」に、心が議事録を終える道具を 2 回とも呼んだ（2026-10-30）。
        道具の結果を受けた続きも同じに見る（会話を探す道具の続きで、また終える道具を呼んだ。2026-10-31）"""
        text = _user_text(_tail(list(chat_ctx.items)))
        if text and not MINUTES_ASK.search(self._strip(text)):
            tools = [t for t in tools if getattr(t, 'id', None) not in MINUTES_MOVES]
        # ゲームの体を受け持っていなければ、ゲームの道具（体・見る・知識）と目的の道具は渡さない
        if not self._body_linked():
            hidden = set(self._ids('act', 'look', 'know')) | set(GOAL_TOOLS)
            tools = [t for t in tools if getattr(t, 'id', None) not in hidden]
        # 配信のコメントへの返事では、コメントから使ってよい道具だけ（tools/ の FROM_COMMENTS）
        return toolbox.for_comments(tools) if self.from_comment else tools

    def _body_linked(self) -> bool:
        return self.body is not None and self.body.linked

    def _speakers_since_ciel(self) -> int:
        """シエルが最後に話してから話した人の数（話者が分からない発言は数えない）"""
        names = set()
        for t in reversed(self.history.turns if self.history is not None else []):
            if t.role == 'assistant' and t.text:
                break
            if t.role == 'user' and t.text and t.speaker is not None:
                names.add(id(t.speaker))
        return len(names)

    # ---- 文脈 ----

    def build(self, chat_ctx: llm.ChatContext, *, talker_instructions: str | None = None,
              turn: dict | None = None) -> llm.ChatContext:
        """LiveKit が渡した会話（会話の指示＋LiveKit が持つ発言＋今回の分）から、送る会話を作る。
        talker_instructions があれば小脳（会話の指示をこれに替え、最近の発言を少なく）、無ければ心（全部の指示）。
        turn（turns.py の pipeline_turn）の話者の 1 行・タッチは、今回の発言の前に置く（LiveKit の会話は書き換えない）"""
        items = list(chat_ctx.items)
        instructions = next((i for i in items if getattr(i, 'role', None) == 'system'), None)
        tail = [i for i in _tail(items) if i is not instructions]
        tail_users = {_text(i) for i in tail if _is_user(i)}
        turn = turn or {}
        out = llm.ChatContext()
        if talker_instructions is not None:
            out.add_message(role='system', content=talker_instructions)
        elif instructions is not None:
            out.items.append(instructions)
        if self.self_image and not models.LOCAL_TEST:
            out.items.append(llm.ChatMessage(role='user', content=[
                '[わたしの姿]（わたし、シエルの見た目の絵。いつも知っている自分の姿）',
                llm.ImageContent(image=self.self_image, inference_detail='low')]))
        for t in self._recent(TALKER_TURNS if talker_instructions is not None else DEEP_TURNS):
            text = t.text[:TURN_CHARS]
            if t.role == 'user':
                if any(text in u for u in tail_users):
                    continue   # 今回の発言（の切れ端）は、LiveKit の側の分を使う
                out.add_message(role='user', content=f'{t.name}：{self._marked(text)}')
            else:
                out.add_message(role='assistant', content=text)
        notes = self._notes(deep=talker_instructions is None, memory=turn.get('memory'))
        self.handed = None
        if talker_instructions is None and tail_users:
            # 切れ目を待っている知らせは、相手への返事の中で伝える。長い話の途中で聞く係が議事録を始めると、
            # 「とり始めた」は話し終わりまで待って約 26 秒後になり、最後の質問への答えになって議事録にふれなかった（2026-10-31）
            waiting = self._waiting()
            if waiting:
                self.handed, text = next(iter(waiting.items()))
                notes = '\n\n'.join(x for x in (notes, f'[まだ伝えていない知らせ]\n{text}') if x)
        if notes:
            out.add_message(role='system', content=notes)
        if talker_instructions is None and self.eyes is not None:
            # 見ていない画像・画像を指した話のときだけ、この返事に画像を添える（小脳には添えない）
            picture = self.eyes.message_for_reply(_user_text(tail))
            if picture is not None:
                out.items.append(picture)
        speaker = '\n'.join(x for x in (turn.get('tag'), turn.get('touch')) if x)
        if speaker and tail_users:
            out.add_message(role='system', content=speaker)   # 今回の発言の話者（とタッチ）
        out.items.extend(self._mark_item(i) for i in tail)
        return out

    def _waiting(self) -> dict[str, str]:
        return {w: t for w, t in (self.waiting() if self.waiting is not None else {}).items() if w in DEEP_WHY and t}

    def _mark_item(self, item):
        """今回の発言の、付箋になった頼みを付箋の印に置き換えた写し（送る会話だけ。LiveKit の会話は変えない）"""
        if not _is_user(item):
            return item
        text = _text(item)
        marked = self._marked(text)
        return item if marked == text else llm.ChatMessage(role='user', content=[marked])

    def _marked(self, text: str) -> str:
        """付箋になった頼みを「（→ #3 議事録をとる：実行中）」に置き換える。今回の発言も、最近の発言として渡す過去の分も
        （過去の「議事録開始して」を読んだ心が、終了の頼みと取り違えて終了の道具を呼んだ。2026-10-30）"""
        return self.board.mark(text) if self.board is not None else text

    def _strip(self, text: str) -> str:
        """付箋になった頼みを除いた発言（頼みごととして数え直さない）"""
        return self.board.strip(text) if self.board is not None else text

    def _recent(self, n: int):
        if self.history is None:
            return []
        rows = [t for t in self.history.turns if t.ready.is_set() and t.text and t.role in ('user', 'assistant')]
        return rows[-n:]

    def _notes(self, deep: bool, memory: str | None = None) -> str:
        """今回の返事のための補足（会話の後ろ、今回の発言の前に置く）"""
        lines = [clock.now_line()]
        if self.brief:
            lines.append(self.brief)
        if self.initiative is not None:
            note = self.initiative.state_note()
            if note is not None:
                self._state = note
            if self._state and self.style is not None and self.style.talk == 'chatty':
                lines.append(self._state)
        if self.board is not None:
            lines.append(self.board.context())   # 今どうなっているか（小脳も、していないことを言わないように読む）
        if self.eyes is not None:
            lines.append(self.eyes.context())    # 見せてもらった画像の説明文
        if self.body is not None:
            lines.append(self.body.context())    # マイクラの様子（小脳も、見ていないことを言わないように読む）
        if self.goals is not None:
            lines.append(self.goals.context())   # 今の目的（goals.py。小脳も、していないことを言わないように読む）
        if deep and self.minutes is not None:
            lines.append(self.minutes.context())
            note = self.minutes.take_note()
            if note:
                lines.append(note)
        if memory:
            lines.append(memory)
        if self.style is not None and self.style.talk == 'quiet' and self.quiet_turn:
            lines.append(self.quiet_turn)
        return '\n\n'.join(line for line in lines if line)

    # ---- 今のまとめ ----

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(live.LIVE_POLL_SECONDS)
            try:
                self.step(time.monotonic())
            except Exception:
                log.exception('心：今のまとめの見回りに失敗')

    def step(self, now: float) -> None:
        if self.history is None or not self.brief_instructions:
            return
        if self._briefing is not None and not self._briefing.done():
            return
        through = self.history.settled_through()
        new = sum(1 for t in self.history.between(self._brief_through, through) if t.role == 'user' and t.text)
        if not live.due(new, now - self._brief_at):
            return
        self._brief_at = now
        self._briefing = asyncio.create_task(self._write_brief(through))

    async def _write_brief(self, through: int) -> None:
        rows = [t for t in self.history.between(self._brief_through, through) if t.text][-BRIEF_TURNS:]
        wall = datetime.now(JST)
        request = {
            'now': f'{wall:%Y-%m-%d %H:%M}',
            'talk': self.style.talk if self.style is not None else 'normal',
            **({'previous': self._brief_raw} if self._brief_raw else {}),
            'conversation': [{'speaker': t.name, 'text': t.text[:TURN_CHARS]} for t in rows],
            **({'thoughts': self._state} if self._state else {}),
        }
        model = models.model('brief')
        try:
            r = await models.client_for('brief', self.client).chat.completions.create(**models.options(
                'brief', model=model, reasoning_effort='low', response_format={'type': 'json_object'}, timeout=BRIEF_TIMEOUT,
                messages=[{'role': 'system', 'content': self.brief_instructions},
                          {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)}]))
            models.record('brief', model, getattr(r, 'usage', None))
            result = json.loads(r.choices[0].message.content or '{}')
        except Exception as e:   # 書けなくても、会話は続ける（次の機会に回す）
            log.warning('心：今のまとめを書けない：%s', type(e).__name__)
            return
        self.apply_brief(result, through)

    def apply_brief(self, result, through: int) -> None:
        if not isinstance(result, dict):
            return
        raw = {k: result[k].strip()[:300] for k, _ in BRIEF_LABELS if isinstance(result.get(k), str) and result[k].strip()}
        self._brief_raw, self._brief_through = raw, through
        lines = [f'{label}：{raw[k]}' for k, label in BRIEF_LABELS if k in raw]
        self.brief = '\n'.join(['[今のまとめ]', *lines]) if lines else None
        log.info('心：今のまとめを書いた（%d 項目）', len(lines))
        debug_log.record('mind_brief', brief=self.brief)


def only_given(chunk, fns: list):
    """返事の流れから、今回渡した道具（fns）の呼び出しだけを通す。LiveKit は、送らなかった道具でも Agent の道具なら
    呼んでしまう（voice/agent_activity.py の tool_ctx は Agent の道具全部）。渡していない道具（コメントから使えない道具・
    絞った議事録の道具）を呼ばせないために、ここで落とす。（通す chunk, 落とした道具の名前）を返し、全部落として
    何も残らなければ chunk は None"""
    delta = None if isinstance(chunk, str) else getattr(chunk, 'delta', None)
    if delta is None or not delta.tool_calls:
        return chunk, []
    given = {getattr(t, 'id', None) for t in fns}
    kept = [c for c in delta.tool_calls if c.name in given]
    dropped = [c.name for c in delta.tool_calls if c.name not in given]
    if not dropped:
        return chunk, []
    if not kept and not delta.content and getattr(chunk, 'usage', None) is None:
        return None, dropped
    return chunk.model_copy(update={'delta': delta.model_copy(update={'tool_calls': kept})}), dropped


def one_body_call(chunk, taken: list, moving=frozenset()):
    """1 つの返事で、体を動かす道具（体の道具・目的の道具）は 1 つだけ通す。体の技は一度に 1 つなので、同時に呼ぶと
    取り合いになって両方失敗した（集めると作るを同時に呼んだ。2026-11-07）。taken は、この返事ですでに通した呼び出しの名前。
    moving は 1 つだけ通す道具の名前（Mind.one_call_tools）。
    （通す chunk, 落とした道具の名前）を返し、全部落として何も残らなければ chunk は None"""
    delta = None if isinstance(chunk, str) else getattr(chunk, 'delta', None)
    if delta is None or not delta.tool_calls:
        return chunk, []
    kept, dropped = [], []
    for c in delta.tool_calls:
        if c.name in moving and any(n in moving for n in taken):
            dropped.append(c.name)
            continue
        taken.append(c.name)
        kept.append(c)
    if not dropped:
        return chunk, []
    if not kept and not delta.content and getattr(chunk, 'usage', None) is None:
        return None, dropped
    return chunk.model_copy(update={'delta': delta.model_copy(update={'tool_calls': kept})}), dropped


def latest_user_text(chat_ctx) -> str:
    """今回の分の、最後の相手の発言"""
    tail = _tail(list(chat_ctx.items))
    return next((_text(i) for i in reversed(tail) if _is_user(i) and _text(i)), '')


def local_context(ctx: llm.ChatContext, source: llm.ChatContext | None = None) -> llm.ChatContext:
    """Qwen 用に system と連続する assistant の発言をまとめる。道具の順序と元の記録は変えない。"""
    out = llm.ChatContext()
    instructions = [i.text_content for i in ctx.items if isinstance(i,llm.ChatMessage) and i.role == 'system']
    if instructions:
        out.add_message(role='system',content='\n\n'.join(instructions))
    out.items.extend(i for i in ctx.items if not (isinstance(i,llm.ChatMessage) and i.role == 'system'))
    if not any(_is_user(i) for i in out.items) and source is not None:
        # 文字入力の記録が確定するより先に道具の結果が戻ることがある。
        # Qwen の tool continuation にも、LiveKit が持つ元の依頼を添える。
        latest = next((i for i in reversed(source.items) if _is_user(i)),None)
        if latest is not None:
            out.items.insert(1 if instructions else 0,latest)
    if not any(_is_user(i) for i in out.items):
        # A greeting or service notice can precede the first human utterance.
        # Preserve the real internal notice as the query required by Qwen.
        notice = next((i.text_content for i in reversed(ctx.items)
                       if isinstance(i,llm.ChatMessage) and i.role == 'system' and i.text_content), None)
        if notice:
            out.add_message(role='user', content=notice)
    # 自分から話す番では、最近の返答が複数続いた末尾になることがある。
    # Qwen は末尾の assistant が2件以上あると400を返す。内容を順に残し、
    # 送信用の写しだけをまとめる。FunctionCall/Output の境界は越えない。
    merged = []
    for item in out.items:
        if (isinstance(item,llm.ChatMessage) and item.role == 'assistant' and merged
                and isinstance(merged[-1],llm.ChatMessage) and merged[-1].role == 'assistant'):
            previous = merged[-1]
            merged[-1] = previous.model_copy(update={'content': [*previous.content, '\n\n', *item.content]})
        else:
            merged.append(item)
    out.items[:] = merged
    if out.items and isinstance(out.items[-1],llm.ChatMessage) and out.items[-1].role == 'assistant':
        # 自発的な返答も新しい生成。末尾が assistant のままだと Qwen は
        # prefill（その発言の続き）として扱い、EOSだけを返すことがある。
        # 現在の内部通知を user 形式のイベントとして末尾にも渡す。
        # 実際のユーザー依頼は繰り返さず、tool output の続きにも足さない。
        notices = []
        for item in reversed(ctx.items):
            if not (isinstance(item,llm.ChatMessage) and item.role == 'system'):
                break
            notices.append(item.text_content or '')
        out.add_message(role='user',content='\n\n'.join(reversed(notices)))
    return out


def _tail(items: list) -> list:
    """今回の分：最後のシエルの返事より後ろ（今回の発言・今回だけの指示・道具の呼び出しと結果）"""
    last = max((n for n, i in enumerate(items) if getattr(i, 'role', None) == 'assistant'), default=-1)
    return items[last + 1:]


def _text(item) -> str:
    return (getattr(item, 'text_content', None) or '').strip()


def _is_user(item) -> bool:
    return getattr(item, 'role', None) == 'user'


def _user_text(items: list) -> str:
    """相手の発言をつないだ文"""
    return ''.join(_text(i) for i in items if _is_user(i))

