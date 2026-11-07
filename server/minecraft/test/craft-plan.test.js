import assert from 'node:assert/strict';
import { test } from 'node:test';

import mcData from 'minecraft-data';
import recipeMod from 'prismarine-recipe';

import { planCraft } from '../src/craft-plan.js';
import { planGoal } from '../src/goal-plan.js';

const registry = mcData('1.21.11');
const { Recipe } = recipeMod('1.21.11');
const recipes = (id) => Recipe.find(id, null);

// 石のつるはしを 1 本持っていて「もう一本」を頼まれ、作る段だけの計画になり、丸石が足りずに止まった（2026-11-07）
test('作りたい物を持っていても、もう 1 つ作る計画にする', () => {
  const inv = { stone_pickaxe: 1, cobblestone: 1, stick: 2, wooden_pickaxe: 1, oak_log: 5 };
  const p = planCraft(registry, recipes, 'stone_pickaxe', 1, inv, true);
  assert.deepEqual(p.missing, { cobblestone: 2 });
  const g = planGoal(registry, recipes, 'stone_pickaxe', 1, inv, true);
  assert.deepEqual(g.steps.map((s) => [s.kind, s.item, s.count]), [['gather', 'cobblestone', 2], ['craft', 'stone_pickaxe', 1]]);
});

test('途中の物（棒・板）は、持っている分を使う', () => {
  const p = planCraft(registry, recipes, 'wooden_pickaxe', 1, { stick: 2, oak_planks: 3 }, true);
  assert.deepEqual(p.missing, {});
  assert.deepEqual(p.steps.map((s) => s.name), ['wooden_pickaxe']);
});
