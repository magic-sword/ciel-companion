// 経路探索の歩き方の決まり（技 skills.js と、身を守る係 guard.js が使う）
import pathfinderPkg from 'mineflayer-pathfinder';

const { Movements } = pathfinderPkg;

// 歩くときの決まり：ブロックを壊さない・置かない（持ち主の建物を崩したり、土を積んだりしない）
export function carefulMovements(bot) {
  const m = new Movements(bot);
  m.canDig = false;
  m.allow1by1towers = false;
  m.scafoldingBlocks = [];
  return m;
}

// 集めるときの決まり：掘ってよい（mineflayer-collectblock は、掘る前に canDig を見て、だめなら黙って飛ばす）。積みはしない
export function diggingMovements(bot) {
  const m = carefulMovements(bot);
  m.canDig = true;
  return m;
}

// 掘ってよい、自然のブロック（葉・原木・土・砂・石など）。板・ガラス・レンガなど、建物に使われやすいものは入れない
export const NATURAL = /_leaves$|_log$|_wood$|^(dirt|grass_block|coarse_dirt|podzol|rooted_dirt|mycelium|sand|red_sand|gravel|snow|snow_block|vine|short_grass|tall_grass|fern|large_fern|moss_block|moss_carpet|mud|clay|stone|deepslate|andesite|diorite|granite|tuff|netherrack|azalea|flowering_azalea|mangrove_roots)$/;
// 木の上にいるかを見るブロック
export const TREE = /_leaves$|_log$|_wood$/;
const ESCAPE_DROP = 6;   // 飛び降りてよい高さ（3 ブロックを超えた分だけダメージ。6 なら 3）

// 道が見つからないときの歩き方：自然のブロックだけは掘ってよく、少し高い段差も飛び降りる。
// 高い木の上で生き返り、葉を掘らない・4 ブロックより下りない歩き方では、降りる道が無かった（2026-11-05）
export function escapeMovements(bot) {
  const m = carefulMovements(bot);
  m.canDig = true;
  m.maxDropDown = ESCAPE_DROP;
  for (const b of Object.values(bot.registry.blocksByName)) {
    if (!NATURAL.test(b.name)) m.blocksCantBreak.add(b.id);
  }
  return m;
}
