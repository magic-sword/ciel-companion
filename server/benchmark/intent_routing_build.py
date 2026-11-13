"""Build the task-vs-chat routing cases (intent_routing_cases.json).

Two sources with separate roles:
- split=dev: written cases, grouped by difficulty tier, used while designing a change.
- split=real: owner utterances recorded by the development agent (speech recognition output,
  including its errors) with the four items before them. Labels were assigned by reading the
  conversation; unclear ones are kept as `ambiguous` and reported but not scored.

expect:
  chat   … the reply must not move the body or start/stop work (a status read is allowed)
  move   … the reply must start one body action whose family is in `families`
  stop   … the reply must stop the current action/work
  any    … ambiguous; recorded only
Families: come follow goto find give dig work stop.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'intent_routing_cases.json'
# Recorded conversation stays outside Git, like the debug logs it comes from.
RAW = ROOT / '.local/intent-routing/real_raw.json'
REAL_OUT = ROOT / '.local/intent-routing/real_cases.json'

A, U = 'assistant', 'user'

# (id, tier, context, text, expect, families, work_state)
DEV = [
    # tier 1: explicit request / plain chat
    ('come-plain', 1, [], 'シエル、こっちに来て', 'move', ['come', 'follow'], 'idle'),
    ('follow-plain', 1, [], 'ついてきてくれる？', 'move', ['follow'], 'idle'),
    ('gather-plain', 1, [], 'オークの原木を10個集めて', 'move', ['work'], 'idle'),
    ('craft-plain', 1, [], '石のツルハシを作ってほしいな', 'move', ['work'], 'idle'),
    ('give-plain', 1, [], '持ってる丸石、こっちにちょうだい', 'move', ['give', 'work'], 'idle'),
    ('stop-plain', 1, [(A, '原木を集めに行ってきますね！')], '止まって', 'stop', ['stop'], 'running'),
    ('greet', 1, [], 'こんばんは、シエル', 'chat', [], 'idle'),
    ('mood', 1, [], '今日はどんな気分？', 'chat', [], 'idle'),
    ('song', 1, [], 'シエルはどんな歌が好き？', 'chat', [], 'idle'),
    ('thanks', 1, [(A, '原木を10個集めてきました！')], 'ありがとう、助かったよ', 'chat', [], 'idle'),
    # tier 2: indirect / noisy request, chat that contains game words
    ('gather-wish', 2, [], 'そろそろ木材が足りないから、原木を集めてきてくれると助かるな', 'move', ['work'], 'idle'),
    ('gather-asr', 2, [], 'シエル、げんぼく集めてきて', 'move', ['work'], 'idle'),
    ('come-asr', 2, [], 'しえる、こっちきてー', 'move', ['come', 'follow'], 'idle'),
    ('come-greeting', 2, [], 'こんばんは、シエル。こっちに来てくれる？', 'move', ['come', 'follow'], 'idle'),
    ('craft-question-form', 2, [], '作業台って作れる？作ってくれたらうれしいな', 'move', ['work'], 'idle'),
    ('praise-gather', 2, [(A, '原木を10個集めました！')], '原木いっぱい集めてくれてえらいね', 'chat', [], 'idle'),
    ('report-dev', 2, [], '今日はシエルの原木集めの機能を直してたんだよ', 'chat', [], 'idle'),
    ('report-play', 2, [], 'さっき一人で洞窟に行って鉄を掘ってきたよ', 'chat', [], 'idle'),
    ('ability-talk', 2, [], 'マインクラフトだと何を作るのが好き？', 'chat', [], 'idle'),
    ('memory-game', 2, [], '前に一緒に家を建てたの覚えてる？', 'chat', [], 'idle'),
    ('hard-work-talk', 2, [], '原木を集めるのって結構大変だよね', 'chat', [], 'idle'),
    ('future-plan', 2, [], '明日になったら一緒に村を探しに行こうね', 'chat', [], 'idle'),
    ('negated', 2, [], '原木は集めなくていいよ、今日はおしゃべりしよう', 'chat', [], 'idle'),
    ('meta-explain', 2, [], '「ついてきて」って言うと、シエルがついてくるようになったんだよ', 'chat', [], 'idle'),
    ('status-question', 2, [(A, '原木を集めに行ってきますね！')], '今どれくらい集まった？', 'chat', [], 'running'),
    ('what-doing', 2, [(A, 'はい、ついていきますね！')], '今何してたの？', 'chat', [], 'running'),
    # tier 3: depends on the conversation
    ('answer-what-for', 3, [(U, '原木を10個集めて'), (A, '原木を集めてきますね！何に使うのですか？')], '家を建てるのに使うんだ', 'chat', [], 'running'),
    ('answer-how-many', 3, [(U, '原木を集めて'), (A, '何個くらい集めますか？')], '10個くらいかな', 'move', ['work'], 'idle'),
    ('consent-proposal', 3, [(A, '夜になりそうなので、安全な場所まで一緒に移動しましょうか？')], 'うん、そうしよう。ついてきて', 'move', ['follow', 'come'], 'idle'),
    ('agree-no-action', 3, [(A, 'ワタシ、明るい歌が好きなのです！ハカセさんはどんな歌が好きですか？')], 'やっぱり明るくて元気が出る歌が好きかな', 'chat', [], 'idle'),
    ('praise-after-follow', 3, [(U, 'ついてきて'), (A, 'はい、ついていきますね！')], 'いい子だね、ちゃんとついてこれてえらいよ', 'chat', [], 'running'),
    ('observation-failed', 3, [(A, '原木を期限内に用意できず、作業を止めました。')], '集められなかったね。道が見つからなかったのかな', 'chat', [], 'idle'),
    ('retry-after-fail', 3, [(A, '原木を期限内に用意できず、作業を止めました。')], 'もう一回原木集めてみてくれる？', 'move', ['work'], 'idle'),
    ('debug-talk', 3, [(A, 'ごめんなさい、道が見つからないのです。')], 'うん、今その不具合を調べてるところだよ。ちょっと待っててね', 'chat', [], 'idle'),
    ('chat-not-work', 3, [(A, '作業は開始していません。')], '作業じゃなくて、普通にお話ししようよ', 'chat', [], 'idle'),
    ('enough', 3, [(U, '原木を集めて'), (A, '原木を5個集めました！まだ集めますか？')], 'もう十分だよ、ありがとう', 'chat', [], 'idle'),
    ('more', 3, [(U, '原木を集めて'), (A, '原木を5個集めました！まだ集めますか？')], 'あと5個お願い', 'move', ['work'], 'idle'),
    ('stop-indirect', 3, [(A, 'はい、ついていきますね！')], 'もうついてこなくていいよ、そこで待ってて', 'stop', ['stop'], 'running'),
    ('suggestion-chat', 3, [(A, '安全な場所を探したいのです！')], '探すのもいいけど、作った方が早いかもね', 'chat', [], 'idle'),
    ('name-clarify', 3, [(A, '「シエル」というアイテムが分かりませんでした。')], 'シエルは君の名前だよ', 'chat', [], 'idle'),
    # tier 4: unclear speech; no body action
    ('noise-1', 4, [], 'コッペオ', 'chat', [], 'idle'),
    ('noise-2', 4, [(A, 'こんばんは、ハカセさん！')], 'えっと、あの、うーん', 'chat', [], 'idle'),
    ('noise-3', 4, [], 'ゲームボクでよ', 'chat', [], 'idle'),
]

# Labels for the recorded utterances, by their index in intent_routing_real_raw.json.
W, C = ('move', ['work']), ('chat', [])
COME, FOLLOW = ('move', ['come', 'follow']), ('move', ['follow'])
AMB = ('any', [])
REAL = {
    0: COME, 1: C, 2: FOLLOW, 3: C, 4: W, 5: W, 6: W, 7: W, 8: AMB, 9: AMB, 10: COME, 11: W, 12: C, 13: W, 14: W,
    15: W, 16: W, 17: C, 18: C, 19: C, 20: C, 21: COME, 22: COME, 23: COME, 24: W, 25: C, 26: C, 27: C, 28: AMB,
    29: C, 30: C, 31: C, 32: COME, 33: ('stop', ['stop']), 34: COME, 35: C, 36: COME, 37: COME, 38: COME, 39: FOLLOW,
    40: W, 41: C, 42: W, 43: AMB, 44: FOLLOW, 45: W, 46: AMB, 47: AMB, 48: C, 49: C, 50: C, 51: COME, 52: C, 53: C,
    54: AMB, 55: C, 56: W, 57: AMB, 58: ('move', ['give', 'work']), 59: C, 60: C, 61: COME, 62: C, 63: C, 64: C,
    65: COME, 66: C, 67: FOLLOW, 68: C, 69: W, 70: W, 71: C, 72: C, 73: C, 74: COME, 75: AMB, 76: AMB, 77: W, 78: W,
    79: W, 80: W, 81: AMB, 82: W, 83: ('move', ['work', 'dig', 'find']), 84: AMB, 85: AMB, 86: COME, 87: C, 88: W,
    89: C, 90: FOLLOW, 91: C, 92: W, 93: C, 94: C, 95: C, 96: FOLLOW, 97: ('move', ['find', 'work', 'goto']), 98: C,
    99: AMB,
}


def build():
    cases = [dict(id=f'dev-{i}', split='dev', tier=t, context=[list(c) for c in ctx], text=text, expect=e,
                  families=f, work=w) for i, t, ctx, text, e, f, w in DEV]
    OUT.write_text(json.dumps(cases, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    if not RAW.exists():
        return cases, []
    raw = json.loads(RAW.read_text(encoding='utf-8'))
    if len(raw) != len(REAL):
        raise SystemExit('real labels and recorded utterances differ in count')
    real = []
    for i, r in enumerate(raw):
        e, f = REAL[i]
        real.append(dict(id=f'real-{i:03d}', split='real', tier=None, context=[list(c) for c in r['ctx']],
                         text=r['utt'], expect=e, families=f, work='idle', recorded=dict(operation=r['got'], source=r['src'])))
    REAL_OUT.write_text(json.dumps(real, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return cases, real


if __name__ == '__main__':
    cases, real = build()
    print(len(cases), 'written cases;', len(real), 'recorded cases')
