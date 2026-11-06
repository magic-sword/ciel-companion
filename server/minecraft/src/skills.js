// 体の技。1 つずつ決まった処理で書き、その場でコードを書かせない。docs/minecraft-design-ja.md の 4.2。
// 技は一度に 1 つ。新しい技を受けたら、今の技を止めてから始める。終わったら（止めたときも）必ず done を 1 回送る。
// 身を守る係（guard.js）が経路探索を使っているあいだは、技は待ち、守り終えたら続ける（guarded）。
import pathfinderPkg from 'mineflayer-pathfinder';
import { Vec3 } from 'vec3';

import { guarded } from './guard.js';
import { blocksFor } from './names.js';
import { knows, rememberAround } from './sight.js';
import { footing } from './state.js';
import { escapeMovements, NATURAL, playerMovements, SCAFFOLD, TREE } from './movements.js';

const { goals } = pathfinderPkg;
const FOLLOW_RANGE = 2;     // ついていくときに空ける距離
const COME_RANGE = 2;
const SEARCH_DISTANCE = 48; // 集めるブロックを探す距離
const FIND_COUNT = 64;
const TRIES_PER_ITEM = 3;   // 1 個あたりに試すブロックの数（掘れないものが続いたらあきらめる）
const PATH_ERRORS = /Timeout|NoPath|No path|decide path|GoalChanged|PathStopped/i;
const STUCK_MS = 8000;      // ついていくとき、離れたまま、これだけ近づけず、その場から動けなければ、詰まったとみなす
const STUCK_MOVE = 4;       // その場から動いたとみなす距離（ブロック。木の上で旋回しても、ここまでは動く）
const CLOSER = 1;           // 近づいたとみなす距離（ブロック）
const SCAFFOLD_WANT = 4;    // 足場が無いとき、集める数
const SCAFFOLD_SEARCH = 8;  // 足場にするブロックを探す距離
// 足場の材料が取れるブロック（土は素手で、石はツルハシで）
const SCAFFOLD_SOURCES = ['dirt', 'grass_block', 'coarse_dirt', 'rooted_dirt', 'stone', 'cobblestone', 'deepslate', 'andesite',
  'diorite', 'granite', 'tuff', 'netherrack'];
const DIG_LIMIT = 48;       // 足元を掘って降りるとき、掘るのはここまで
const DANGER = /^(lava|water)$/;
const TABLE_SEARCH = 32;    // 作業台を探す距離
const TABLE_RANGE = 2;      // 作業台を使うときに近づく距離
// 掘る道具の段（弱い順）。要る道具を言うとき、いちばん弱いものを言う
const TOOL_TIERS = ['wooden', 'golden', 'stone', 'copper', 'iron', 'diamond', 'netherite'];

// 技の失敗。reason は会話サーバーが理由として読む決まった名前、note は途中までの成果（集めた数など）
class Failed extends Error {
  constructor(reason, note = null) {
    super(reason);
    this.note = note;
  }
}

export class Runner {
  // report(type, fields)：会話サーバーへ送る。owner：持ち主のプレイヤー名（player を省いたときの相手）
  // guard：身を守る係（guard.Guard）
  constructor(report, owner, guard = null) {
    this.report = report;
    this.owner = owner;
    this.guard = guard;
    this.bot = null;
    this.current = null;   // {id, skill, args, token}
  }

  attach(bot) {
    this.bot = bot;
  }

  doing() {
    const c = this.current;
    return c ? { id: c.id, skill: c.skill, args: c.args } : null;
  }

  // 今の技を止める。reason は done の note に入る（stopped・replaced・died・disconnected・unlinked）
  stop(reason) {
    const c = this.current;
    if (!c) return;
    c.token.cancelled = true;
    c.token.reason = reason;
    const bot = this.bot;
    if (this.guard?.active) return;   // 守っている最中の経路探索は止めない（技は待っているので、そのまま終わる）
    if (bot?.pathfinder) {
      bot.pathfinder.stop();
      bot.pathfinder.setGoal(null);
    }
    bot?.collectBlock?.cancelTask().catch(() => {});
  }

  async start({ id, skill, args }) {
    if (!this.bot?.entity) {
      this.report('done', { id, ok: false, reason: 'not_spawned' });
      return;
    }
    // 始める前に分かるだめな理由（知らない名前・道具が無い）は、started の代わりに error で返す。
    // 心は道具の返事でそれを知り、その場で正直に言える（「flower」で頼み、始めたと言ったあとで断られた。2026-11-06）
    const refused = SKILL_PREPARE[skill]?.(this.bot, args);
    if (refused) {
      this.report('error', { id, ...refused });
      return;
    }
    this.stop('replaced');
    const token = { cancelled: false, reason: null };
    const c = { id, skill, args, token };
    this.current = c;
    this.report('started', { id, skill });
    let result;
    try {
      const note = await SKILL_RUN[skill](this.bot, args, token, { owner: this.owner, guard: this.guard });
      result = token.cancelled ? cancelled(skill, token, note) : { ok: true, note };
    } catch (err) {
      if (token.cancelled) result = cancelled(skill, token);
      else if (err instanceof Failed) result = { ok: false, reason: err.message, ...(err.note ? { note: err.note } : {}) };
      else if (PATH_ERRORS.test(`${err?.name} ${err?.message}`)) result = { ok: false, reason: 'no_path' };
      else {
        console.warn(`技が失敗した skill=${skill} error=${err?.name ?? err}`, err?.stack?.split('\n').slice(0, 4).join(' | ') ?? '');
        result = { ok: false, reason: 'error', detail: String(err?.message ?? err?.name ?? '').slice(0, 120) };
      }
    }
    if (this.current === c) this.current = null;
    this.report('done', { id, ...result });
  }
}

// 止めたとき。ついていくのは止めるまで続く技なので、止めるのがふつうの終わり
function cancelled(skill, token, note) {
  if (skill === 'follow' && token.reason === 'stopped') return { ok: true, note: { stopped: true } };
  return { ok: false, reason: token.reason ?? 'stopped', ...(note ? { note } : {}) };
}

function playerEntity(bot, args, owner) {
  const name = args.player ?? owner;
  if (!name) throw new Failed('no_owner');
  const entity = bot.players[name]?.entity;
  if (!entity) throw new Failed('player_not_visible');
  return entity;
}

function counts(bot) {
  const c = {};
  for (const item of bot.inventory.items()) c[item.name] = (c[item.name] ?? 0) + item.count;
  return c;
}

function gained(before, after) {
  const g = {};
  for (const [name, n] of Object.entries(after)) {
    const d = n - (before[name] ?? 0);
    if (d > 0) g[name] = d;
  }
  return g;
}

const total = (g) => Object.values(g).reduce((a, b) => a + b, 0);

// 歩いて行く。ふつうのプレイヤーの歩き方（飛び降りる・自然のブロックを壊す・足場を積む）で行き、道が無ければ、
// 足場が無いなら近くで集め、少し高い段差も飛び降りる歩き方でもう一度。守りに割り込まれたら、守り終えてから続ける（guarded）
async function walk(bot, guard, token, goal) {
  const go = (movements) => guarded(guard, token, () => {
    bot.pathfinder.setMovements(movements(bot));
    return bot.pathfinder.goto(goal());
  });
  try {
    return await go(playerMovements);
  } catch (err) {
    if (token.cancelled || !PATH_ERRORS.test(`${err?.name} ${err?.message}`)) throw err;
    await gatherScaffold(bot, guard, token);
    if (token.cancelled) return undefined;
    return await go(escapeMovements);
  }
}

// 手持ちの足場（土・丸石など）の数
export function scaffoldCount(bot) {
  return bot.inventory.items().filter((i) => SCAFFOLD.includes(i.name)).reduce((n, i) => n + i.count, 0);
}

// 足場が無ければ、近くの見えている土・石を掘って集める（石は掘れる道具があるときだけ）。集めた数を返す
export async function gatherScaffold(bot, guard, token) {
  if (scaffoldCount(bot) >= SCAFFOLD_WANT) return 0;
  const sources = SCAFFOLD_SOURCES.map((n) => bot.registry.blocksByName[n]).filter((b) => b && harvestable(bot, b));
  const start = scaffoldCount(bot);
  const tried = new Set();
  while (!token.cancelled && scaffoldCount(bot) < SCAFFOLD_WANT && tried.size < SCAFFOLD_WANT * TRIES_PER_ITEM) {
    const pos = bot.findBlocks({ matching: sources.map((b) => b.id), maxDistance: SCAFFOLD_SEARCH, count: FIND_COUNT })
      .find((p) => !tried.has(p.toString()) && knows(bot, p));
    if (!pos) break;
    tried.add(pos.toString());
    const target = bot.blockAt(pos);
    if (!target) continue;
    try {
      await guarded(guard, token, () => {
        bot.collectBlock.movements = playerMovements(bot);
        return bot.collectBlock.collect(target);
      });
    } catch (err) {
      if (!PATH_ERRORS.test(`${err?.name} ${err?.message}`)) throw err;
    }
  }
  return scaffoldCount(bot) - start;
}

const TOSS_RANGE = 3;      // 渡すときに近づく距離

const SKILL_RUN = {
  async follow(bot, args, token, { owner, guard }) {
    const target = playerEntity(bot, args, owner);
    const follow = (movements = playerMovements) => {
      bot.pathfinder.setMovements(movements(bot));
      bot.pathfinder.setGoal(new goals.GoalFollow(target, FOLLOW_RANGE), true);
    };
    await guard?.idle();   // 守っている最中なら、終わってからついていく（守りの行き先を上書きしない）
    if (token.cancelled) return;
    follow();
    // 止めるまで続く。相手が見えなくなったら終える。守り終えたら、またついていく。
    // 離れたまま近づけず、その場から動けない（旋回している）なら詰まり：1 度目は足場を集めて、高い段差も飛び降りる
    // 歩き方に替える。それでも詰まれば、道が無いとして終え、心に返す（木の上なら dig_down などを心が選ぶ）
    let generation = guard?.generation;
    let tries = 0;
    const reset = () => ({ at: Date.now(), pos: bot.entity.position.clone(), best: target.position.distanceTo(bot.entity.position) });
    let mark = reset();
    while (!token.cancelled) {
      await new Promise((r) => setTimeout(r, 500));
      if (token.cancelled) break;
      if (guard?.active) {
        mark = reset();
        continue;
      }
      if (!bot.entities[target.id]) throw new Failed('player_not_visible');
      if (guard && guard.generation !== generation) {
        generation = guard.generation;
        follow(tries ? escapeMovements : playerMovements);
        mark = reset();
      }
      const distance = target.position.distanceTo(bot.entity.position);
      const far = distance > FOLLOW_RANGE + 4;
      if (!far) {
        if (tries) follow();
        tries = 0;
        mark = reset();
      } else if (distance < mark.best - CLOSER || bot.entity.position.distanceTo(mark.pos) > STUCK_MOVE) {
        mark = reset();   // 近づいている・その場を離れて動いている（相手が走って離れていくときも）
      } else if (Date.now() - mark.at > STUCK_MS) {
        // 1 度目：足場を集め、高めの段差も飛び降りる。2 度目：木の上なら足元を掘って降りる。それでもだめなら終える
        const onTree = footing(bot)?.height;
        if (tries >= 2 || (tries === 1 && !onTree)) throw new Failed('no_path', { stuck: true, distance: Math.round(distance) });
        tries += 1;
        bot.pathfinder.setGoal(null);
        if (tries === 1) await gatherScaffold(bot, guard, token);
        else await descend(bot, undefined, token, guard).catch((err) => {
          if (!(err instanceof Failed)) throw err;
        });
        if (token.cancelled) break;
        follow(escapeMovements);
        mark = reset();
      }
    }
  },

  async come(bot, args, token, { owner, guard }) {
    await walk(bot, guard, token, () => {
      const p = playerEntity(bot, args, owner).position;
      return new goals.GoalNear(p.x, p.y, p.z, COME_RANGE);
    });
  },

  async go_to(bot, args, token, { owner, guard }) {
    await walk(bot, guard, token, () => {
      if (args.x === undefined) {
        const p = playerEntity(bot, args, owner).position;
        return new goals.GoalNear(p.x, p.y, p.z, COME_RANGE);
      }
      if (args.y === undefined) return new goals.GoalXZ(args.x, args.z);
      return new goals.GoalNear(args.x, args.y, args.z, 1);
    });
  },

  // 足元を掘って降りる。depth を省けば、木の上から地面まで。自然のブロックだけを掘り、すぐ下が溶岩・水なら掘らない
  async dig_down(bot, args, token, { guard }) {
    return descend(bot, args.depth, token, guard);
  },

  async give(bot, args, token, { owner, guard }) {
    const have = bot.inventory.items().filter((i) => i.name === args.item);
    if (!have.length) throw new Failed('not_have');
    const target = playerEntity(bot, args, owner);
    await walk(bot, guard, token, () => {
      const p = target.position;
      return new goals.GoalNear(p.x, p.y, p.z, TOSS_RANGE);
    });
    if (token.cancelled) return undefined;
    await bot.lookAt(target.position.offset(0, 1.6, 0), true);
    const total = have.reduce((n, i) => n + i.count, 0);
    const count = Math.min(args.count ?? total, total);
    await bot.toss(have[0].type, null, count);
    return { gave: { [args.item]: count } };
  },

  // 近くのブロックを掘って集める。掘るのは、シエルが見て知っているブロックだけ（sight.js。埋まった鉱石へ掘り進まない）
  async collect(bot, args, token, { guard }) {
    const blocks = blocksFor(bot.registry, args.block);
    if (!blocks.length) throw new Failed('unknown_block');
    const ids = blocks.map((b) => b.id);
    const names = new Set(blocks.map((b) => b.name));
    const before = counts(bot);
    let got = {};
    // 掘れない（道具が無い・掘ると危ない）ブロックは、collectblock が黙って飛ばす。同じ場所を何度も選ばないよう、試した場所を覚える
    const tried = new Set();
    let unreachable = 0;   // 道が見つからなかったブロックの数
    while (!token.cancelled && total(got) < args.count && tried.size < args.count * TRIES_PER_ITEM) {
      const pos = bot.findBlocks({ matching: ids, maxDistance: SEARCH_DISTANCE, count: FIND_COUNT })
        .find((p) => !tried.has(p.toString()) && knows(bot, p));
      if (!pos) break;
      tried.add(pos.toString());
      const target = bot.blockAt(pos);
      if (target) {
        try {
          await guarded(guard, token, () => {
            bot.collectBlock.movements = playerMovements(bot);   // 守る係が歩き方を変えたあとでも、掘れるように戻す
            return bot.collectBlock.collect(target);
          });
          rememberAround(bot, pos, (n) => names.has(n));   // 木の幹の上のほうも、続けて集められる
        } catch (err) {
          // そのブロックへの道が見つからない・決めきれない。技全体はやめずに、次のブロックへ
          // （遠くの木で「Took to long to decide path」になり、集めるのを丸ごとやめた。2026-11-05）
          if (!PATH_ERRORS.test(`${err?.name} ${err?.message}`)) throw err;
          unreachable += 1;
        }
      }
      got = gained(before, counts(bot));
    }
    const note = { gained: got, wanted: args.count, unreachable };
    if (token.cancelled) return note;
    if (total(got) === 0) throw new Failed(unreachable ? 'no_path' : tried.size ? 'cannot_harvest' : 'not_found', note);
    // 頼まれた数に届かなかった：道が見つからない・掘れない・近くにもう無い
    if (total(got) < args.count) note.short = unreachable ? 'no_path' : tried.size >= args.count * TRIES_PER_ITEM ? 'cannot_harvest' : 'not_found';
    return note;
  },

  // 持ち物から物を作る（板・棒・作業台・ツルハシなど）。作業台が要るものは、近くの作業台を使い、無ければ持っている作業台を置く。
  // 材料が足りなければ、足りない物を返す（何を先に作る・集めるかは心が決める）
  async craft(bot, args, token, { guard }) {
    const item = bot.registry.itemsByName[args.item];
    const before = counts(bot);
    let table = null;
    let recipe = bot.recipesFor(item.id, null, 1, null)[0];
    if (!recipe) {
      const all = bot.recipesAll(item.id, null, true);
      if (!all.length) throw new Failed('cannot_craft');
      const needsTable = all.every((r) => r.requiresTable);
      if (needsTable) {
        table = await findTable(bot, guard, token);
        if (token.cancelled) return undefined;
        recipe = table ? bot.recipesFor(item.id, null, 1, table)[0] : null;
      }
      if (!recipe) throw new Failed(needsTable && !table ? 'no_table' : 'missing_materials', { needs: missing(bot, all) });
    }
    const made = () => (counts(bot)[args.item] ?? 0) - (before[args.item] ?? 0);
    while (!token.cancelled && made() < args.count && recipe) {
      await bot.craft(recipe, 1, table ?? undefined);
      recipe = bot.recipesFor(item.id, null, 1, table)[0];
    }
    const note = { gained: made() > 0 ? { [args.item]: made() } : {}, wanted: args.count };
    if (!token.cancelled && made() < args.count) {
      const needs = missing(bot, bot.recipesAll(item.id, null, table ?? true));
      if (made() === 0) throw new Failed('missing_materials', { ...note, needs });
      note.short = 'missing_materials';
      note.needs = needs;
    }
    return note;
  },
};


// 足元を掘って降りる（技 dig_down と、木の上でついていけないとき）。depth を省けば、木の上から地面まで。
// 自然のブロックだけを掘り、すぐ下が溶岩・水なら掘らない
async function descend(bot, depth, token, guard) {
  const startY = bot.entity.position.y;
  let dug = 0;
  for (let i = 0; i < (depth ?? DIG_LIMIT) && !token.cancelled; i++) {
    if (guard?.active) await guard.idle();
    if (token.cancelled) break;
    const feet = bot.entity.position.floored();
    const below = bot.blockAt(feet.offset(0, -1, 0));
    if (!below) break;
    if (below.boundingBox === 'empty') {   // 落ちている途中
      await bot.waitForTicks(5);
      continue;
    }
    if (depth === undefined && !TREE.test(below.name)) break;   // 地面に着いた
    if (!NATURAL.test(below.name) || !bot.canDigBlock(below)) {
      throw new Failed('cannot_dig', { descended: Math.round(startY - bot.entity.position.y), dug, blocked_by: below.name });
    }
    const under = bot.blockAt(feet.offset(0, -2, 0));
    if (under && DANGER.test(under.name)) {
      throw new Failed('danger', { descended: Math.round(startY - bot.entity.position.y), dug, below: under.name });
    }
    if (bot.tool?.equipForBlock) await bot.tool.equipForBlock(below, {}).catch(() => {});
    await bot.dig(below, true);
    dug += 1;
    await bot.waitForTicks(4);
  }
  return { descended: Math.round(startY - bot.entity.position.y), dug };
}

// 始める前に確かめる。だめなら { reason, note }（started の代わりに error で返す）
const SKILL_PREPARE = {
  collect(bot, args) {
    const blocks = blocksFor(bot.registry, args.block);
    if (!blocks.length) return { reason: 'unknown_block' };
    if (blocks.some((b) => harvestable(bot, b))) return null;
    return { reason: 'needs_tool', note: { tool: weakestTool(bot, blocks) } };
  },
  craft(bot, args) {
    return bot.registry.itemsByName[args.item] ? null : { reason: 'unknown_item' };
  },
};

// 素手か、持っている道具で、落ちる物が取れるか
export function harvestable(bot, block) {
  if (!block.harvestTools) return true;
  return Object.keys(block.harvestTools).some((id) => bot.inventory.items().some((i) => i.type === Number(id)));
}

export function weakestTool(bot, blocks) {
  const tools = blocks.flatMap((b) => Object.keys(b.harvestTools ?? {}).map((id) => bot.registry.items[Number(id)]?.name)).filter(Boolean);
  const tier = (n) => TOOL_TIERS.findIndex((t) => n.startsWith(t + '_'));
  return tools.sort((a, b) => tier(a) - tier(b))[0] ?? null;
}

// 材料のいちばん少なく足りない作り方で、足りない物と数
export function missing(bot, recipes) {
  const have = counts(bot);
  let best = null;
  for (const r of recipes) {
    const need = {};
    for (const d of r.delta ?? []) {
      if (d.count >= 0) continue;
      const name = bot.registry.items[d.id]?.name;
      if (!name) continue;
      const short = -d.count - (have[name] ?? 0);
      if (short > 0) need[name] = (need[name] ?? 0) + short;
    }
    if (!best || total(need) < total(best)) best = need;
  }
  return best ?? {};
}

// 近くの作業台（見て知っているもの）。無ければ、持っている作業台を足元のそばに置く。どちらも無ければ null
async function findTable(bot, guard, token) {
  const id = bot.registry.blocksByName.crafting_table.id;
  const pos = bot.findBlocks({ matching: id, maxDistance: TABLE_SEARCH, count: 8 }).find((p) => knows(bot, p));
  const table = pos ? bot.blockAt(pos) : await placeTable(bot);
  if (!table) return null;
  await walk(bot, guard, token, () => new goals.GoalNear(table.position.x, table.position.y, table.position.z, TABLE_RANGE));
  return bot.blockAt(table.position);
}

async function placeTable(bot) {
  const item = bot.inventory.items().find((i) => i.name === 'crafting_table');
  if (!item) return null;
  const feet = bot.entity.position.floored();
  for (const [dx, dz] of [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [-1, -1], [1, -1], [-1, 1], [2, 0], [-2, 0], [0, 2], [0, -2]]) {
    const at = feet.offset(dx, 0, dz);
    const here = bot.blockAt(at);
    const below = bot.blockAt(at.offset(0, -1, 0));
    if (here?.name !== 'air' || below?.boundingBox !== 'block') continue;
    await bot.equip(item, 'hand');
    await bot.lookAt(at.offset(0.5, 0.5, 0.5), true);
    await bot.placeBlock(below, new Vec3(0, 1, 0));
    const placed = bot.blockAt(at);
    if (placed?.name === 'crafting_table') return placed;
  }
  throw new Failed('no_room');
}

