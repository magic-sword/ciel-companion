import { BodyCommands, commandBot } from './body-command.js';
// 体の技。1 つずつ決まった処理で書き、その場でコードを書かせない。docs/minecraft-design-ja.md の 4.2。
// 技は一度に 1 つ。新しい技を受けたら、今の技を止めてから始める。終わったら（止めたときも）必ず done を 1 回送る。
// 身を守る係（guard.js）が経路探索を使っているあいだは、技は待ち、守り終えたら続ける（guarded）。
import pathfinderPkg from 'mineflayer-pathfinder';
import { Vec3 } from 'vec3';

import { guarded } from './guard.js';
import { planCraft } from './craft-plan.js';
import { planGoal } from './goal-plan.js';
import { blocksFor } from './names.js';
import { knows, rememberAround } from './sight.js';
import { collectMovements, escapeMovements, NATURAL, playerMovements, SCAFFOLD } from './movements.js';

const { goals } = pathfinderPkg;
const FOLLOW_RANGE = 2;     // ついていくときに空ける距離
const COME_RANGE = 2;
const SEARCH_DISTANCE = 48; // 集めるブロックを探す距離
const FIND_COUNT = 64;
const TRIES_PER_ITEM = 3;   // 1 個あたりに試すブロックの数（掘れないものが続いたらあきらめる）
const PATH_ERRORS = /Timeout|NoPath|No path|decide path|GoalChanged|PathStopped|Stuck/i;
const STILL_MS = 8000;      // 歩く・集めるあいだ、動かず・掘らず・置かずがこれだけ続いたら、行き先を取り消す（watched）
const STILL_MOVE = 0.3;
const PICKUP_RANGE = 4;       // 掘ったブロックから、拾いに行く範囲（ブロック）
const PICKUP_MAX = 4;         // 1 つのブロックのあとに拾いに行く数
const PICKUP_SETTLE_TICKS = 6;
const PICKUP_WAIT_MS = 1500;  // そばへ行ってから、拾えるまで待つ
const GROUND_WAIT_MS = 2000; // 掘る前に、足が地面に着くのを待つ上限
const SLOW_DIG_MS = 5000;    // これより時間のかかる掘り方は、ログに残す     // 動いたとみなす距離（ブロック）
const STUCK_MS = 8000;      // ついていくとき、離れたまま、これだけ近づけず、その場から動けなければ、詰まったとみなす
const STUCK_MOVE = 4;       // その場から動いたとみなす距離（ブロック。その場で旋回しても、ここまでは動く）
const CLOSER = 1;           // 近づいたとみなす距離（ブロック）
const SCAFFOLD_WANT = 4;    // 足場が無いとき、集める数
const SCAFFOLD_SEARCH = 8;  // 足場にするブロックを探す距離
// 足場の材料が取れるブロック（土は素手で、石はツルハシで）
const SCAFFOLD_SOURCES = ['dirt', 'grass_block', 'coarse_dirt', 'rooted_dirt', 'stone', 'cobblestone', 'deepslate', 'andesite',
  'diorite', 'granite', 'tuff', 'netherrack'];
const DIG_LIMIT = 48;       // 足元を掘って降りるとき、掘るのはここまで
const DANGER = /^(lava|water)$/;
const FIND_NEAR = 32;        // 探しているあいだ、見回す距離
const WALK_RINGS = [16, 32, 48];   // 歩いて探すとき、始めた所から広げる距離（8 方向ずつ）
const WAYPOINT_MS = 30000;   // 歩いて探すとき、1 か所へ向かう上限（水辺を回り込み続けて 90 秒かかった。2026-11-07）
const DIG_MAX = 24;          // 掘って探すとき、掘り下げる段の上限
const AUTO_WALK_RINGS = [16];   // auto で地中の物を探すとき、掘る前に歩いて見回す輪（山肌・崖に出ていることが多い）
const DIG_SPOTS = 3;           // 掘って探すとき、場所を変えてやり直す上限
const DIG_SPOT_RANGE = 16;     // 掘り始める場所を探す距離
const DIG_SPOT_CANDIDATES = 256;
const DIG_SPOT_GAP = 6;        // やり直すとき、前に試した場所からあける距離
const DIG_RETRY = new Set(['danger', 'not_found', 'cannot_dig']);   // 別の場所で掘り直す失敗（needs_tool は心に返す）
const FLUIDS = /^(lava|water|bubble_column)$/;
const TABLE_SEARCH = 32;    // 作業台を探す距離
const TABLE_RANGE = 2;
const TABLE_SPOTS = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [-1, -1], [1, -1], [-1, 1], [2, 0], [-2, 0], [0, 2], [0, -2]];   // 作業台を置く場所（足元からのずれ）
const CRAFT_SETTLE_TICKS = 4;      // 作業台を使うときに近づく距離
// 掘る道具の段（弱い順）。要る道具を言うとき、いちばん弱いものを言う
const TOOL_TIERS = ['wooden', 'golden', 'stone', 'copper', 'iron', 'diamond', 'netherite'];

// 技の失敗。reason は会話サーバーが理由として読む決まった名前、note は途中までの成果（集めた数など）
class Failed extends Error {
  constructor(reason, note = null) {
    super(reason);
    this.note = note;
  }
}

export class Runner extends BodyCommands {
  constructor(report, owner, guard = null) {
    super({
      report,
      available: () => Boolean(this.bot?.entity),
      prepare: c => SKILL_PREPARE[c.skill]?.(this.bot, c.args),
      run: c => this._runSkill(c),
      halt: async c => {
        if (this.guard?.active) return;
        const bot = c.bot ?? this.bot;
        bot?.pathfinder?.stop();
        bot?.pathfinder?.setGoal(null);
        bot?.stopDigging?.();
        await bot?.collectBlock?.cancelTask();
      },
    });
    this.owner = owner;
    this.guard = guard;
    this.bot = null;
  }

  attach(bot) {
    this.bot = bot;
    if (bot) { groundedDig(bot); this.blocked = false; }
  }

  doing() {
    const c = this.current;
    return c ? { id: c.id, skill: c.skill, args: c.args } : null;
  }

  async _runSkill(c) {
    const { skill, args, token } = c;
    c.bot = this.bot;
    const bot = commandBot(this.bot, c, this);
    try {
      const note = await SKILL_RUN[skill](bot, args, token, { owner: this.owner, guard: this.guard });
      return token.cancelled ? cancelled(skill, token, note) : { ok: true, note };
    } catch (err) {
      if (token.cancelled) return cancelled(skill, token);
      if (err instanceof Failed) return { ok: false, reason: err.message, ...(err.note ? { note: err.note } : {}) };
      if (PATH_ERRORS.test(`${err?.name} ${err?.message}`)) return { ok: false, reason: 'no_path' };
      console.warn(`skill failed: skill=${skill} error=${err?.name ?? 'error'}`);
      return { ok: false, reason: 'error', detail: String(err?.message ?? err?.name ?? '').slice(0, 120) };
    }
  }
}

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

// ブロックを掘って取れる物の名前（石 → 丸石、草ブロック → 土、石炭の鉱石 → 石炭）と、ブロックそのものの名前
function dropsOf(registry, blocks) {
  const out = new Set(blocks.map((b) => b.name));
  for (const b of blocks) {
    for (const d of b.drops ?? []) {
      const id = typeof d === 'object' ? (d.drop?.id ?? d.drop) : d;
      const name = registry.items[id]?.name;
      if (name) out.add(name);
    }
  }
  return out;
}

function gained(before, after) {
  const g = {};
  for (const [name, n] of Object.entries(after)) {
    const d = n - (before[name] ?? 0);
    if (d > 0) g[name] = d;
  }
  return g;
}


// 掘る前に、足が地面に着くのを待つ（GROUND_WAIT_MS まで）。mineflayer は掘り始めた瞬間に掘る時間を決め、足が浮いていると
// 5 倍にする（地面に降りても戻さない）。着いた直後の跳ねている瞬間に掘り始め、原木 1 本に 15 秒、腕を振り続けて
// 空振りに見えた（2026-11-06）。時間のかかる掘り方をしたら、あとで確かめられるようログに残す
export function groundedDig(bot, log = console.log) {
  if (bot.__groundedDig) return;
  bot.__groundedDig = true;
  const dig = bot.dig.bind(bot);
  bot.dig = async (block, ...rest) => {
    const end = Date.now() + GROUND_WAIT_MS;
    while (bot.entity && !bot.entity.onGround && !bot.entity.isInWater && Date.now() < end) await bot.waitForTicks(1);
    const ms = bot.digTime(block);
    if (ms >= SLOW_DIG_MS) {
      log(`掘るのに時間がかかる block=${block?.name} ms=${ms} onGround=${bot.entity?.onGround} inWater=${bot.entity?.isInWater} held=${bot.heldItem?.name ?? "なし"}`);
    }
    return dig(block, ...rest);
  };
}

// 掘ったブロックのまわり（PICKUP_RANGE）に落ちている物を拾いに行く。collectblock は、掘ったブロックの真ん中から 0.5 以内に
// 落ちた物しか拾わず、少しずれて落ちた原木や、高い所から落ちた原木を拾わなかった（4 本掘って 0 本。2026-11-06）
export async function pickUpNear(bot, pos, guard, token) {
  const center = pos.offset(0.5, 0.5, 0.5);
  await bot.waitForTicks(PICKUP_SETTLE_TICKS);   // 落ちきるのを待つ
  for (let i = 0; i < PICKUP_MAX && !token.cancelled; i++) {
    const me = bot.entity.position;
    const item = Object.values(bot.entities)
      .filter((e) => e.name === 'item' && e.position && e.position.distanceTo(center) <= PICKUP_RANGE)
      .sort((a, b) => a.position.distanceTo(me) - b.position.distanceTo(me))[0];
    if (!item) return;
    try {
      await guarded(guard, token, () => {
        bot.pathfinder.setMovements(playerMovements(bot));
        const p = item.position;
        return watched(bot, () => bot.pathfinder.goto(new goals.GoalNear(p.x, p.y, p.z, 1)));
      });
    } catch (err) {
      if (!PATH_ERRORS.test(`${err?.name} ${err?.message}`)) throw err;
      return;
    }
    const end = Date.now() + PICKUP_WAIT_MS;
    while (bot.entities[item.id] && Date.now() < end) await bot.waitForTicks(2);
    if (bot.entities[item.id]) return;   // 拾えない（葉の上など）。あきらめる
  }
}

// 見張り：run（経路探索を使う処理）のあいだ、体が動かず・掘らず・置かずのままなら、行き先を取り消して Stuck で終える。
// mineflayer-pathfinder は、道を歩き終えたのに行き先に届いていない（原木が葉に隠れて見えない位置で止まった）と、
// 道を探し直さずに待ち続ける。止める合図（stop）もその状態では効かず、原木を集める技が 14 分止まった（2026-11-06）
export async function watched(bot, run, stillMs = STILL_MS) {
  let last = bot.entity.position.clone();
  let at = Date.now();
  let fired = false;
  const timer = setInterval(() => {
    // 掘っているあいだだけは、動かなくても待つ。足場を積むときは体が上がるので動いたと分かる（積もうとして跳ね続け、
    // 天井の葉で上がれずに止まったとき、積んでいる最中とみなして待ち続けた。2026-11-06）
    const busy = bot.targetDigBlock;
    if (busy || bot.entity.position.distanceTo(last) > STILL_MOVE) {
      last = bot.entity.position.clone();
      at = Date.now();
    } else if (!fired && Date.now() - at > stillMs) {
      fired = true;
      bot.pathfinder.setGoal(null);   // goto は GoalChanged で終わる（collectblock の中でも）
    }
  }, 1000);
  const stuck = () => Object.assign(new Error('Stuck: no progress'), { name: 'Stuck' });
  try {
    const r = await run();
    if (fired) throw stuck();
    return r;
  } catch (err) {
    throw fired ? stuck() : err;
  } finally {
    clearInterval(timer);
  }
}

// 歩いて行く。ふつうのプレイヤーの歩き方（飛び降りる・自然のブロックを壊す・足場を積む）で行き、道が無ければ、
// 足場が無いなら近くで集め、少し高い段差も飛び降りる歩き方でもう一度。守りに割り込まれたら、守り終えてから続ける（guarded）
async function walk(bot, guard, token, goal) {
  const go = (movements) => guarded(guard, token, () => {
    bot.pathfinder.setMovements(movements(bot));
    return watched(bot, () => bot.pathfinder.goto(goal()));
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
        return watched(bot, () => bot.collectBlock.collect(target));
      });
      await pickUpNear(bot, pos, guard, token);
    } catch (err) {
      if (!PATH_ERRORS.test(`${err?.name} ${err?.message}`)) throw err;
    }
  }
  return scaffoldCount(bot) - start;
}

const TOSS_RANGE = 2;      // 渡すときに近づく距離（3 では投げた物が相手を越えて落ちることがあった）
const GIVE_SPAWN_TICKS = 4;  // 投げた物が見えるまで待つ
const GIVE_SEARCH = 6;       // 投げた物を探す距離
const GIVE_WAIT_MS = 6000;   // 相手が拾うのを待つ（拾えるまで 2 秒かかる）

const SKILL_RUN = {
  async follow(bot, args, token, { owner, guard }) {
    const target = playerEntity(bot, args, owner);
    const follow = (movements = playerMovements) => {
      bot.pathfinder.setMovements(movements(bot));
      bot.pathfinder.setGoal(new goals.GoalFollow(target, FOLLOW_RANGE), true);
    };
    await guard?.idle(token);   // 守っている最中なら、終わってからついていく（守りの行き先を上書きしない）
    if (token.cancelled) return;
    follow();
    // 止めるまで続く。相手が見えなくなったら終える。守り終えたら、またついていく。
    // 離れたまま近づけず、その場から動けない（旋回している）なら詰まり：1 度目は足場を集めて、高い段差も飛び降りる
    // 歩き方に替える。それでも詰まれば、道が無いとして終え、心に返す（どうするかは心が様子を見て決める）
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
        // 1 度目：足場を集め、高めの段差も飛び降りる。それでもだめなら終える
        if (tries >= 1) throw new Failed('no_path', { stuck: true, distance: Math.round(distance) });
        tries += 1;
        bot.pathfinder.setGoal(null);
        await gatherScaffold(bot, guard, token);
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

  // 足元を depth ブロック掘って降りる。自然のブロックだけを掘り、すぐ下が溶岩・水なら掘らない
  // 見える所に無いブロックを探す（docs/minecraft-design-ja.md の 25 章）。how：
  //   walk：始めた所から 8 方向へ、少しずつ遠くまで歩いて見回す（木・花・砂・水辺など、地面の上の物）
  //   dig：固い地面から、階段状に掘り下げながら見る（石・鉱石など、地中の物。上り道が残る）
  //   auto：ツルハシが要るブロック（石・鉱石）なら、まず近くを歩いて見回し（山肌・崖に出ていることが多い）、無ければ dig。
  //         ほかは walk（どちらで探すかは、ふつう心が知識を見て決める）
  // 見つけたら止める（集めるのは collect）。見つけたブロックは覚えるので、続けて collect すれば掘れる
  async find(bot, args, token, { guard }) {
    const blocks = blocksFor(bot.registry, args.block);
    if (!blocks.length) throw new Failed('unknown_block');
    const ids = blocks.map((b) => b.id);
    const auto = args.how === 'auto' || !args.how;
    const underground = blocks.some((b) => b.harvestTools);
    const how = auto ? (underground ? 'dig' : 'walk') : args.how;
    if (how === 'dig') {
      await ensureHarvestTool(bot, blocks, token, guard);
      if (token.cancelled) return;
    }
    const start = bot.entity.position.clone();
    const seen = () => {
      const p = bot.findBlocks({ matching: ids, maxDistance: FIND_NEAR, count: FIND_COUNT }).find((q) => knows(bot, q));
      return p ? { found: bot.blockAt(p)?.name, at: { x: p.x, y: p.y, z: p.z } } : null;
    };
    const first = seen();
    if (first) return { ...first, how, already: true };
    if (how === 'dig') {
      if (auto) {   // 先に近くを歩いて見回す（1 つめの輪だけ）
        const hit = await walkToFind(bot, AUTO_WALK_RINGS, token, guard, seen, start);
        if (token.cancelled) return undefined;
        if (hit) return { ...hit, how: 'walk' };
      }
      return digSomewhere(bot, args.max ?? DIG_MAX, token, guard, seen);
    }
    const hit = await walkToFind(bot, WALK_RINGS, token, guard, seen, start);
    if (token.cancelled) return undefined;
    if (hit) return { ...hit, how };
    throw new Failed('not_found', { how, visited: WALK_RINGS.length * 8 });
  },

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
    // 胸のあたりへ軽く投げる（頭の高さへ投げると、相手を越えて穴や水に落ちることがあった）
    await bot.lookAt(target.position.offset(0, 0.8, 0), true);
    const total = have.reduce((n, i) => n + i.count, 0);
    const count = Math.min(args.count ?? total, total);
    // 渡せたかを、相手が拾ったか（playerCollect）で確かめる。拾われずに落ちたままなら、自分で拾い直して not_received
    // （投げた石のつるはしが相手に届かず、なくなった。2026-11-07）
    const before = new Set(Object.values(bot.entities).filter((e) => e.name === 'item').map((e) => e.id));
    const taken = new Map();   // 落とした物の id → 拾った人
    const onCollect = (collector, collected) => taken.set(collected.id, collector);
    bot.on('playerCollect', onCollect);
    try {
      await bot.toss(have[0].type, null, count);
      await bot.waitForTicks(GIVE_SPAWN_TICKS);
      const mine = Object.values(bot.entities).filter((e) => e.name === 'item' && !before.has(e.id)
        && e.position && e.position.distanceTo(bot.entity.position) <= GIVE_SEARCH);
      const end = Date.now() + GIVE_WAIT_MS;
      while (mine.some((e) => bot.entities[e.id] && !taken.has(e.id)) && Date.now() < end && !token.cancelled) {
        await bot.waitForTicks(2);
      }
      const byTarget = mine.filter((e) => taken.get(e.id)?.username === target.username).length;
      const left = mine.filter((e) => bot.entities[e.id] && !taken.has(e.id));
      if (left.length && !byTarget) {
        for (const e of left) await pickUpNear(bot, e.position.floored(), guard, token);   // 自分で拾い直す
        throw new Failed('not_received', { item: args.item });
      }
      if (!byTarget && mine.some((e) => taken.get(e.id) === bot.entity)) throw new Failed('not_received', { item: args.item });
      return { gave: { [args.item]: count }, received: byTarget > 0 || !mine.length };
    } finally {
      bot.removeListener('playerCollect', onCollect);
    }
  },

  // 近くのブロックを掘って集める。掘るのは、シエルが見て知っているブロックだけ（sight.js。埋まった鉱石へ掘り進まない）
  async collect(bot, args, token, { guard }) {
    const blocks = blocksFor(bot.registry, args.block);
    if (!blocks.length) throw new Failed('unknown_block');
    await ensureHarvestTool(bot, blocks, token, guard);
    if (token.cancelled) return;
    const ids = blocks.map((b) => b.id);
    const names = new Set(blocks.map((b) => b.name));
    // 数えるのは、そのブロックから取れる物だけ（石なら丸石）。道を作るときに掘れた土などは数えない
    // （丸石 2 個と土 1 個で「3 個集めた」と終わり、目的の係が丸石 2/3 で止まった。2026-11-07）
    const wanted = dropsOf(bot.registry, blocks);
    const total = (g) => Object.entries(g).reduce((n, [k, v]) => n + (wanted.has(k) ? v : 0), 0);
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
          await guarded(guard, token, async () => {
            await ensureHarvestTool(bot, [target], token, guard);
            if (token.cancelled) return;
            bot.collectBlock.movements = collectMovements(bot, target);
            try {
              return await watched(bot, () => bot.collectBlock.collect(target));
            } finally {
              bot.collectBlock.movements = playerMovements(bot);
              if (!guard?.active) bot.pathfinder.setMovements(bot.collectBlock.movements);
            }
          });
          rememberAround(bot, pos, (n) => names.has(n));   // 木の幹の上のほうも、続けて集められる
          await pickUpNear(bot, pos, guard, token);
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

  // 持ち物から物を作る（板・棒・作業台・ツルハシなど）。途中の物（板・棒・作業台）が足りなければ、持っている原木から先に作る。
  // 作業台が要るものは、近くの作業台を使い、無ければ作って置く。それでも足りなければ、元の材料（原木など）で足りない物を返す。
  // 1 段しか作れず、原木だけ持っていて「板と棒が足りない」で終わり、心が次の手順を呼ばずに止まった（2026-11-07）
  async craft(bot, args, token, { guard }) {
    const before = counts(bot);
    const knownTable = bot.findBlocks({ matching: bot.registry.blocksByName.crafting_table.id, maxDistance: TABLE_SEARCH, count: 8 })
      .some((p) => knows(bot, p));
    const plan = planCraft(bot.registry, (id) => bot.recipesAll(id, null, true), args.item, args.count, counts(bot),
      knownTable || (before.crafting_table ?? 0) > 0);
    if (plan.cannot) throw new Failed('cannot_craft');
    if (Object.keys(plan.missing).length) {
      throw new Failed(plan.needsTable ? 'no_table' : 'missing_materials', { needs: plan.missing, steps: plan.steps.map((st) => st.name) });
    }
    let table = null;
    for (const step of plan.steps) {
      if (token.cancelled) break;
      if (step.recipe.requiresTable && !table) {
        table = await findTable(bot, guard, token);
        if (token.cancelled) break;
        if (!table) throw new Failed('no_table');
      }
      await bot.craft(step.recipe, step.times, step.recipe.requiresTable ? table : undefined);
      await bot.waitForTicks(CRAFT_SETTLE_TICKS);   // 持ち物の更新を待つ（作ってすぐの作業台が、まだ持ち物に見えなかった）
    }
    const made = (counts(bot)[args.item] ?? 0) - (before[args.item] ?? 0);
    const note = { gained: made > 0 ? { [args.item]: made } : {}, wanted: args.count };
    if (!token.cancelled && made < args.count) {
      if (made <= 0) throw new Failed('missing_materials', note);
      note.short = 'missing_materials';
    }
    return note;
  },
};


// 始めた所から輪を広げ、8 方向へ歩いて見回す（find の walk）。見つけたら { found, at, visited }、無ければ null
async function walkToFind(bot, rings, token, guard, seen, start) {
  let visited = 0;
  for (const r of rings) {
    for (let k = 0; k < 8 && !token.cancelled; k++) {
      const a = (k / 8) * 2 * Math.PI;
      const x = Math.round(start.x + r * Math.cos(a)), z = Math.round(start.z + r * Math.sin(a));
      const limit = setTimeout(() => bot.pathfinder.setGoal(null), WAYPOINT_MS);   // 長くかかる方は、あきらめて次の方へ
      try {
        // 1 回だけ向かう（walk のやり直し・足場集めはしない。行けない方は飛ばして次の方へ）
        await guarded(guard, token, () => {
          bot.pathfinder.setMovements(playerMovements(bot));
          return watched(bot, () => bot.pathfinder.goto(new goals.GoalNear(x, bot.entity.position.y, z, 4)));
        });
      } catch (err) {
        if (!PATH_ERRORS.test(`${err?.name} ${err?.message}`)) throw err;   // 行けない方は飛ばす
      } finally {
        clearTimeout(limit);
      }
      visited += 1;
      const hit = seen();
      if (hit) return { ...hit, visited };
    }
  }
  return null;
}

// マイクラの yaw：0 が北（-z）、π/2 が西（-x）
const DIRS = [new Vec3(0, 0, -1), new Vec3(-1, 0, 0), new Vec3(0, 0, 1), new Vec3(1, 0, 0)];
const NOT_GROUND = /_leaves$|_log$|_wood$|^(snow|vine|short_grass|tall_grass|fern|large_fern|moss_carpet|azalea|flowering_azalea|mangrove_roots)$/;

// feet に立って dir へ 1 段目を掘り始められるか：水・溶岩に触れない・降りた先に足場がある・自然のブロックだけ
// （湖の上に張り出した薄い地面では、どの向きも降りた先が空っぽ。2026-11-07）
function canStartDig(bot, feet, dir) {
  const front = feet.plus(dir);
  const step = front.offset(0, -1, 0);
  const targets = [front.offset(0, 1, 0), front, step];
  for (const p of targets) {
    const around = [p, p.offset(1, 0, 0), p.offset(-1, 0, 0), p.offset(0, 0, 1), p.offset(0, 0, -1), p.offset(0, 1, 0)];
    if (around.some((q) => FLUIDS.test(bot.blockAt(q)?.name ?? ''))) return false;
  }
  const floor = bot.blockAt(step.offset(0, -1, 0));
  if (!floor || floor.boundingBox !== 'block') return false;
  return targets.every((p) => {
    const b = bot.blockAt(p);
    return !b || b.boundingBox === 'empty' || (NATURAL.test(b.name) && bot.canDigBlock(b));
  });
}

// feet から掘り始められる向き（向いている方から順に 4 方向）。どれも駄目なら null
function digDirection(bot, feet) {
  const yaw = ((bot.entity.yaw % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
  const first = Math.round(yaw / (Math.PI / 2)) % 4;
  for (let k = 0; k < 4; k++) {
    const dir = DIRS[(first + k) % 4];
    if (canStartDig(bot, feet, dir)) return dir;
  }
  return null;
}

// 近くで、掘り始められる立ち場所（見えている自然の地面で、上 2 つが空き、どこかの向きへ掘り始められる所）。近い順
function digSpots(bot, tried) {
  const ids = Object.values(bot.registry.blocksByName)
    .filter((b) => b.boundingBox === 'block' && NATURAL.test(b.name) && !NOT_GROUND.test(b.name)).map((b) => b.id);
  const here = bot.entity.position;
  return bot.findBlocks({ matching: ids, maxDistance: DIG_SPOT_RANGE, count: DIG_SPOT_CANDIDATES })
    .map((p) => p.offset(0, 1, 0))
    .filter((feet) => [feet, feet.offset(0, 1, 0)].every((q) => (bot.blockAt(q)?.boundingBox ?? 'block') === 'empty'))
    .filter((feet) => knows(bot, feet.offset(0, -1, 0)) && !tried.some((t) => t.distanceTo(feet) < DIG_SPOT_GAP))
    .filter((feet) => digDirection(bot, feet))
    .sort((a, b) => a.distanceTo(here) - b.distanceTo(here));
}

// 掘って探す（find の dig）。足元から掘り始められなければ、近くの固い地面へ移ってから掘る。
// 水に当たる・洞窟に抜けるなど、その場所で続けられなければ、別の場所でやり直す（DIG_SPOTS か所まで）
async function digSomewhere(bot, max, token, guard, seen) {
  const tried = [];
  let last = null;
  for (let n = 0; n < DIG_SPOTS && !token.cancelled; n++) {
    let feet = bot.entity.position.floored();
    let dir = bot.entity.onGround && !tried.some((t) => t.distanceTo(feet) < DIG_SPOT_GAP) ? digDirection(bot, feet) : null;
    if (!dir) {
      const spot = digSpots(bot, tried)[0];
      if (!spot) break;
      tried.push(spot);
      const limit = setTimeout(() => bot.pathfinder.setGoal(null), WAYPOINT_MS);
      try {
        await guarded(guard, token, () => {
          bot.pathfinder.setMovements(playerMovements(bot));
          return watched(bot, () => bot.pathfinder.goto(new goals.GoalBlock(spot.x, spot.y, spot.z)));
        });
      } catch (err) {
        if (!PATH_ERRORS.test(`${err?.name} ${err?.message}`)) throw err;
        continue;   // 行けない：次の場所へ
      } finally {
        clearTimeout(limit);
      }
      if (token.cancelled) break;
      feet = bot.entity.position.floored();
      dir = digDirection(bot, feet);
      if (!dir) continue;
    }
    tried.push(feet.clone());
    try {
      return await digToFind(bot, max, token, guard, seen, bot.entity.position.clone(), dir);
    } catch (err) {
      // 道具が要る（needs_tool）は、場所を変えても同じなので心に返す。ほかは別の場所で掘り直す
      if (!(err instanceof Failed) || !DIG_RETRY.has(err.message)) throw err;
      if (err.message === 'not_found' && err.note?.stopped_at !== 'cave') throw err;   // 深くまで掘って無かった：やり直さない
      last = err;
    }
  }
  if (token.cancelled) return undefined;
  if (last) throw last;
  throw new Failed('not_found', { how: 'dig', dug: 0, stopped_at: 'no_ground' });
}

// dir へ、階段状に掘り下げながら探す。1 段ごとに：前の足の高さ・頭の高さ・前の 1 段下を掘り、そこへ降りる。
// 自然のブロックだけ掘る。水・溶岩に当たりそうなら止める（danger）。必要な道具を用意し、装備してから掘る。
async function digToFind(bot, max, token, guard, seen, start, dir) {
  let dug = 0;
  for (let i = 0; i < max && !token.cancelled; i++) {
    if (guard?.active) await guard.idle(token);
    const feet = bot.entity.position.floored();
    const front = feet.plus(dir);
    const step = front.offset(0, -1, 0);
    const targets = [front.offset(0, 1, 0), front, step];
    for (const p of targets) {
      // 掘った先や隣に水・溶岩があれば、流れ込むので止める
      const around = [p, p.offset(1, 0, 0), p.offset(-1, 0, 0), p.offset(0, 0, 1), p.offset(0, 0, -1), p.offset(0, 1, 0)];
      const fluid = around.map((q) => bot.blockAt(q)).find((b) => b && FLUIDS.test(b.name));
      if (fluid) throw new Failed('danger', { how: 'dig', dug, descended: Math.round(start.y - bot.entity.position.y), below: fluid.name });
    }
    const floor = bot.blockAt(step.offset(0, -1, 0));
    if (!floor || floor.boundingBox !== 'block') {   // 降りた先の足場が無い（洞窟の上など）：そこで見回して終える
      const hit = seen();
      if (hit) return { ...hit, how: 'dig', dug };
      throw new Failed('not_found', { how: 'dig', dug, descended: Math.round(start.y - bot.entity.position.y), stopped_at: 'cave' });
    }
    for (const p of targets) {
      const b = bot.blockAt(p);
      if (!b || b.boundingBox === 'empty') continue;
      if (!NATURAL.test(b.name) || !bot.canDigBlock(b)) {
        throw new Failed('cannot_dig', { how: 'dig', dug, blocked_by: b.name });
      }
      await equipForDig(bot, b, token, guard);
      if (token.cancelled) return;
      await bot.dig(b, true);
      dug += 1;
    }
    try {
      await guarded(guard, token, () => {
        bot.pathfinder.setMovements(playerMovements(bot));
        return watched(bot, () => bot.pathfinder.goto(new goals.GoalBlock(step.x, step.y, step.z)));
      });
    } catch (err) {
      if (!PATH_ERRORS.test(`${err?.name} ${err?.message}`)) throw err;
    }
    const hit = seen();
    if (hit) return { ...hit, how: 'dig', dug, descended: Math.round(start.y - bot.entity.position.y) };
  }
  if (token.cancelled) return undefined;
  throw new Failed('not_found', { how: 'dig', dug, descended: Math.round(start.y - bot.entity.position.y) });
}

// 足元を depth ブロック掘って降りる（技 dig_down）。
// 自然のブロックだけを掘り、すぐ下が溶岩・水なら掘らない
async function descend(bot, depth, token, guard) {
  const startY = bot.entity.position.y;
  let dug = 0;
  for (let i = 0; i < Math.min(depth, DIG_LIMIT) && !token.cancelled; i++) {
    if (guard?.active) await guard.idle(token);
    if (token.cancelled) break;
    const feet = bot.entity.position.floored();
    const below = bot.blockAt(feet.offset(0, -1, 0));
    if (!below) break;
    if (below.boundingBox === 'empty') {   // 落ちている途中
      await bot.waitForTicks(5);
      continue;
    }
    if (!NATURAL.test(below.name) || !bot.canDigBlock(below)) {
      throw new Failed('cannot_dig', { descended: Math.round(startY - bot.entity.position.y), dug, blocked_by: below.name });
    }
    const under = bot.blockAt(feet.offset(0, -2, 0));
    if (under && DANGER.test(under.name)) {
      throw new Failed('danger', { descended: Math.round(startY - bot.entity.position.y), dug, below: under.name });
    }
    await equipForDig(bot, below, token, guard);
    if (token.cancelled) break;
    await bot.dig(below, true);
    dug += 1;
    await bot.waitForTicks(4);
  }
  return { descended: Math.round(startY - bot.entity.position.y), dug };
}

// 始める前に確かめる。だめなら { reason, note }（started の代わりに error で返す）
const SKILL_PREPARE = {
  find(bot, args) {
    return blocksFor(bot.registry, args.block).length ? null : { reason: 'unknown_block' };
  },
  // 見て知っている所に無い場合は、ここで断る。道具不足は技の中で作成する。始めたと返したあとですぐ失敗すると、
  // 心は「今まさに作っている」と言い違えた（2026-11-07）
  collect(bot, args) {
    const blocks = blocksFor(bot.registry, args.block);
    if (!blocks.length) return { reason: 'unknown_block' };
    // 道具が足りなければ、技の中で材料を集めて作ってから続ける。
    if (!blocks.some((b) => harvestable(bot, b))) return null;
    const ids = blocks.map((b) => b.id);
    const seen = bot.findBlocks({ matching: ids, maxDistance: SEARCH_DISTANCE, count: FIND_COUNT }).some((p) => knows(bot, p));
    return seen ? null : { reason: 'not_found', note: { gained: {}, wanted: args.count } };
  },
  craft(bot, args) {
    if (!bot.registry.itemsByName[args.item]) return { reason: 'unknown_item' };
    const inv = counts(bot);
    const hasTable = (inv.crafting_table ?? 0) > 0
      || bot.findBlocks({ matching: bot.registry.blocksByName.crafting_table.id, maxDistance: TABLE_SEARCH, count: 8 }).some((p) => knows(bot, p));
    const plan = planCraft(bot.registry, (id) => bot.recipesAll(id, null, true), args.item, args.count, inv, hasTable);
    if (plan.cannot) return { reason: 'cannot_craft' };
    if (Object.keys(plan.missing).length) return { reason: 'missing_materials', note: { needs: plan.missing } };
    return null;
  },
};

// 探索・採集で必要な道具を、既存の作成計画で用意する。同じ技・停止合図の中で実行し、
// 別の Runner を始めて元の依頼を取り消さない。見つからない材料や未対応の材料では失敗を返す。
async function ensureHarvestTool(bot, blocks, token, guard) {
  if (token.cancelled || blocks.some((b) => harvestable(bot, b))) return;
  const tool = weakestTool(bot, blocks);
  if (!tool) throw new Failed('needs_tool');
  const hasTable = (counts(bot).crafting_table ?? 0) > 0
    || bot.findBlocks({ matching: bot.registry.blocksByName.crafting_table.id, maxDistance: TABLE_SEARCH, count: 8 }).some((p) => knows(bot, p));
  const plan = planGoal(bot.registry, (id) => bot.recipesAll(id, null, true), tool, 1, counts(bot), hasTable);
  if (plan.error) throw new Failed('needs_tool', { tool });
  for (const step of plan.steps) {
    if (token.cancelled) return;
    if (step.kind === 'craft') {
      await SKILL_RUN.craft(bot, { item: step.item, count: step.count }, token, { guard });
    } else if (step.kind === 'gather') {
      const wanted = (counts(bot)[step.item] ?? 0) + step.count;
      // 一度の採集で足りない場合も、残りだけを探して集める。無限には探さない。
      for (let attempt = 0; attempt < TRIES_PER_ITEM && !token.cancelled; attempt++) {
        const remaining = wanted - (counts(bot)[step.item] ?? 0);
        if (remaining <= 0) break;
        try {
          await SKILL_RUN.collect(bot, { block: step.item, count: Math.min(64, remaining) }, token, { guard });
        } catch (err) {
          if (!(err instanceof Failed) || err.message !== 'not_found') throw err;
        }
        if (token.cancelled) return;
        if ((counts(bot)[step.item] ?? 0) < wanted && attempt < TRIES_PER_ITEM - 1) {
          await SKILL_RUN.find(bot, { block: step.item, how: 'auto' }, token, { guard });
        }
      }
      if (token.cancelled) return;
      const missing = wanted - (counts(bot)[step.item] ?? 0);
      if (missing > 0) throw new Failed('missing_materials', { tool, needs: { [step.item]: missing } });
    } else {
      throw new Failed('missing_materials', { tool, needs: { [step.item]: step.count } });
    }
  }
  if (!token.cancelled && !blocks.some((b) => harvestable(bot, b))) throw new Failed('needs_tool', { tool });
}

async function equipForDig(bot, block, token, guard) {
  await ensureHarvestTool(bot, [block], token, guard);
  if (token.cancelled) return;
  if (bot.tool?.equipForBlock) await bot.tool.equipForBlock(block, {});
  // 最速の道具がドロップ条件を満たさない場合も、採掘可能な道具を必ず手に持つ。
  if (block.harvestTools && !block.harvestTools[bot.heldItem?.type]) {
    const item = bot.inventory.items().find((i) => block.harvestTools[i.type]);
    if (!item) throw new Failed('needs_tool', { tool: weakestTool(bot, [block]) });
    await bot.equip(item, 'hand');
  }
}

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
  let item = null;
  for (let i = 0; i < 20 && !item; i++) {
    item = bot.inventory.items().find((it) => it.name === 'crafting_table');
    if (!item) await bot.waitForTicks(1);
  }
  if (!item) return null;
  const feet = bot.entity.position.floored();
  const open = (p) => {
    const b = bot.blockAt(p);
    return b && b.boundingBox === 'empty' && !FLUIDS.test(b.name);
  };
  const tryPlace = async (at) => {
    const below = bot.blockAt(at.offset(0, -1, 0));
    if (!open(at) || below?.boundingBox !== 'block') return null;
    try {
      await bot.equip(item, 'hand');
      await bot.lookAt(at.offset(0.5, 0.5, 0.5), true);
      await bot.placeBlock(below, new Vec3(0, 1, 0));
    } catch {
      return null;   // 置けなかった（面が見えない・届かない）：次の場所へ
    }
    const placed = bot.blockAt(at);
    return placed?.name === 'crafting_table' ? placed : null;
  };
  // 足と同じ高さ、1 段上、1 段下の順に、近くの空いた所（下が地面）を探す
  for (const dy of [0, 1, -1]) {
    for (const [dx, dz] of TABLE_SPOTS) {
      const placed = await tryPlace(feet.offset(dx, dy, dz));
      if (placed) return placed;
    }
  }
  // 空きが無い（1 マスの穴の中など）：プレイヤーと同じく、横の自然のブロックを 1 つ掘って場所を空けてから置く（2026-11-07）
  for (const dir of DIRS) {
    const at = feet.plus(dir);
    const wall = bot.blockAt(at);
    const below = bot.blockAt(at.offset(0, -1, 0));
    if (!wall || wall.boundingBox !== 'block' || below?.boundingBox !== 'block') continue;
    if (!NATURAL.test(wall.name) || !bot.canDigBlock(wall)) continue;
    const near = [at.offset(1, 0, 0), at.offset(-1, 0, 0), at.offset(0, 0, 1), at.offset(0, 0, -1), at.offset(0, 1, 0)];
    if (near.some((q) => FLUIDS.test(bot.blockAt(q)?.name ?? ''))) continue;   // 掘ると水・溶岩が流れ込む
    if (bot.tool?.equipForBlock) await bot.tool.equipForBlock(wall, {}).catch(() => {});
    await bot.dig(wall, true);
    const placed = await tryPlace(at);
    if (placed) return placed;
  }
  throw new Failed('no_room');
}

