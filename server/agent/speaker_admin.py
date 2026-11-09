# -*- coding: utf-8 -*-
"""覚えている人の記録の管理（一覧・メモを見る・呼び名を直す・削除・共有）。自宅サーバーで、会話サーバーのコンテナの中から使う。

  docker compose exec agent python speaker_admin.py list
  docker compose exec agent python speaker_admin.py notes <番号>
  docker compose exec agent python speaker_admin.py relation <番号>
  docker compose exec agent python speaker_admin.py rename <番号> <新しい呼び名>
  docker compose exec agent python speaker_admin.py delete <番号>
  docker compose exec agent python speaker_admin.py delete-all
  docker compose exec agent python speaker_admin.py share <番号>            開発用の会話サーバーとも共有する（本番からだけ）
  docker compose exec agent python speaker_admin.py unshare <番号>          共有をやめる（本番からだけ）
  docker compose exec agent python speaker_admin.py drop-dev-notes <番号>   開発用の会話で書いたメモだけを消す

声の特徴そのものは表示しない。メモとシエルの気持ちは本人に関わる情報なので、見るのは管理のときだけにする。
本番と開発用は同じ DB を使う（docs/services/shared-memory-ja.md）。見えるのは、CIEL_MEMORY_SCOPE の会話サーバーから見える人だけ。
開発用からは、本番と共有している人の呼び名を変える・消すことはできない。delete-all も、その会話サーバーで覚えた人だけを消す。
"""
import asyncio
import os
import sys

import psycopg

import speaker_store


async def main(args: list[str]) -> int:
    url = os.environ.get('CIEL_DB_URL')
    if not url:
        print('CIEL_DB_URL がありません')
        return 1
    scope = speaker_store.memory_scope()
    store = await speaker_store.Store.open()   # 表と印が無ければ作る（会話の始めと同じ）
    if store is not None:
        await store.close()
    seen_sql = speaker_store.visible(scope)
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
        cmd = args[0] if args else 'list'

        async def visible(pid: int) -> bool:
            row = await (await conn.execute('SELECT 1 FROM people p WHERE p.id = %s AND ' + seen_sql, (pid,))).fetchone()
            if row is None:
                print('その番号の人はいません')
            return row is not None

        async def mine(pid: int) -> bool:
            """この会話サーバーが呼び名を変える・消すことのできる人"""
            if not await visible(pid):
                return False
            row = await (await conn.execute('SELECT origin FROM people WHERE id = %s', (pid,))).fetchone()
            if row[0] != scope:
                print('その人は本番と共有している人なので、ここ（開発用）では直せません。本番で直してください')
                return False
            return True

        if cmd == 'list':
            rows = await (await conn.execute(
                'SELECT p.id, p.name, p.consented_at, p.last_seen_at, count(v.id), '
                '(SELECT count(*) FROM person_notes n WHERE n.person_id = p.id), '
                "(SELECT count(*) FROM person_notes n WHERE n.person_id = p.id AND n.origin = 'dev'), "
                'p.origin, p.shared FROM people p LEFT JOIN voiceprints v ON v.person_id = p.id '
                'WHERE ' + seen_sql + ' GROUP BY p.id ORDER BY p.id')).fetchall()
            print(f'（{scope} の会話サーバーから見える人）')
            print('番号\t名前\t同意した日時\t最後に話した日時\t見本の数\tメモの数（うち開発用で書いた数）\t印')
            for pid, name, consented, seen, n, n_notes, n_dev, origin, shared in rows:
                seen_text = f'{seen:%Y-%m-%d %H:%M}' if seen else '-'
                mark = origin + ('・共有' if shared else '')
                print(f'{pid}\t{name}\t{consented:%Y-%m-%d %H:%M}\t{seen_text}\t{n}\t{n_notes}（{n_dev}）\t{mark}')
        elif cmd == 'notes' and len(args) == 2:
            if not await visible(int(args[1])):
                return 1
            for text, origin in await (await conn.execute(
                    'SELECT text, origin FROM person_notes WHERE person_id = %s ORDER BY id', (int(args[1]),))).fetchall():
                print('-', text + ('　［開発用で書いた］' if origin == 'dev' else ''))
        elif cmd == 'relation' and len(args) == 2:
            if not await visible(int(args[1])):
                return 1
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
            if not await mine(int(args[1])):
                return 1
            await conn.execute('UPDATE people SET name = %s WHERE id = %s', (args[2], int(args[1])))
            print('直しました')
        elif cmd == 'delete' and len(args) == 2:
            if not await mine(int(args[1])):
                return 1
            await conn.execute('DELETE FROM people WHERE id = %s', (int(args[1]),))
            print('消しました')
        elif cmd == 'delete-all':
            n = (await conn.execute('DELETE FROM people WHERE origin = %s', (scope,))).rowcount
            print(f'{scope} の会話サーバーで覚えた人を {n} 人消しました')
        elif cmd == 'drop-dev-notes' and len(args) == 2:
            if not await visible(int(args[1])):
                return 1
            n = (await conn.execute("DELETE FROM person_notes WHERE person_id = %s AND origin = 'dev'",
                                    (int(args[1]),))).rowcount
            print(f'開発用の会話で書いたメモを {n} 件消しました')
        elif cmd in ('share', 'unshare') and len(args) == 2:
            if scope != 'main':
                print('共有する人を決めるのは、本番の会話サーバーからだけです')
                return 1
            n = (await conn.execute("UPDATE people SET shared = %s WHERE id = %s AND origin = 'main'",
                                    (cmd == 'share', int(args[1])))).rowcount
            print(('開発用の会話サーバーとも共有します' if cmd == 'share' else '共有をやめました') if n else 'その番号の人はいません')
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main(sys.argv[1:])))
