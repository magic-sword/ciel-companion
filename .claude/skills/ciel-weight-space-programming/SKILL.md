---
name: ciel-weight-space-programming
description: シエルのローカルLLMの重み直接編集を調査・設計・比較評価する。量子化GGUFでのWSP実行、高精度重みの因果解析、人格・身体性とツール・一般性能への影響を調べる実験に使う。
---

# シエルの重み編集を進める

作業起点はリポジトリのルート。[研究と実施方針](../../../docs/operations/weight-space-programming-ja.md)と[評価仕様](../../../docs/testing/weight-space-benchmark-ja.md)を読む。推論APIの指定だけで重み編集済みとは扱わない。

量子化モデルの直接編集を頼まれた場合は、先に[量子化GGUFの実行手順](references/quantized-gguf.md)を読む。高精度checkpointがないことだけで、その経路を中断しない。確認済みの適用範囲から方法を選ぶ。

評価基準の設計・見直しや介入効果の比較には[改善量を測る採点スキル](../ciel-benchmark-progress/SKILL.md)を使う。基準の高得点や同じ合否だけで改善余地なしと判断せず、段階別・観点別の感度と対応差を確認する。

1. 現行GGUF・tokenizer・template・推論設定・共有モードの識別を確保する。35B MoEへ0.8Bの層・方向を流用しない。高精度重みと内部hookを使う方法では元checkpoint・資源も確認し、不足時は量子化直接編集で検証できる範囲と、内部活性の因果解析に必要な準備を分ける。
2. シエルの設定原本と`character.md` / `ciel_self.md`を照合。安定した人格と、現在の体・権限・作業・記憶を分ける。後者はホストから渡し続ける。「待てが苦手」を取消無視へ変えない。
3. `python -B -m server.benchmark.weight_space validate`でsuiteを確認。固定した開発セットで基準を採り、編集用対照例と質問系列を分ける。既存promptありを主比較、最小promptを補助比較にする。
4. 高精度重みの内部編集は、対照文脈の活性→因果介入→小rank差分の順に仮説を確かめる。量子化直接編集は対象テンソル・ブロック形式と編集の意味を確定してから別コピーで試す。実token位置を確認し、JSON/tool-call/停止/非シエル文脈を保護する。候補は毎回baseから生成。分母不良・非有限値を棄却し、保存dtypeで差分を再計測する。候補数とforward/token/時間予算を先に固定する。
5. 再変換・再量子化する方法は、現行・再変換した未編集対照・編集して同条件で量子化した候補を比較する。量子化スケールだけの直接編集は未編集GGUFと候補を同一推論環境で比較し、対象外の全バイト一致を検証する。開発で選定後にholdoutを評価。未採点・タイムアウト・token上限・環境不一致を合格扱いにしない。正規表現だけで人格の合格を決めない。
   プロンプト改善を比較するときは`compare --change prompt`を指定し、重みhashを同じにする。home helperの`stage --prompt-revision <commit>`で元本文を再配置し、両版を同じ評価器で測る。不採用候補は通常promptへ残さず、`prompt_candidates/`へ分離し、`stage --prompt-dir <候補ディレクトリ>`で明示的に選ぶ。固定知識と動的記憶の外部化、GCAとテキスト取得の違いは実施方針の該当節を参照する。
6. 音声は[音声スキル](../ciel-voice-benchmark/SKILL.md)、実際の移動・作業・停止は[Minecraftスキル](../ciel-minecraft-benchmark/SKILL.md)で評価。mock tool結果はMCP疎通や実機動作の証拠ではない。
7. manifestへ全候補・根拠・hash・変換条件・未確認範囲を残し、[確認状況](../../../docs/testing/verification-status-ja.md)を更新する。本番ファイルは上書きしない。復元は未変更baseのhashで確認する。

実行器と課題・テストはGit管理、重み・活性・録音・結果はGit対象外。追加の学習やプロンプト変更はWSP単独とは別条件として記録する。資料の更新は[ciel-documentation](../ciel-documentation/SKILL.md)に従う。
