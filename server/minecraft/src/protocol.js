// 会話サーバーと体のあいだの決まり（JSON、v:1）。docs/games/minecraft/minecraft-design-ja.md の 4.2。
// 受けた命令は、ここで形を確かめてから動かす。一覧に無い技・形の違う引数は動かさない（任意のコードは実行しない）。

export const VERSION = 1;
const NAME = /^[A-Za-z0-9_]{1,16}$/;        // マイクラのプレイヤー名
const BLOCK = /^[a-z0-9_]{1,64}$/;           // ブロック・持ち物の名前（oak_log など）
const CHAT_CHARS = 256;                      // マイクラのチャットの上限
const TELL_CHARS = 2000;                     // オーナーの言葉を作業へ渡す上限（作業の依頼文と同じ）
const COLLECT_MAX = 64;
const CRAFT_MAX = 64;
const DIG_MAX = 32;
const GIVE_MAX = 64 * 36;   // 持ち物の欄すべて
const COORD_MAX = 30_000_000;

// 技と、その引数の確かめ方。返すのは整えた引数か、だめな理由
export const SKILLS = {
  pursue: a => Object.keys(a).every(k=>['request','goal_id'].includes(k))
    && typeof a.request==='string' && a.request.trim().length>0 && a.request.length<=2000
    && typeof a.goal_id==='string' && /^[a-f0-9-]{36}$/.test(a.goal_id)
    ? {args:{request:a.request,goal_id:a.goal_id}} : {error:'bad_args'},
  edit_region: a => onlyPlan(a) ? {args:{plan_id:a.plan_id,budget_ms:a.budget_ms}} : {error:'bad_args'},
  pointed_action: a => typeof a.selection_id==='string' && /^[a-f0-9-]{36}$/.test(a.selection_id)
    && ['move','recover'].includes(a.action)
    ? {args:{selection_id:a.selection_id,action:a.action}} : {error:'bad_args'},
  // ついていく（止めるまで続く）。player を省けば持ち主
  follow: (a) => player(a),
  // そばまで来る
  come: (a) => player(a),
  // 場所へ行く：{x, z} か {x, y, z}、または {player}
  go_to: (a) => {
    if (a.player !== undefined) return player(a);
    const x = coord(a.x), z = coord(a.z);
    if (x === null || z === null) return { error: 'bad_args' };
    if (a.y === undefined) return { args: { x, z } };
    const y = coord(a.y);
    return y === null ? { error: 'bad_args' } : { args: { x, y, z } };
  },
  // 近くのブロックを掘って集める。block はブロックの ID か、flower・log・dirt・coal のような呼び名（names.js）
  collect: (a) => {
    if (typeof a.block !== 'string' || !BLOCK.test(a.block)) return { error: 'bad_args' };
    const count = a.count === undefined ? 1 : a.count;
    if (!Number.isInteger(count) || count < 1 || count > COLLECT_MAX) return { error: 'bad_args' };
    return { args: { block: a.block, count } };
  },
  // 見える所に無いブロックを探す。how：walk（歩いて見回す）・dig（階段状に掘り下げる）・auto（体が選ぶ）。max は dig の段の上限
  find: (a) => {
    if (typeof a.block !== 'string' || !BLOCK.test(a.block)) return { error: 'bad_args' };
    const how = a.how === undefined ? 'auto' : a.how;
    if (!['walk', 'dig', 'auto'].includes(how)) return { error: 'bad_args' };
    if (a.max !== undefined && (!Number.isInteger(a.max) || a.max < 1 || a.max > 48)) return { error: 'bad_args' };
    return { args: { block: a.block, how, ...(a.max !== undefined ? { max: a.max } : {}) } };
  },
  // 足元を depth ブロック掘って降りる（自然のブロックだけ掘る）
  dig_down: (a) => {
    return Number.isInteger(a.depth) && a.depth >= 1 && a.depth <= DIG_MAX ? { args: { depth: a.depth } } : { error: 'bad_args' };
  },
  // 持ち物から物を作る（板・棒・作業台・ツルハシなど）。count は作りたい数
  craft: (a) => {
    if (typeof a.item !== 'string' || !BLOCK.test(a.item)) return { error: 'bad_args' };
    const count = a.count === undefined ? 1 : a.count;
    if (!Number.isInteger(count) || count < 1 || count > CRAFT_MAX) return { error: 'bad_args' };
    return { args: { item: a.item, count } };
  },
  // 持ち物を渡す（そばへ行って投げる）。player を省けば持ち主。count を省けば持っている分すべて
  give: (a) => {
    if (typeof a.item !== 'string' || !BLOCK.test(a.item)) return { error: 'bad_args' };
    if (a.count !== undefined && (!Number.isInteger(a.count) || a.count < 1 || a.count > GIVE_MAX)) return { error: 'bad_args' };
    const p = player(a);
    if (p.error) return p;
    return { args: { ...p.args, item: a.item, ...(a.count !== undefined ? { count: a.count } : {}) } };
  },
};

function onlyPlan(a) {
  return Object.keys(a).every(k=>['plan_id','budget_ms'].includes(k)) && typeof a.plan_id==='string'
    && /^[a-f0-9-]{36}$/.test(a.plan_id) && Number.isFinite(a.budget_ms) && a.budget_ms>0 && a.budget_ms<=120000;
}

function player(a) {
  if (a.player === undefined) return { args: {} };
  return typeof a.player === 'string' && NAME.test(a.player) ? { args: { player: a.player } } : { error: 'bad_args' };
}

function coord(v) {
  return typeof v === 'number' && Number.isFinite(v) && Math.abs(v) <= COORD_MAX ? v : null;
}

// 受けた文字列を命令にする。{cmd} か {error, id}
export function parseCommand(raw) {
  let m;
  try {
    m = JSON.parse(raw);
  } catch {
    return { error: 'bad_json' };
  }
  if (m === null || typeof m !== 'object' || Array.isArray(m)) return { error: 'bad_json' };
  if (m.v !== VERSION) return { error: 'bad_version' };
  const id = Number.isInteger(m.id) ? m.id : undefined;
  switch (m.type) {
    case 'do': {
      if (id === undefined) return { error: 'bad_id' };
      const check = Object.hasOwn(SKILLS, m.skill) ? SKILLS[m.skill] : null;
      if (check === null) return { error: 'unknown_skill', id };
      const args = m.args === undefined ? {} : m.args;
      if (args === null || typeof args !== 'object' || Array.isArray(args)) return { error: 'bad_args', id };
      const r = check(args);
      if (m.request_id !== undefined && (typeof m.request_id !== 'string' || m.request_id.length > 160)) return { error: 'bad_args', id };
      return r.error ? { error: r.error, id } : { cmd: { type: 'do', id, skill: m.skill, args: r.args,
        ...(m.request_id ? { request_id: m.request_id } : {}) } };
    }
    case 'stop':
      if (m.task !== undefined && !Number.isInteger(m.task)) return { error: 'bad_id' };
      return { cmd: { type: 'stop', ...(m.task !== undefined ? { task: m.task } : {}) } };
    // The owner's words to a running command (a work), heard by the body's model as the owner speaking.
    case 'tell': {
      if (!Number.isInteger(m.task)) return { error: 'bad_id' };
      if (typeof m.text !== 'string' || !m.text.trim() || m.text.length > TELL_CHARS) return { error: 'bad_args' };
      return { cmd: { type: 'tell', task: m.task, text: m.text.trim() } };
    }
    case 'chat': {
      if (typeof m.text !== 'string' || !m.text.trim()) return { error: 'bad_args' };
      // 改行や制御文字はコマンドの区切りにならないよう、空白にする。先頭の / はコマンドになるので送らない
      const text = m.text.replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, CHAT_CHARS);
      if (text.startsWith('/')) return { error: 'bad_args' };
      return { cmd: { type: 'chat', text } };
    }
    case 'state':
      return { cmd: { type: 'state' } };
    // 今の景色を 1 枚撮る（eye.js）。返事は seen（JPEG を base64）か error
    case 'look':
      if (id === undefined) return { error: 'bad_id' };
      return { cmd: { type: 'look', id } };
    default:
      return { error: 'unknown_type' };
  }
}

export function message(type, fields = {}) {
  return JSON.stringify({ v: VERSION, type, ...fields });
}
