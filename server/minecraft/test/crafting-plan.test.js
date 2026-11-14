import test from 'node:test';
import assert from 'node:assert/strict';
import * as mc from '../src/vendor/mindcraft/src/utils/mcdata.js';

// mcdata.js loads recipe data at login; load the body's version directly.
mc.useVersion('1.21.11');

const steps = plan => plan.split('\n').filter(line => /^(Craft|Mine|Smelt) /.test(line));
const index = (lines, pattern) => lines.findIndex(line => pattern.test(line));

test('a stone pickaxe from nothing makes a table and a wooden pickaxe before mining cobblestone', () => {
  const plan = mc.getDetailedCraftingPlan('stone_pickaxe', 1, {});
  const lines = steps(plan);
  assert.match(plan, /- 3 oak_log/);
  assert.ok(index(lines, /-> 1 crafting_table$/) < index(lines, /-> 1 wooden_pickaxe$/));
  assert.ok(index(lines, /-> 1 wooden_pickaxe$/) < index(lines, /^Mine 3 cobblestone .*wooden_pickaxe/));
  assert.ok(index(lines, /^Mine 3 cobblestone/) < index(lines, /-> 1 stone_pickaxe$/));
});

test('owned tools and stations are not planned again', () => {
  const lines = steps(mc.getDetailedCraftingPlan('stone_pickaxe', 1, { wooden_pickaxe: 1, crafting_table: 1 }));
  assert.equal(index(lines, /wooden_pickaxe$|crafting_table$/), -1);
  assert.notEqual(index(lines, /^Mine 3 cobblestone/), -1);
});

test('smelted items plan the raw item, a furnace and fuel, with tools by tier', () => {
  const lines = steps(mc.getDetailedCraftingPlan('iron_pickaxe', 1, {}));
  assert.ok(index(lines, /-> 1 stone_pickaxe$/) < index(lines, /^Mine 3 raw_iron from iron_ore with a stone_pickaxe/));
  assert.ok(index(lines, /-> 1 furnace$/) < index(lines, /^Smelt 3 raw_iron/));
  assert.ok(index(lines, /^Smelt 3 raw_iron/) < index(lines, /-> 1 iron_pickaxe$/));
  assert.equal(index(lines, /copper/), -1);
  assert.equal(mc.getBlockTool('iron_ore'), 'stone_pickaxe');
  assert.equal(mc.getBlockTool('oak_log'), null);
});

test('hand-gathered and simple crafted items keep the short plan', () => {
  assert.match(mc.getDetailedCraftingPlan('oak_log', 2, {}), /base item, you need to find 2 more/);
  assert.deepEqual(steps(mc.getDetailedCraftingPlan('stick', 4, {})), ['Craft 1 oak_log -> 4 oak_planks', 'Craft 2 oak_planks -> 4 stick']);
});
