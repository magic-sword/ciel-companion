# -*- coding: utf-8 -*-
"""シエル自身の記録の管理（出来事・育った好みを見る・取り消す）。自宅サーバーで、会話サーバーのコンテナの中から使う。

  docker compose exec agent python self_admin.py likes             … 育った好みと、根拠の出来事
  docker compose exec agent python self_admin.py history           … 好みを足した・変えた・外した記録
  docker compose exec agent python self_admin.py events [数]        … 最近の出来事（既定 20）
  docker compose exec agent python self_admin.py remove-like <番号>  … 育った好みを外す（記録にも残す）
  docker compose exec agent python self_admin.py remove-event <番号> … 出来事を消す

人の名前・事情は、出来事にも好みにも書いていない（diary.py・growth.py）。育ち方の決まりは growth.py。
"""
import asyncio
import os
import sys

import psycopg
from psycopg.types.json import Jsonb

from jst import JST


async def main(args: list[str]) -> int:
    url = os.environ.get('CIEL_DB_URL')
    if not url:
        print('CIEL_DB_URL がありません')
        return 1
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
        cmd = args[0] if args else 'likes'
        if cmd == 'likes':
            rows = await (await conn.execute(
                'SELECT id, kind, text, why, evidence, created_at, updated_at FROM ciel_likes ORDER BY created_at, id')).fetchall()
            if not rows:
                print('育った好みはまだない')
            for i, kind, text, why, evidence, created, updated in rows:
                print(f'{i}\t{kind}\t{text}\t（{why}）\t{created.astimezone(JST):%Y-%m-%d} 育つ・{updated.astimezone(JST):%Y-%m-%d} 更新')
                for e in evidence:
                    print(f'\t\t根拠 {e.get("date")}：{e.get("text")}')
        elif cmd == 'history':
            for at, action, like_id, kind, text, why in await (await conn.execute(
                    'SELECT at, action, like_id, kind, text, why FROM ciel_like_history ORDER BY at, id')).fetchall():
                print(f'{at.astimezone(JST):%Y-%m-%d %H:%M}\t{action}\t#{like_id}\t{kind}\t{text}\t（{why}）')
        elif cmd == 'events':
            limit = int(args[1]) if len(args) == 2 else 20
            for i, at, kind, text in await (await conn.execute(
                    'SELECT id, at, kind, text FROM ciel_events ORDER BY at DESC, id DESC LIMIT %s', (limit,))).fetchall():
                print(f'{i}\t{at.astimezone(JST):%Y-%m-%d %H:%M}\t{kind}\t{text}')
        elif cmd == 'remove-like' and len(args) == 2:
            async with conn.transaction():
                row = await (await conn.execute(
                    'DELETE FROM ciel_likes WHERE id = %s RETURNING kind, text, why, evidence', (int(args[1]),))).fetchone()
                if row is None:
                    print('その番号の好みはない')
                    return 1
                await conn.execute(
                    'INSERT INTO ciel_like_history (action, like_id, kind, text, why, evidence) '
                    "VALUES ('removed_by_admin', %s, %s, %s, %s, %s)", (int(args[1]), *row[:3], Jsonb(row[3])))
            print(f'外した：{row[1]}')
        elif cmd == 'remove-event' and len(args) == 2:
            cur = await conn.execute('DELETE FROM ciel_events WHERE id = %s', (int(args[1]),))
            print('消した' if cur.rowcount else 'その番号の出来事はない')
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main(sys.argv[1:])))
