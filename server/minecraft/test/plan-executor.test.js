import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { Vec3 } from 'vec3';
import { runPlan } from '../src/vendor/mindcraft/src/agent/library/plan.js';
import { remaining, materials } from '../src/vendor/mindcraft/src/agent/library/region.js';
import { findSites } from '../src/vendor/mindcraft/src/agent/library/sites.js';
import { farmBlueprint, farmSteps } from '../src/vendor/mindcraft/src/agent/library/farm.js';

const require = createRequire(import.meta.url);
const registry = require('prismarine-registry')('1.21.11');
const World = require('prismarine-world')(registry);
const Chunk = require('prismarine-chunk')(registry);

// Flat grass at y = 63 over x, z in -16..15, with the bot standing at the origin.
function fixture(inventory = {}) {
  const world = new World(() => new Chunk()).sync;
  for (let cx = -1; cx <= 0; cx++) for (let cz = -1; cz <= 0; cz++) world.setColumn(cx, cz, new Chunk());
  const set = (x, y, z, name) => world.setBlockStateId(new Vec3(x, y, z), registry.blocksByName[name].defaultState);
  for (let x = -16; x < 16; x++) for (let z = -16; z < 16; z++) {
    for (let y = 60; y < 63; y++) set(x, y, z, 'dirt');
    set(x, 63, z, 'grass_block');
  }
  const items = { ...inventory };
  const bot = {
    registry, output: '', interrupt_code: false,
    entity: { position: new Vec3(0.5, 64, 0.5) },
    inventory: { get slots() { return Object.entries(items).filter(([, n]) => n > 0).map(([name, count]) => ({ name, count })); } },
    blockAt: p => world.getBlock(p),
    findBlocks: () => [],
    pathfinder: { stop() {} }, stopDigging() {}, emit() {},
  };
  return { bot, set, items };
}

const step = (id, needs, state, extra = {}) => ({
  id, needs, label: id, done: () => state[id], run: async () => { state.log.push(id); state[id] = true; },
  seconds: () => 1, ...extra,
});

test('a plan runs each step after the steps it needs and skips what already holds', async () => {
  const { bot } = fixture();
  const state = { log: [], b: true };
  const ok = await runPlan(bot, [step('c', ['a', 'b'], state), step('a', [], state), step('b', [], state)]);
  assert.equal(ok, true);
  assert.deepEqual(state.log, ['a', 'c']);
});

test('a step that does not reach its state stops the plan after two tries and names what is left', async () => {
  const { bot } = fixture();
  const state = { log: [] };
  const stuck = step('a', [], state, { run: async () => { state.log.push('a'); } });
  const ok = await runPlan(bot, [stuck, step('b', ['a'], state)]);
  assert.equal(ok, false);
  assert.deepEqual(state.log, ['a', 'a']);
  assert.match(bot.output, /Could not a after 2 tries\. Not done yet: b\./);
});

test('a step that runs past its own time is stopped there, not at the end of the plan', async () => {
  const { bot } = fixture();
  const state = { log: [] };
  const slow = step('a', [], state, { run: async () => { while (!bot.interrupt_code) await new Promise(r => setTimeout(r, 20)); }, seconds: () => 0.05 });
  const began = Date.now();
  assert.equal(await runPlan(bot, [slow], { tries: 1 }), false);
  assert.ok(Date.now() - began < 4000);
  assert.match(bot.output, /Timed out on "a"/);
});

test('the farm plan reads the work left from the world and sums the steps\' own times', async () => {
  const { bot, set, items } = fixture({ wheat_seeds: 3 });
  const blueprint = farmBlueprint(new Vec3(2, 63, 2), 3);
  assert.equal(remaining(blueprint, bot).length, 17);
  assert.deepEqual(materials(blueprint, bot), { water_bucket: 1, wheat_seeds: 8 });
  // A hole in the ground needs dirt; a planted cell no longer needs its seed.
  set(2, 63, 2, 'air');
  set(3, 63, 2, 'farmland');
  set(3, 64, 2, 'wheat');
  assert.deepEqual(materials(blueprint, bot), { dirt: 1, water_bucket: 1, wheat_seeds: 7 });
  const steps = Object.fromEntries(farmSteps(blueprint).map(s => [s.id, s]));
  assert.equal(steps.seeds.done(bot), false);
  items.wheat_seeds = 7;
  assert.equal(steps.seeds.done(bot), true);
  assert.equal(steps.water.done(bot), false);
  assert.deepEqual(steps.farm.needs, ['hoe', 'seeds', 'bucket', 'water', 'dirt']);
  assert.equal(steps.farm.seconds(bot), 20 + 6 * remaining(blueprint, bot).length);
  assert.equal(remaining(blueprint, bot).length, 15);
});

test('places for a farm avoid water and trees and prefer level ground near the bot', () => {
  const { bot, set } = fixture();
  for (let x = -3; x <= 3; x++) for (let z = -3; z <= 3; z++) set(x, 63, z, 'water');
  set(6, 64, 0, 'oak_log');
  const sites = findSites(bot, 3, 3, { radius: 12 });
  assert.equal(sites.length, 3);
  for (const site of sites) {
    const { x, z } = site.corner;
    assert.ok(x > 3 || x + 2 < -3 || z > 3 || z + 2 < -3, `site ${x},${z} overlaps the water`);
    assert.ok(!(x <= 6 && 6 <= x + 2 && z <= 0 && 0 <= z + 2), 'site under the tree');
    assert.equal(site.changes, 0);
  }
  assert.ok(sites[0].distance <= sites[2].distance);
});

test('a place counts the blocks to level and is left out when the ground rises more than a block', () => {
  const { bot, set } = fixture();
  set(1, 64, 1, 'grass_block');
  const [site] = findSites(bot, 3, 3, { radius: 1 });
  assert.deepEqual([site.corner.x, site.corner.y, site.corner.z, site.changes], [-1, 63, -1, 1]);
  set(1, 65, 1, 'grass_block');
  assert.deepEqual(findSites(bot, 3, 3, { radius: 1 }), []);
});
