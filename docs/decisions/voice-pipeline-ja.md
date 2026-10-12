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
