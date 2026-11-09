# YouTubeコメントの入力と返答

> 責務：配信コメントの取得・選別・権限・会話への入力。

この資料は配信URLの指定、コメント取得と選別、会話への投入、返答権限を説明する。非同期入力の外枠・優先順位は[反応契約](../conversation/service-events-and-reactions-ja.md)、取得処理は[サービス境界](../conversation/service-boundaries-ja.md)を参照する。

アプリの配信設定にYouTubeのURLを指定し、サーバー側の`YOUTUBE_API_KEY`で動画情報とライブコメントを取得する。任意URLをモデルに取得させず、資格情報はホストが保持する。取得間隔・同時要求・保持本文量を制限し、YouTubeのクォータと通信失敗を扱う。

新着コメントを基盤アダプターから入力イベントへ変換する。元の時刻・IDを保持し、古いコメント、重複、混雑時の集約を[反応基盤](../conversation/service-events-and-reactions-ja.md)で管理する。通常の会話や歌をコメントで無条件に割り込ませない。コメントへの返答は生成完了だけで発話済みにしない。

コメントの本文は信頼できない入力として扱う。持ち主の本人確認・保存同意・ゲーム操作の権限へ昇格させず、コメントから許可した能力だけを公開する。道具の結果を受けた続きでも発言元の権限を維持する。明示的に公開していない呼び出しは実行前に拒否する。

実装は`youtube_chat.py`、`youtube_source.py`、MCPの配信データ取得サービス、`reactions.py`と`mind.py`を参照する。テストは`test_youtube_chat.py`、`test_comment_tools.py`等。現在の実機確認範囲は[確認状況](../testing/verification-status-ja.md)が正本。
