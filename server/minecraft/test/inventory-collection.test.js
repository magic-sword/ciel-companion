import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { Vec3 } from 'vec3';
import { summarize } from '../src/state.js';
import { fingerprint, stateText } from '../src/ciel/words.js';

const require = createRequire(import.meta.url);
const registry = require('prismarine-registry')('1.21.11');
const World = require('prismarine-world')(registry);
const Chunk = require('prismarine-chunk')(registry);

function fixture() {
  const world = new World(() => new Chunk()).sync;
  world.setColumn(0, 0, new Chunk());
  const set = (p, name) => world.setBlockStateId(p, registry.blocksByName[name].defaultState);
  const targetPos = new Vec3(2, 64, 2), otherPos = new Vec3(3, 64, 2);
  for (const p of [targetPos, otherPos]) { set(p, 'crafting_table'); set(p.offset(0, -1, 0), 'stone'); }
  const bot = { registry, world, version: '1.21.11', entity: { position: new Vec3(.5, 64, .5), effects: {} },
    entities: {}, inventory: { items: () => [] }, blockAt: p => world.getBlock(p), health: 20, food: 20,
    game: { dimension: 'overworld' }, heldItem: null, waitForTicks: async () => {},
    findBlocks: () => [targetPos, otherPos] };
  bot.pathfinder = { setMovements(m) { this.movements = m; }, setGoal() {}, stop() {} };
  return { bot, set, target: bot.blockAt(targetPos), other: bot.blockAt(otherPos) };
}

test('single-count inventory items survive both state serialization and conversation text', () => {
  const { bot } = fixture();
  const many = Array.from({ length: 16 }, (_, n) => ({ name: `item_${n}`, count: n + 2 }));
  bot.inventory.items = () => [...many, { name: 'furnace', count: 1 }, { name: 'crafting_table', count: 1 }];
  const state = summarize(bot, null);
  assert.equal(Object.keys(state.inventory).length, 18);
  assert.equal(state.inventory.furnace, 1);
  const text = stateText(state, null, true);
  assert.ok(text.includes('furnace×1'));
  assert.ok(text.includes('crafting_table×1'));
  assert.notEqual(fingerprint(state), fingerprint({ ...state, inventory: { ...state.inventory, furnace: 2 } }));
});

