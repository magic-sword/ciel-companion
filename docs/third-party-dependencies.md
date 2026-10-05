# 公開リポジトリと第三者依存関係

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

現在のLive2D等は未追跡のため、.gitignoreで除外できます。既に追跡・公開したファイルに
.gitignoreを追加しても過去のコミットからは消えません。
`git status --short` とステージ済み差分を確認し、除外物を `git add -f` しないでください。
プロジェクト自身のLICENSEを選定し、その対象から第三者SDK・キャラクター素材を区別してください。
