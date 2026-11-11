# 量子化GGUFで重み直接編集を試す

作業起点はリポジトリのルート。以下は現行Qwen3.5-35B-A3B-Q4_K_Mで確認した経路。他モデル・他テンソルは形式・shape・token対応を改めて確認する。理論と配置条件は[実施方針](../../../../docs/operations/weight-space-programming-ja.md#量子化済み35bの限定的な直接編集)、測定結果は[実測の正本](../../../../docs/testing/weight-space-results-ja.md#量子化35bのeos重み編集)を読む。

## 方法を選ぶ

- ブロックスケールの編集：元checkpoint不要。既存量子化値をスケールできる。確認済み実装はEOS出力行のQ6_Kのみ。
- 任意の方向を足す編集：必要な行・層を逆量子化して差分を作り、対応量子化器で戻す方法を検討する。未編集の往復変換対照も必要。今回のスケール編集器は対応しない。
- 内部ニューロンの因果修復：対応hookとモデル構造の観察が必要。元高精度重みが必要な方法と、量子化エンジン上で実現できる方法を個別に判断する。

量子化GGUFから元の高精度値は復元できない。直接編集が実行できたことと会話品質が改善したことを分けて報告する。確認済みEOS1.05倍の予備試験では本文が変わらず、改善しなかった。これを改善済みレシピとして採用しない。

## 編集前と編集後の確認

1. 元GGUF hash、architecture、テンソル型・shape、token文字列とID、入力埋込みとの共有有無を確認する。ファイル名のQ4_K_Mだけから全テンソルを4bitと判断しない。
2. 対象と仮説、候補数・生成量・時間予算を固定する。量子化値を無根拠に一律変更しない。EOS行の拡大はlogitが負なら終了を抑えるため、常に短くなる操作ではない。
3. 原本はread-onlyマウント。新規コピーへ編集し、原本hash・候補hash、実保存後の差分ノルム・有限値・丸め誤差を記録する。対象外全バイトの一致が失敗した候補は推論しない。
4. 同一環境の未編集と候補で会話の内容充足・反復・長さと、JSON・計算・停止/ツールを比較する。CPU候補を共有GPU基準へ直接比較しない。空返答・途中終了を短文化の成功と数えない。
5. 候補は本番へ自動反映しない。効果なし・退行・欠測なら採用せず、根拠と未測定範囲を実測の正本へ残す。専用コンテナ終了と共有プロセスの継続を確認する。

## 確認済み編集器の再実行

実装は`server/benchmark/gguf_eos_edit.py`。検証するarchitecture・shape・token・型はコードに固定され、異なるモデルは拒否する。Q6_Kの256要素/210byteブロック末尾FP16スケールを8個編集する。既存ファイルを上書きしない。係数1超〜1.1以下はこの予備実験の探索制限であり、一般的な安全範囲ではない。

解析用コンテナの専用依存先に`gguf==0.19.0`と`numpy==2.5.4`を準備する。自宅hostはensurepipがなかったため、既存LLM imageの`/opt/vision-venv/bin/python`から`pip --target /work/deps`を使った。通常コンテナ内へ追加インストールしない。

コンテナ内での実行例（`/models`はread-only、`/work`は専用実験先）：

```sh
PYTHONPATH=/work/deps /opt/vision-venv/bin/python /work/gguf_eos_edit.py /models/Qwen3.5-35B-A3B-Q4_K_M.gguf /work/eos105.gguf --factor 1.05
```

新しいbasenameでモデルと隣接JSON manifestを保存する。既存候補を使う場合も現在のファイルhashとmanifestを照合する。

## 隔離比較と取得

`server/benchmark/gguf_eos_experiment.py`は自宅host上で動くCPU専用の7課題pilot。候補は`eos105.gguf`、manifestは`eos105.json`、出力は`pilot-01`に固定されている。別候補や再実行ではコードのパス・出力IDと計画を先に揃え、既存結果を削除して再利用しない。実験実行中に配置済みコードやpromptを入れ替えない。

必要な配置ファイル：

- 編集器、比較器、`server/benchmark/weight_space.py`
- `server/benchmark/weight_space/{suite,conversation-suite}.json`
- 現行の`character.md`・`ciel_self.md`・`app.md`・`tool_discovery.md`・`game.md`

配置先は`~/work/ciel-weight-space-quant`直下。`scripts/server/weight-space-remote.py`は既存SSH設定を利用し、`--upload`のファイルをbasenameで配置する。実験先は読み込むPythonファイルに`root`として渡される。

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts/server/weight-space-remote.py <実行するローカルPythonファイル> --upload server/benchmark/gguf_eos_edit.py
```

実行ファイルには、明示した専用コンテナでの編集、または`subprocess.run(['python3','-B',str(root/'gguf_eos_experiment.py')],check=True)`等の必要な操作だけを書く。上記は操作の入口の例であり、依存・fixture配置の代用ではない。

結果取得用Pythonは`root/'pilot-01'`のJSON、隣接編集manifest、ソースとprompt、共有`/mode`、専用コンテナの残存確認をJSONとして標準出力へ出す。`--save-json <新しいローカルファイル>`でGit対象外の`server/benchmark/data/`へ保存できる。秘密・環境変数・会話の個人情報を収集しない。

比較器は例外時にも専用`ciel-wsp-quant-pilot`を終了する。強制終了で残った場合は名前・ラベル`ciel.test=wsp-quant`を確認してそのコンテナだけを終了する。量子化編集の依頼は通常サービスの停止・置換や別GPU環境の購入までを自動で許可するものではない。
