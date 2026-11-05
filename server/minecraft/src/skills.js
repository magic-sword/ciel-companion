// 体の技。1 つずつ決まった処理で書き、その場でコードを書かせない。docs/minecraft-design-ja.md の 4.2。
// 技は一度に 1 つ。新しい技を受けたら、今の技を止めてから始める。終わったら（止めたときも）必ず done を 1 回送る。
// 身を守る係（guard.js）が経路探索を使っているあいだは、技は待ち、守り終えたら続ける（guarded）。
import pathfinderPkg from 'mineflayer-pathfinder';

import { guarded } from './guard.js';
import { carefulMovements, diggingMovements } from './movements.js';

const { goals } = pathfinderPkg;
const FOLLOW_RANGE = 2;     // ついていくときに空ける距離
const COME_RANGE = 2;
const SEARCH_DISTANCE = 48; // 集めるブロックを探す距離
const FIND_COUNT = 64;
const TRIES_PER_ITEM = 3;   // 1 個あたりに試すブロックの数（掘れないものが続いたらあきらめる）

class Failed extends Error {}

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
      else if (err instanceof Failed) result = { ok: false, reason: err.message };
      else {
        console.warn(`技が失敗した skill=${skill} error=${err?.name ?? err}`, err?.stack?.split('\n').slice(0, 4).join(' | ') ?? '');
        result = { ok: false, reason: 'error' };
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
    // 止めるまで続く。相手が見えなくなったら終える。守り終えたら、またついていく
    let generation = guard?.generation;
    while (!token.cancelled) {
      await new Promise((r) => setTimeout(r, 500));
      if (token.cancelled) break;
      if (guard?.active) continue;
      if (!bot.entities[target.id]) throw new Failed('player_not_visible');
      if (guard && guard.generation !== generation) {
        generation = guard.generation;
        follow();
      }
    }
  },

  async come(bot, args, token, { owner, guard }) {
    await guarded(guard, token, () => {
      const p = playerEntity(bot, args, owner).position;
      bot.pathfinder.setMovements(carefulMovements(bot));
      return bot.pathfinder.goto(new goals.GoalNear(p.x, p.y, p.z, COME_RANGE));
    });
  },

  async go_to(bot, args, token, { owner, guard }) {
    await guarded(guard, token, () => {
      bot.pathfinder.setMovements(carefulMovements(bot));
      if (args.x === undefined) {
        const p = playerEntity(bot, args, owner).position;
        return bot.pathfinder.goto(new goals.GoalNear(p.x, p.y, p.z, COME_RANGE));
      }
      if (args.y === undefined) return bot.pathfinder.goto(new goals.GoalXZ(args.x, args.z));
      return bot.pathfinder.goto(new goals.GoalNear(args.x, args.y, args.z, 1));
    });
  },

  async collect(bot, args, token, { guard }) {
    const block = bot.registry.blocksByName[args.block];
    if (!block) throw new Failed('unknown_block');
    const before = counts(bot);
    let got = {};
    // 掘れない（道具が無い・掘ると危ない）ブロックは、collectblock が黙って飛ばす。同じ場所を何度も選ばないよう、試した場所を覚える
    const tried = new Set();
    while (!token.cancelled && total(got) < args.count && tried.size < args.count * TRIES_PER_ITEM) {
      const pos = bot.findBlocks({ matching: block.id, maxDistance: SEARCH_DISTANCE, count: FIND_COUNT })
        .find((p) => !tried.has(p.toString()));
      if (!pos) break;
      tried.add(pos.toString());
      const target = bot.blockAt(pos);
      if (target) {
        await guarded(guard, token, () => {
          bot.collectBlock.movements = diggingMovements(bot);   // 守る係が歩き方を変えたあとでも、掘れるように戻す
          return bot.collectBlock.collect(target);
        });
      }
      got = gained(before, counts(bot));
    }
    if (!token.cancelled && total(got) === 0) throw new Failed(tried.size ? 'cannot_harvest' : 'not_found');
    return { gained: got };
  },
};
