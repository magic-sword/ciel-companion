import assert from 'node:assert/strict';
import { test } from 'node:test';

import mcData from 'minecraft-data';
import recipeMod from 'prismarine-recipe';

import { planCraft } from '../src/craft-plan.js';

const registry = mcData('1.21.11');
const { Recipe } = recipeMod('1.21.11');
const recipes = (id) => Recipe.find(id, null);

// 石のつるはしを 1 本持っていて「もう一本」を頼まれ、作る段だけの計画になり、丸石が足りずに止まった（2026-11-07）

test('途中の物（棒・板）は、持っている分を使う', () => {
  const p = planCraft(registry, recipes, 'wooden_pickaxe', 1, { stick: 2, oak_planks: 3 }, true);
  assert.deepEqual(p.missing, {});
  assert.deepEqual(p.steps.map((s) => s.name), ['wooden_pickaxe']);
});
