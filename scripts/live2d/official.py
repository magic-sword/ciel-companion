"""シエルの Live2D 作業が、最新の正式モデルから始まっているかを確かめ、違えば止める。

正式モデルは assets/ciel/current/approved.json の rig（assets/ciel/rig/ciel.cmo3）と、そのハッシュ rig_sha256。
- require_official_rig(path)：組み込みの最初の入力は、正式モデルそのもの（ハッシュが一致）でなければ止める。
- require_current_export(model3)：途中の作業モデル（Cubism で保存し直すとハッシュが変わる）は、Cubism で書き出した SDK が
  今の SDK（assets/ciel/runtime）の部品とパラメーターを全部持つかで確かめる。古いモデルから始めると欠けるので止まる。
.cmo3 の中身は読まない（ハッシュだけ）。部品やパラメーターは、書き出した .moc3 を Cubism Core で読んで比べる。

コマンドとしても使える：
  python -I scripts/live2d/official.py モデル.cmo3 [書き出し.model3.json ...]
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

APPROVED = ROOT/'assets/ciel/current/approved.json'
RUNTIME = ROOT/'assets/ciel/runtime/Ciel.model3.json'


class NotOfficial(SystemExit):
    pass


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def approved():
    return json.loads(APPROVED.read_text(encoding='utf-8'))


def official_rig():
    return ROOT/approved()['rig']


def _stop(message):
    raise NotOfficial('[official] 止めました：' + message +
                      f'\n  正式モデル：{official_rig().relative_to(ROOT).as_posix()}（approved.json の rig_sha256）。'
                      '\n  最新の正式モデルのコピーから作業をやり直してください。')


def require_official_rig(path):
    """組み込みの最初の入力が、正式モデルそのものか"""
    a = approved()
    if _sha(path) != a['rig_sha256']:
        _stop(f'{path} は正式モデルではありません（ハッシュが approved.json と違う）。')
    if _sha(ROOT/a['rig']) != a['rig_sha256']:
        _stop('正式モデルのファイルが approved.json と食い違っています（採用の手順が途中で止まっている）。')


def _export_names(model3):
    import cubism_core as cc
    m = cc.Model(str(model3))
    m.update()
    return {d['id'] for d in m.drawables()}, set(m.param_range)


def require_current_export(model3):
    """書き出した SDK が、今の SDK の部品とパラメーターを全部持っているか"""
    need_d, need_p = _export_names(RUNTIME)
    got_d, got_p = _export_names(model3)
    for label, need, got in (('部品', need_d, got_d), ('パラメーター', need_p, got_p)):
        missing = sorted(need - got)
        if missing:
            _stop(f'{model3} には、今の SDK の{label}が {len(missing)} 個ありません（例：{", ".join(missing[:5])}）。'
                  '古いモデルから書き出した可能性があります。')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    for arg in sys.argv[1:]:
        if arg.endswith('.cmo3'):
            require_official_rig(arg)
            print(f'OK {arg}：正式モデルそのもの')
        elif arg.endswith('.model3.json'):
            require_current_export(arg)
            print(f'OK {arg}：今の SDK の部品とパラメーターをすべて持つ')
        else:
            raise SystemExit(f'.cmo3 か .model3.json を指定してください：{arg}')


if __name__ == '__main__':
    main()
