# 作業・会話の表示契約

更新：2026-11-10。送信元、Unityの操作画面・配信映像・独立状態カード、ベンチマークを同じ契約へ移行済み。旧段一覧、pausedへの状態集約、作業を指定しない停止・再開は撤去した。ソースとオフライン検証の記録であり、本番配布の記録ではない。

## 表示する事実

作業の正本はサービスのwork 1。シエルは計画・レシピ・修復手順を複製せず、依頼名、状態、サービスの説明、判断待ちの内容、残り実行予算を表示する。空の段一覧から0/0や進捗率を作らない。予算は完了予測ではない。サービスの状態を確認できない間は予算を表示しない。

| work.state | 表示 | 操作 |
|---|---|---|
| accepted | 受付済み・開始待ち | 止める |
| running | 実行中 | 止める |
| needs_decision | 判断待ち。サービスからの説明 | 止める／確認済みの判断に再試行する |
| cancelling | 停止確認中 | 再開・再試行を表示しない |
| succeeded | できた！ | なし |
| failed | 完了できませんでした | なし |
| cancelled | 停止を確認しました | なし |

終端は8秒間表示する。新しい作業を受け付けたら新しい作業を表示する。最後に確認した終端の事実は通信の鮮度が落ちても実行中へ戻さない。表示の形式不一致は終端の成功表示にも優先して状態不明にする。

作業と会話・リアクションは並行して示す。例：「石のツルハシ／実行中」と「会話：コメントへの返事を考えています」。発話中だから作業完了とは判断しない。独立配信カードには会話専用行を設け、依頼者の個人名・記憶内容・内部ログを載せない。長時間作業を伴わない機能選択・応答待ちも別に示す。`load_capabilities`等は利用者向けの機能名で表示する。直接の追従など、work以外の体の作業も会話とは別に表示する。

## ciel.goalの状態通知

名前・topicは維持し、形式を **goal.state v2** に統一する。v1の変換・別名・二重送信は行わない。

```json
{
  "v": 2, "type": "goal.state", "stream_id": "会話内の送信元UUID", "revision": 12,
  "confirmed": true, "confirmed_ago_ms": 0, "valid_for_ms": 10000,
  "has_task": true,
  "task": {
    "session": "サービスのセッション", "task_id": "作業ID", "revision": 3,
    "service": "minecraft", "service_label": "Minecraft", "title": "石のツルハシを用意する",
    "state": "needs_decision", "message": "材料が見つかりません", "reason": "not_found",
    "remaining_known": true, "remaining_ms": 42000,
    "decision_id": "判断ID", "decision_message": "",
    "can_stop": true, "can_retry": true
  }
}
```

作業なしは `has_task=false, task=null`。UnityのJsonUtilityがnullを空オブジェクトとして復元する場合にも、has_taskから区別する。外側revisionは送信ごとの連番、task.revisionはサービスの状態版であり別物。同じ作業版の正常な状態取得も確認時刻を更新して通知し、完了・判断待ちの発話は重複させない。remaining_msだけは同じ作業版でも減る。

サービスの確認間隔は2秒、RPC期限は6秒、表示の確認有効期間は10秒。通信失敗は即座にconfirmed=falseとし、アプリだけ通信が途絶えた場合も受信時刻とconfirmed_ago_msから有効期間を判定する。状態変更時刻を接続確認の代用にしない。実行予算はサービスの残りとホストの固定期限の小さい方に制限する。判断・再送・復旧で期限を延ばさない。

実行中に確認が失効したら「状態不明・停止未確認」を表示し、最後の作業IDは保持する。同じ版の正常応答でも確認を復旧できる。古い外側revision、退役したstreamの通知は適用しない。不正な通知・未対応の版は状態不明にし、待機・成功・停止に置換しない。

## 対象を固定した操作

```json
{
  "v": 2, "type": "goal.control", "action": "retry",
  "stream_id": "会話内の送信元UUID", "session": "サービスのセッション",
  "task_id": "作業ID", "revision": 3, "decision_id": "判断ID"
}
```

操作はstopまたはretry。Unityは表示中のスナップショットと最新状態のID・版・判断IDを照合する。ホストもロック取得後に再検証する。古い画面の操作を新しい作業に付け替えない。retryは確認が新鮮なneeds_decisionだけ。状態不明でも最後の作業を指定したstopは可能だが、送信しただけで停止済みと表示しない。cancellingからの再試行や終端への操作は表示しない。

## 実装と検証

- 送信・操作検証：`server/agent/goals.py`。状態確認の例外でも監視を継続する。
- Unity：`CielConversation.Goal.cs`の受信・操作と`CielWorkPresentation`が共通契約。操作パネル、配信の重畳表示、独立状態カードが同じ表示モデルを使う。
- ベンチマーク：drivers/run/policyもtask.stateを参照する。採点は従来どおりRCONで実物を確認し、表示を採点の正解にはしない。期限・課題集合は変更していない。停止未確認のcancellingは不能報告後の待機とみなさず、旧形式の受信は環境障害として中断する。
- Python：`test_goals.py`、実MCPの`test_game_env.py`、ベンチマークの回帰。
- .NET 10：`dotnet run --project scripts/unity/work-display-check/WorkDisplayCheck.csproj`。実際のC#受信・操作・表示ソースをリンクし、時計・JSON・送信だけ代用して35項目を確認。UnityのJsonUtilityそのものや描画を検証する試験ではない。生成物はserver/benchmark/data内。
- Unity Editor用：`CielStreamStatusCheck.Run`、`CielAudienceCardCheck.Run`。本体・EditorのC#コンパイルと、Unityでの実行・画面描画は別に記録する。

この端末ではEditorバッチ起動がライセンスエラー（198）で停止したため、Editorでの実行・画像出力は未確認。代替のC#検証器は通過した。Python一式とC#ビルドの最終結果は[回帰テスト](regression-tests-ja.md)を参照。

## 反映時の単位

会話サーバーとUnityアプリを同じv2対応版として再ビルド・配布する。起動済みアプリも再起動し、会話を再接続する。旧アプリと新サーバーの混在を互換処理で隠さない。ゲーム側のwork 1は変更していないため、この表示変更だけでMinecraft本体・ワールドを再起動する必要はない。本番反映は確認済みGitコミット単位という運用を維持する。
