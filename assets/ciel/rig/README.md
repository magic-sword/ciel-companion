# 正式なCubismモデル

編集対象は **[ciel.cmo3](ciel.cmo3)** だけ（115層。ハッシュは [approved.json](../current/approved.json) の `rig_sha256`）。新しい作業は必ずこのファイルのコピーから始め、`.local/` で組み込み・書き出しをしてから、採用時にここを置き換える。候補モデルや版ごとのモデルはここに置かない。

| 中身 | 場所 |
| --- | --- |
| 表情の切り替えファイル（通常を含む11表情） | `expressions/` |
| 身体・上着の制御と親子関係 | [body-outfit/](body-outfit/README.md) |
| 尻尾の制御・物理演算 | `tail/` |
| 現行モデルの確認図・検証結果 | [proofs/current/](proofs/current/)（[全表情と姿勢](proofs/current/all-expressions.png)） |
| Unity への更新一式 | [../runtime/README.md](../runtime/README.md) |

## 表情

| 表情 | 切り替え |
| --- | --- |
| 嬉しい | `ParamHappy=1` と左右の `ParamEye*Smile=1` |
| にこにこ | `ParamRelaxed=1` |
| 驚き | `ParamSurprised=1` |
| ぷんすか・しょんぼり・困り・照れ・半泣き | `ParamAngry`・`ParamSad`・`ParamTroubled`・`ParamEmbarrassed`・`ParamTeary` を1。どれも折れ耳 `ParamEarFold=1`・`ParamEar=0` |
| わくわく | `ParamExcited=1`・`ParamEar=1` |
| ジト目 | `ParamJitome=1`・`ParamEar=-0.35`・`ParamCheek=0.15` |

ほかの専用キーは0へ戻す。まばたき・目線・口パクは固定しない。頬の赤み（`ParamCheek` と各表情の赤み）は目の下の部品より上に描く。

## 身体・尻尾・ほっぺ

- 上着 `ParamCielJacketVisible`（0=脱衣、1=着用）、手 `ParamCielHandPoseL/R`（0=自然手、1=開き手、2=握り手）。
- 尻尾 `ParamCielTailWag`（−1=画面左、0=体の後ろ、1=画面右）。中ほど・毛先は物理演算の出力。
- ほっぺ `ParamCielCheekPoke/PullX/PullY/Jiggle{L,R}`。L はモデルの左（画面の右）。揺れ（Jiggle）は物理演算の出力。詳しくは [current/README.md](../current/README.md)。

過去の版の確認図・候補は Git の履歴（タグ `archive/pre-history-cleanup` 以前）か、ローカルの `.local/history/` にある。
