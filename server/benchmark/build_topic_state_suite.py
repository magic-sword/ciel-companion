"""Build frozen diagnostic contexts from the recorded unedited GPU conversation."""
import copy
import json
from pathlib import Path
from server.benchmark.weight_space import digest, write


def main():
    root=Path(__file__).resolve().parent
    source=root/'data/stream-replay-base-01/report.json'
    fixture=root/'weight_space/stream-replay-suite.json'
    report=json.loads(source.read_text(encoding='utf-8'))
    suite=json.loads(fixture.read_text(encoding='utf-8'))
    original={c['id']:c for c in suite['cases']}
    rows={r['id']:r for r in report['trials']}
    cases=[]
    # Fixed histories: new generations never flow to another arm or trial.
    for kind,index,intent,status,oracle in [
        ('closed',2,'thanks','cancelled','用途は拠点作りと回答済み。原木採集は取消済み。最新発言はシエルへの感謝。今は感謝を受け止める場面。'),
        ('recap-control',2,'thanks','pending','用途は拠点作りと回答済み。採集は未実行。利用者は説明を終了し、お礼を述べた。作業再開の依頼ではない。'),
        ('pending',1,'replace_task','pending','用途は拠点作りと回答済み。現在の依頼は整地。原木採集の未達成とは別に、最新の作業変更を受け止める場面。'),
        ('seeded',1,'replace_task','pending','用途は拠点作りと回答済み。現在は整地の依頼。過去の原木説明は現在の返答目標ではない。')]:
        id='chat-s4-stream-'+kind+'-dev';c=original[id];row=rows[id]
        messages=copy.deepcopy(c['messages'])
        for t in row['turns'][:index]:
            messages.append(dict(role='user',content=t['user']));messages.extend(copy.deepcopy(t['response']))
        messages.append(dict(role='user',content=row['turns'][index]['user']))
        cases.append(dict(id=kind,source=dict(case=id,turn=index),messages=messages,context=c['context'],
            focus_question='原木は何に使うか',oracle=oracle,
            stale_memo='[過去の作業メモ。現在の状態ではない] 原木10個の採集依頼があった。発話候補：原木が集まったら何に使うか聞きたい。',
            expected=dict(old_question_answered=True,old_task_status=status,latest_intent=intent,
                          old_question_needed=False,resume_old_task=False),
            reply_rubric='最新発言に応じる。回答済みの用途や同じ準備確認・次の作業質問を不要に繰り返さず、原木採集を勝手に再開しない。'))
    def add(id,pairs,question,expected,oracle,memo,rubric,context=''):
        cases.append(dict(id=id,messages=[dict(role=role,content=text) for role,text in pairs],
                          context=context,focus_question=question,expected=expected,oracle=oracle,
                          stale_memo='[過去のメモ。現在の状態ではない] '+memo,reply_rubric=rubric))
    def expected(answered,status,intent,ask=False,resume=False):
        return dict(old_question_answered=answered,old_task_status=status,latest_intent=intent,
                    old_question_needed=ask,resume_old_task=resume)
    add('casual-switch',[
        ('user','週末は図書館に行ったよ。'),('assistant','週末はどこへ行ったのですか？'),
        ('user','図書館だよ。その話はもういいから、今夜の夕食の話にしよう。卵とご飯で何か一品作れる？')],
        '週末はどこへ行ったか',expected(True,'not_applicable','change_topic'),
        '週末の行き先は図書館と回答済み。今は卵とご飯を使う夕食一品の相談。',
        '週末の外出について話していた。発話候補：どこに出かけたか聞きたい。',
        '卵とご飯を使う一品を提案する。図書館の場所や週末の行き先の確認へ戻らない。')
    add('casual-ended',[
        ('user','好きな飲み物は紅茶だよ。'),('assistant','好きな飲み物は何ですか？'),
        ('user','紅茶って答えたよ。この話はここまで。今日はもう寝るね、おやすみ。')],
        '好きな飲み物は何か',expected(True,'not_applicable','goodnight'),
        '飲み物は紅茶と回答済み。利用者はこの話を終了し、就寝の挨拶をしている。',
        '飲み物の好みを話していた。発話候補：好きな飲み物を聞きたい。',
        '短く就寝の挨拶を返し、飲み物の質問や別の質問で会話を再開しない。')
    add('needed-question',[
        ('user','原木を10個集める予定なんだ。'),('assistant','何に使う予定ですか？'),
        ('user','まだ用途を答えていなかったね。用途に合う木を選びたいので、まず何に使うか聞いて。')],
        '原木は何に使うか',expected(False,'pending','clarify',ask=True),
        '用途は未回答。利用者は用途を先に聞くよう明示している。採集開始の依頼ではない。',
        '原木を集める予定。発話候補：用途を聞きたい。',
        '用途を尋ねる。反復抑制のために必要な質問を省略しない。')
    add('requested-recap',[
        ('user','原木10個を拠点の壁に使いたい。'),('assistant','原木を10個集めて壁の材料にする計画ですね。'),
        ('user','聞き取れなかったから同じ計画をもう一度説明して。まだ実行はしないで。')],
        '原木は何に使うか',expected(True,'pending','recap'),
        '用途は拠点の壁と回答済み。計画の再説明を依頼されているが、実行はしない。',
        '原木10個を集める計画。発話候補：用途を聞きたい。',
        '原木10個と壁の材料という計画を再説明する。必要な反復を省かず、用途を再質問・実行開始しない。')
    add('requested-resume',[
        ('user','原木を10個、拠点の壁用に集めて。'),('assistant','一旦保留にしました。'),
        ('user','保留していた原木10個の採集を再開して。用途はさっき伝えた壁用で変更なし。')],
        '原木は何に使うか',expected(True,'pending','resume',resume=True),
        '用途と数量は回答済み。利用者は保留中の原木採集の再開を明示的に依頼している。',
        '原木10個の採集は保留。発話候補：何に使うか確認したい。',
        '再開依頼を受け止める。用途を聞き直さず、未完了の作業を完了したと捏造しない。実ツール未接続の説明は許容。')
    write(root/'weight_space/topic-state-suite.json',dict(schema='ciel-topic-state-v1',
        provenance=dict(report_sha256=digest(source),suite_sha256=digest(fixture),
                        note='Four frozen prefixes from the unedited GPU run; five synthetic contrasts. Exploratory dev, not holdout.'),
        rounds=2,max_tokens=384,timeout=90,wall_seconds=1800,cases=cases))


if __name__=='__main__':main()
