# 声で人を覚える仕組みの改善：調べたこと

日付：2026-10-25（日本時間）。きっかけ：複数人で使うと、短い名乗り・「いいよ」が本人の声として使われず、同意の聞き直しが続いた（[話者の識別の決定記録](decisions/speaker-identification-ja.md)）。短い声で本人を確かめられないことが分かったので、論文・製品の事例・法律の考え方を調べた。

## 1. 短い声で本人を確かめるのは、今のモデルでは難しい

| 調べたこと | 分かったこと |
|---|---|
| ECAPA-TDNN（今使っているモデル）の短い声での精度 | VoxCeleb1-O の試験で、誤り率（EER）は 3 秒で 2.4%、1 秒で 18.4%。1 秒の声で学習し直しても 10.3%（[Beyond Short Segments, Interspeech 2026](https://arxiv.org/pdf/2609.25007)）。学習済みの ECAPA で、1 秒 7.0%・1.5 秒 3.0%・2 秒 2.3% とする報告もある（[VoiceExtender](https://arxiv.org/pdf/2310.04681)）。0.5 秒前後の「いいよ」は、さらに短い |
| 短い声に強いモデル | ERes2NetV2 は短い声向けに作られ、VoxCeleb1-O で 3 秒 0.98%・2 秒 1.48%（[ERes2NetV2](https://arxiv.org/html/2406.02167v1)）。CAM++ は ECAPA より良く、計算が軽い（[CAM++](https://arxiv.org/pdf/2303.00332)）。どちらも [3D-Speaker](https://github.com/alibaba-damo-academy/3D-Speaker) にある。3D-Speaker の試験（録る距離・機器・方言がばらばら）では、VoxCeleb より誤りが多い（ERes2NetV2 で 6.5%）（[3D-Speaker-Toolkit](https://arxiv.org/pdf/2403.19971)） |
| 点数のぶれの補正 | 類似度をそのまま比べず、「ほかの人たちとの類似度」の分布で補正する AS-norm が、今の強い仕組みでは標準（[DKU-MSXF, VoxSRC 2023](https://arxiv.org/pdf/2308.08766)、[TAS-norm](https://arxiv.org/html/2504.04512v1)）。声の長さを使って点数を補正する方法（QMF）もある（[Kiwano](https://arxiv.org/pdf/2606.22369)）。長さの違いには効くが、短い声では補正がずれることもある |
| 決まった言葉で確かめる | 登録と確認で同じ言葉を言ってもらう方式（テキスト依存）は、短い声でも精度が上がりやすい（[You et al., Odyssey 2014](https://www.isca-archive.org/odyssey_2014/you14_odyssey.html)、[比較研究](https://arxiv.org/pdf/1707.04373)） |

まとめ：0.5 秒の声で本人を確かめることは、モデルを替えても難しい。モデルの改善が効くのは 1.5〜3 秒くらいの声から。

## 2. 製品は、声の登録を「会話のついで」にしていない

- **Google（Voice Match）**：設定で、決まった文（「OK Google、ワークアウトのプレイリストを流して」など）を何回か言って登録する。1 台に 6 人まで（[What Hi-Fi](https://www.whathifi.com/news/you-can-now-train-google-assistant-to-better-recognise-your-voice)、[Google](https://support.google.com/googlenest/answer/7320960)）。
- **Amazon（Alexa Voice ID）**：アプリか「声を覚えて」で、決まった文を言って登録する（以前は 10 文）。家族も一人ずつ登録できる（[Amazon](https://digprjsurvey.amazon.com/csad/help/node/GYY4637XC2STFL9R)、[VentureBeat](https://venturebeat.com/business/amazons-alexa-can-now-learn-your-voice-automatically)）。
- 会議の話者分離（その場で人を分ける）は研究が多いが、別の日に来た人を覚えて当てるところまでは扱っていない（[オンライン話者分離](https://arxiv.org/pdf/2109.06483)）。

シエルは今、会話の中の数回の発言から声の見本を作っている。そのため、見本が短く少なく、次の会話の最初に当たりにくい。

## 3. 同意は、はっきり・別の手順で取るのがよいとされる

- 声紋（声から人を見分けるための特徴）は、米国イリノイ州の BIPA や欧州の GDPR で、特に守るべき情報として扱われる。BIPA では、会話の中で口で知らせるだけでは足りず、書面（画面での確認なども含む）の同意が求められるという解説がある。会話の音声から登録の手順なしに声紋を作るほうが、明示的な登録より危ないとされる（[Barnes & Thornburg](https://laborandemployment.btlaw.com/post/102n7n1/the-voiceprint-you-didnt-mean-to-create-what-delgado-v-meta-means-for-employer)、[ABA](https://www.americanbar.org/groups/litigation/resources/newsletters/class-actions-derivative-suits/voiceprints-ai-bipa-new-trends-biometric-privacy-litigation/)、[Aculab](https://aculab.com/blog/biometrics/blog-making-the-most-of-voice-biometrics)）。
- 日本の個人情報保護法では、個人を識別できる声紋は個人識別符号に当たると一般に解説されている。利用目的の通知・公表（第 21 条）と、目的外の利用に同意が要ること（第 16 条）が基本（[第 21 条の解説](https://ja.wikibooks.org/wiki/%E5%80%8B%E4%BA%BA%E6%83%85%E5%A0%B1%E3%81%AE%E4%BF%9D%E8%AD%B7%E3%81%AB%E9%96%A2%E3%81%99%E3%82%8B%E6%B3%95%E5%BE%8B%E7%AC%AC21%E6%9D%A1)）。個人識別符号に当たるかの判断は、個人情報保護委員会のガイドラインで確かめる必要がある（ここでは一次資料まで確かめていない）。
- これは法律の助言ではない。ほかの人へ公開する前に、利用規約・説明の文面と合わせて確かめる。

## 4. シエルへの改善案

| 案 | 中身 | 効き目 | 手間 |
|---|---|---|---|
| A. 声の登録の手順を作る | アプリの参加者パネルに「声を登録する」を置く。画面に出す 3〜5 文（1 文 2〜3 秒）を本人に読んでもらい、その声で見本を作る。同意は画面のボタンで取る（「名前と声を覚えてよい」） | 大きい。見本が長く多くなり、次の会話の最初から当たりやすくなる。同意がはっきりする（画面での確認は、口の「いいよ」より強い同意の記録になる） | 中（アプリと会話サーバー） |
| B. 声での同意を長めの言葉にする | 「覚えていい？」の返事に、名前を含む 1 文を言ってもらう（「シエル、田中の声と名前を覚えていいよ」）。1.5 秒以上あれば声でも確かめられる | 中。いまの「直前の人の返事とみなす」の弱点（代わりに答えた人を見分けられない）を減らせる | 小（プロンプトと判定） |
| C. 声のモデルを替える | ECAPA を ERes2NetV2 か CAM++ に替える | 1.5〜3 秒の声で効く。0.5 秒の返事にはあまり効かない。覚えている人の見本を全部作り直す必要がある（今の見本と互換が無い） | 大 |
| D. 点数の補正（AS-norm） | ほかの人たちの声の集まり（公開データ）と比べて、類似度を補正する | 中。基準の値が人や部屋によってぶれにくくなる | 中（公開データの用意と使用条件の確認） |
| E. 実際の声で測る | 開発用サーバーの声の保存（`data/debug/AUDIO`）で、利用者・家族の声を少し録り、短い返事・名乗りの類似度を測る | どの案が要るかを決める元になる | 小 |

おすすめの順：まず **A**（登録の手順と画面での同意）と **B**（長めの同意の言葉）。いま困っていること（同意が通らない・最初に当たらない）に、いちばん直接効く。そのあと **E** で実際の声を測り、それでも足りなければ **C**・**D** を考える。
