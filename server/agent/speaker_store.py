# -*- coding: utf-8 -*-
"""覚えている人の記録（PostgreSQL＋pgvector）。本人が同意した人の名前・声の特徴・メモだけを置く。

- people：人（名前、声を覚える同意の日時、メモを残す同意の日時、最後に話した日時）
- voiceprints：声の特徴（192 次元、人ごとに複数、多すぎたら古いものから消す）
- person_notes：その人について覚えておくメモ（短い文、人ごとに上限あり。notes.py が書く）
- person_relationship：シエルがその人をどう思っているか（親しさの段階・気持ち・一時的な気分。relationship.py が書く）
録音そのものは置かない。表は会話サーバーが起動のたびに作る（あれば何もしない）。
人を消すと、声の特徴もメモも関係も一緒に消える。管理（一覧・削除）は speaker_admin.py。
"""
import logging
import os
from dataclasses import dataclass
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
ALTER TABLE people ADD COLUMN IF NOT EXISTS notes_consented_at timestamptz;
CREATE TABLE IF NOT EXISTS person_notes (
    id bigserial PRIMARY KEY,
    person_id bigint NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    text text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS person_notes_person ON person_notes(person_id);
CREATE TABLE IF NOT EXISTS person_relationship (
    person_id bigint PRIMARY KEY REFERENCES people(id) ON DELETE CASCADE,
    stage smallint NOT NULL DEFAULT 0,
    feeling text NOT NULL DEFAULT '',
    mood text NOT NULL DEFAULT '',
    sessions integer NOT NULL DEFAULT 0,
    stage_sessions integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""
MAX_NOTES = 50   # 1 人あたりのメモの上限（多すぎたら古いものから消す）


@dataclass
class Relationship:
    """シエルがその人をどう思っているか（1 人 1 行）"""
    stage: int = 0            # 親しさの段階（relationship.STAGES。下げない）
    feeling: str = ''         # シエルの気持ち（一人称の短い文）
    mood: str = ''            # 前の会話から続く一時的な気分（拗ね・寂しさなど。次の会話で書き直す）
    sessions: int = 0         # ちゃんと話した会話の数
    stage_sessions: int = 0   # いまの段階になってから、ちゃんと話した会話の数


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

    async def load_all(self) -> list[tuple[int, str, list[np.ndarray], datetime | None, bool, int]]:
        """（番号、名前、声の特徴の一覧、最後に話した日時、メモを残す同意の有無、メモの数）"""
        rows = await (await self.conn.execute(
            'SELECT p.id, p.name, p.last_seen_at, p.notes_consented_at IS NOT NULL, '
            '(SELECT count(*) FROM person_notes n WHERE n.person_id = p.id), v.embedding '
            'FROM people p JOIN voiceprints v ON v.person_id = p.id ORDER BY p.id, v.id'
        )).fetchall()
        people: dict[int, tuple] = {}
        for pid, name, seen, notes_ok, n_notes, emb in rows:
            people.setdefault(pid, (name, seen, notes_ok, n_notes, []))[4].append(np.asarray(emb, dtype=np.float32))
        return [(pid, name, embs, seen, notes_ok, n) for pid, (name, seen, notes_ok, n, embs) in people.items()]

    async def set_notes_consent(self, person_id: int) -> None:
        await self.conn.execute('UPDATE people SET notes_consented_at = now() WHERE id = %s', (person_id,))

    async def notes(self, person_id: int) -> list[tuple[int, str]]:
        return await (await self.conn.execute(
            'SELECT id, text FROM person_notes WHERE person_id = %s ORDER BY updated_at, id', (person_id,))).fetchall()

    async def change_notes(self, person_id: int, add: list[str], update: dict[int, str], delete: list[int]) -> None:
        """メモを足す・書き直す・消す（その人のメモだけ）。上限を超えたら古いものから消す"""
        async with self.conn.cursor() as cur:
            for i in delete:
                await cur.execute('DELETE FROM person_notes WHERE id = %s AND person_id = %s', (i, person_id))
            for i, text in update.items():
                await cur.execute('UPDATE person_notes SET text = %s, updated_at = now() WHERE id = %s AND person_id = %s',
                                  (text, i, person_id))
            for text in add:
                await cur.execute('INSERT INTO person_notes (person_id, text) VALUES (%s, %s)', (person_id, text))
            await cur.execute(
                'DELETE FROM person_notes WHERE person_id = %s AND id NOT IN '
                '(SELECT id FROM person_notes WHERE person_id = %s ORDER BY updated_at DESC, id DESC LIMIT %s)',
                (person_id, person_id, MAX_NOTES))

    async def count_notes(self, person_id: int) -> int:
        return (await (await self.conn.execute(
            'SELECT count(*) FROM person_notes WHERE person_id = %s', (person_id,))).fetchone())[0]

    async def relationship(self, person_id: int) -> 'Relationship | None':
        row = await (await self.conn.execute(
            'SELECT stage, feeling, mood, sessions, stage_sessions FROM person_relationship WHERE person_id = %s',
            (person_id,))).fetchone()
        return Relationship(*row) if row else None

    async def save_relationship(self, person_id: int, r: 'Relationship') -> None:
        await self.conn.execute(
            'INSERT INTO person_relationship (person_id, stage, feeling, mood, sessions, stage_sessions) '
            'VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (person_id) DO UPDATE SET stage = EXCLUDED.stage, '
            'feeling = EXCLUDED.feeling, mood = EXCLUDED.mood, sessions = EXCLUDED.sessions, '
            'stage_sessions = EXCLUDED.stage_sessions, updated_at = now()',
            (person_id, r.stage, r.feeling, r.mood, r.sessions, r.stage_sessions))

    async def add_person(self, name: str) -> int:
        row = await (await self.conn.execute('INSERT INTO people (name) VALUES (%s) RETURNING id', (name,))).fetchone()
        return row[0]

    async def rename(self, person_id: int, name: str) -> None:
        await self.conn.execute('UPDATE people SET name = %s WHERE id = %s', (name, person_id))

    async def add_voiceprints(self, person_id: int, embeddings: list[np.ndarray], seconds: float | None) -> list[int]:
        """見本を足し、足した行の番号を返す（人違いだと分かったときに消せるように）"""
        ids = []
        async with self.conn.cursor() as cur:
            for e in embeddings:
                await cur.execute('INSERT INTO voiceprints (person_id, embedding, seconds) VALUES (%s, %s, %s) RETURNING id',
                                  (person_id, e, seconds))
                ids.append((await cur.fetchone())[0])
            await cur.execute(
                'DELETE FROM voiceprints WHERE person_id = %s AND id NOT IN '
                '(SELECT id FROM voiceprints WHERE person_id = %s ORDER BY id DESC LIMIT %s)',
                (person_id, person_id, MAX_VOICEPRINTS))
        return ids

    async def delete_voiceprints(self, ids: list[int]) -> None:
        await self.conn.execute('DELETE FROM voiceprints WHERE id = ANY(%s)', (ids,))

    async def touch(self, person_id: int) -> None:
        await self.conn.execute('UPDATE people SET last_seen_at = now() WHERE id = %s', (person_id,))

    async def delete_person(self, person_id: int) -> None:
        await self.conn.execute('DELETE FROM people WHERE id = %s', (person_id,))
