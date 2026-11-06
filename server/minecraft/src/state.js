// 体の様子を、会話サーバーへ送る形にまとめる（2 秒ごと、と頼まれたとき）。docs/minecraft-design-ja.md の 4.2。
// ブロックと敵は、シエルの目から見えるものだけを入れる（sight.js。地中の鉱石を話して不自然だった。2026-11-06）
import { FLOWER_NAMES } from './names.js';
import { canSee, notices, remember } from './sight.js';

const NEAR = 16;          // 近くとみなす距離（ブロック）
const INVENTORY_ITEMS = 12;
const NIGHT_START = 13000;   // timeOfDay（0〜23999）。13000〜23000 は敵が湧く暗さ
const NIGHT_END = 23000;

export function isNight(timeOfDay) {
  return timeOfDay >= NIGHT_START && timeOfDay < NIGHT_END;
}

const round = (v) => Math.round(v * 10) / 10;
const BLOCKS_NEAR = 16;
const TREE = /_leaves$|_log$|_wood$/;
const GROUND_SCAN = 40;

// 足元のブロックと、木の上なら地面からの高さ（葉・原木・空気を下へ数える）。木の上でなければ height は null
export function footing(bot) {
  if (!bot?.entity) return null;
  const feet = bot.entity.position.floored();
  const below = bot.blockAt(feet.offset(0, -1, 0));
  if (!below) return null;
  if (!TREE.test(below.name)) return { on: below.name, height: null };
  let height = 0;
  for (let dy = 1; dy <= GROUND_SCAN; dy++) {
    const b = bot.blockAt(feet.offset(0, -dy, 0));
    if (!b || !(TREE.test(b.name) || b.boundingBox === 'empty')) break;
    height = dy;
  }
  return { on: below.name, height };
}
// 向いている方角（マイクラの yaw：0 が北、北から西へ回る。mineflayer の yaw はラジアン）
const DIRECTIONS = ['north', 'northwest', 'west', 'southwest', 'south', 'southeast', 'east', 'northeast'];
export function facing(bot) {
  if (!bot?.entity) return null;
  const turn = ((bot.entity.yaw / (2 * Math.PI)) % 1 + 1) % 1;
  return DIRECTIONS[Math.round(turn * 8) % 8];
}

const BLOCKS_COUNT = 256;
// 「何が見える？」「木を集めて」に答えるための、近くのブロック（原木・鉱石・草花・危ないもの・使えるもの）
const INTERESTING = /_log$|_ore$|^(lava|water|crafting_table|chest|furnace|ancient_debris)$/;
const interesting = (name) => INTERESTING.test(name) || FLOWER_NAMES.includes(name);

// 近くの、今見えるブロックの種類と数（重いので、呼ぶのは 10 秒に 1 回ほど。main.js）。見えたブロックは覚える（集めるときに使う）
export function nearbyBlocks(bot) {
  if (!bot?.entity) return {};
  const ids = Object.values(bot.registry.blocksByName).filter((b) => interesting(b.name)).map((b) => b.id);
  const counts = {};
  for (const p of bot.findBlocks({ matching: ids, maxDistance: BLOCKS_NEAR, count: BLOCKS_COUNT })) {
    const name = bot.blockAt(p)?.name;
    if (!name || !canSee(bot, p)) continue;
    remember(bot, p, name);
    counts[name] = (counts[name] ?? 0) + 1;
  }
  return counts;
}

export function summarize(bot, doing, blocks = {}) {
  if (!bot || !bot.entity) return { connected: false, doing: doing ?? null };
  const me = bot.entity.position;
  const near = Object.values(bot.entities)
    .filter((e) => e !== bot.entity && e.position && e.position.distanceTo(me) <= NEAR)
    .map((e) => ({ e, distance: round(e.position.distanceTo(me)) }))
    .sort((a, b) => a.distance - b.distance);
  const inventory = {};
  for (const item of bot.inventory.items()) inventory[item.name] = (inventory[item.name] ?? 0) + item.count;
  const top = Object.entries(inventory).sort((a, b) => b[1] - a[1]).slice(0, INVENTORY_ITEMS);
  return {
    connected: true,
    pos: { x: round(me.x), y: round(me.y), z: round(me.z) },
    dimension: bot.game?.dimension ?? null,
    health: round(bot.health),
    food: bot.food,
    time: bot.time?.timeOfDay ?? null,
    night: bot.time ? isNight(bot.time.timeOfDay) : null,
    raining: Boolean(bot.isRaining),
    held: bot.heldItem?.name ?? null,
    inventory: Object.fromEntries(top),
    players: near.filter(({ e }) => e.type === 'player').map(({ e, distance }) => ({ name: e.username, distance })),
    hostiles: near.filter(({ e }) => e.type === 'hostile' && notices(bot, e)).map(({ e, distance }) => ({ name: e.name, distance })),
    blocks,
    footing: footing(bot),
    doing: doing ?? null,
  };
}
