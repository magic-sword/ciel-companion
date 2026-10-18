# -*- coding: utf-8 -*-
"""覚えている人の記録の管理（一覧・メモを見る・呼び名を直す・削除）。自宅サーバーで、会話サーバーのコンテナの中から使う。

  docker compose exec agent python speaker_admin.py list
  docker compose exec agent python speaker_admin.py notes <番号>
  docker compose exec agent python speaker_admin.py relation <番号>
  docker compose exec agent python speaker_admin.py rename <番号> <新しい呼び名>
  docker compose exec agent python speaker_admin.py delete <番号>
  docker compose exec agent python speaker_admin.py delete-all

声の特徴そのものは表示しない。メモとシエルの気持ちは本人に関わる情報なので、見るのは管理のときだけにする。
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
                'SELECT p.id, p.name, p.consented_at, p.last_seen_at, count(v.id), '
                '(SELECT count(*) FROM person_notes n WHERE n.person_id = p.id) FROM people p '
                'LEFT JOIN voiceprints v ON v.person_id = p.id GROUP BY p.id ORDER BY p.id')).fetchall()
            print('番号\t名前\t同意した日時\t最後に話した日時\t見本の数\tメモの数')
            for pid, name, consented, seen, n, n_notes in rows:
                seen_text = f'{seen:%Y-%m-%d %H:%M}' if seen else '-'
                print(f'{pid}\t{name}\t{consented:%Y-%m-%d %H:%M}\t{seen_text}\t{n}\t{n_notes}')
        elif cmd == 'notes' and len(args) == 2:
            for (text,) in await (await conn.execute(
                    'SELECT text FROM person_notes WHERE person_id = %s ORDER BY id', (int(args[1]),))).fetchall():
                print('-', text)
        elif cmd == 'relation' and len(args) == 2:
            row = await (await conn.execute(
                'SELECT stage, feeling, mood, sessions, stage_sessions, updated_at FROM person_relationship '
                'WHERE person_id = %s', (int(args[1]),))).fetchone()
            if row is None:
                print('まだ関係を書いていません')
            else:
                stage, feeling, mood, sessions, stage_sessions, updated = row
                print(f'段階：{stage}（ちゃんと話した会話 {sessions}、この段階で {stage_sessions}、更新 {updated:%Y-%m-%d %H:%M}）')
                print(f'気持ち：{feeling or "-"}')
                print(f'気分：{mood or "-"}')
        elif cmd == 'rename' and len(args) == 3:
            n = (await conn.execute('UPDATE people SET name = %s WHERE id = %s', (args[2], int(args[1])))).rowcount
            print('直しました' if n else 'その番号の人はいません')
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
