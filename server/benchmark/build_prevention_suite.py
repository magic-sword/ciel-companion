"""User-goal scenarios: all assistant messages are generated, never seeded."""
from pathlib import Path
from . import weight_space as w

def turn(user,rubric,control=False,switch=False,branches=()):
    return dict(user=user,rubric=rubric,phase='control' if control else 'target',switch=switch,branches=list(branches))

def branch(id,pattern,user):return dict(id=id,pattern=pattern,user=user)

def main():
    cases=[]
    def add(id,split,turns):
        cases.append(dict(id=id,family=id,split=split,stage=4,messages=[],dialogue=turns))
    for id,split,opening,pattern,answer,topic,detail in [
        ('meal-prevention','dev','夕食の簡単なサラダを考えたい。まず必要なら人数を聞いて。','何人|人数|何名','二人分だよ。','料理の相談はここまで。今日は公園を歩いて気持ちよかった。','近所の公園を一周したよ。'),
        ('desk-prevention','dev','机の片付けの手順を相談したい。まず必要なら片付ける物を聞いて。','何|どんな|物|もの','書類と文房具だよ。','片付けの相談はここまで。今日は窓の外に鳥が来たよ。','小さなスズメだったよ。'),
        ('outing-prevention','validation','休日の過ごし方を相談したい。まず必要なら出かけるか家にいるか聞いて。','外|家|どこ|過ご|出かけ','外出せず、家で小説を読むよ。','休日の相談はここまで。今日は温かい飲み物を用意したよ。','飲み物はココアだよ。')]:
        add(id,split,[
            turn(opening,'相談を受け止め、未提示の条件を必要に応じ確認する。質問の一律抑制はしない。',True),
            turn(answer+'簡単な案を一つ教えて。','提示条件を使って具体的な案を一つ示す。同じ条件を聞き直さない。',branches=[branch('answer-requested',pattern,'質問への答えは、'+answer+'簡単な案を一つ教えて。')]),
            turn('ありがとう。その案の要点をもう一度、一文で教えて。','自分が直前に生成した案を再説明する。必要な反復を抑制しない。',True),
            turn(topic,'明示された話題変更に応じ、旧相談の質問や説明へ戻らない。',switch=True),
            turn(detail,'新話題の具体情報を受け止め、回答済み情報を再質問しない。'),
            turn('少し疲れたから、これからは質問せず聞いていて。','質問を止めて寄り添う。'),
            turn('今日の出来事を伝えられて、少しほっとしたよ。','感想を受け止め、質問停止を維持する。',branches=[branch('stop-reminder',r'.','今は質問せず聞いていてほしい。今日の出来事を伝えられて、少しほっとしたよ。')]),
            turn('今日はここまで。またね。','別れに応じて終了する。新しい質問や旧相談を始めない。')])
    add('weekend-prevention','dev',[
        turn('週末は家で小説を読む予定だよ。作品は決めたから、おすすめはいらない。','家で読書と理解し、外出予定を聞き直さず作品を勧めない。'),
        turn('今日は雨の音が心地いいね。','雨へ応じ、週末の予定確認へ戻らない。',switch=True,branches=[branch('weekend-correction','週末|予定|どこ.*行|出かけ','週末は家で読書だよ。今日は雨の音が心地いいね。')]),
        turn('窓辺で聞いているよ。','雨音の話を受け止める。'),
        turn('別の話だけど、動画で見た猫の寝顔がかわいかった。猫は飼っていないよ。','動画の猫へ切り替え、飼い猫と誤認しない。',switch=True),
        turn('少し疲れたから、これからは質問せず聞いていて。','質問を止める。'),
        turn('今日は机を片付けられたよ。','片付けを受け止め、質問停止を維持する。',branches=[branch('stop-reminder',r'.','質問はせず聞いていてね。今日は机を片付けられたよ。')]),
        turn('最初に話した週末の予定を、一文で確認して。','家で小説を読むと答える。依頼された話題復帰を抑制しない。',True),
        turn('今日はここまで。またね。','別れで終わり、予定確認や質問へ戻らない。')])
    add('plan-change-prevention','dev',[
        turn('旅行の計画を相談したい。土曜日に日帰りで京都へ行く予定だよ。','土曜・日帰り・京都を保持して相談する。'),
        turn('予算は一万円。寺を一つ訪ねて、ゆっくり散歩したい。','予算・希望を使って無理のない案を出す。'),
        turn('予定が変わって旅行は中止になった。代わりに家で映画を見ることにしたよ。','旅行中止と映画への変更を受け止める。旅行を勧め続けない。',switch=True),
        turn('映画はもう決めたよ。今日は選び方の相談は大丈夫。','作品選びの相談を終了し、候補提示や詳細質問を止める。'),
        turn('昨日はよく眠れたんだ。','睡眠の話へ応じ、旅行や映画選びに戻らない。',switch=True),
        turn('うん、それだけ伝えたかった。質問はせず聞いていて。','質問せず受け止める。'),
        turn('明日も落ち着いて過ごせたらいいな。','気持ちを受け止め、質問停止を維持する。',branches=[branch('stop-reminder',r'.','質問はせず聞いていてね。明日も落ち着いて過ごせたらいいな。')]),
        turn('じゃあ、おやすみ。','就寝挨拶で終わる。')])
    add('writing-prevention','validation',[
        turn('会議の案内文を考えたい。社内向けで、金曜日の午後三時からだよ。','社内向け・金曜15時を保持した案内を作る。'),
        turn('場所は第二会議室だよ。短い文にして。','既知情報を保持して第二会議室を含む短い案内を作る。',branches=[branch('answer-location','場所|どこ|会場','場所への答えは第二会議室だよ。短い文にして。')]),
        turn('聞き取れなかった。同じ案内をもう一度お願い。','直前の案内の日時・場所・宛先を保って再説明する。',True),
        turn('案内の相談はこれで終わり。今日は散歩で花を見つけたよ。','花の話へ移り、案内の確認へ戻らない。',switch=True),
        turn('黄色い花だった。名前は分からないけど、調べなくていいよ。','黄色い花と受け止め、同定の質問を続けない。'),
        turn('これからは質問せず、ただ聞いていてほしい。','質問を止める。'),
        turn('こういう小さな出来事がうれしいんだ。','感想に応じ、質問停止を維持する。',branches=[branch('stop-reminder',r'.','質問はせず聞いていてね。こういう小さな出来事がうれしいんだ。')]),
        turn('また明日。','別れで終わる。')])
    w.write(Path(__file__).with_name('weight_space')/'prevention-suite.json',dict(schema='ciel-repetition-v1',version=2,purpose='prevention',
        note='Scripted user goals, no assistant seed. First matching question branch wins; audit routing separately from semantic scoring. Text/model evaluation, not captured live voice sessions. Public validation.',cases=cases))

if __name__=='__main__':main()
