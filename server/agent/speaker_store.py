# -*- coding: utf-8 -*-
"""覚えている人の記録（PostgreSQL＋pgvector）。本人が同意した人の名前と声の特徴だけを置く。

- people：人（名前、同意した日時、最後に話した日時）
- voiceprints：声の特徴（192 次元、人ごとに複数、多すぎたら古いものから消す）
録音そのものは置かない。表は会話サーバーが起動のたびに作る（あれば何もしない）。
管理（一覧・削除）は speaker_admin.py。
"""
import logging
import os
from datetime import datetime

import numpy as np
import psycopg
from pgvector.psycopg import register_vector_async

log = logging.getLogger('ciel-agent.speaker_store')

DIM = 192
MAX_VOICEPRINTS = 30   # 1 人あたりの見本の上限

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS people (
    id bigserial PRIMARY KEY,
    name text NOT NULL,
    consented_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz
);
CREATE TABLE IF NOT EXISTS voiceprints (
    id bigserial PRIMARY KEY,
    person_id bigint NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    embedding vector({DIM}) NOT NULL,
    seconds real,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS voiceprints_person ON voiceprints(person_id);
"""


class Store:
    def __init__(self, conn: psycopg.AsyncConnection) -> None:
        self.conn = conn

    @classmethod
    async def open(cls) -> 'Store | None':
        """CIEL_DB_URL の DB へつなぐ。つなげなければ None（その会話は、覚えている人なしで続ける）"""
        url = os.environ.get('CIEL_DB_URL')
        if not url:
            log.warning('CIEL_DB_URL が無いので、人の声は会話の間だけ覚える')
            return None
        try:
            conn = await psycopg.AsyncConnection.connect(url, autocommit=True, connect_timeout=5)
            await conn.execute(SCHEMA)
            await register_vector_async(conn)
            return cls(conn)
        except Exception as e:
            log.warning('記録の場所（DB）へつなげない：%s', type(e).__name__)
            return None

    async def close(self) -> None:
        await self.conn.close()

    async def load_all(self) -> list[tuple[int, str, list[np.ndarray], datetime | None]]:
        """（番号、名前、声の特徴の一覧、最後に話した日時）"""
        rows = await (await self.conn.execute(
            'SELECT p.id, p.name, p.last_seen_at, v.embedding FROM people p JOIN voiceprints v ON v.person_id = p.id '
            'ORDER BY p.id, v.id'
        )).fetchall()
        people: dict[int, tuple[str, datetime | None, list[np.ndarray]]] = {}
        for pid, name, seen, emb in rows:
            people.setdefault(pid, (name, seen, []))[2].append(np.asarray(emb, dtype=np.float32))
        return [(pid, name, embs, seen) for pid, (name, seen, embs) in people.items()]

    async def add_person(self, name: str) -> int:
        row = await (await self.conn.execute('INSERT INTO people (name) VALUES (%s) RETURNING id', (name,))).fetchone()
        return row[0]

    async def rename(self, person_id: int, name: str) -> None:
        await self.conn.execute('UPDATE people SET name = %s WHERE id = %s', (name, person_id))

    async def add_voiceprints(self, person_id: int, embeddings: list[np.ndarray], seconds: float | None) -> None:
        async with self.conn.cursor() as cur:
            for e in embeddings:
                await cur.execute('INSERT INTO voiceprints (person_id, embedding, seconds) VALUES (%s, %s, %s)',
                                  (person_id, e, seconds))
            await cur.execute(
                'DELETE FROM voiceprints WHERE person_id = %s AND id NOT IN '
                '(SELECT id FROM voiceprints WHERE person_id = %s ORDER BY id DESC LIMIT %s)',
                (person_id, person_id, MAX_VOICEPRINTS))

    async def touch(self, person_id: int) -> None:
        await self.conn.execute('UPDATE people SET last_seen_at = now() WHERE id = %s', (person_id,))

    async def delete_person(self, person_id: int) -> None:
        await self.conn.execute('DELETE FROM people WHERE id = %s', (person_id,))
