// マイクラの知識の窓口の facts：minecraft-data（体と同じ版）から、正確な値を引く。docs/game-knowledge-design-ja.md の 3.2。
// 体の動き（src/craft-plan.js・src/skills.js）と同じ部品を使い、答えと体の動きが食い違わないようにする。
import { createRequire } from 'node:module';

import { planCraft } from '../craft-plan.js';

const require = createRequire(import.meta.url);
const TOOL_TIERS = ['wooden', 'golden', 'stone', 'copper', 'iron', 'diamond', 'netherite'];
const RECIPES_SHOWN = 3;
const NEAR_SHOWN = 5;

export const KINDS = ['block', 'item', 'recipe', 'mob', 'biome', 'effect', 'enchantment'];

export class Facts {
  constructor(version = '1.21.11') {
    this.version = version;
    this.registry = require('prismarine-registry')(version);
    this.Recipe = require('prismarine-recipe')(this.registry).Recipe;
  }

  // kind と name から答える。見つからなければ { found: false, near: [似た名前] }
  lookup(kind, name) {
    const r = this.registry;
    const key = normalize(name);
    const table = {
      block: r.blocksByName, item: r.itemsByName, recipe: r.itemsByName, mob: r.entitiesByName,
      biome: r.biomesByName, effect: byLower(r.effectsByName), enchantment: r.enchantmentsByName,
    }[kind];
    if (!table) return { found: false, error: 'unknown_kind', kinds: KINDS };
    const hit = table[key] ?? Object.values(table).find((x) => normalize(x.displayName ?? '') === key);
    if (!hit) return { found: false, kind, name, near: near(Object.keys(table), key) };
    return { found: true, kind, version: this.version, ...this[kind](hit) };
  }

  block(b) {
    const r = this.registry;
    const tools = Object.keys(b.harvestTools ?? {}).map((id) => r.items[Number(id)]?.name).filter(Boolean);
    return {
      name: b.name, displayName: b.displayName, hardness: b.hardness,
      tool_needed: tools.length ? weakest(tools) : null,   // null なら素手でも落ちる物が取れる
      drops: (r.blockLoot[b.name]?.drops ?? []).map(drop),
      ...(b.diggable === false ? { diggable: false } : {}),
    };
  }

  item(i) {
    const food = this.registry.foodsByName[i.name];
    return {
      name: i.name, displayName: i.displayName, stackSize: i.stackSize,
      ...(food ? { food: { foodPoints: food.foodPoints, saturation: food.saturation } } : {}),
      ...this.recipe(i),
    };
  }

  // 作り方（何通りかと、ふつうの作り方）と、何も持っていないところから作るときに集める物
  recipe(i) {
    const r = this.registry;
    const list = this.Recipe.find(i.id, null);
    if (!list.length) return { craftable: false };
    // ふつうの材料（オーク・丸石）の作り方を先に見せる。深層岩・ブラックストーンは後（体の craft-plan と同じ選び方）
    const names = (x) => (x.delta ?? []).filter((d) => d.count < 0).map((d) => r.items[d.id]?.name ?? '');
    const rank = (x) => (names(x).some((n) => /deepslate|blackstone/.test(n)) ? 2 : names(x).some((n) => /^oak_|^cobblestone$/.test(n)) ? 0 : 1);
    const ways = [...list].sort((a, b) => rank(a) - rank(b)).slice(0, RECIPES_SHOWN).map((x) => ({
      makes: x.result?.count ?? 1,
      needs_crafting_table: Boolean(x.requiresTable),
      ingredients: Object.fromEntries((x.delta ?? []).filter((d) => d.count < 0).map((d) => [r.items[d.id]?.name, -d.count])),
    }));
    const plan = planCraft(r, (id) => this.Recipe.find(id, null), i.name, 1, {}, false);
    return {
      craftable: true, ways, ways_total: list.length,
      from_scratch: { gather: plan.missing, steps: plan.steps.map((s) => s.name) },   // 原木・丸石など、集める物
    };
  }

  mob(e) {
    return {
      name: e.name, displayName: e.displayName, type: e.type, category: e.category, width: e.width, height: e.height,
      drops: (this.registry.entityLoot[e.name]?.drops ?? []).map(drop),
    };
  }

  biome(b) {
    return { name: b.name, displayName: b.displayName, category: b.category, temperature: b.temperature,
      precipitation: b.has_precipitation, dimension: b.dimension };
  }

  effect(e) {
    return { name: normalize(e.name), displayName: e.displayName, type: e.type };
  }

  enchantment(e) {
    return { name: e.name, displayName: e.displayName, maxLevel: e.maxLevel, category: e.category, curse: e.curse,
      treasureOnly: e.treasureOnly, exclude: e.exclude };
  }
}

// 「Cobblestone」「cobble stone」「minecraft:cobblestone」→ cobblestone
export function normalize(name) {
  return String(name ?? '').trim().toLowerCase().replace(/^minecraft:/, '').replace(/[\s-]+/g, '_');
}

function byLower(table) {
  return Object.fromEntries(Object.entries(table).map(([k, v]) => [normalize(k), v]));
}

function weakest(tools) {
  const tier = (n) => TOOL_TIERS.findIndex((t) => n.startsWith(t + '_'));
  return [...tools].sort((a, b) => tier(a) - tier(b))[0];
}

function drop(d) {
  return {
    // minecraft-data は、シルクタッチのあり・なしで分かれる落ち方を 0.5 ずつで書いている。どちらも、その条件ならいつも落ちる
    item: d.item, chance: d.silkTouch || d.noSilkTouch ? 1 : Math.round(d.dropChance * 1000) / 1000, count: d.stackSizeRange,
    ...(d.silkTouch ? { silk_touch_only: true } : {}), ...(d.noSilkTouch ? { without_silk_touch: true } : {}),
    ...(d.playerKill ? { player_kill_only: true } : {}),
  };
}

// 似た名前（含む・含まれる・文字の違いが少ない順）
export function near(names, key) {
  const dist = (a, b) => {
    const m = Array.from({ length: b.length + 1 }, (_, i) => i);
    for (let i = 1; i <= a.length; i++) {
      let prev = m[0];
      m[0] = i;
      for (let j = 1; j <= b.length; j++) {
        const t = m[j];
        m[j] = Math.min(m[j] + 1, m[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
        prev = t;
      }
    }
    return m[b.length];
  };
  return names
    .map((n) => ({ n, s: n.includes(key) || key.includes(n) ? Math.abs(n.length - key.length) / 10 : dist(n, key) }))
    .sort((a, b) => a.s - b.s)
    .slice(0, NEAR_SHOWN)
    .map((x) => x.n);
}
