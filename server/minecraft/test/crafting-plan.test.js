import test from 'node:test';
import assert from 'node:assert/strict';
import { copyFileSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';

// mcdata.js loads recipe data only after a bot logs in. Import a copy of the vendored file
// with the 1.21.11 data preloaded, inside this package so its dependencies resolve.
const dir = new URL(`./.tmp-crafting-plan-${randomUUID()}/`, import.meta.url);
mkdirSync(new URL('src/utils/', dir), { recursive: true });
mkdirSync(new URL('src/agent/', dir), { recursive: true });
const source = new URL('../src/vendor/mindcraft/src/utils/mcdata.js', import.meta.url);
copyFileSync(source, new URL('src/utils/mcdata.js', dir));
const copy = new URL('src/utils/mcdata.js', dir);
writeFileSync(copy, readFileSync(copy, 'utf8').replace(/^let mcdata = null;$/m, "let mcdata = minecraftData('1.21.11');"));
writeFileSync(new URL('src/agent/settings.js', dir), "export default { minecraft_version: '1.21.11' };\n");
const mc = await import(copy);
test.after(() => rmSync(dir, { recursive: true, force: true }));

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
