# 体の命令と停止のライフサイクル

> 責務：低水準の体の命令、世代・切替・後片付け・停止確認。

この資料はゲームの低水準命令の所有権・切替・停止確認を説明する。利用者の長い依頼は[work契約](game-work-contract-ja.md)、画面への投影は[表示契約](../app/work-display-contract-ja.md)が正本。アプリ側に別の計画器を置かない。

## 状態の所有者

`server/minecraft/src/body-command.js`の`BodyCommands`が体の現在・待機命令と世代を管理する。`Runner`はMinecraft固有の準備、技、後片付けを担当する。`game://state.body`の版1スナップショットを現在状態とし、開始・終了イベントだけから推測しない。

受付と実行開始を区別する。状態は`idle`、`accepted`、`preparing`、`running`、`waiting`、`stopping`、確認できない場合の`unknown`。待機には防御・食事・停止期限超過などの理由を付ける。workの`cancelling`とbodyの`stopping`は異なる層の状態である。

## 切替と取消

- 古い命令の停止と後片付けを待ってから次を開始する。停止未確認なら新しい命令を開始しない。
- 停止の対象ID・接続世代を固定し、遅い停止・完了・開始応答を新しい命令へ適用しない。
- 停止中の置換要求は最新を採用する。期限超過で断った要求を、後から勝手に再実行しない。
- 同じ依頼IDの再送は重複実行しない。履歴・応答キャッシュには上限がある。
- 非同期の体操作は命令の所有権を検証して行う。防御・食事等の自動操作も、進行中の技を無断で奪わない。

workを持つ間の直接の体操作はホストで競合を防ぐ。Minecraft内の各段はゲーム側のtask実行器から同じ体の入口を使う。PythonのGoalRunnerが段を作ったり直接採集・製作を重ねたりする旧方式は撤去済み。

## 観測と再接続

通知とスナップショットの接続世代・revision・命令IDを照合する。終了が開始応答に先着しても命令を復活させない。正本から消えた命令の付箋は閉じるが、付箋を現在状態の正本にしない。切断をidleや停止完了へ変換しない。

会話サーバーの`game_env.py`が状態を反映し、`activity.state.body`でUIへ渡す。bodyの表示とworkの表示を二重の計画進捗にしない。思考・検索・発話は体の待ち行列へ入れない。

## 検証と反映

`server/minecraft/test/body-command.test.js`、`server/agent/tests/test_game_env.py`・`test_goals.py`が対象。停止と後片付け、世代違い、終了先着、重複、再接続、停止未確認時の新規操作拒否を確認する。[回帰テスト](../testing/regression-tests-ja.md)と[確認状況](../testing/verification-status-ja.md)を参照。

形式や状態を変更するときはminecraft-body、会話サーバー、Unityを揃えて反映する。Minecraft本体やワールドの再起動で体のサービス更新を代用しない。
