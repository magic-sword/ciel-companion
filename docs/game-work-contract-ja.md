# ゲーム側MCPの作業契約

2026-11-09実装。接続profileは2、`profile.work.version`は1。ゲーム側が計画と実行状態の正本を持ち、シエル側は受付・判断回答・中止・状態の投影を行う。最初の能力はMinecraftのアイテム調達。

## 通信の対応

`game://profile` の `work` に能力の一覧と `submit`・`status`・`answer`・`cancel` のツール名を公開する。呼び出しは通常のMCP `tools/call`、イベントは既存の `notifications/message`（logger=`ciel.event`）。profileの旧版は拒否し、旧 `minecraft_goal_plan/step/repair` と直接の採集・製作ツールは公開しない。

使用中のPython SDK 1.30.0にはMCP Tasksの型があり、JS SDK 1.32.2では `experimental.tasks.registerToolTask` が実験的APIとして提供される。今回の独自状態には、判断待ちと体の停止確認が含まれるため、通常のツール上の作業契約を使用する。標準Tasksと並行した二重管理や、標準Tasks対応を示す広告は行わない。

## 作業の依頼と状態

`minecraft_task_submit` の入力：

```json
{
  "request_id": "user-item-id",
  "capability": "minecraft.obtain_item",
  "arguments": {"item": "stone_pickaxe", "quantity": 1, "quantity_mode": "inventory_target"},
  "budget_ms": 90000,
  "constraints": {"resource_scope": "search", "failure_policy": "ask"}
}
```

数量は1〜64。`inventory_target` は所持目標、`gain` は開始時から増やす数。新規製作回数の指定は未対応として受付前に確認する。`resource_scope=nearby` は資源未発見時に探索の段を追加しない指定、`search` は既存探索を許す指定であり、数値の探索半径を保証する機能ではない。`failure_policy=stop` は継続できないときに停止を確認して中止、`ask` は判断待ち。制約を省略・変更して実行しない。

`budget_ms` は受付時の残り時間で100〜120000ms。サーバーの単調時計で期限を固定し、再送・修復・判断回答では更新しない。シエル側は依頼の解釈時間も差し引く。終了処理の余裕を予約し、サーバー単独でも期限で中止へ移る。

同一request_idの再送は同じtask_idを返す。引数が違う再送は `request_id_conflict`、実行中・停止未確認・体の別作業中は `busy`。履歴上限512件に達した接続では新規作業を拒否し、IDを追い出して再実行する処理は行わない。

状態応答には `version`、`session`、`task_id`、`request_id`、単調増加の `revision`、`state`、`capability`、`arguments`、`reason`、`evidence`、`decision`、`remaining_ms`、事実に基づく短い `message` がある。

状態は `accepted`・`running`・`needs_decision`・`cancelling`・`succeeded`・`failed`・`cancelled`。未対応の版、別session/task、古いrevision、終端状態からの復帰は適用しない。通信エラーは「状態不明・停止未確認」と表示し、成功や停止に読み替えない。

## 判断と中止

`minecraft_task_answer` は `task_id`、`decision_id`、`action=retry|cancel`。IDの一致する判断待ちだけを受け付け、retryも元の制約と期限内に限定する。既知の修復は合計6回、同じ段・引数・理由で2回まで。判断からの再試行も同じ予算を消費し、既に修復を重ねた作業の無制限な再試行は拒否する。未知の段を共通部の子目標ツリーに変換しない。

`minecraft_task_cancel` はtask_idを指定する。体へ対象を固定した停止を送り、現在・待機の操作がなくblockedでもないことを確認して `cancelled` とする。確認できないときは `cancelling / stop_unconfirmed` を保ち、新しい作業を拒否する。遅い計画・技の完了・判断回答で再開しない。

シエルの明示的な停止入力は推論待ちを通さず処理する。依頼理解の生成中でも世代を更新し、後から返った判断で作業を始めない。質問・引用・否定を単なる停止キーワードで実行しない。

## 状態と計測

最新状態は `minecraft_task_status` で再取得でき、`game://state.work` にも含む。通知 `work_state` を主に使い、シエル側の2秒間隔の状態取得で欠落を補う。`work_action` と `work_action_result` はゲーム内部で実際に技を発行したときと結果が戻ったときの計測用イベント。

ベンチマークはこれらのイベントで初回操作・未完了操作を追跡し、MCPの状態取得回数は `status_polls`、技の発行は `work_actions` として分ける。状態取得だけで操作回数の上限を消費しない。最終採点はRCONの所持品等で独立して行い、作業の成功通知を採点の正解にしない。

Unityへは[作業・会話の表示契約](work-display-contract-ja.md)の `goal.state v2` で送る。元のstate、session/task_id/revision、判断ID、確認の有効期間、残り予算を保持する。操作は `goal.control v2` で表示対象を固定する。空の段一覧、旧pausedへの集約、can_resumeは撤去した。画面と配信が同じ表示モデルを使い、会話・リアクションは作業と並行して示す。

関連：[全体の再設計](minecraft-execution-redesign-ja.md)、[ベンチマーク](minecraft-benchmark-ja.md)。
