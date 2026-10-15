# 声質変換サービス（Seed-VC）

会話サーバー（`../agent`）が受け取った OpenAI の声を、シエルの声へリアルタイムに変換する。自宅の GPU サーバーで、会話サーバーと同じマシンに置く（127.0.0.1 だけで待ち受ける）。

- 変換は [Seed-VC](https://github.com/Plachtaa/seed-vc)（GPL-3.0、モデルの重みも GPL-3.0）のリアルタイム用の小さいモデル（`DiT_uvit_tat_xlsr_ema.pth`）を使う。Seed-VC 本体はイメージを作るときに版を固定して取得し、このリポジトリには入れない。
- Seed-VC を使うコードを含むので、**このフォルダ（`server/voice-conversion/`）は GPL-3.0**（`LICENSE`）。会話サーバーとは WebSocket でつなぐ別のプログラムにして、ほかの部分のライセンスと分けている。
- 参照音声（シエルの声。Irodori-TTS で合成）は `data/reference.wav` に置く（Git の外）。

## 使い方

```
docker compose --profile vc up -d --build   # server/ で。初回はモデルを data/hf へダウンロードする
python bench.py 入力.wav 出力.wav  # 確認（遅れと処理の速さ）
```

GPU のメモリを 2〜4 GB 使う。同じ GPU を使う vLLM（gemma4-developer-agent）を動かしたままでは入らないので、止めてから起動する。

## 変換の設定（`stream_vc.Settings`）

`block_time`（1 回に変換する長さ）を短くすると遅れは小さくなるが、処理が重くなる。処理の時間が `block_time` を超えると音が途切れる（実時間比 1 未満が条件）。
