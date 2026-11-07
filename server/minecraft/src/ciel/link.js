// 体と MCP のあいだのつなぎ役。docs/game-environment-mcp-design-ja.md の 4 章。
// - 体（main.js）から見ると、WebSocket の会話と同じ「つながっている相手」（readyState・send）。体が送る機械の言葉を受け、
//   シエル向けの言葉（words.js）にして MCP の側へ渡す。体へは、WebSocket と同じ JSON の命令を command で送る
//   （形の確かめは protocol.js のまま。任意のコードは実行しない）。
// - 以前は会話サーバーの minecraft.py の Body がしていたことを、ここでする。
import { doneFor, eventFor, fingerprint, refused, stateText, title } from './words.js';

const START_TIMEOUT_MS = 3000;    // 技を頼んでから「始めた」が返るまでの上限
const LOOK_TIMEOUT_MS = 25000;    // 景色を頼んでから絵が返るまでの上限（初めはブラウザを開いて描き終えるまで 10 秒ほど）
const PLAN_TIMEOUT_MS = 5000;     // 目的の計画（plan → planned）を待つ上限
export const STEP_TIMEOUT_MS = 900000;   // 目的の段（技 1 つ）が終わるまで待つ上限

function timeout(promise, ms, onTimeout) {
  let t;
  return Promise.race([promise, new Promise((resolve) => { t = setTimeout(() => resolve(onTimeout()), ms); })])
    .finally(() => clearTimeout(t));
}

export class CielLink {
  // command(raw)：体へ命令を送る（main.js）。notice(e)：シエルへの知らせ（mcp.js が MCP の知らせにする）。
  // changed()：様子が変わった（mcp.js が resources/updated を送る）
  constructor({ command, owner = null, notice = () => {}, changed = () => {} }) {
    this.command = command;
    this.owner = owner;
    this.notice = notice;
    this.changed = changed;
    this.readyState = 1;
    this.state = null;
    this._ids = 1;
    this._pending = new Map();   // id → 返事を待つ resolve（started・error・seen・planned）
    this._waiting = new Map();   // id → 目的の係が終わりを待つ resolve（知らせ・付箋は会話サーバーの目的の係が持つ）
    this._tasks = new Map();     // id → {title, skill}（頼まれた技。付箋の題）
    this._shown = '';
  }

  // ---- 体から（main.js の send） ----

  send(raw) {
    let m;
    try {
      m = JSON.parse(raw);
    } catch {
      return;
    }
    const kind = m.type;
    if (kind === 'hello' || kind === 'state') {
      this.state = kind === 'hello' ? m.state : m;
      if (kind === 'hello' && m.owner) this.owner = m.owner;
      this._maybeChanged();
    } else if (['started', 'error', 'seen', 'planned'].includes(kind)) {
      const r = this._pending.get(m.id);
      if (r) {
        this._pending.delete(m.id);
        r(m);
      }
    } else if (kind === 'done') {
      this._done(m);
    } else if (kind === 'event') {
      if (kind === 'event' && (m.kind === 'spawned' || m.kind === 'disconnected')) this._maybeChanged();
      const e = eventFor(m, this.owner);
      if (e) this.notice(e);
    }
  }

  _maybeChanged() {
    const shown = JSON.stringify([this.playing(), this.text(), fingerprint(this.state)]);
    if (shown !== this._shown) {
      this._shown = shown;
      this.changed();
    }
  }

  _done(m) {
    const task = this._tasks.get(m.id);
    this._tasks.delete(m.id);
    const waiting = this._waiting.get(m.id);
    if (waiting) {   // 目的の係が頼んだ技
      this._waiting.delete(m.id);
      waiting(m);
      return;
    }
    if (!task) return;
    const r = doneFor(m, task.title);
    const e = { kind: 'task_done', urgency: 'normal', key: null, task: m.id, ...r };
    if (!m.ok && m.reason === 'error') e.error = { where: `body.${task.skill}`, detail: String(m.detail ?? '') };
    this.notice(e);
  }

  // ---- 様子 ----

  playing() {
    return Boolean(this.state?.connected);
  }

  text() {
    return stateText(this.state, this.owner, true);
  }

  // ---- 頼む（mcp.js の道具から） ----

  _ask(msg, ms, onTimeout) {
    const id = this._ids++;
    const p = new Promise((resolve) => this._pending.set(id, resolve));
    this.command(JSON.stringify({ v: 1, id, ...msg }));
    return { id, answer: timeout(p, ms, () => { this._pending.delete(id); return onTimeout(); }) };
  }

  // 技を頼む。始めたか（started）を返す。終わったら task_done の知らせが届く
  async do(skill, args = {}) {
    const name = title(skill, args);
    if ([...this._tasks.values()].some((t) => t.title === name)) return { status: 'already_doing' };   // 同じ頼みは、もうしている
    const { id, answer } = this._ask({ type: 'do', skill, args }, START_TIMEOUT_MS, () => ({ type: 'timeout' }));
    this._tasks.set(id, { title: name, skill });
    const m = await answer;
    if (m.type === 'started') return { status: 'started', task: id, title: name };
    this._tasks.delete(id);
    return m.type === 'timeout' ? { status: 'no_answer' } : refused(m);
  }

  // 目的の係が頼む技：始めて、終わりまで待って、体の done（ok・reason・note）を返す。付箋も知らせも作らない
  async runSkill(skill, args) {
    const id = this._ids++;
    const done = new Promise((resolve) => this._waiting.set(id, resolve));
    const started = new Promise((resolve) => this._pending.set(id, resolve));
    this._tasks.set(id, { title: title(skill, args), skill });
    this.command(JSON.stringify({ v: 1, type: 'do', id, skill, args }));
    const s = await timeout(started, START_TIMEOUT_MS, () => { this._pending.delete(id); return { type: 'timeout' }; });
    if (s.type !== 'started') {
      this._waiting.delete(id);
      this._tasks.delete(id);
      if (s.type === 'timeout') return { ok: false, reason: 'no_answer' };
      const r = refused(s);
      return { ok: false, reason: r.reason, note: s.note ?? {}, why: r.why };
    }
    return timeout(done, STEP_TIMEOUT_MS, () => {
      this._waiting.delete(id);
      this.stop();
      return { ok: false, reason: 'error', detail: 'timeout' };
    });
  }

  // 目的（物を作る）の段の一覧を、体に決めてもらう（体の plan → planned）
  async plan(item, count) {
    const { answer } = this._ask({ type: 'plan', item, count }, PLAN_TIMEOUT_MS, () => ({ type: 'timeout' }));
    const m = await answer;
    if (m.type === 'planned') return { steps: m.steps ?? [], inventory: m.inventory ?? {} };
    return m.type === 'timeout' ? { error: 'no_answer' } : { error: m.reason ?? 'error', why: refused(m).why };
  }

  // 今の景色を 1 枚撮ってもらう
  async look() {
    const { answer } = this._ask({ type: 'look' }, LOOK_TIMEOUT_MS, () => ({ type: 'timeout' }));
    const m = await answer;
    if (m.type === 'seen') return { jpeg: m.jpeg, facing: m.facing };
    return m.type === 'timeout' ? { status: 'no_answer' } : refused(m);
  }

  stop() {
    this.command(JSON.stringify({ v: 1, type: 'stop' }));
    return { status: 'stopped' };
  }

  // 会話が離れた：待っているものを、切れた扱いで終える
  close() {
    this.readyState = 3;
    for (const r of this._pending.values()) r({ type: 'error', reason: 'unlinked' });
    this._pending.clear();
    for (const r of this._waiting.values()) r({ ok: false, reason: 'unlinked' });
    this._waiting.clear();
    for (const id of this._tasks.keys()) this.notice({ kind: 'task_done', urgency: 'normal', key: null, task: id,
      ...doneFor({ id, ok: false, reason: 'unlinked' }, this._tasks.get(id).title) });
    this._tasks.clear();
  }
}
