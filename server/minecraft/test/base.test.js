import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { Vec3 } from 'vec3';
import { setBase, baseStation, atHome, describeBase, BASE_RANGE } from '../src/vendor/mindcraft/src/agent/library/base.js';
import { stations } from '../src/vendor/mindcraft/src/agent/library/obtain.js';
import { getCraftingActions, useVersion } from '../src/vendor/mindcraft/src/utils/mcdata.js';

useVersion('1.21.11');
const require = createRequire(import.meta.url);
const registry = require('prismarine-registry')('1.21.11');
const World = require('prismarine-world')(registry);
const Chunk = require('prismarine-chunk')(registry);

function fixture(baseFile = null) {
  const world = new World(() => new Chunk()).sync;
  for (let cx = -4; cx <= 3; cx++) for (let cz = -1; cz <= 0; cz++) world.setColumn(cx, cz, new Chunk());
  const set = (x, y, z, name) => world.setBlockStateId(new Vec3(x, y, z), registry.blocksByName[name].defaultState);
  for (let x = -64; x < 64; x++) for (let z = -8; z < 8; z++) set(x, 63, z, 'grass_block');
  const bot = {
    registry, baseFile, entity: { position: new Vec3(0.5, 64, 0.5) },
    inventory: { slots: [], items: () => [] },
    blockAt: p => world.getBlock(p),
    findBlocks: ({ matching, maxDistance, count }) => {
      // As mineflayer: a predicate, or block ids.
      const ids = typeof matching === 'function' ? null : new Set([matching].flat());
      const match = b => b && (ids ? ids.has(b.type) : matching(b));
      const found = [];
      for (let x = -64; x < 64; x++) for (let z = -8; z < 8; z++) for (let y = 63; y < 66; y++) {
        const p = new Vec3(x, y, z);
        if (p.distanceTo(bot.entity.position) <= maxDistance && match(world.getBlock(p))) found.push(p);
      }
      return found.sort((a, b) => a.distanceTo(bot.entity.position) - b.distanceTo(bot.entity.position)).slice(0, count);
    },
  };
  return { bot, set };
}

test('a base keeps the stations at home, across restarts, and forgets one that is gone', () => {
  const file = join(mkdtempSync(join(tmpdir(), 'ciel-base-')), 'base.json');
  const { bot, set } = fixture(file);
  set(3, 64, 0, 'crafting_table');
  setBase(bot);
  assert.deepEqual(JSON.parse(readFileSync(file, 'utf8')).stations, { crafting_table: [3, 64, 0] });
  assert.match(describeBase(bot), /The base is at 0, 64, 0 with a crafting_table\./);
  // A furnace placed at home stays as the base's; one placed far away does not.
  assert.equal(atHome(bot, 'furnace', new Vec3(-2, 64, 1)), true);
  assert.equal(atHome(bot, 'chest', new Vec3(40, 64, 0)), false);
  const again = fixture(file);
  again.set(3, 64, 0, 'crafting_table');
  again.bot.entity.position = new Vec3(30.5, 64, 0.5);
  assert.deepEqual(baseStation(again.bot, 'crafting_table'), new Vec3(3, 64, 0));
  again.bot.entity.position = new Vec3(3 + BASE_RANGE + 2, 64, 0.5);
  assert.equal(baseStation(again.bot, 'crafting_table'), null, 'too far to walk back');
  assert.equal(baseStation(again.bot, 'furnace'), null, 'the furnace is gone from the world');
  assert.equal(JSON.parse(readFileSync(file, 'utf8')).stations.furnace, undefined);
});

test('a plan uses the base\'s table and furnace instead of making new ones', () => {
  const { bot, set } = fixture();
  set(3, 64, 0, 'crafting_table'); set(4, 64, 0, 'furnace');
  setBase(bot);
  bot.entity.position = new Vec3(-30.5, 64, 0.5);
  assert.deepEqual(stations(bot, {}), { crafting_table: true, furnace: true });
  const withBase = getCraftingActions('iron_ingot', 1, { raw_iron: 1, coal: 1 }, stations(bot, {}));
  assert.deepEqual(withBase.map(a => a.type), ['smelt']);
  const without = getCraftingActions('iron_ingot', 1, { raw_iron: 1, coal: 1 }, { crafting_table: false, furnace: false });
  assert.ok(without.some(a => a.type === 'craft' && a.item === 'furnace'));
});
