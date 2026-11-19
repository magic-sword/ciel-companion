import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Vec3 } from 'vec3';

import { facing, footing, isNight, summarize } from '../src/state.js';

test('夜の範囲', () => {
  assert.equal(isNight(6000), false);
  assert.equal(isNight(13000), true);
  assert.equal(isNight(22999), true);
  assert.equal(isNight(23000), false);
});

test('入っていなければ connected=false だけ', () => {
  assert.deepEqual(summarize(null, null), { connected: false, doing: null });
});

test('様子をまとめる：近い順・遠いものは入れない・持ち物を足し合わせる', () => {
  const me = { position: new Vec3(0.04, 64, 0) };
  const bot = {
    entity: me,
    entities: {
      1: me,
      2: { type: 'player', username: 'magic', position: new Vec3(3, 64, 4) },
      3: { type: 'hostile', name: 'zombie', position: new Vec3(0, 64, 2) },
      4: { type: 'hostile', name: 'creeper', position: new Vec3(40, 64, 0) },
      5: { type: 'animal', name: 'cow', position: new Vec3(1, 64, 0) },
    },
    inventory: { items: () => [{ name: 'oak_log', count: 10 }, { name: 'dirt', count: 3 }, { name: 'oak_log', count: 5 }] },
    game: { dimension: 'overworld' },
    health: 18, food: 20, time: { timeOfDay: 14000 }, isRaining: false, heldItem: null,
    blockAt: () => ({ name: 'grass_block', boundingBox: 'block' }),
  };
  const s = summarize(bot, { id: 1, skill: 'follow', args: {} });
  assert.deepEqual(s.pos, { x: 0, y: 64, z: 0 });
  assert.deepEqual(s.players, [{ name: 'magic', distance: 5 }]);
  assert.deepEqual(s.hostiles, [{ name: 'zombie', distance: 2 }]);
  assert.deepEqual(s.inventory, { oak_log: 15, dirt: 3 });
  assert.equal(s.night, true);
  assert.equal(s.doing.skill, 'follow');
});

test('アカウントの確認なしのサーバーでの ID（自宅サーバーで入れた値）', async () => {
  const { offlineUuid } = await import('../src/whitelist.js');
  assert.equal(offlineUuid('Ciel'), 'f9bc7f17-3069-38fd-aa6d-e59c0a825a27');
});

test('足元のブロックの名前だけを返す（木の上かどうかは決めない）', () => {
  const bot = { entity: { position: new Vec3(0.5, 80, 0.5) }, blockAt: () => ({ name: 'oak_leaves', boundingBox: 'block' }) };
  assert.deepEqual(footing(bot), { on: 'oak_leaves' });
  assert.equal(footing({ entity: null }), null);
});

test('向いている方角（mineflayer の yaw は北が 0、西が π/2）', () => {
  const at = (yaw) => facing({ entity: { yaw } });
  assert.equal(at(0), 'north');
  assert.equal(at(Math.PI / 2), 'west');
  assert.equal(at(Math.PI), 'south');
  assert.equal(at(-Math.PI / 2), 'east');
  assert.equal(at(Math.PI / 4), 'northwest');
  assert.equal(facing(null), null);
});

test('今の拠点：距離と、無くなった道具の置き場（読み込まれていない所はあるものとする）', async () => {
  const { baseSummary } = await import('../src/state.js');
  const { baseLine, stateText } = await import('../src/ciel/words.js');
  const blocks = { '1,64,0': 'crafting_table', '2,64,0': 'air' };
  const bot = {
    entity: { position: new Vec3(3, 64, 4) },
    base: { home: [0, 64, 0], stations: { crafting_table: [1, 64, 0], chest: [2, 64, 0], furnace: [90, 64, 0] } },
    blockAt: (p) => (blocks[`${p.x},${p.y},${p.z}`] ? { name: blocks[`${p.x},${p.y},${p.z}`] } : null),
  };
  const b = baseSummary(bot);
  assert.deepEqual(b, { home: [0, 64, 0], distance: 5, stations: ['crafting_table', 'furnace'], gone: ['chest'] });
  assert.equal(baseLine(b), '拠点：0,64,0（ここから 5 ブロック。作業台・かまどがある。チェストは無くなっている）');
  assert.equal(baseLine(null), '拠点：まだ決めていない');
  assert.equal(baseSummary({ base: null }), null);
  const text = stateText({ connected: true, health: 20, food: 20, inventory: {}, base: b }, null, true);
  assert.match(text, /\n拠点：0,64,0/);
});
