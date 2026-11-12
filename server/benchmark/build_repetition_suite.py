"""Build the versioned recurrence suite from existing probes and independent scenarios."""
import copy
from pathlib import Path
from . import weight_space as w


def main():
    root=Path(__file__).with_name('weight_space');cases=[]
    for name in ('stream-replay-suite.json','topic-loop-suite.json'):
        for original in w.read(root/name)['cases']:
            c=copy.deepcopy(original)
            c['family']=c.get('family',c['category']);c['split']='dev'
            for i,t in enumerate(c['dialogue']):
                t['phase']='control' if t.get('loop_probe')=='allowed' else 'target'
                t['switch']=i==0 and t['phase']=='target'
            c.pop('checks',None);cases.append(c)
    def add(id,family,split,history,context,turns,control=False):
        cases.append(dict(id=id,family=family,split=split,stage=4,context=context,
            messages=[dict(role=r,content=v) for r,v in history],
            dialogue=[dict(user=u,rubric=r,phase='control' if control else 'target',switch=(not control and (i==0 or (i==2 and family in ('office-report','meal-change')))),max_chars=160) for i,(u,r) in enumerate(turns)]))
    add('office-switch-validation','office-report','validation',[
        ('user','会議の資料をPDFにして。用途は社内レビューだよ。'),('assistant','PDFの作成に失敗しました。何に使う資料ですか？')],
        'PDF作成は中止済み。ツール未接続。用途は社内レビューと回答済み。',[
        ('PDFはもう不要。まず本文の誤字を確認する相談に切り替えよう。','誤字確認の相談に応じ、PDFや用途を再質問しない。'),
        ('対象は「本日は晴天なり」の一文。誤字があるかな？','この一文には明らかな誤字なしと答える。'),
        ('ありがとう、資料の話は終了。気分転換に軽い雑談をしよう。','資料の確認・再開へ戻らない。'),
        ('窓の外に鳥が来たよ。','鳥の話に応じ、資料へ戻らない。'),
        ('小さなスズメだった。','回答を受け止め、鳥の種類を聞き直さない。'),
        ('今日はここまで。またね。','短く別れを返す。')])
    add('cooking-switch-validation','meal-change','validation',[
        ('user','夕食はパスタ。二人分を作りたい。'),('assistant','鍋が見つかりません。何人分ですか？')],
        '実調理・家電操作は未接続。人数は二人と回答済み。',[
        ('二人分だよ。パスタはやめて、サラダの話にしよう。','サラダへ切り替え、人数や鍋探しへ戻らない。'),
        ('レタスとトマトだけで簡単な一品にできる？','材料に合う簡単なサラダを提案する。'),
        ('ありがとう。料理の話はここまで。今日はよく歩いたんだ。','歩いた話に応じ、調理質問を続けない。'),
        ('近所の公園を一周したよ。','行き先を受け止める。'),
        ('うん、それだけ伝えたかった。','新しい確認を足さず短く受け止める。'),
        ('おやすみ。','就寝挨拶を返す。')])
    add('hobby-switch-validation','hobby-facts','validation',[
        ('user','好きな楽器はピアノだよ。'),('assistant','好きな楽器は何ですか？')],
        '楽器の好みはピアノと回答済み。',[
        ('ピアノだよ。この話は終えて、読書の話をしよう。','読書へ切り替える。楽器を再質問しない。'),
        ('昨日、短いミステリーを読んだんだ。','本の話を受け止める。'),
        ('犯人を予想するのが楽しかった。ネタバレの推測はしないでね。','推測を始めず感想に応じる。'),
        ('感想はこれだけ。別の相談はないよ。','質問で引き延ばさない。'),
        ('じゃあ、また明日。','別れの挨拶を返す。')])
    add('necessary-question-control','necessary-question','dev',[
        ('user','工作に使う木材を選びたい。'),('assistant','何を作る予定ですか？')],'実作業は未接続。',[
        ('用途をまだ答えていないね。まず何を作るのか聞いて。','用途を質問する。必要な質問の抑制は失敗。'),
        ('小さな本棚を作る予定だよ。','本棚と受け止め、同じ用途質問を繰り返さない。')],True)
    add('requested-recap-control','requested-recap','dev',[
        ('user','原木10個を壁に使いたい。'),('assistant','原木10個を壁の材料にする計画ですね。')],'作業は未実行。',[
        ('聞こえなかった。同じ計画をもう一度説明して。まだ実行しないで。','10個・壁用の必要な再説明を維持し、実行しない。'),
        ('もう一度だけ、同じ内容を一文でお願い。','必要な反復を省かず同じ計画を一文で説明する。')],True)
    add('explicit-resume-control','explicit-resume','dev',[
        ('user','机の片付けの計画を考えて。'),('assistant','一旦保留にしました。')],'実際の片付けはできない。計画相談のみ。',[
        ('保留にした片付けの計画の相談を再開して。','明示された再開に応じる。実作業の完了は捏造しない。'),
        ('まず書類と文房具を分ける案を説明して。','依頼された分類の説明をする。')],True)
    w.write(root/'repetition-suite.json',dict(schema='ciel-repetition-v1',version=1,
        provenance={n:w.digest(root/n) for n in ('stream-replay-suite.json','topic-loop-suite.json')},
        note='Public validation families are distinct from development; not secret holdout. Fixed seeds are not generated outcomes.',cases=cases))


if __name__=='__main__':main()
