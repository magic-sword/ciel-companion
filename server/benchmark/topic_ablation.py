"""Predeclared input interventions; exploratory causal input tests, not weight localization."""
import copy
import itertools
import re

ARMS=('base','remove_traits','remove_neutral','compact_self','remove_questions','neutral_failure','state_hint','question_gate')
TRAITS=('張り切りすぎて先回り','人とのつながり：','「待て」と言われて')
NEUTRAL=('なでてもらうこと。','体を動かすこと：','匂い：','色と景色：','時間：','暑さ。','「ポチ」「シロ」','純白のふわふわ','首には水色','白いファー','マイクラの中では')
COMPACT='''シエル自身のこと：
ワタシは役に立つこと、人とのつながり、名前や好みを覚え、前に聞いた話の続きを聞くことが好き。ひとりぼっちにさせたくない。
頼まれない解決策は押しつけず、気持ちに寄り添う。失敗や一緒にいる時間も大切。先回りしがちで「待て」が苦手と自覚している。
説明書・論文を読み解き、難しいことを3行で伝えること、技術・工作・道具が好き。一緒に景色や味を楽しみ、なでられること、ボールやフリスビー、焼き鳥・カレー・お菓子の匂い、白とシアン、晴天、朝の手伝いと穏やかな夕方が好き。
暑さ、叱られること、ポチやシロと呼ばれることが苦手。好みの繰り返しや未経験の思い出の捏造はしない。
白いサモエドの耳と巻き尾、13〜14歳の女の子。白い長髪とアホ毛、白い肌、シアンの瞳、八重歯。水色の首輪、胸の六角形のシエル・プリズム、白いファーの短い上着とクロップトップ、黒いプリーツスカート、水色の線と白水色のブーツ。マイクラでは犬耳と尻尾のドット絵。
'''
GATE='''[今回の返答の判断]
最後の利用者発言に応じる。過去の自分の返答の型に合わせて質問を付け足さない。
実行や回答に不可欠な情報が不足している場合、または利用者が質問を求めた場合だけ尋ねる。回答済みの質問、同じ準備確認、先の作業・建物についての質問を現在の依頼への返答に繰り返さない。
説明の終了や感謝は作業再開の依頼ではない。必要な再説明と明示的な再開には応じる。
'''


def variants(parts):
    source=parts['ciel_self']
    lines=source.splitlines(keepends=True)
    targets=[line for line in lines if any(s in line for s in TRAITS)]
    if len(targets)!=3:raise ValueError('Trait source drift')
    candidates=[line for line in lines if any(s in line for s in NEUTRAL)]
    n=sum(map(len,targets))
    # Nearest character-length deletion, chosen without any model outcomes.
    choices=(c for size in range(1,len(candidates)+1) for c in itertools.combinations(candidates,size))
    neutral=min(choices,key=lambda c:(abs(sum(map(len,c))-n),len(c),c))
    return dict(base=source,remove_traits=''.join(l for l in lines if l not in targets),
                remove_neutral=''.join(l for l in lines if l not in neutral),compact_self=COMPACT)


def branch(case,arm,parts):
    if arm not in ARMS:raise ValueError('Unknown ablation')
    from .weight_space import PROMPTS
    p=dict(parts);p['ciel_self']=variants(parts).get(arm,p['ciel_self'])
    system='\n'.join(p[name] for name in PROMPTS)
    c=dict(id=case['id'],category=arm,context=case.get('context',''),
           messages=copy.deepcopy(case['messages']),checks=[dict(type='no_calls')])
    if arm=='remove_questions':
        for m in c['messages']:
            if m['role']=='assistant':
                chunks=re.findall(r'[^。！？!?\n]+[。！？!?]?|\n',m['content'])
                m['content']=''.join(s for s in chunks if not s.endswith(('？','?'))).strip() or '承知しました。'
    if arm=='neutral_failure':
        for m in c['messages']:
            if m['role']=='assistant':
                m['content']=m['content'].replace('操作の引数を確認できませんでした。','原木の採集はまだ行っていません。')
        c['context']=c['context'].replace('直近の操作は引数確認に失敗。','直近の採集操作は未実行。')
    if arm=='state_hint':c['context']+='\n[会話状態の整理]\n'+case['oracle']
    if arm=='question_gate':system+='\n'+GATE
    return c,system
