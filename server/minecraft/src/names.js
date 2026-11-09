// 「花」「土」「石炭」のような呼び名から、集めるブロックを決める。docs/games/minecraft/minecraft-design-ja.md の 18 章。
// 心は「flower」のような、ブロックの ID ではない名前で頼むことがある（花を集めてと頼まれ、flower で頼んで断られた。2026-11-06）。
// ブロックの ID ならそのまま。持ち物の名前（dirt・cobblestone・coal など）なら、それが落ちるブロックも入れる。

const FLOWERS = ['dandelion', 'poppy', 'blue_orchid', 'allium', 'azure_bluet', 'red_tulip', 'orange_tulip', 'white_tulip',
  'pink_tulip', 'oxeye_daisy', 'cornflower', 'lily_of_the_valley', 'torchflower', 'sunflower', 'lilac', 'rose_bush', 'peony',
  'pink_petals', 'wildflowers', 'open_eyeblossom', 'closed_eyeblossom', 'cactus_flower'];
const ORES = ['coal', 'iron', 'copper', 'gold', 'redstone', 'lapis', 'diamond', 'emerald'];

// 呼び名 → ブロックの名前（関数なら、ブロックの名前を受けて当てはまるか）
const GROUPS = {
  flower: (n) => FLOWERS.includes(n),
  flowers: (n) => FLOWERS.includes(n),
  log: (n) => /_log$/.test(n) && !n.startsWith('stripped_'),
  logs: (n) => /_log$/.test(n) && !n.startsWith('stripped_'),
  wood: (n) => /_log$/.test(n) && !n.startsWith('stripped_'),
  leaves: (n) => /_leaves$/.test(n),
  ore: (n) => /_ore$/.test(n),
  ores: (n) => /_ore$/.test(n),
  // 持ち物の名前と、それが落ちるブロック
  dirt: ['dirt', 'grass_block', 'coarse_dirt', 'rooted_dirt'],
  cobblestone: ['cobblestone', 'stone'],
  cobbled_deepslate: ['cobbled_deepslate', 'deepslate'],
  stone: ['stone', 'cobblestone'],
  rock: ['stone', 'cobblestone'],
  sand: ['sand'],
  gravel: ['gravel'],
  flint: ['gravel'],
  clay_ball: ['clay'],
  wheat_seeds: ['short_grass', 'tall_grass'],
  seeds: ['short_grass', 'tall_grass'],
  grass: ['short_grass', 'tall_grass'],
};
for (const ore of ORES) {
  const blocks = ore === 'lapis' ? ['lapis_ore', 'deepslate_lapis_ore'] : [`${ore}_ore`, `deepslate_${ore}_ore`];
  GROUPS[ore] = blocks;
  GROUPS[`${ore}_ore`] = blocks;
  GROUPS[`deepslate_${ore}_ore`] = blocks;
  if (['iron', 'copper', 'gold'].includes(ore)) GROUPS[`raw_${ore}`] = blocks;
}
GROUPS.lapis_lazuli = GROUPS.lapis;

// 呼び名から、集めてよいブロック（registry のブロックの一覧）。無ければ空
export function blocksFor(registry, name) {
  const all = Object.values(registry.blocksByName);
  const group = GROUPS[name];
  if (typeof group === 'function') return all.filter((b) => group(b.name));
  if (group) return group.map((n) => registry.blocksByName[n]).filter(Boolean);
  // 「oak_logs」「poppies」のような複数形も受ける
  for (const n of [name, name.replace(/s$/, ''), name.replace(/ies$/, 'y')]) {
    if (registry.blocksByName[n]) return [registry.blocksByName[n]];
  }
  return [];
}

// 様子に入れる、草花の名前
export const FLOWER_NAMES = FLOWERS;
