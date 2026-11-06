import assert from 'node:assert/strict';
import { test } from 'node:test';

import { Facts, near, normalize } from '../src/knowledge/facts.js';

const facts = new Facts('1.21.11');

test('ブロック：要る道具と落ちる物', () => {
  const stone = facts.lookup('block', 'stone');
  assert.equal(stone.tool_needed, 'wooden_pickaxe');
  assert.ok(stone.drops.some((d) => d.item === 'cobblestone' && d.without_silk_touch && d.chance === 1));
  assert.equal(facts.lookup('block', 'iron_ore').tool_needed, 'stone_pickaxe');
  assert.equal(facts.lookup('block', 'dirt').tool_needed, null);   // 素手で取れる
});

test('作り方：ふつうの材料を先に、何も無いところから集める物', () => {
  const sp = facts.lookup('item', 'stone_pickaxe');
  assert.deepEqual(sp.ways[0].ingredients, { cobblestone: 3, stick: 2 });
  assert.equal(sp.ways[0].needs_crafting_table, true);
  assert.deepEqual(sp.from_scratch.gather, { cobblestone: 3, oak_log: 2 });
  assert.deepEqual(facts.lookup('recipe', 'wooden_pickaxe').from_scratch.gather, { oak_log: 3 });
  assert.equal(facts.lookup('item', 'diamond').craftable, true);   // ダイヤのブロックから戻せる
  assert.equal(facts.lookup('item', 'oak_log').craftable, false);
  assert.equal(facts.lookup('item', 'bread').food.foodPoints, 5);
});

test('生き物・バイオーム・効果', () => {
  const z = facts.lookup('mob', 'zombie');
  assert.equal(z.type, 'hostile');
  assert.ok(z.drops.some((d) => d.item === 'rotten_flesh'));
  assert.equal(facts.lookup('biome', 'plains').precipitation, true);
  assert.equal(facts.lookup('effect', 'Speed').name, 'speed');
});

test('名前の揺れと、見つからないとき', () => {
  assert.equal(normalize('minecraft:Cobble Stone'), 'cobble_stone');
  assert.equal(facts.lookup('block', 'Cobblestone').name, 'cobblestone');
  const miss = facts.lookup('item', 'cobble');
  assert.equal(miss.found, false);
  assert.equal(miss.near[0], 'cobblestone');
  assert.equal(facts.lookup('weapon', 'sword').error, 'unknown_kind');
  assert.deepEqual(near(['apple', 'stone', 'stick'], 'stoen').slice(0, 1), ['stone']);
});
