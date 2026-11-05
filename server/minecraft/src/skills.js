// 体の技。1 つずつ決まった処理で書き、その場でコードを書かせない。docs/minecraft-design-ja.md の 4.2。
// 技は一度に 1 つ。新しい技を受けたら、今の技を止めてから始める。終わったら（止めたときも）必ず done を 1 回送る。
// 身を守る係（guard.js）が経路探索を使っているあいだは、技は待ち、守り終えたら続ける（guarded）。
import pathfinderPkg from 'mineflayer-pathfinder';

import { guarded } from './guard.js';
import { carefulMovements, diggingMovements, escapeMovements, NATURAL, TREE } from './movements.js';

const { goals } = pathfinderPkg;
const FOLLOW_RANGE = 2;     // ついていくときに空ける距離
const COME_RANGE = 2;
const SEARCH_DISTANCE = 48; // 集めるブロックを探す距離
const FIND_COUNT = 64;
const TRIES_PER_ITEM = 3;   // 1 個あたりに試すブロックの数（掘れないものが続いたらあきらめる）
const PATH_ERRORS = /Timeout|NoPath|No path|decide path|GoalChanged|PathStopped/i;
const STUCK_MS = 6000;      // ついていくとき、離れたままこれだけ動けなければ、道が無いとみなす
const STUCK_MOVE = 1;       // 動いたとみなす距離（ブロック）
const DIG_LIMIT = 48;       // 足元を掘って降りるとき、掘るのはここまで
const DANGER = /^(lava|water)$/;

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

// 歩いて行く。ふだんの歩き方（壊さない・置かない）で道が無ければ、自然のブロックだけ掘ってよい歩き方でもう一度。
// 守りに割り込まれたら、守り終えてから続ける（guarded）
async function walk(bot, guard, token, goal) {
  const go = (movements) => guarded(guard, token, () => {
    bot.pathfinder.setMovements(movements(bot));
    return bot.pathfinder.goto(goal());
  });
  try {
    return await go(carefulMovements);
  } catch (err) {
    if (token.cancelled || !PATH_ERRORS.test(`${err?.name} ${err?.message}`)) throw err;
    return await go(escapeMovements);
  }
}

const TOSS_RANGE = 3;      // 渡すときに近づく距離

const SKILL_RUN = {
  async follow(bot, args, token, { owner, guard }) {
    const target = playerEntity(bot, args, owner);
    const follow = () => {
      bot.pathfinder.setMovements(carefulMovements(bot));
      bot.pathfinder.setGoal(new goals.GoalFollow(target, FOLLOW_RANGE), true);
    };
    await guard?.idle();   // 守っている最中なら、終わってからついていく（守りの行き先を上書きしない）
    if (token.cancelled) return;
    follow();
    // 止めるまで続く。相手が見えなくなったら終える。守り終えたら、またついていく。
    // 離れたまま動けなければ（高い木の上など）、自然のブロックを掘ってよい歩き方に替える。追いついたら戻す
    let generation = guard?.generation;
    let escaping = false;
    let mark = { at: Date.now(), pos: bot.entity.position.clone() };
    while (!token.cancelled) {
      await new Promise((r) => setTimeout(r, 500));
      if (token.cancelled) break;
      if (guard?.active) continue;
      if (!bot.entities[target.id]) throw new Failed('player_not_visible');
      if (guard && guard.generation !== generation) {
        generation = guard.generation;
        follow();
      }
      const far = target.position.distanceTo(bot.entity.position) > FOLLOW_RANGE + 4;
      if (!far || bot.entity.position.distanceTo(mark.pos) > STUCK_MOVE) {
        mark = { at: Date.now(), pos: bot.entity.position.clone() };
        if (!far && escaping) {
          escaping = false;
          follow();
        }
      } else if (!escaping && Date.now() - mark.at > STUCK_MS) {
        escaping = true;
        bot.pathfinder.setMovements(escapeMovements(bot));
        bot.pathfinder.setGoal(new goals.GoalFollow(target, FOLLOW_RANGE), true);
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
    const startY = bot.entity.position.y;
    let dug = 0;
    for (let i = 0; i < (args.depth ?? DIG_LIMIT) && !token.cancelled; i++) {
      if (guard?.active) await guard.idle();
      if (token.cancelled) break;
      const feet = bot.entity.position.floored();
      const below = bot.blockAt(feet.offset(0, -1, 0));
      if (!below) break;
      if (below.boundingBox === 'empty') {   // 落ちている途中
        await bot.waitForTicks(5);
        continue;
      }
      if (args.depth === undefined && !TREE.test(below.name)) break;   // 地面に着いた
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

  async collect(bot, args, token, { guard }) {
    const block = bot.registry.blocksByName[args.block];
    if (!block) throw new Failed('unknown_block');
    const before = counts(bot);
    let got = {};
    // 掘れない（道具が無い・掘ると危ない）ブロックは、collectblock が黙って飛ばす。同じ場所を何度も選ばないよう、試した場所を覚える
    const tried = new Set();
    let unreachable = 0;   // 道が見つからなかったブロックの数
    while (!token.cancelled && total(got) < args.count && tried.size < args.count * TRIES_PER_ITEM) {
      const pos = bot.findBlocks({ matching: block.id, maxDistance: SEARCH_DISTANCE, count: FIND_COUNT })
        .find((p) => !tried.has(p.toString()));
      if (!pos) break;
      tried.add(pos.toString());
      const target = bot.blockAt(pos);
      if (target) {
        try {
          await guarded(guard, token, () => {
            bot.collectBlock.movements = diggingMovements(bot);   // 守る係が歩き方を変えたあとでも、掘れるように戻す
            return bot.collectBlock.collect(target);
          });
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
};
