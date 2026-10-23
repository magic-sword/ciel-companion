"""会話のまとめ（議事録・目標と計画・調べもののまとめ）。

- kinds.py：項目の種類（要点・話題・決定・やること・問い・発見・目標・アイデア）。形の検証と Markdown への変換。
- templates.py：テンプレート（config/summaries/）。見出しと種類の組み合わせと、書き方の指示。
- state.py：ID の付いた項目の一覧。ライブの差分（足す・直す・消す）と、清書での置き換え。
- live.py：会議の途中に、新しい発言の分だけ軽いモデルで差分を作る。
決めたことは docs/decisions/meeting-minutes-ja.md。
"""
