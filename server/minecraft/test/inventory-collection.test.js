import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { Vec3 } from 'vec3';
import { summarize } from '../src/state.js';
import { fingerprint, stateText } from '../src/ciel/words.js';
import { collectMovements, miningMovements, playerMovements } from '../src/movements.js';
import { Runner } from '../src/skills.js';

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

test('mining keeps block placement available and prefers non-harvest scaffold',()=>{
  const {bot}=fixture();
  const m=miningMovements(bot,null,new Set(),new Set(['cobblestone']));
  assert.equal(m.allow1by1towers,true);
  assert.ok(m.scafoldingBlocks.includes(registry.itemsByName.cobblestone.id));
  assert.ok(m.scafoldingBlocks.indexOf(registry.itemsByName.coarse_dirt.id)<m.scafoldingBlocks.indexOf(registry.itemsByName.cobblestone.id));
  assert.equal(m.canDig,true);
  const stone={name:'cobblestone',type:registry.itemsByName.cobblestone.id,count:30};
  const dirt={name:'coarse_dirt',type:registry.itemsByName.coarse_dirt.id,count:4};
  bot.inventory.items=()=>[stone,dirt];
  assert.equal(m.getScaffoldingItem(),dirt);
  bot.inventory.items=()=>[stone];
  assert.equal(m.getScaffoldingItem(),stone,'the harvest remains usable when needed');
});

test('explicit collection allows one crafting table while protecting all other tables', () => {
  const { bot, target, other } = fixture();
  assert.equal(playerMovements(bot).safeToBreak(target), false);
  const allowed = collectMovements(bot, target);
  assert.equal(allowed.safeToBreak(target), true);
  assert.equal(allowed.safeToBreak(other), false);
  assert.ok(allowed.blocksCantBreak.has(registry.blocksByName.oak_planks.id));
  assert.equal(playerMovements(bot).safeToBreak(target), false);
});

test('collect command recovers a requested table and restores normal movement protection', async () => {
  const { bot, set, target, other } = fixture();
  let count = 0;
  bot.inventory.items = () => count ? [{ name: 'crafting_table', count, type: registry.itemsByName.crafting_table.id }] : [];
  bot.collectBlock = { async collect(block) {
    // collectblock uses the active pathfinder's real safeToBreak check before digging.
    bot.pathfinder.setMovements(this.movements);
    assert.equal(bot.pathfinder.movements.safeToBreak(other), false);
    if (!bot.pathfinder.movements.safeToBreak(block)) return;
    set(block.position, 'air'); count++;
  } };
  const events = [];
  const runner = new Runner((type, fields) => events.push({ type, ...fields }));
  runner.bot = bot;
  await runner.start({ id: 1, skill: 'collect', args: { block: 'crafting_table', count: 1 } });
  const done = events.find(e => e.type === 'done');
  assert.equal(done.ok, true, JSON.stringify(done));
  assert.deepEqual(done.note.gained, { crafting_table: 1 });
  assert.equal(bot.blockAt(target.position).name, 'air');
  assert.equal(bot.blockAt(other.position).name, 'crafting_table');
  assert.ok(bot.pathfinder.movements.blocksCantBreak.has(target.type));
});

test('explicit collection does not make an unbreakable target diggable', () => {
  const { bot, set, target } = fixture();
  set(target.position, 'bedrock');
  const bedrock = bot.blockAt(target.position);
  assert.equal(collectMovements(bot, bedrock).safeToBreak(bedrock), false);
});
