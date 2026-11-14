# ゲーム側MCPの作業契約

> 責務：ゲーム非依存の依頼・予算・判断・取消・work状態の契約。

2026-11-09実装。接続profileは2、`profile.work.version`は1。ゲーム側が計画と実行状態の正本を持ち、シエル側は受付・判断回答・中止・状態の投影を行う。最初の能力はMinecraftのアイテム調達。

## 通信の対応

`game://profile` の `work` に能力の一覧と `submit`・`status`・`answer`・`cancel` のツール名を公開する。呼び出しは通常のMCP `tools/call`、イベントは既存の `notifications/message`（logger=`ciel.event`）。profileの旧版は拒否し、旧 `minecraft_goal_plan/step/repair` と直接の採集・製作ツールは公開しない。

使用中のPython SDK 1.30.0にはMCP Tasksの型があり、JS SDK 1.32.2では `experimental.tasks.registerToolTask` が実験的APIとして提供される。今回の独自状態には、判断待ちと体の停止確認が含まれるため、通常のツール上の作業契約を使用する。標準Tasksと並行した二重管理や、標準Tasks対応を示す広告は行わない。

## 作業の依頼と状態

`minecraft_task_submit` の入力：

```json
{
  "request_id": "user-item-id",
  "capability": "minecraft.pursue_goal",
  "arguments": {"request": "石のつるはしを1本作ってください。"},
  "budget_ms": 90000,
  "constraints": {}
}
```

元の自然文（1〜2000字）を変更せず渡す。能力の`handoff={version:1,argument:"request",constraints:{},seconds:120}`に従い、ホストは依頼意図と権限を確認した後、引数生成の追加推論を行わない。依頼は上流Agent.handleMessageへ入り、Prompter・History・SelfPrompter・NPCと標準命令で処理する。CIEL独自の目標JSON、命令選択プロンプト、材料計画を重ねない。対応できない依頼や失敗は標準動作の結果として報告する。

能力の説明文には能力が何をするかだけを書き、ほかの能力や撤去済みの名前を書かない（ほかの用途を挙げると、その依頼がこの能力へ寄った）。

CIEL側で数量目標を固定したり、自動帰還・不足分の補充を実施したりしない。これらは依頼内容とMindcraftの判断に委ねる。上流Agentの応答終了かつ身体がidleになった場合、native_finished=true・objective_verified=falseを証拠としてworkをsucceededへ進める。これは応答処理の終了であり、成果の検証成功ではない。本文に未検証であることを明示し、実際の目的達成はゲーム観測・ベンチマーク・利用者の確認で判定する。retryは元の依頼を上流Agentへ再送し、同じ目標所持数を保証する独自処理は挟まない。旧minecraft.obtain_itemとminecraft.edit_regionは受け付けない。

`budget_ms` は受付時の残り時間で100〜120000ms。サーバーの単調時計で期限を固定し、再送・修復・判断回答では更新しない。シエル側は依頼の解釈時間も差し引く。終了処理の余裕を予約し、サーバー単独でも期限で中止へ移る。

同一request_idの再送は同じtask_idを返す。引数が違う再送は `request_id_conflict`。追従だけが動いている場合は新規workを受け付け、対象ID付きの停止を確認してからMindcraftへ渡す。施工は計画の検証後に停止する。解釈・停止待ちも元の予算に含め、別の身体命令に切り替わった場合はそれを停止しない。資源や到達可能性まで受付時に保証するものではない。

別workの実行中・停止未確認・追従以外の体の別作業中・防御や食事中・次の身体命令が待機中は `busy`。今回の自動切り替えは追従からworkへの移行を対象とし、採集・施工中の別workへの置換は行わない。履歴上限512件に達した接続では新規作業を拒否し、IDを追い出して再実行する処理は行わない。

状態応答には `version`、`session`、`task_id`、`request_id`、単調増加の `revision`、`state`、`capability`、`arguments`、`reason`、`evidence`、`decision`、`remaining_ms`、事実に基づく短い `message` がある。

状態は `accepted`・`running`・`needs_decision`・`cancelling`・`succeeded`・`failed`・`cancelled`。未対応の版、別session/task、古いrevision、終端状態からの復帰は適用しない。通信エラーは「状態不明・停止未確認」と表示し、成功や停止に読み替えない。

## 判断と中止

`minecraft_task_answer` は `task_id`、`decision_id`、`action=retry|cancel`。IDの一致する判断待ちだけを受け付け、retryも元の制約と期限内、3回までに限定する。Mindcraftの外側にレシピ分解・修復ループを重ねない。実行例外は失敗として返し、成功するまで探索を繰り返す根拠にしない。

`minecraft_task_cancel` はtask_idを指定する。体へ対象を固定した停止を送り、現在・待機の操作がなくblockedでもないことを確認して `cancelled` とする。確認できないときは `cancelling / stop_unconfirmed` を保ち、新しい作業を拒否する。遅い計画・技の完了・判断回答で再開しない。

シエルの明示的な停止入力は推論待ちを通さず処理する。依頼理解の生成中でも世代を更新し、後から返った判断で作業を始めない。質問・引用・否定を単なる停止キーワードで実行しない。

## 状態と計測

最新状態は `minecraft_task_status` で再取得でき、`game://state.work` にも含む。通知 `work_state` を主に使い、シエル側の2秒間隔の状態取得で欠落を補う。`work_action` と `work_action_result` はゲーム内部で実際に技を発行したときと結果が戻ったときの計測用イベント。

`work_activity`は同じ操作IDの`thinking`・`executing`・`returning`を知らせ、workのmessage/revisionへ反映する。古い操作や終了後の通知は反映しない。これは表示上の進捗であり、所持品・到達の成功証拠ではない。

ベンチマークはこれらのイベントで初回操作・未完了操作を追跡し、MCPの状態取得回数は `status_polls`、技の発行は `work_actions` として分ける。状態取得だけで操作回数の上限を消費しない。最終採点はRCONの所持品等で独立して行い、作業の成功通知を採点の正解にしない。

Unityへは[作業・会話の表示契約](../app/work-display-contract-ja.md)の `goal.state v2` で送る。元のstate、session/task_id/revision、判断ID、確認の有効期間、残り予算を保持する。操作は `goal.control v2` で表示対象を固定する。空の段一覧、旧pausedへの集約、can_resumeは撤去した。画面と配信が同じ表示モデルを使い、会話・リアクションは作業と並行して示す。

## 施工能力の追加設計

現在のMindcraft標準構成では、この節の独自prepare→edit_region実行経路を公開しない。minecraft_prepare_regionとminecraft_pointed_actionも非公開。以下は保持している旧実装の契約であり、現行Agentの施工保証ではない。再導入は使用感を確認してから別途判断する。

現行work 1の状態・予算・取消・判断APIは維持し、Minecraftの能力として`minecraft.edit_region`を提供する。施工の対象・完成条件・準備は[Minecraftの段階1設計](minecraft/minecraft-design-ja.md#段階1を完了するための設計)が所有する。`tasks.js`はpursue_goalとedit_regionを能力別に検証・実行する。

施工のsubmitは`arguments={"plan_id":"ゲームが発行したID"}`、`constraints={"failure_policy":"stop"}`、既存のrequest_idと残りbudget_msを持つ。計画IDは権限ではなく、同じ所有者・接続・ワールド・未失効の計画であることをサービスが検証する。状態応答のargumentsはこの依頼を保持し、evidenceに正規化した施工仕様・確認済みセル数・変更数・部分結果を置く。UIへ内部の段一覧を公開しない。

サービスはsubmit時に計画を一つのtaskへ結び付ける。同一request_idの再送は同じtask、別request_idで使用済みplan_idを流用した場合は`plan_already_used`。再依頼は現地を読み直した新計画を必要とする。完成済みのセルは新計画でも保持する。計画作成・依頼解釈・確認に使った時間を引いた残りだけを渡し、準備完了時に90秒へ戻さない。

実行可能ならaccepted→running→succeeded、途中の不能は既存の取消処理で物理停止を確認し、cancelledと理由・部分結果を返す。無効な計画は受付前の拒否で、成功workを作らない。停止未確認はcancellingのまま新作業を拒否する。施工の曖昧さはsubmit前の草案で確認し、既存のneeds_decision/retryを新しい範囲への変更に流用しない。work_answerのretryは制約も期限も変更しない既存意味を維持する。

実装時は能力別の入力検証・計画器・結果メッセージへ分離し、採集用のitem/quantityを施工へ強制しない。work 1とgoal.state/control v2で表現できる範囲を使い、もし外枠の互換性を変える必要が判明したら、契約版と送受信・UI・評価器を同じ変更で更新する。別の施工専用状態機械を会話ホストへ追加しない。

関連：[ベンチマーク](minecraft/minecraft-benchmark-ja.md)。
