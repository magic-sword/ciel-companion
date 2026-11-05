import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Vec3 } from 'vec3';

import { guarded, pickThreat } from '../src/guard.js';

function world(health, others, owner = null) {
  const me = { position: new Vec3(0, 64, 0) };
  const entities = { 0: me };
  others.forEach((e, i) => { entities[i + 1] = e; });
  const players = owner ? { Hakase: { entity: owner } } : {};
  return { entity: me, entities, players, health };
}
const mob = (name, x, z = 0) => ({ type: 'hostile', name, position: new Vec3(x, 64, z) });

test('敵がいなければ何もしない', () => {
  assert.equal(pickThreat(world(20, [{ type: 'animal', name: 'cow', position: new Vec3(1, 64, 0) }]), null), null);
  assert.equal(pickThreat(world(20, [mob('zombie', 10)]), null), null);   // 遠い
});

test('近い敵に反撃する', () => {
  const z = mob('zombie', 4);
  assert.deepEqual(pickThreat(world(20, [mob('spider', 5), z]), null), { action: 'fight', target: z });
});

test('クリーパーは叩かずに離れる', () => {
  const c = mob('creeper', 3);
  assert.deepEqual(pickThreat(world(20, [c, mob('zombie', 2)]), null), { action: 'flee', target: c });
});

test('体力が少なければ、持ち主のほうへ逃げる', () => {
  const owner = { type: 'player', username: 'Hakase', position: new Vec3(-10, 64, 0) };
  const z = mob('zombie', 3);
  assert.deepEqual(pickThreat(world(5, [z, owner], owner), 'Hakase'), { action: 'flee', target: z, to: owner });
});

test('囲まれたら逃げる', () => {
  const z = mob('zombie', 2);
  assert.deepEqual(pickThreat(world(20, [z, mob('zombie', 3), mob('skeleton', 5)]), null), { action: 'flee', target: z, to: null });
});

test('手を出さなければ襲わないものには向かわない', () => {
  assert.equal(pickThreat(world(20, [mob('enderman', 2), mob('zombified_piglin', 2)]), null), null);
});

test('持ち主に近づいた敵にも向かう', () => {
  const owner = { type: 'player', username: 'Hakase', position: new Vec3(12, 64, 0) };
  const s = mob('skeleton', 15);
  assert.deepEqual(pickThreat(world(20, [owner, s], owner), 'Hakase'), { action: 'fight', target: s });
});

test('守りに割り込まれた動きは、守り終えてからやり直す', async () => {
  const guard = { active: false, generation: 0, idle: async () => { guard.active = false; } };
  let calls = 0;
  const result = await guarded(guard, { cancelled: false }, async () => {
    calls += 1;
    if (calls === 1) {
      guard.active = true;
      guard.generation += 1;
      throw new Error('GoalChanged');
    }
    return 'arrived';
  });
  assert.equal(result, 'arrived');
  assert.equal(calls, 2);
});

test('守りと関係ない失敗はそのまま投げる', async () => {
  const guard = { active: false, generation: 0, idle: async () => {} };
  await assert.rejects(guarded(guard, { cancelled: false }, async () => { throw new Error('NoPath'); }), /NoPath/);
});
