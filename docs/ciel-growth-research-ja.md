# シエルの好み・性格の育て方：参考にした研究と実例

調べた日：2026-11-03。シエルの好みを「変わらない芯」と「出来事から育つ部分」に分けて持つ作り（[決定記録](decisions/ciel-growth-ja.md)）を決めるときに参考にしたもの。多くは要旨・紹介ページ・論文の一部で確かめたもので、本文の細かい数字までは確かめていないものがある（各項目に書く）。

## 1. 人物像を層に分けて持つ

### Emergi-PersonaOS（2026）

- Haoluan Fu ほか、「Emergi-PersonaOS: A Persona Agent Operating System for Situational Adaptation and Controllable Evolution」、arXiv:2609.27417。<https://arxiv.org/abs/2609.27417>
- 人の性格を 3 層で捉える心理学の考え方（変わりにくい気質・状況や経験で育つその人らしいやり方・自分についての物語）をもとに、AI の人物像を 3 層に分ける。その場の状態（約 100 字）と、長く続く信念を分ける。
- 育つ部分の書き換えは、体験と結果を記録し、なぜ変わったかを確かめてから行う。書き換えの候補は審査で却下でき、根拠と版の記録を残す。多くの先行研究（Reflexion など）は記憶や行動の仕方を書き換えるだけで、人物像そのものは書き換えていない、と指摘している。
- 取り入れたこと：芯（`ciel_self.md`）・育った好み（`ciel_likes`）・物語（`ciel_events`）の 3 層。根拠の出来事を写して持つ。変えた記録（`ciel_like_history`）。審査は、モデルに任せず決まり（`growth.check`）で行う。
- 確かめた範囲：要旨と紹介ページ。PDF の本文は読めなかった。

### Evolving Agents（2024）

- Jiale Li ほか、「Evolving Agents: Interactive Simulation of Dynamic and Diverse Human Personalities」、arXiv:2404.02718。<https://arxiv.org/abs/2404.02718>
- 1 日の出来事を振り返り（感情・認知）、性格の「状態・特徴・矛盾・好み」を毎日書き換える（Character Growth）。7 日間の試しで、性格（Big Five）が変わった。
- 著者が挙げた問題：LLM の偏りで育ち方がいい方向に偏り、3 人とも不安の強さが下がって似てきた。書き換えが指示文頼みで、指示の精度に強く左右される。Character Growth を外した版と大きな差が出なかった。
- 取り入れたこと：好き（like）だけでなく、ちょっと苦手（dislike）・気になっている（curious）も育てる。書き換えを指示文だけに任せず、根拠の数・日数・間隔・上限をコードで決める。
- 確かめた範囲：本文（HTML 版）の大部分。

### Generative Agents（2023）

- Joon Sung Park ほか、「Generative Agents: Interactive Simulacra of Human Behavior」、UIST 2023。arXiv:2304.03442。
- 観察した出来事を記憶に貯め、ときどき振り返って、より高い水準の考え（信念）を作る。出来事から人物像が変わる作りの出発点。
- 取り入れたこと：出来事を貯めて、振り返りで好みを作る流れ。
- 確かめた範囲：既に知られている内容と、それを引く論文の説明。

## 2. 長く話すと人物像がぶれる

### Measuring and Controlling Persona Drift（2024）

- Kenneth Li ほか、「Measuring and Controlling Persona Drift in Language Model Dialogs」、arXiv:2402.10962。<https://arxiv.org/abs/2402.10962>
- 会話が進むと、人物像の一貫性が数往復のうちに落ちる（8 往復ほどで大きくぶれたモデルがある）。原因の一つは、最初の指示への注意が薄れること。
- 関連：Luz de Araujo ほか「Persistent Personas?」（arXiv:2512.12775、<https://arxiv.org/abs/2512.12775>）は、100 往復を超える会話で、人物像が薄れて「人物像なしのふつうの振る舞い」に戻っていくと報告。Choi ほか「Examining Identity Drift in Conversations of LLM Agents」（arXiv:2412.00804、<https://arxiv.org/abs/2412.00804>）は、大きなモデルほどぶれが大きかったと報告。
- 取り入れたこと：育った好みも、芯と同じく返事のたびに指示へ入れる（pipeline は返事のたびに指示を組み立て直すので、最初の指示だけが遠くなることは少ない）。
- 確かめた範囲：要旨と紹介ページ。

### LD-Agent（2025）

- 「Hello Again! LLM-powered Personalized Agent for Long-term Dialogue」、NAACL 2025。arXiv:2406.05925。<https://arxiv.org/abs/2406.05925>
- 相手だけでなく、エージェント自身の人物像も発言から抜き出して、長く覚える（人物像の倉庫を更新し続ける）。出来事の記憶は、長期と短期に分けて持つ。
- 新しい特徴と古い特徴が食い違ったときの扱いは書かれていない。会話の回数が増えるほど、人物像の部分の成績が落ちた（出来事の記憶のほうが安定していた）。
- 取り入れたこと：食い違いの扱いを、こちらで決めた（同じ・似た好みは足さずに書き直す、芯と食い違うものは作らない、外すときも根拠を求める）。
- 確かめた範囲：本文（HTML 版）の一部。

### MemoryBank（2023）

- Wanjun Zhong ほか、「MemoryBank: Enhancing Large Language Models with Long-Term Memory」、arXiv:2305.10250。<https://arxiv.org/abs/2305.10250>
- 忘却曲線にならって記憶を更新し、相手の人柄の見立てを日ごとにまとめ直す。
- 取り入れたこと：直接はまだ（出来事は件数で古いものから消すだけ）。

## 3. 育つことを見せる実例

### aibo（ソニー）

- ソニー「aibo の性格」（ヘルプガイド）。<https://helpguide.sony.net/aibo/ers1000/v1/en/contents/TP0001970096.html>
- 飼い主との関わりと経験で性格が育ち、同じ aibo でも飼い主によって違う性格になる。接し方を変えたり、新しいおもちゃを与えたりすると、性格が変わることがある。今の性格はアプリで見られる。
- 取り入れたこと：育った好みと根拠を、あとから見られるようにする（今は `self_admin.py`。アプリで見せるのは、これからの候補）。

## 4. 自分のことを話す効果と、正直さ

### チャットボットの自己開示（2020〜）

- Yi-Chieh Lee・Naomi Yamashita・Yun Huang・Wai Fu、「"I Hear You, I Feel You": Encouraging Deep Self-disclosure through a Chatbot」、CHI 2020。紹介：<https://ischool.illinois.edu/news-events/events/2020/04/17/cirss-seminar-yi-chieh-lee>
  - 1 か月・47 人の実験で、チャットボットが自分のことを話すと、相手も深く話すようになり（その効果が続き）、親しさと楽しさが増した。
- 「Dialoging Resonance: How Users Perceive, Reciprocate and React to Chatbot's Self-Disclosure in Conversational Recommendations」、arXiv:2106.01666。<https://arxiv.org/abs/2106.01666>
  - 事実だけを話すより、気持ちを込めて話すほうが親しさが高く、人らしく感じられた。
- 「From Small Talk to Rapport: Exploring Robot Self-Disclosure in Collaborative Tasks」、arXiv:2608.28154。<https://arxiv.org/abs/2608.28154>
  - ロボットが過去の会話について話しても、本当の自己開示とは受け取られにくく、「アンケートみたい」と言われた。
- 取り入れたこと：シエル自身の話（内なる考えの share）を足した。育った好みを話すときは、報告ではなく、気持ちと一緒に話す（`growth.context` の指示）。
- 確かめた範囲：要旨と紹介ページ。

### ロボットのうそへの受け止め方（2024）

- Rosero・Dula・Kelly・Malle・Phillips、「Human perceptions of social robot deception behaviors: an exploratory analysis」、Frontiers in Robotics and AI（2024）。<https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11411098/>
- 約 500 人に、ロボットのうそ 3 種類を場面で見せた。外の世界についてのうそ（思いやりからのもの）は比較的受け入れられ、内面を偽る（痛いふり）ことは嫌われ、能力を隠すことはいちばん嫌われた。
- 取り入れたこと：体験していない思い出を作らない。好みは本当にあった出来事からだけ育てる。
- 確かめた範囲：本文の概要。

## 5. 長く使ってもらうこと

- ジュネーブ大学の博士論文。<https://archive-ouverte.unige.ch/unige:15710>：長期の利用で、最初の物珍しさが薄れても関心が落ちなかった理由として、出来事の記憶を挙げている。
- Georgia Tech の長期の人とロボットの関わりの論文（<https://faculty.cc.gatech.edu/~beki/c42.pdf>）：物珍しさは数日〜数か月で薄れ、3 か月を超える関わりはよく分かっていない。
- 確かめた範囲：検索結果の要約。

## まだ調べていないこと・これからの候補

- 育った好みを、アプリで見せる・本人が直す形（aibo の例）。
- 出来事の忘れ方（MemoryBank の忘却曲線など。今は件数で古いものから消すだけ）。
- 好みが育ったことを、利用者がどう受け止めるかの評価（実際の会話で確かめる）。
