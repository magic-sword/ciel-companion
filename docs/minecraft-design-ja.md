# Minecraftサービス

> 責務：Minecraft固有の体・計画・知識・視覚と接続先・変更入口。

この資料はMinecraft固有の体・知識・視覚の構成と操作範囲を説明する。接続は[ゲーム環境MCP](game-environment-mcp-design-ja.md)、依頼の外枠は[作業契約](game-work-contract-ja.md)、評価方法は[ベンチマーク](minecraft-benchmark-ja.md)が正本。

## 構成と責務

Java版MinecraftとMineflayerの体を別サービスとして動かす。`server/minecraft/`がMCP入口、所有権、計画・レシピ、移動・採集・製作、実状態による確認・局所修復を持つ。ゲームの知識・日本語名・失敗理由もゲーム側で管理する。会話ホストにはMinecraft用の計画ツリーを持たせない。

| 部分 | 実装 |
|---|---|
| MCPと接続profile 2 | `src/ciel/mcp.js` |
| work 1の依頼・状態・取消 | `src/ciel/tasks.js` |
| ゲーム内部の段・修復 | `src/ciel/goals.js` |
| 低水準の所有権・切替 | `src/body-command.js`とRunner |
| 表示文・日本語名 | `src/ciel/words.js` |
| 知識の検索と取得 | `src/knowledge/` |

ホストの`CIEL_GAMES`は`minecraft=http://127.0.0.1:8771/mcp`を指定する。接続だけでは体を取得せず、アプリからの有効化と所有権取得を必要とする。通常ワールドと専用ベンチマークは接続先も復元範囲も異なる。

## 利用者の依頼

LLMは公開された能力から目的・数量・制約・予算を構造化する。`minecraft.obtain_item`の採集・製作はゲームが段を組み、観測して進める。旧plan/step/repairと直接の採集・製作MCPツールは公開しない。追従・移動・観察等の公開範囲は`mcp.js`とprofileを確認する。

不足材料・未発見・道具不足等は制約に従って探索、判断待ち、中止へ進む。無期限探索をしない。失敗の説明と実際の停止確認を別に扱い、依頼の完了はゲームの実状態から報告する。停止後に遅い段や推論で再開しない。

## 知識と視覚

ローカルのゲームデータ・Wiki取得済み情報を知識サービスから検索する。知識検索と公開Web調査は別の能力であり、外部検索が使えないローカルモードでもゲーム側の知識は利用できる。出典・対象バージョン・必要な範囲を示し、取得結果を履歴へ無制限に積まない。

視覚は体が提供する観測・画像を[画像入力](vision-design-ja.md)へ渡す。画像の生成、LLMによる理解、ワールドの正式な状態を区別する。ローカルモードでは現在の画像認識機能は利用不可であり、画像を読めたふりをしない。採点は見た目やLLMの主張ではなく評価器のRCON観測で行う。

## 出来事と安全

被ダメージ・死亡等は環境の出来事として発行する。ID・世代・順序・時刻を検証して、[反応基盤](service-events-and-reactions-ja.md)へ渡す。状態確定と痛がる表情・発話は独立して処理する。

体を共有できる会話数、同時操作、防御・食事の所有権はゲームサービスで制御する。コメントを持ち主の命令へ昇格させない。採点用RCONや任意コマンドはエージェントへ公開しない。

## 起動・調査・測定

サービス定義は`server/compose.yaml`等、固定するMinecraft・Node・SDK版はComposeとpackage-lockが正本。秘密・モデル・ワールドはGitへ入れない。EULA同意と既存の接続設定を維持する。

通常ワールドの調査は[デバッグスキル](../.claude/skills/ciel-minecraft-debug/SKILL.md)、復元を伴う評価は[ベンチマーク](minecraft-benchmark-ja.md)を使う。自宅の専用環境で確認し、手元PCで新しいMinecraftを起動して代用しない。現在の確認済み範囲は[確認状況](verification-status-ja.md)を参照する。
