# 公開リポジトリと第三者依存関係

Minecraft基盤としてMindcraftのコミット `e1c1fc3ffa481506c2445fc639e16dba504b5920`（https://github.com/mindcraft-bots/mindcraft、MIT、Copyright (c) 2024 Kolby Nottingham）を固定した。`server/minecraft/src/vendor/mindcraft/`に上流src全体・profiles・botsのテンプレート・settings・packageメタデータ・LICENSE全文を保持する。出典と原本／改変後SHA-256はprovenance.json、上流との差分はupstream.patchに記録し、`scripts/server/check-mindcraft-vendor.py`で検査する。Dockerのsrcコピーで許諾表示も同梱する。上流Agent・Prompter・History・SelfPrompter・NPCと身体実行を使用し、モデルにはCIELを注入する。上流クラウド接続・独立TTS・vision・任意コード生成は有効化しない。Agentの静的依存であるses 1.9.1、eslint 9.13.0、google-translate-api-x 10.7.1もCIEL側package-lock.jsonで固定する。ゲーム履歴の生成先botsはGit管理外とする。

> 責務：SDK・モデル・素材の依存と利用許諾、リポジトリへ含める範囲。

vendorのテキストはLFに固定し、検証用hashとGitからの配布バイトを揃える。provenanceのnormalization_only_filesは改行だけが上流と異なるファイルを示す。upstream.patchは上流原本への適用検査を行い、末尾改行の有無も記録する。差分中の上流の空白は保持する。

確認日: 2026-10-05。これは採用構成の記録であり、第三者の利用条件を置き換えるものではありません。

| 対象 | Gitでの扱い | 復元方法・条件 |
|---|---|---|
| 自作C#・設定スクリプト・Unity設定・.meta | 管理する | プロジェクト自身のOSSライセンスは未選定 |
| Live2D SDK全体（Core、Components、サンプル） | 管理しない | 公式サイトから取得しrestore-cubism.ps1で復元 |
| 自作のLive2D互換ヘルパーと置換スクリプト | 管理する | scripts/cubism、repair-cubism.ps1 |
| LiveKit SDK | manifestとlockを管理 | Package ManagerとGit LFSで取得 |
| SdkCheckシーン | 管理しない | CIEL/SDK/Configure and Validateで生成 |
| LiveKitTokenSource設定 | 管理しない | 同コマンドで空の設定を生成。秘密情報を埋め込まない |
| Library、Logs、UserSettings、ビルド出力、.env | 管理しない | ローカル生成・設定 |
| unity/.vscode/extensions.json | 管理する | 共有可能な拡張機能推薦のみ |

## Live2D

Coreは[Proprietary Software License](https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html)
に従います。RedistributableFiles.txtへの記載は無条件でSDKバイナリをソースリポジトリへ
公開してよいという意味ではありません。再配布条件は同契約の第5条等にあります。

Componentsは[Live2D Open Software License](https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html)
に従います。「Open」という名前でも、自作コードのMIT等へ一括でライセンス変更できません。
Componentsのソース公開自体を一律禁止と判断したわけではなく、独自条件を持つSDKを
同梱しない公開方針として、ソース・文書・バイナリをまとめてローカル導入に分けます。

サンプルには[Free Material License](https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html)
および[モデル別条件](https://www.live2d.com/eula/live2d-sample-model-terms_en.html)があります。
サンプル由来の確認シーンも生成物として除外します。シエルの絵・声・モデルについても、
将来のソース公開ライセンスとは別に公開範囲を決めてください。

アプリのソース公開と、SDKを組み込んだAPK等の配布は別の確認事項です。
Live2Dに依存する実行部分まで、すべてOSSになるわけではありません。

## LiveKit

Unity SDK 2.1.0は[Apache License 2.0](https://github.com/livekit/client-sdk-unity/blob/v2.1.0/LICENSE.md)
です。SDK実体はGit除外済みのLibraryへ取得し、公開するのは依存指定と解決済みリビジョンです。
バイナリ配布時にはSDKおよび推移的依存のLICENSE/NOTICEも確認します。

## コミット前の確認

Live2D SDK本体はGit対象外です。正式なキャラクターモデル・素材の管理とは区別します。既に追跡・公開したファイルに
.gitignoreを追加しても過去のコミットからは消えません。
`git status --short` とステージ済み差分を確認し、除外物を `git add -f` しないでください。
プロジェクト自身のLICENSEを選定し、その対象から第三者SDK・キャラクター素材を区別してください。

## 会話サーバーの話者の識別（2026-10-15 追加）

自宅サーバーの Docker イメージの中で使い、Git には含めない（`server/agent/requirements.txt`・`Dockerfile`・`server/compose.yaml` で版を固定）。

| 対象 | ライセンス | 使い方 |
|---|---|---|
| [SpeechBrain](https://github.com/speechbrain/speechbrain) 1.0.3 | Apache-2.0 | ECAPA の読み込みと計算 |
| [speechbrain/spkrec-ecapa-voxceleb](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)（版 `0f99f2d`） | Apache-2.0 | 声の特徴のモデル。イメージを作るときに取得する |
| PyTorch 2.5.1（CPU 版） | BSD-3-Clause | SpeechBrain が使う |
| [psycopg](https://www.psycopg.org/) 3.2.9 | LGPL-3.0 | DB への接続（ライブラリとして使うだけで、改変しない） |
| [pgvector-python](https://github.com/pgvector/pgvector-python) 0.4.1 | MIT | ベクトルの受け渡し |
| [pgvector/pgvector](https://hub.docker.com/r/pgvector/pgvector) 0.8.0-pg17（PostgreSQL 17 ＋ pgvector） | PostgreSQL License | 記録の場所のコンテナ |
