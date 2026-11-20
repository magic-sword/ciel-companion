# -*- coding: utf-8 -*-
"""シエルの心（CIEL_MODEL=pipeline のとき）。返事を作るたびに、会話の記録（conversation.Conversation）から文脈を組み立てる。

Realtime の組み立てでは、会話モデルが自分の会話をもう 1 つ持ち、そこへ話者の行・時刻・議事録の状態・心の状態を
system の項目として差し込んで合わせていた（記録が 2 つ。docs/conversation/conversation-pipeline-ja.md の 2 章）。
ここでは、LiveKit が持つ会話からは今回の分（今回の発言・今回だけの指示・道具の呼び出し）だけを使い、ほかは記録から作る。

返事はいつも心が作る。固定の指示（人物像・話し方・道具の使い方）と道具の一覧は会話の間変えず、最近の発言（_window）、
今回の補足（_notes：時刻・今のまとめ・付箋・体や目的の様子）、今回の発言の順に並べる。前の返事と先頭が同じなので、
推論のキャッシュが履歴の終わりまで効く。ゲーム中の持ち主の発言には、同じ並びの後ろに決定の書き方を足して、
話すこととすることを一つの決定にする（game_decision.py）。
- 今のまとめ：発言が増えたら（summaries/live.py と同じ決め方）会話を読み直して書く（config/prompts/mind_brief.md）。
  最近の発言より前の流れはここで伝える。
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

DEEP_TURNS = 40            # 心の外（議事録の係など）に渡す最近の発言の数
WINDOW_KEEP = 40           # 心に渡す最近の発言：区切り直すときに残す数
WINDOW_MAX = 60            # 心に渡す最近の発言：これを超えたら区切り直す（それまでは履歴の先頭を変えない）
TURN_CHARS = 1200          # 1 つの発言から渡す文字数
BRIEF_TURNS = 60           # 今のまとめを書くときに渡す発言の数（前に書いてからの分）
BRIEF_TIMEOUT = 20.0
EVENT_REPLIES = ('minutes', 'song', 'enrolled', 'research', 'comment', 'game', 'image', 'initiative', 'idea')
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
FILLER = re.compile(r'[\s、。，．,.!?！？…ー〜あえうっんそだは]+')
BRIEF_LABELS = (('topic', '話題'), ('flow', '流れ'), ('decided', '決まったこと'), ('open', 'まだ決まっていないこと'),
                ('people', '人'), ('say', 'シエルが言いたいこと'))


class Mind:
    def __init__(self, history, *, style=None, minutes=None, quiet_turn: str = '',
                 brief_instructions: str = '', client=None, board=None, body=None, eyes=None,
                 self_image: str = '') -> None:
        self.history = history        # conversation.Conversation（唯一の記録）
        self.style = style            # mode.ConversationStyle
        self.minutes = minutes        # minutes.Minutes
        self.board = board            # board.Board（頼まれたこと・していることの付箋。今どうなっているかはここで読む）
        self.body = body              # game_env.GameEnv（ゲームの体。つなぐ先があるときだけ）
        self.goals = None             # goals.GoalRunner（長い目的の係。agent.py が置く）
        self.stream = None            # youtube_chat.YouTubeChat（配信中か。agent.py が置く）
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
        self.reply_origin = ''
        self._next_origin = ''
        self.from_comment = False        # 今の返事（と、その道具の結果の続き）は配信のコメントへの返事
        self.waiting = None              # まだ言っていない知らせ（why → 指示）を返す（mouth.Mouth.waiting）
        self.handed: str | None = None   # 今の返事に添えた知らせの why（言い終えたら agent.py が口から外す）
        self._task: asyncio.Task | None = None
        self.is_owner = lambda: True      # 今の発言が持ち主のものか（agent.py が置く）
        self._window_first = None       # 心に渡している最近の発言の、最初の発言（_window）

    @property
    def client(self):
        if self._client is None:
            self._client = models.create_client('brief')
        return self._client

    # ---- 返事を作る契機 ----

    def on_say(self, why: str) -> None:
        """口が返事を頼む直前（mouth.Mouth.before_say）。議事録・歌の知らせ・声の登録の一言は、心が作る"""
        self.from_comment = why == 'comment'
        self._next_origin = why

    def route(self, chat_ctx: llm.ChatContext, turn: dict | None = None) -> str:
        """この返事を作るか（'mind'）、黙るか（'skip'）。返事はいつも心が作る。turn は turns.py の pipeline_turn"""
        tail = _tail(list(chat_ctx.items))
        if any(getattr(i, 'type', None) == 'function_call_output' for i in tail):
            self.reply_origin = 'tool_result'
            return 'mind'   # 道具の結果を受けた続き
        self.reply_origin = self._next_origin or 'reply'
        self._next_origin = ''
        if self.reply_origin in EVENT_REPLIES:
            # Preserve a comment's origin and avoid treating a notification as a repeated user request.
            return 'mind'
        self.from_comment = False   # 声の発言への返事（口を通さない）
        # 頼みだけの発言かは、最後の発言で見る（付箋になった頼みは、頼みごととして数えない）
        latest = next((_text(i) for i in reversed(tail) if _is_user(i) and _text(i)), '')
        latest_rest = self._strip(latest)
        if latest and latest_rest != latest and not FILLER.sub('', latest_rest):
            # 頼みだけの発言で、付箋になった（「あ、議事録開始して」）。返事はせず、議事録係の知らせだけを言う。
            # 心が「議事録、とりながら進めていますよ」と返し、そのあと知らせも言って 2 回になった（2026-10-30）
            debug_log.record('mind_route', why='on_board')
            return 'skip'
        return 'mind'

    def playing(self) -> bool:
        """体を受け持っていて、ゲームの中にいる"""
        return self.body is not None and self.body.playing()

    def _game_ask(self, text: str) -> bool:
        words = getattr(self.body, 'route_words', None) if self._body_linked() else None
        return bool(words is not None and words.search(text))

    def _ids(self, *roles: str) -> frozenset:
        return self.body.tool_ids(*roles) if self.body is not None else frozenset()

    def one_call_tools(self) -> frozenset:
        """1 つの返事で 1 つだけ通す道具（one_body_call）"""
        return self._ids('act') | GOAL_ONE

    def after_reply(self, done: bool) -> None:
        """返事を言い終えたあと：見せてもらった画像の話を終える"""
        if done and self.eyes is not None:
            self.eyes.reply_finished()

    def tools_for(self, chat_ctx: llm.ChatContext, tools: list) -> list:
        """心に見せる道具。会話の間は同じ一覧にする：Qwen の書式では道具の一覧が固定の指示より前に入るので、
        発言ごとに出し入れすると先頭からキャッシュが外れる。ゲームの体を受け持っていない間はゲームの道具を、
        配信のコメントへの返事ではコメントから使えない道具を見せない（どちらも会話の途中ではめったに変わらない）"""
        if not self._body_linked():
            hidden = set(self._ids('act', 'look', 'know')) | set(GOAL_TOOLS)
            tools = [t for t in tools if getattr(t, 'id', None) not in hidden]
        return toolbox.for_comments(tools) if self.from_comment else tools

    def refused_now(self, chat_ctx: llm.ChatContext) -> frozenset:
        """見せてはいるが、今回の返事では呼んでも実行しない道具（呼ばれたら断る。mind.only_given）。
        議事録を始める・終える道具は、今回の発言に頼みの言葉があるときだけ通す（付箋になった頼みは除く）。
        付箋で状態を渡しても、長い話のあとの「予算は去年と同じくらい」に、心が議事録を終える道具を 2 回とも呼んだ（2026-10-30）。
        道具の結果を受けた続きも同じに見る（会話を探す道具の続きで、また終える道具を呼んだ。2026-10-31）"""
        text = _user_text(_tail(list(chat_ctx.items)))
        if text and MINUTES_ASK.search(self._strip(text)):
            return frozenset()
        return frozenset(MINUTES_MOVES) | (frozenset() if getattr(self.minutes, 'recording', False) else {'get_minutes_status'})

    def _body_linked(self) -> bool:
        return self.body is not None and self.body.linked

    # ---- 文脈 ----

    def build(self, chat_ctx: llm.ChatContext, *, turn: dict | None = None) -> llm.ChatContext:
        """LiveKit が渡した会話（会話の指示＋LiveKit が持つ発言＋今回の分）から、送る会話を作る。
        turn（turns.py の pipeline_turn）の話者の 1 行・タッチは、今回の発言の前に置く（LiveKit の会話は書き換えない）"""
        items = list(chat_ctx.items)
        instructions = next((i for i in items if getattr(i, 'role', None) == 'system'), None)
        tail = [i for i in _tail(items) if i is not instructions]
        tail_users = {_text(i) for i in tail if _is_user(i)}
        turn = turn or {}
        out = llm.ChatContext()
        if instructions is not None:
            out.items.append(instructions)
        if self.self_image and not models.LOCAL_TEST:
            out.items.append(llm.ChatMessage(role='user', content=[
                '[わたしの姿]（わたし、シエルの見た目の絵。いつも知っている自分の姿）',
                llm.ImageContent(image=self.self_image, inference_detail='low')]))
        window = self._window()
        # 今回の発言として記録に入った分は、最後のシエルの返事より後ろの行だけ。それより前の同じ言葉
        # （2 回目の「うん」・同じ質問のくり返し）は過去の発言として残す：消すと履歴の途中が変わり、
        # そこから後ろのキャッシュが毎回外れた（2026-11-20）
        current = next((n for n in range(len(window), 0, -1) if window[n - 1].role == 'assistant'), 0)
        for n, t in enumerate(window):
            text = t.text[:TURN_CHARS]
            if t.role == 'user':
                if n >= current and any(text in u for u in tail_users):
                    continue   # 今回の発言（の切れ端）は、LiveKit の側の分を使う
                text = self._marked(text)
            out.add_message(**turn_message(t, text))
        notes = self._notes(deep=True, memory='\n\n'.join(x for x in (turn.get('memory'), turn.get('recall')) if x))
        self.handed = None
        if tail_users:
            # 切れ目を待っている知らせは、相手への返事の中で伝える。長い話の途中で聞く係が議事録を始めると、
            # 「とり始めた」は話し終わりまで待って約 26 秒後になり、最後の質問への答えになって議事録にふれなかった（2026-10-31）
            waiting = self._waiting()
            if waiting:
                self.handed, text = next(iter(waiting.items()))
                if text:
                    notes = '\n\n'.join(x for x in (notes, f'[まだ伝えていない知らせ]\n{text}') if x)
        if notes:
            out.add_message(role='system', content=notes)
        if self.eyes is not None:
            # 見ていない画像・画像を指した話のときだけ、この返事に画像を添える
            picture = self.eyes.message_for_reply(_user_text(tail))
            if picture is not None:
                out.items.append(picture)
        speaker = '\n'.join(x for x in (turn.get('tag'), turn.get('touch')) if x)
        if speaker and tail_users:
            out.add_message(role='system', content=speaker)   # 今回の発言の話者（とタッチ）
        out.items.extend(self._mark_item(i) for i in tail)
        return out

    def _waiting(self) -> dict[str, str]:
        return {w: t for w, t in (self.waiting() if self.waiting is not None else {}).items() if w in EVENT_REPLIES}

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

    def _rows(self):
        if self.history is None:
            return []
        return [t for t in self.history.turns if t.ready.is_set() and t.text and t.role in ('user', 'assistant', 'event')]

    def _recent(self, n: int):
        return self._rows()[-n:]

    def _window(self):
        """心に渡す最近の発言。始まりは WINDOW_MAX を超えたときだけ、まとめて WINDOW_KEEP 件まで進める：
        1 発言ごとにずらすと、履歴の先頭が毎回変わって、そこから後ろのキャッシュが全部外れる"""
        rows = self._rows()
        start = next((i for i, t in enumerate(rows) if t is self._window_first), None)
        if start is None or len(rows) - start > WINDOW_MAX:
            start = max(0, len(rows) - WINDOW_KEEP)
        self._window_first = rows[start] if rows else None
        return rows[start:]

    def _notes(self, deep: bool, memory: str | None = None) -> str:
        """今回の返事のための補足（会話の後ろ、今回の発言の前に置く）"""
        lines = [clock.now_line()]
        if self.brief:
            lines.append(self.brief)
        if self.board is not None:
            lines.append(self.board.context())   # 今どうなっているか（小脳も、していないことを言わないように読む）
        if self.eyes is not None:
            lines.append(self.eyes.context())    # 見せてもらった画像の説明文
        if self.body is not None:
            lines.append(self.body.context())    # マイクラの様子（小脳も、見ていないことを言わないように読む）
        if self.goals is not None:
            lines.append(self.goals.context())   # 今の目的（goals.py。小脳も、していないことを言わないように読む）
        if self.stream is not None:
            lines.append(self.stream.context())  # 配信中なら、視聴者がいること（youtube_chat.py）
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
        if models.LOCAL_TEST:
            import inference_activity
            if not inference_activity.activity.available():
                return
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


def only_given(chunk, fns: list, refused=frozenset(), *, target=None):
    """返事の流れから、今回渡した道具（fns）の呼び出しだけを通す。LiveKit は、送らなかった道具でも Agent の道具なら
    呼んでしまう（voice/agent_activity.py の tool_ctx は Agent の道具全部）。渡していない道具（コメントから使えない道具・
    絞った議事録の道具）を呼ばせないために、ここで落とす。（通す chunk, 落とした道具の名前）を返し、全部落として
    何も残らなければ chunk は None"""
    delta = None if isinstance(chunk, str) else getattr(chunk, 'delta', None)
    if delta is None or not delta.tool_calls:
        return chunk, []
    # refused：一覧には載せているが、今回は実行しない道具。多くの道具は実行の入口（execute_capability）から呼ばれるので、
    # target で入口の先の道具の名前に直して見る（capabilities.CapabilityCatalog.target）
    given = {getattr(t, 'id', None) for t in fns}
    name = target or (lambda c: c.name)
    ok = lambda c: c.name in given and name(c) not in refused   # noqa: E731
    kept = [c for c in delta.tool_calls if ok(c)]
    dropped = [name(c) for c in delta.tool_calls if not ok(c)]
    if not dropped:
        return chunk, []
    if not kept and not delta.content and getattr(chunk, 'usage', None) is None:
        return None, dropped
    return chunk.model_copy(update={'delta': delta.model_copy(update={'tool_calls': kept})}), dropped


def one_body_call(chunk, taken: list, moving=frozenset(), *, target=None):
    """1 つの返事で、体を動かす道具（体の道具・目的の道具）は 1 つだけ通す。体の技は一度に 1 つなので、同時に呼ぶと
    取り合いになって両方失敗した（集めると作るを同時に呼んだ。2026-11-07）。taken は、この返事ですでに通した呼び出しの名前。
    moving は 1 つだけ通す道具の名前（Mind.one_call_tools）。
    （通す chunk, 落とした道具の名前）を返し、全部落として何も残らなければ chunk は None"""
    delta = None if isinstance(chunk, str) else getattr(chunk, 'delta', None)
    if delta is None or not delta.tool_calls:
        return chunk, []
    kept, dropped = [], []
    for c in delta.tool_calls:
        name = target(c) if target is not None else c.name
        if name in moving and any(n in moving for n in taken):
            dropped.append(name)
            continue
        taken.append(name)
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


def _event_fact(text: str) -> str:
    """記録した出来事のうち、会話に渡すのは事実の一文だけ（ID・時刻・観測値はモデルに要らない）"""
    try:
        return json.loads(text).get('fact') or text
    except (ValueError, AttributeError):
        return text


def turn_message(turn, text: str) -> dict:
    """記録の 1 件を、会話モデルへ渡す 1 件にする（心と、外部の実行クライアントに渡す文脈で同じ形）。
    人の発言は「名前：発言」、出来事は事実の一文の system（ローカルでは local_context が SYSTEM: にする）"""
    if turn.role == 'user':
        return {'role': 'user', 'content': f'{turn.name}：{text}'}
    if turn.role == 'event':
        return {'role': 'system', 'content': _event_fact(text)}
    return {'role': 'assistant', 'content': text}


# Qwen rejects system messages after the first one. Notes keep their place as
# user turns with the source marker Mindcraft uses for the same constraint; a
# plain sentence after it reads as data rather than as a document to annotate.
NOTE_PREFIX = 'SYSTEM: '


def local_context(ctx: llm.ChatContext, source: llm.ChatContext | None = None, *, trailing_notes: bool = True) -> llm.ChatContext:
    """固定systemと時系列の内部補足を送る。Falseは従来方式との比較用。元の記録は変えない。"""
    out = llm.ChatContext()
    # Recover the real request before converting notes: an internal event must
    # not masquerade as evidence that the original user request is present.
    missing_user = not any(_is_user(i) for i in ctx.items)
    if trailing_notes:
        for index, item in enumerate(ctx.items):
            if index > 0 and isinstance(item,llm.ChatMessage) and item.role == 'system':
                out.add_message(role='user',content=NOTE_PREFIX+(item.text_content or ''))
            else:
                out.items.append(item)
    else:
        instructions=[i.text_content for i in ctx.items if isinstance(i,llm.ChatMessage) and i.role=='system']
        if instructions:out.add_message(role='system',content='\n\n'.join(instructions))
        out.items.extend(i for i in ctx.items if not (isinstance(i,llm.ChatMessage) and i.role=='system'))
    if missing_user and source is not None:
        # 文字入力の記録が確定するより先に道具の結果が戻ることがある。
        # Qwen の tool continuation にも、LiveKit が持つ元の依頼を添える。
        latest = next((i for i in reversed(source.items) if _is_user(i)),None)
        if latest is not None:
            out.items.insert(1 if out.items and getattr(out.items[0],'role',None)=='system' else 0,latest)
    if not any(_is_user(i) for i in out.items):
        notice=next((i.text_content for i in reversed(ctx.items) if isinstance(i,llm.ChatMessage) and i.role=='system' and i.text_content),None)
        out.add_message(role='user',content='' if trailing_notes else notice or '')
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

