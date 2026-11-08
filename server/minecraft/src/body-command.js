// 体の作業の所有権。終了と後片付けが済むまで、次の作業へ渡さない。
import { randomUUID } from 'node:crypto';

export function cancelledWait(token, promise) {
  if (!token?.signal) return promise;
  if (token.cancelled) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const abort = () => { cleanup(); resolve(); };
    const cleanup = () => token.signal.removeEventListener('abort', abort);
    token.signal.addEventListener('abort', abort, { once: true });
    Promise.resolve(promise).then(value => { cleanup(); resolve(value); }, err => { cleanup(); reject(err); });
  });
}

export class BodyCommands {
  constructor({ report, run, prepare = () => null, available = () => true, halt = () => {}, stopMs = 5000 }) {
    Object.assign(this, { report, run, prepare, available, halt, stopMs });
    this.session = randomUUID();
    this.revision = 0;
    this.current = null;
    this.pending = null;
    this.last = null;
    this.blocked = false;
    this.maintenance = null;
    this.defending = false;
    this._pumping = false;
    this._finished = new Map();
    this._highestIds = new Map();
  }

  snapshot() {
    const view = c => c ? { id: c.id, skill: c.skill, args: c.args, phase: c.phase,
      since: c.since, reason: c.reason ?? '', request_id: c.request_id ?? '' } : null;
    return { version: 1, session: this.session, revision: this.revision,
      current: view(this.current), pending: view(this.pending), last: this.last,
      owner: this.defending ? 'defending' : this.maintenance ? 'eating' : '',
      owner_since: this.defending ? this._defenseAt : this._mealAt, blocked: this.blocked };
  }

  changed() {
    this.revision++;
    this.report('body', this.snapshot());
  }

  phase(c, phase, reason = '') {
    c.phase = phase; c.reason = reason; c.since = Date.now();
    this.changed();
  }

  start(command) {
    const scope = command.scope ?? '';
    const key = `${scope}:${command.id}`;
    // 再送は同じID。同じ題の別依頼は置換として受ける。
    const known = [this.current, this.pending].find(c => c?.id === command.id && (c.scope ?? '') === scope);
    if (known) return known.done;
    if (this._finished.has(key)) {
      this.report('done', { id: command.id, command_scope: scope, ...this._finished.get(key) });
      return Promise.resolve();
    }
    if (command.id <= (this._highestIds.get(scope) ?? -1)) {
      this.report('error', { id: command.id, reason: 'replaced' });
      return Promise.resolve();
    }
    if (this.blocked) {
      this.report('error', { id: command.id, reason: 'stop_timeout' });
      return Promise.resolve();
    }
    const controller = new AbortController();
    this._highestIds.set(scope, command.id);
    if (this._highestIds.size > 512) this._highestIds.delete(this._highestIds.keys().next().value);
    const c = { ...command, phase: 'accepted', since: Date.now(), operations: new Set(),
      token: { cancelled: false, reason: null, signal: controller.signal }, controller };
    c.done = new Promise(resolve => { c.resolve = resolve; });
    if (this.pending) this._finish(this.pending, { ok: false, reason: 'replaced' });
    this.pending = c;
    this.report('accepted', { id: c.id, command_scope: scope });
    if (this.current) this._stop(this.current, 'replaced');
    this.changed();
    void this._pump();
    return c.done;
  }

  stop(reason, id, scope) {
    const matches = c => c && (id === undefined || c.id === id) && (scope === undefined || (c.scope ?? '') === scope);
    if (matches(this.pending)) {
      const c = this.pending;
      this.pending = null;
      this._finish(c, { ok: false, reason });
    }
    if (matches(this.current)) return this._stop(this.current, reason);
    this.changed();
    return Promise.resolve();
  }

  _stop(c, reason) {
    if (!c.token.cancelled) {
      c.token.cancelled = true; c.token.reason = reason; c.controller.abort();
      this.phase(c, 'stopping', reason);
      // haltも所有権の一部。失敗・未完了なら、次を重ねない。
      c.cleanup = Promise.resolve().then(() => this.halt(c)).catch(() => { c.cleanupFailed = true; });
      c.timer = setTimeout(() => {
        this.blocked = true;
        this.phase(c, 'stopping', 'stop_timeout');
        if (this.pending) {
          const pending = this.pending; this.pending = null;
          this._finish(pending, { ok: false, reason: 'stop_timeout' });
        }
      }, this.stopMs);
      c.timer.unref?.();
    }
    return c.done;
  }

  async _pump() {
    if (this._pumping || this.maintenance) return;
    this._pumping = true;
    try {
      while (this.pending && !this.blocked) {
        const c = this.pending; this.pending = null; this.current = c;
        let result;
        try {
          if (this.defending) {
            this.phase(c, 'waiting', 'defending');
            await this.waitForDefense(c.token);
          }
          if (!c.token.cancelled) {
            this.phase(c, 'preparing');
            const refused = this.available() ? this.prepare(c) : { reason: 'not_spawned' };
            if (refused) result = { ok: false, ...refused };
            else {
              this.phase(c, 'running');
              this.report('started', { id: c.id, skill: c.skill, command_scope: c.scope ?? '' });
              result = await this.run(c);
            }
          }
        } catch (err) {
          result = { ok: false, reason: 'error', detail: String(err?.message ?? err).slice(0, 120) };
        }
        if (c.cleanup) await c.cleanup;
        clearTimeout(c.timer);
        if (c.cleanupFailed) {
          this.blocked = true;
          if (this.pending) {
            const pending = this.pending; this.pending = null;
            this._finish(pending, { ok: false, reason: 'stop_timeout' });
          }
        }
        else this.blocked = false;
        if (c.token.cancelled) result = { ...result, ok: c.skill === 'follow' && c.token.reason === 'stopped', reason: c.token.reason };
        this.current = null;
        this._finish(c, result ?? { ok: false, reason: 'stopped' });
      }
    } finally { this._pumping = false; }
  }

  _finish(c, result) {
    this.last = { id: c.id, skill: c.skill, args: c.args,
      phase: ['stopped', 'replaced', 'unlinked', 'disconnected', 'died'].includes(result.reason) ? 'cancelled'
        : result.ok ? 'succeeded' : 'failed',
    since: Date.now(), result };
    this.report('done', { id: c.id, command_scope: c.scope ?? '', ...result });
    this._finished.set(`${c.scope ?? ''}:${c.id}`, result);
    if (this._finished.size > 512) this._finished.delete(this._finished.keys().next().value);
    this.changed();
    c.resolve();
  }

  // 防御は新たな通常操作を止め、発行済みの操作の終了を待ってから所有権を取る。
  async defense(on) {
    this.defending = on;
    const c = this.current;
    if (on) {
      this._defenseAt = Date.now();
      this._defenseDone = new Promise(resolve => { this._releaseDefense = resolve; });
      if (c && !c.token.cancelled) this.phase(c, 'waiting', 'defending');
      await Promise.allSettled([...(c?.operations ?? []), ...(this.maintenance ? [this.maintenance] : [])]);
    } else {
      this._releaseDefense?.(); this._releaseDefense = null;
      if (c && !c.token.cancelled) this.phase(c, 'running');
    }
    this.changed();
  }

  waitForDefense(token) { return cancelledWait(token, this._defenseDone ?? Promise.resolve()); }

  // 食事は空いている体だけ使う。受付中の命令を追い越さない。
  async maintain(fn) {
    if (this.current || this.pending || this.maintenance || this.defending || this.blocked) return false;
    this.maintenance = Promise.resolve().then(fn);
    this._mealAt = Date.now();
    this.changed();
    try { await this.maintenance; return true; }
    finally { this.maintenance = null; this.changed(); void this._pump(); }
  }
}

// 技が発行する非同期の体操作を数える。防御中・取消後は次の操作を発行しない。
export function commandBot(bot, command, owner) {
  const asyncMethods = new Set(['equip', 'dig', 'craft', 'placeBlock', 'toss', 'lookAt', 'consume', 'goto', 'collect', 'equipForBlock']);
  const wrap = target => new Proxy(target, { get(obj, name) {
    const value = Reflect.get(obj, name, obj);
    if (['pathfinder', 'collectBlock', 'tool'].includes(name) && value) return wrap(value);
    if (typeof value !== 'function') return value;
    if (!asyncMethods.has(name)) return value.bind(obj);
    return async (...args) => {
      if (owner.defending) await owner.waitForDefense(command.token);
      if (command.token.cancelled) throw new Error('cancelled');
      const operation = Promise.resolve().then(() => {
        if (command.token.cancelled) throw new Error('cancelled');
        return value.apply(obj, args);
      });
      command.operations.add(operation);
      try { return await operation; }
      finally { command.operations.delete(operation); }
    };
  } });
  return wrap(bot);
}
