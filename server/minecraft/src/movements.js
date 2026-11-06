// 経路探索の歩き方の決まり（技 skills.js と、身を守る係 guard.js が使う）
import pathfinderPkg from 'mineflayer-pathfinder';

const { Movements } = pathfinderPkg;

// 守るとき（guard.js）の決まり：ブロックを壊さない・置かない（戦いながら掘ったり積んだりしない）
export function carefulMovements(bot) {
  const m = new Movements(bot);
  m.canDig = false;
  m.allow1by1towers = false;
  m.scafoldingBlocks = [];
  return m;
}


// 掘ってよい、自然のブロック（葉・原木・土・砂・石など）。板・ガラス・レンガなど、建物に使われやすいものは入れない
export const NATURAL = /_leaves$|_log$|_wood$|^(dirt|grass_block|coarse_dirt|podzol|rooted_dirt|mycelium|sand|red_sand|gravel|snow|snow_block|vine|short_grass|tall_grass|fern|large_fern|moss_block|moss_carpet|mud|clay|stone|deepslate|andesite|diorite|granite|tuff|netherrack|azalea|flowering_azalea|mangrove_roots)$/;

const ESCAPE_DROP_MAX = 12;   // 体力が十分なら、ここまで飛び降りる（ダメージ 9）
const KEEP_HEALTH = 8;        // 飛び降りたあとに残す体力（20 まで）
const LIQUID_COST = 10;   // 水・溶岩の 1 マスを、ふつうの 10 歩分の遠回りとみなす（既定は 1）
const PLAYER_DROP = 4;   // ふだん飛び降りる高さ（ダメージは 1 まで）
// 足場に積んでよい、手持ちのブロック（自然のもの。板・原木のように、作るのに使う物は積まない）
export const SCAFFOLD = ['dirt', 'cobblestone', 'cobbled_deepslate', 'netherrack', 'stone', 'andesite', 'diorite', 'granite',
  'tuff', 'deepslate', 'coarse_dirt', 'mud', 'moss_block'];

// ふだんの歩き方（ついていく・行く・集める）：ふつうのプレイヤーのように、段差は飛び降り、自然のブロックは壊し、
// 手持ちの土・丸石などを積んで足場にする。板・ガラス・レンガなど建物に使うものは壊さない（持ち主の建物を崩さない）。
// 前は壊さない・積まない歩き方で始め、詰まったら替えていたが、高い木の上で旋回し続けて詰まりと分からなかった
// （「ふつうのプレイヤーなら飛び降りたり、壊したり、積んだりする」。2026-11-06）
export function playerMovements(bot) {
  const m = carefulMovements(bot);
  m.canDig = true;
  m.maxDropDown = PLAYER_DROP;
  m.allow1by1towers = true;
  // 水の中はなるべく通らず、水の中で止まって掘らない（水の中では掘るのが 5 倍遅く、原木 1 本に 15 秒かかった。
  // 泳ぎながらでは進めず、落ちた原木も拾えなかった。2026-11-06）
  m.liquidCost = LIQUID_COST;
  m.scafoldingBlocks = SCAFFOLD.map((n) => bot.registry.itemsByName[n]?.id).filter((id) => id !== undefined);
  for (const b of Object.values(bot.registry.blocksByName)) {
    if (!NATURAL.test(b.name)) m.blocksCantBreak.add(b.id);
  }
  return m;
}

// ふだんの歩き方で道が無いとき：高い段差も、体力が KEEP_HEALTH 残る分まで飛び降りる（4〜12 ブロック。体力 20 なら 12）。
// 高い木の途中で、下まで 6 ブロックより高く、降りられなかった（2026-11-06）
export function escapeMovements(bot) {
  const m = playerMovements(bot);
  m.maxDropDown = escapeDrop(bot.health);
  return m;
}

export function escapeDrop(health) {
  const h = Number.isFinite(health) ? Math.floor(health) : 20;
  return Math.max(PLAYER_DROP, Math.min(ESCAPE_DROP_MAX, h - KEEP_HEALTH + 3));
}
