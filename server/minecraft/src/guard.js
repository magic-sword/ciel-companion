// 身を守る係：会話を待たずに、体が自分で敵に反撃し、危ないときは逃げる。docs/minecraft-design-ja.md の 4.2。
// 立って待っているあいだにクモに 3 回倒された（2026-11-05、自宅サーバー）ので足した。
// - 守っているあいだは、経路探索をこの係が使う。技（skills.js）は止めずに待たせ、守り終えたら続ける（guarded）。
// - どの敵とどうするか（pickThreat）は、モデルを使わずに決める。
import pathfinderPkg from 'mineflayer-pathfinder';

import { carefulMovements } from './movements.js';
import { cancelledWait } from './body-command.js';

const { goals } = pathfinderPkg;
const TICK_MS = 250;
const NOTICE = 16;        // 敵を見る距離
const FIGHT = 6;          // この距離まで来た敵に反撃する
const GUARD_OWNER = 6;    // 持ち主にこの距離まで来た敵にも向かう
const REACH = 3;          // 叩ける距離
const HIT_EVERY_MS = 650; // 叩く間隔（剣の溜めに合わせる）
const CREEPER_FLEE = 6;   // クリーパーは叩かずに離れる
const LOW_HEALTH = 6;     // 体力がこれ以下なら戦わずに逃げる
const CROWD = 3;          // 近くにこの数の敵がいたら、戦わずに逃げる（夜、囲まれて持ち主と一緒に倒された。2026-11-05）
const FLEE_DISTANCE = 12;
// 手を出さなければ襲ってこないもの。こちらから叩くと群れで来る
const LEAVE_ALONE = new Set(['enderman', 'piglin', 'zombified_piglin', 'piglin_brute']);
const WEAPONS = ['netherite_sword', 'diamond_sword', 'iron_sword', 'stone_sword', 'golden_sword', 'wooden_sword',
  'netherite_axe', 'diamond_axe', 'iron_axe', 'stone_axe', 'golden_axe', 'wooden_axe'];

// 今どうするか：{action: 'fight'|'flee', target, to?} か null
export function pickThreat(bot, ownerName) {
  if (!bot?.entity) return null;
  const me = bot.entity.position;
  const owner = ownerName ? bot.players[ownerName]?.entity ?? null : null;
  const hostiles = Object.values(bot.entities)
    .filter((e) => e.type === 'hostile' && e.isValid !== false && !LEAVE_ALONE.has(e.name) && e.position)
    .map((e) => ({ e, d: e.position.distanceTo(me) }))
    .filter(({ d }) => d <= NOTICE)
    .sort((a, b) => a.d - b.d);
  if (!hostiles.length) return null;
  const creeper = hostiles.find(({ e, d }) => e.name === 'creeper' && d <= CREEPER_FLEE);
  if (creeper) return { action: 'flee', target: creeper.e };
  const nearest = hostiles[0];
  if (bot.health <= LOW_HEALTH && nearest.d <= FIGHT + 2) return { action: 'flee', target: nearest.e, to: owner };
  const fighting = hostiles.filter(({ e }) => e.name !== 'creeper');
  if (fighting.filter(({ d }) => d <= FIGHT).length >= CROWD) return { action: 'flee', target: nearest.e, to: owner };
  const close = fighting.find(({ d }) => d <= FIGHT);
  if (close) return { action: 'fight', target: close.e };
  if (owner) {
    const nearOwner = fighting.find(({ e }) => e.position.distanceTo(owner.position) <= GUARD_OWNER);
    if (nearOwner) return { action: 'fight', target: nearOwner.e };
  }
  return null;
}

export class Guard {
  constructor(report, owner) {
    this.report = report;
    this.owner = owner;
    this.bot = null;
    this.active = false;
    this.generation = 0;     // 守り始めるたびに増える（技が、守りに割り込まれたかを見分ける）
    this._plan = null;       // 今の {action, target}
    this._lastHit = 0;
    this._hits = 0;          // 今回の守りで叩いた回数・倒した数（ログ用）
    this._kills = 0;
    this._waiters = [];
    this._timer = null;
    this.body = null;
    this._taking = false;
    this._operations = new Set();
  }

  attach(bot) {
    this.detach();
    this.bot = bot;
    if (bot) this._timer = setInterval(() => this._tick(), TICK_MS);
  }

  detach() {
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
    this._end(false);
    this.bot = null;
  }

  // 守り終えるのを待つ
  idle(token) {
    if (!this.active) return Promise.resolve();
    let resolve;
    const wait = new Promise(r => { resolve = r; this._waiters.push(r); });
    return cancelledWait(token, wait).finally(() => {
      this._waiters = this._waiters.filter(r => r !== resolve);
    });
  }

  _tick() {
    if (this._taking || this._ending) return;
    const bot = this.bot;
    if (!bot?.entity || bot.health <= 0) return this._end(false);
    const was = this._plan;
    if (was?.action === 'fight' && was.target.isValid === false) {
      this._kills += 1;
      this.report('event', { kind: 'defeated', name: was.target.name });
    }
    // 逃げ始めたら、FLEE_DISTANCE まで離れるまで逃げ続ける。6 ブロックでやめると、クリーパーが近づくたびに
    // 「逃げる・安全」を何十回も繰り返し、最後は爆発で 13.8 減った（2026-11-05）
    const fleeing = was?.action === 'flee' && was.target.isValid !== false
      && was.target.position.distanceTo(bot.entity.position) < FLEE_DISTANCE;
    const plan = fleeing ? was : pickThreat(bot, this.owner);
    if (!plan) return this._end(true);
    if (!this.active) {
      this.active = true;
      this.generation += 1;
      this._hits = 0;
      this._kills = 0;
      bot.collectBlock?.cancelTask().catch(() => {});
      bot.pathfinder.setGoal(null);
      bot.stopDigging?.();
      if (this.body) {
        this._taking = true;
        const attached = bot;
        void this.body.defense(true).finally(() => {
          this._taking = false;
          if (this.bot === attached && this.active) {
            bot.pathfinder.setMovements(carefulMovements(bot));
            this._tick();
          }
        });
        return;
      }
      bot.pathfinder.setMovements(carefulMovements(bot));
    }
    const same = this._plan && this._plan.action === plan.action && this._plan.target === plan.target;
    if (!same) {
      this._plan = plan;
      if (plan.action === 'fight') {
        this._equipWeapon();
        bot.pathfinder.setGoal(new goals.GoalFollow(plan.target, 1.5), true);
        this.report('event', { kind: 'defend', name: plan.target.name });
      } else if (plan.to) {
        bot.pathfinder.setGoal(new goals.GoalFollow(plan.to, 1), true);
        this.report('event', { kind: 'flee', from: plan.target.name, to: 'owner', health: Math.round(bot.health) });
      } else {
        bot.pathfinder.setGoal(new goals.GoalInvert(new goals.GoalFollow(plan.target, FLEE_DISTANCE)), true);
        this.report('event', { kind: 'flee', from: plan.target.name, to: 'away', health: Math.round(bot.health) });
      }
    }
    if (plan.action === 'fight') this._hit(plan.target);
  }

  _hit(target) {
    const bot = this.bot;
    const now = Date.now();
    if (now - this._lastHit < HIT_EVERY_MS) return;
    if (target.position.distanceTo(bot.entity.position) > REACH) return;
    this._lastHit = now;
    this._hits += 1;
    this._track(bot.lookAt(target.position.offset(0, (target.height ?? 1.6) * 0.8, 0), true)
      .then(() => { if (this.active && !this._ending && this.bot === bot) bot.attack(target); }));
  }

  _equipWeapon() {
    const bot = this.bot;
    if (WEAPONS.includes(bot.heldItem?.name)) return;
    const items = bot.inventory.items();
    const best = WEAPONS.map((n) => items.find((i) => i.name === n)).find(Boolean);
    if (best) this._track(bot.equip(best, 'hand'));
  }

  _track(promise) {
    const p = Promise.resolve(promise).catch(() => {});
    this._operations.add(p);
    void p.finally(() => this._operations.delete(p));
  }

  _end(safe) {
    if (!this.active || this._ending) return;
    if (this._operations.size) {
      this._ending = true;
      void Promise.allSettled([...this._operations]).then(() => { this._ending = false; this._end(safe); });
      return;
    }
    this.active = false;
    this._plan = null;
    console.log(new Date().toISOString(), `守り終えた hits=${this._hits} kills=${this._kills} health=${Math.round(this.bot?.health ?? 0)}`);
    if (this.bot?.pathfinder) this.bot.pathfinder.setGoal(null);
    if (safe) this.report('event', { kind: 'safe' });
    for (const r of this._waiters.splice(0)) r();
    void this.body?.defense(false);
  }
}

// 技の動き（経路探索・ブロック集め）を、守りに割り込まれても続ける。止められたら（token.cancelled）やめる
export async function guarded(guard, token, fn) {
  for (;;) {
    if (guard?.active) await guard.idle(token);
    if (token.cancelled) return undefined;
    const generation = guard?.generation;
    try {
      return await fn();
    } catch (err) {
      if (token.cancelled) return undefined;
      if (!guard || (guard.generation === generation && !guard.active)) throw err;
      // 守りに割り込まれた。守り終えてからやり直す
    }
  }
}
