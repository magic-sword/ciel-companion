// 体の技。1 つずつ決まった処理で書き、その場でコードを書かせない。docs/minecraft-design-ja.md の 4.2。
// 技は一度に 1 つ。新しい技を受けたら、今の技を止めてから始める。終わったら（止めたときも）必ず done を 1 回送る。
// 身を守る係（guard.js）が経路探索を使っているあいだは、技は待ち、守り終えたら続ける（guarded）。
import pathfinderPkg from 'mineflayer-pathfinder';
import { Vec3 } from 'vec3';

import { guarded } from './guard.js';
import { planCraft } from './craft-plan.js';
import { blocksFor } from './names.js';
import { knows, rememberAround } from './sight.js';
import { escapeMovements, NATURAL, playerMovements, SCAFFOLD } from './movements.js';

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
const TABLE_SEARCH = 32;    // 作業台を探す距離
const TABLE_RANGE = 2;
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
    if (bot) groundedDig(bot);
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
            return watched(bot, () => bot.collectBlock.collect(target));
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


// 足元を depth ブロック掘って降りる（技 dig_down）。
// 自然のブロックだけを掘り、すぐ下が溶岩・水なら掘らない
async function descend(bot, depth, token, guard) {
  const startY = bot.entity.position.y;
  let dug = 0;
  for (let i = 0; i < Math.min(depth, DIG_LIMIT) && !token.cancelled; i++) {
    if (guard?.active) await guard.idle();
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

