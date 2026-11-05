// 体の様子を、会話サーバーへ送る形にまとめる（2 秒ごと、と頼まれたとき）。docs/minecraft-design-ja.md の 4.2。

const NEAR = 16;          // 近くとみなす距離（ブロック）
const INVENTORY_ITEMS = 12;
const NIGHT_START = 13000;   // timeOfDay（0〜23999）。13000〜23000 は敵が湧く暗さ
const NIGHT_END = 23000;

export function isNight(timeOfDay) {
  return timeOfDay >= NIGHT_START && timeOfDay < NIGHT_END;
}

const round = (v) => Math.round(v * 10) / 10;

export function summarize(bot, doing) {
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
    hostiles: near.filter(({ e }) => e.type === 'hostile').map(({ e, distance }) => ({ name: e.name, distance })),
    doing: doing ?? null,
  };
}
