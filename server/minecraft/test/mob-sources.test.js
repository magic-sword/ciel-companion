import assert from 'node:assert/strict';
import { test } from 'node:test';
import minecraftData from 'minecraft-data';
import { Vec3 } from 'vec3';
import { MOBS, WOOL_COLORS, mobWays } from '../src/vendor/mindcraft/src/agent/library/mobs.js';
import { suitable } from '../src/vendor/mindcraft/src/agent/library/hunt.js';
import { obtainItem } from '../src/vendor/mindcraft/src/agent/library/obtain.js';
import { getCraftingActions, useVersion } from '../src/vendor/mindcraft/src/utils/mcdata.js';

useVersion('1.21.11');

const data = minecraftData('1.21.11');
const items = names => names.flatMap(name => name === 'wool' ? WOOL_COLORS.map(c => `${c}_wool`) : [name]);

test('the mob table names real mobs and items and keeps every drop minecraft-data knows', () => {
  for (const [mob, entry] of Object.entries(MOBS)) {
    assert.ok(data.entitiesByName[mob], mob);
    assert.match(entry.wiki, /^https:\/\/minecraft\.wiki\/w\//);
    for (const [method, way] of Object.entries(entry.methods)) {
      for (const item of items(Object.keys(way.drops))) assert.ok(data.itemsByName[item], `${mob} ${method} ${item}`);
      for (const [min, max] of Object.values(way.drops)) assert.ok(0 <= min && min <= max);
      if (way.tool) assert.ok(getCraftingActions(way.tool, 1, {}, false)?.length > 0, `${way.tool} can be made`);
    }
    if (entry.breed) assert.ok(data.itemsByName[entry.breed], entry.breed);
    const known = Object.keys(entry.methods.kill.drops);
    for (const { item } of data.entityLoot[mob]?.drops ?? []) assert.ok(known.includes(item), `${mob} drops ${item}`);
  }
});

test('the plan stops at a choice where an item has several ways, and follows the way chosen', () => {
  const actions = getCraftingActions('white_bed', 1, { oak_planks: 3, crafting_table: 1 }, true);
  assert.deepEqual(actions[0], { type: 'choose', item: 'white_wool', count: 3, options: ['kill:sheep', 'shear:sheep', 'make'] });
  const killed = getCraftingActions('white_bed', 1, { oak_planks: 3, crafting_table: 1 }, true, { white_wool: 'kill:sheep' });
  assert.deepEqual(killed.map(a => a.type), ['mob', 'craft']);
  assert.equal(killed[0].count, 3);
  assert.equal(killed[0].color, 'white');
  const sheared = getCraftingActions('white_bed', 1, { oak_planks: 3, crafting_table: 1 }, true, { white_wool: 'shear:sheep' });
  assert.ok(sheared.some(a => a.type === 'smelt' && a.item === 'iron_ingot'), 'shears need iron');
  assert.deepEqual(sheared.find(a => a.type === 'mob'), { type: 'mob', item: 'white_wool', count: 3, mob: 'sheep', method: 'shear', tool: 'shears', color: 'white' });
  // One way from a peaceful mob is taken without asking; a hostile one is a choice.
  assert.equal(getCraftingActions('feather', 2, {}, false)[0].type, 'mob');
  assert.deepEqual(getCraftingActions('string', 1, {}, false)[0].options, ['kill:spider', 'make']);
  assert.deepEqual(mobWays('pink_wool').map(w => [w.id, w.color]), [['kill:sheep', 'pink'], ['shear:sheep', 'pink']]);
});

function sheep(wool = 0, { name, baby = false } = {}) {
  const keys = data.entitiesByName.sheep.metadataKeys;
  const metadata = [];
  metadata[keys.indexOf('wool')] = wool;
  metadata[keys.indexOf('baby')] = baby;
  if (name) metadata[keys.indexOf('custom_name')] = name;
  return { name: 'sheep', metadata, position: new Vec3(3, 64, 0), height: 1.3 };
}

test('only an adult, unnamed sheep of the colour asked for is used, and a sheared one only for killing', () => {
  const bot = { registry: data };
  const kill = { mob: 'sheep', method: 'kill', color: 'white' }, shear = { mob: 'sheep', method: 'shear', color: 'white' };
  assert.equal(suitable(bot, sheep(0), shear), true);
  assert.equal(suitable(bot, sheep(0x10), shear), false);
  assert.equal(suitable(bot, sheep(0x10), kill), true);
  assert.equal(suitable(bot, sheep(6), kill), false);
  assert.equal(suitable(bot, sheep(0, { name: 'Dolly' }), kill), false);
  assert.equal(suitable(bot, sheep(0, { baby: true }), kill), false);
});

test('obtaining an item with several ways lists them with costs and waits for a choice', async () => {
  const bot = { registry: data, output: '', interrupt_code: false,
    inventory: { slots: [{ name: 'oak_planks', count: 3 }, { name: 'crafting_table', count: 1 }] },
    entity: { position: new Vec3(0, 64, 0) },
    entities: { 1: sheep(0), 2: sheep(0x10), 3: sheep(15) },
    nearestEntity: predicate => Object.values(bot.entities).find(predicate) ?? null,
    findBlocks: () => [], blockAt: () => null };
  assert.equal(await obtainItem(bot, 'white_bed', 1), false);
  assert.deepEqual(Object.keys(bot.pendingChoice.options), ['kill:sheep', 'shear:sheep', 'make']);
  assert.match(bot.output, /kill:sheep: about 3 sheep needed, 2 suitable sheep seen nearby/);
  assert.match(bot.output, /shear:sheep: about 2 sheep needed, 1 suitable sheep seen nearby, a shears to make first, the sheep stay/);
  assert.match(bot.output, /make: craft or mine white_wool instead \(\d+ steps in all, then another choice\)/);
});
