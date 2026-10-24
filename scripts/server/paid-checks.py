#!/usr/bin/env python3
"""料金のかかる試験（server/agent/paid_checks.toml）のうち、変えたファイルに関係するものと、その料金の目安を出す。

試験そのものは動かさない（開発用の会話サーバーで、必要なものだけ手で動かす）。Python 3.11+。

  python scripts/server/paid-checks.py              # まだコミットしていない変更に関係する試験
  python scripts/server/paid-checks.py --since main~3   # その版から今まで（コミット済みも含む）に関係する試験
  python scripts/server/paid-checks.py --all        # 全部
"""
import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT = 'server/agent/'


def changed(since: str | None) -> list[str]:
    args = ['git', '-C', str(ROOT), 'diff', '--name-only'] + ([since] if since else ['HEAD'])
    names = subprocess.run(args, capture_output=True, text=True, check=True).stdout.split()
    untracked = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '--others', '--exclude-standard'],
                               capture_output=True, text=True, check=True).stdout.split()
    return [n[len(AGENT):] for n in names + untracked if n.startswith(AGENT)]


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--since', help='この版から今までの変更を見る（既定はまだコミットしていない変更）')
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args()
    checks = tomllib.loads((ROOT / AGENT / 'paid_checks.toml').read_text(encoding='utf-8'))
    files = changed(args.since)
    picked = {}
    for name, c in checks.items():
        hits = [f for f in files if any(f.startswith(p) for p in c['covers'])]
        if args.all or hits:
            picked[name] = hits
    if not picked:
        print('料金のかかる試験で、回したほうがよいものはありません（回帰テストは run-regression.py で無料で回せます）。')
        return
    total = 0.0
    for name, hits in picked.items():
        c = checks[name]
        total += c['cost_max_usd']
        print(f'■ {name}：{c["what"]}')
        print(f'  料金の目安：{c["cost"]}')
        if hits:
            print(f'  関係する変更：{", ".join(hits)}')
        print(f'  動かし方：{c["command"]}')
    print(f'\n全部回すと最大でおよそ {total:.1f} ドル。必要なものだけ回してください（docs/paid-checks-ja.md）。')


if __name__ == '__main__':
    main()
