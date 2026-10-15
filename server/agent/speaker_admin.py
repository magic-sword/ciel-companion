# -*- coding: utf-8 -*-
"""覚えている人の記録の管理（一覧・削除）。自宅サーバーで、会話サーバーのコンテナの中から使う。

  docker compose exec agent python speaker_admin.py list
  docker compose exec agent python speaker_admin.py delete <番号>
  docker compose exec agent python speaker_admin.py delete-all

声の特徴そのものは表示しない。
"""
import asyncio
import os
import sys

import psycopg


async def main(args: list[str]) -> int:
    url = os.environ.get('CIEL_DB_URL')
    if not url:
        print('CIEL_DB_URL がありません')
        return 1
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
        cmd = args[0] if args else 'list'
        if cmd == 'list':
            rows = await (await conn.execute(
                'SELECT p.id, p.name, p.consented_at, p.last_seen_at, count(v.id) FROM people p '
                'LEFT JOIN voiceprints v ON v.person_id = p.id GROUP BY p.id ORDER BY p.id')).fetchall()
            print('番号\t名前\t同意した日時\t最後に話した日時\t見本の数')
            for pid, name, consented, seen, n in rows:
                print(f'{pid}\t{name}\t{consented:%Y-%m-%d %H:%M}\t{seen:%Y-%m-%d %H:%M}' if seen else
                      f'{pid}\t{name}\t{consented:%Y-%m-%d %H:%M}\t-', f'\t{n}')
        elif cmd == 'delete' and len(args) == 2:
            n = (await conn.execute('DELETE FROM people WHERE id = %s', (int(args[1]),))).rowcount
            print('消しました' if n else 'その番号の人はいません')
        elif cmd == 'delete-all':
            await conn.execute('DELETE FROM people')
            print('すべて消しました')
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main(sys.argv[1:])))
