# 音声会話の構成の決定記録

日付：2026-10-12（日本時間）。仕様書 `docs/specification-ja.md` の 3・4・9 章を具体化したもの。

## 決めたこと

| 項目 | 決定 | 理由 |
| --- | --- | --- |
| 音声の中継 | **LiveKit Cloud**（開発中は無料枠） | 自宅サーバーは LiveKit Cloud へ外向きにつなぐだけで済み、ルーターのポート開放・ドメイン・TLS 証明書が要らない。外から自宅への入り口を開けない。モバイル回線でも安定する。接続先の URL とキーを変えるだけで、自宅の LiveKit サーバーへ移せる |
| 会話サーバー | 自宅の GPU サーバー `chris_local`（Ubuntu 22.04、RTX A2000 12GB、Docker）で `server/agent` を動かす | 運用費を抑える。外部へは LiveKit Cloud と OpenAI へ外向きにつなぐだけ |
| 会話モデル | OpenAI Realtime API（`gpt-realtime`）から始め、GPT-Live（`gpt-live-1`）と比べる | LiveKit Agents 1.8 の OpenAI プラグインが両方に対応（`CIEL_MODEL` で切り替え） |
| シエルの声 | Seed-VC で、OpenAI の声をシエルの声へ変換（フェーズ2） | OpenAI の音声会話の声は用意された声から選ぶ方式。抑揚・間は保ったまま声色だけ変えられる。Seed-VC は 10 秒程度の参照音声で使える。公式の値で遅延 約 0.43 秒（RTX 3060 ノート、変換 0.3＋機器 0.1） |
| 参照音声 | Irodori-TTS で合成したシエルの声（`D:\CIEL\企画設計\キャラ\シエル\ボイスサンプル`、リポジトリの外）。スタイルは設定資料 第7章 | 追加の参照音声も同じスタイルで作れる。Irodori-TTS のモデルの重みのライセンス（モデルカード）は公開前に確認する |
| GPU の共用 | 会話を試すときは、同じ GPU を使う vLLM（`gemma4-developer-agent-model-1`）を止める。止める前に毎回ユーザーに確認する | GPU のメモリ 12 GB のうち 11.8 GB を vLLM が使っている。Seed-VC は 2〜4 GB 要る |
| 遅延を減らす次の手 | 遅延が目標に届かなければ、Beatrice v2（変換 約 0.05 秒、CPU で動く。専用の学習が要る）を試す | 変換の部分は差し替えられる作りにする |

## 会話の記録

`AgentSession.start(record=False)`：LiveKit Cloud に会話の録音・文字起こし・ログを残さない（仕様書 8 章）。

## 接続の手順（開発）

1. LiveKit Cloud でプロジェクトを作り、Settings → Keys で URL・API キー・API シークレットを得る。Settings → Options で開発用トークンサーバー（Development token server）を有効にし、その ID を控える。
2. `chris_local` の `~/work/ciel-companion/server/agent/.env` に、`.env.example` をもとに LiveKit と OpenAI のキーを書く（利用者が書く。Git に入れない）。
3. `docker compose up -d --build`（同じフォルダ）で会話サーバーを起動する。
4. Unity：`Assets/Settings/LiveKitTokenSource.asset`（Git 管理外）の Token Server Id に、1 の ID を入れる。`Assets/Scenes/Conversation.unity` を開いて再生する（メニュー CIEL ＞ Conversation ＞ Create Scene で作り直せる）。

開発用トークンサーバーは誰でもトークンを取れるので、開発中だけ使う。公開前に、認証つきのトークン発行（仕様書の `server/session-api/`）へ切り替える。

## OpenAI の独自の声（Custom voices）を使わない理由（2026-10-12 調査）

- 利用できるのは「対象の顧客」だけで、営業窓口への申し込みが要る（[Custom voices ガイド](https://developers.openai.com/api/docs/guides/custom-voices)）。
- 声の持ち主本人が決められた同意文を読んだ録音と、同じ人の声の見本（30 秒以内）が要る。Irodori-TTS で合成した声は「本人の同意」を用意できないので、この仕組みの対象外と判断した（合成音声で同意文を作ることは、同意の仕組みのすり抜けになるのでしない）。
- GPT-Live の独自の声は英語のアクセントのみと書かれている。日本語は未確認。
- 以上から、シエルの声は Seed-VC による変換で作る方針を続ける。

## 会話モデルの比較（2026-10-12、公式の料金表 https://developers.openai.com/api/docs/pricing）

| | gpt-realtime-2.1-mini | gpt-realtime-2.1 | gpt-live-1 |
| --- | --- | --- | --- |
| 料金 | 音声 入力 $10・出力 $20／100 万トークン（キャッシュ入力 $0.30） | 音声 入力 $32・出力 $64／100 万トークン（キャッシュ入力 $0.40） | $0.05／分（秒単位）。裏側のモデル・ツールを使うと別料金 |
| 会話 1 分の目安 | 約 $0.02〜0.05 | 約 $0.06〜0.11 | 約 $0.05 |
| 話し方 | 交代で話す（割り込みあり） | 交代で話す（割り込みあり） | 聞きながら話す全二重。あいづち・割り込みが自然 |
| Seed-VC との相性 | よい（変換の遅れ 約 0.4 秒は、返事の出だしが遅れるだけ） | よい | 要検証（全二重のあいづちや重なりが、変換の遅れでずれる） |
| 日本語 | 対応 | 対応 | 公式ページに記載なし（要検証） |
| 利用条件 | 一般 | 一般 | 無料枠では使えない（利用実績の段階 Build 以上） |

1 分の目安は、音声 1 分 = 入力 600 トークン・出力 1,200 トークン、会話の履歴のキャッシュが効く前提の第三者の試算（[forasoft](https://www.forasoft.com/blog/article/openai-realtime-api-pricing)）。

方針：開発の既定は **gpt-realtime-2.1-mini**（安い）。会話の質を gpt-realtime-2.1 と比べ、GPT-Live は日本語と Seed-VC との相性を確かめてから判断する（`CIEL_MODEL`・`CIEL_REALTIME_MODEL` で切り替え）。

## 声質変換の測定（2026-10-13、自宅 GPU RTX A2000 12GB）

- 構成：Seed-VC のリアルタイム用モデル（xlsr tiny、`DiT_uvit_tat_xlsr_ema.pth`）、block 0.18 秒、拡散 8 ステップ、fp16。GPU のメモリは約 1.2 GB。
- 5.2 秒の音声を実時間で流して：処理の実時間比 0.33（間に合う）、変換による遅れ 約 0.19 秒（声の始まりを送ってから、変換した声の始まりが届くまで）。
- vLLM（gemma4-developer-agent-model-1）は、ユーザーの了承のうえ止めてある（しばらく止めたままでよい）。戻すときは `docker start gemma4-developer-agent-model-1`（GPU のメモリが足りなくなるので、声質変換サービスを止めてから）。

## 声の作り方の比較（2026-10-13）

ユーザーの評価：Seed-VC のリアルタイム用モデルは似ておらず、音が割れ・途切れる。高品質モデル（whisper-small）の一括変換・参照音声 16 秒は「かなり良い」。サンプルの量産とファインチューニングで上げられそう。
- 音割れは、変換後の音量が上限を超えて切り取られていたため（リアルタイムの出力の 0.35%）。実装の不具合。

Irodori-TTS（v4.1-Small、MIT）で直接読み上げる方法の速さ（自宅 GPU、参照音声 4 本 + 設定資料 7.1 のキャプション、`server/tts-irodori/bench_tts.py`）：

| 条件 | GPU | 6 字 | 13 字 | 33 字 |
| --- | --- | --- | --- | --- |
| bf16、40 ステップ（標準） | 1.7 GB | 0.66 秒 | 0.80 秒 | 1.22 秒 |
| bf16、16 ステップ | 1.7 GB | 0.44 秒 | 0.51 秒 | 0.72 秒 |
| fp32、40 ステップ | 3.4 GB | 1.48 秒 | 1.93 秒 | 3.59 秒 |

文を受け取ってから声が全部できるまでの時間。読み上げは文ごとなので、返事の出だしの遅れは「最初の文の文字が届くまで」＋「最初の文の合成」。
