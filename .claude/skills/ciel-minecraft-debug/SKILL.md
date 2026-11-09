---
name: ciel-minecraft-debug
description: 稼働中のマイクラのシエルの体（server/minecraft）が止まる・空振りする・作れない・降りられないなどの現場調査に使う。Ciel_Debug で技を再現し、動いている体をデバッガーで読む。専用環境でのローカルLLM試験・課題追加・性能比較は ciel-minecraft-benchmark を使う。
---

# マイクラのシエルの体を調べる

この手順は稼働中のワールドの現場調査用。再現可能な課題で体やローカル LLM を評価・比較するときは、[ベンチマークスキル](../ciel-minecraft-benchmark/SKILL.md)を使う。専用環境で再現できる問題はそちらで調べる。以下の通常コンテナへの接続・再配布手順を、専用ベンチマークの起動手順として使わない。

## 決まり

- 試験用に入れるプレイヤーは **`Ciel_Debug`** だけ（スキンは `assets/minecraft/skins/Ciel_Debug.png`、シエルの 2P カラー。`docs/games/minecraft/minecraft-design-ja.md` の 20 章）。`CielEye` など別の名前を使わない。ホワイトリストにいなければ、12 章「初回」の 3 で入れ直す（その場しのぎに `whitelist add` しない）。
- 世界はユーザーの世界。試すと原木を掘る・作業台を置くなど世界が変わる。持ち主の建物の近くで試さない。試したこと（掘った・置いた場所）は報告に書く。
- 動いているシエル本人（`Ciel`）には、会話がつないでいる（体へつなげる会話は 1 つだけ）。シエルで直接試さず、`Ciel_Debug` で同じ技を試す。
- 体のコンテナを入れ直すと、シエルはマイクラから数秒抜けて入り直す（会話は切れない）。配信中ならユーザーに言ってから。
- 推測で直さない。記録で「どこで・なぜ」を確かめてから直す。見立てが外れたら、そう言って訂正する。

## 1. まず記録を見る

```bash
scripts/server/debug-log.sh pull --dev        # 会話の記録（.local/debug-logs-dev/）。tool・minecraft・board・mind_output を見る
```

- 体のログ：`"${SSH[@]}" 'docker logs --since 30m ciel-minecraft-body-1'`（`source scripts/server/ssh-target.sh` のあと）。「掘るのに時間がかかる」「守り終えた」などが出る。
- シエルの今の様子：`rcon-cli "data get entity Ciel Pos"`・`OnGround`・`Inventory`（マイクラのコンテナ `ciel-minecraft-1` の中）。
- 体の CPU：体のコンテナの `/proc/1/stat` を 5 秒あけて読む（`ps` は無い）。ほぼ 0 なら「何かを待っている」、1 コア近いなら「繰り返しから抜けられない」。

## 2. 動いている体の中を読む

```bash
.claude/skills/ciel-minecraft-debug/scripts/peek.sh bot     # bot の様子（足元・持ち物・集める的・歩く係が動いているか）
.claude/skills/ciel-minecraft-debug/scripts/peek.sh path    # 歩く係（mineflayer-pathfinder）の中（道・置いている最中か・行き先）
```

- 体を一度だけ止めて読み、すぐ続ける。デバッガーの入口が開いたままになるので、調べ終えたら体を入れ直して閉じる。
- `path` で「15 秒止まらなかった」なら、歩く係は道を歩いているか、何もしていない。

## 3. Ciel_Debug で同じ技を試す

```bash
.claude/skills/ciel-minecraft-debug/scripts/run.sh <技> '<引数の JSON>' [--tp "x y z"] [--clear] [--give "item 数"]... [--seconds 60]
# 例
.claude/skills/ciel-minecraft-debug/scripts/run.sh collect '{"block":"oak_log","count":3}' --tp "8.5 71 43.7"
.claude/skills/ciel-minecraft-debug/scripts/run.sh craft '{"item":"wooden_pickaxe","count":1}' --tp "17.5 67 41.3" --clear --give "oak_log 3"
```

- 体のコンテナの中で、体と同じ `src/skills.js` の Runner を動かす（配ってある版。手元の変更を試すときは、先に体を配る：`docs/games/minecraft/minecraft-design-ja.md` の 12 章の起動と同じ `--env-file`・`--profile` で `build`・`up -d minecraft-body`）。
- 記録：`goto`・`collect`・`dig`（掘る時間・足元・水の中）・`craft`・`path_update`/`path_reset`・`blockUpdate`・拾った物。
- シエルと同じ場所で試すと、シエルの困りごとを再現しやすい（`rcon-cli "data get entity Ciel Pos"` の座標を `--tp` に）。tp した先が水や空中だと落ちるので、始めた位置（`始める ... pos`）を確かめる。
- 終わると、写したファイルと、中に残ったプロセスを消す。

## 4. 気をつけること（前に詰まったこと）

- **docker exec を時間切れで止めても、コンテナの中の node は残る**。残った試しが固まって CPU を 3 コア分使い、9229 も取っていた（2026-11-06）。自分で道具を書くときも、終わりにコンテナの中のプロセスを確かめて消す。
- **記録は writeSync で出す**。console.log はパイプへの書き出しが後回しになり、処理が固まると出ないまま消える。
- **行き先（goal）や世界の物を JSON.stringify しない**。`GoalLookAtBlock` は世界を持っていて、文字にしようとして道具のほうが固まった。
- **スポーンの守り**：スポーンから 16 ブロックの中は、管理者でないと掘っても元に戻る（空振りに見える）。管理者が 1 人でもいると働く。今は `SPAWN_PROTECTION=0`（`server/compose.yaml`）。
- **掘る時間は掘り始めた瞬間に決まる**（足が浮いている・水の中だと 5 倍）。`dig` の記録の `digTime` を見る。
- **歩く係は、道を歩き終えて行き先に届かないと、探し直さずに待ち続ける**。体の見張り（`watched`）が 8 秒で取り消す。
- 世界の様子（ブロック・敵）はボットが壁越しに知っている。シエルが「見える」と言ってよいのは `src/sight.js` で見えるものだけ。

## 5. 報告

- 何が起きていたか（記録の時刻と中身）、原因、直したこと、確かめたこと（どこで何を試したか）、世界に残したもの（掘った・置いた場所）を、ユーザーに日本語で伝える。
- 直したら `docs/games/minecraft/minecraft-design-ja.md` に、何が起きて何を直したかを書く（章の番号が重ならないよう、最後の章を見てから足す）。
