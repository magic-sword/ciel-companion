// 会話サーバーと体のあいだの決まり（JSON、v:1）。docs/minecraft-design-ja.md の 4.2。
// 受けた命令は、ここで形を確かめてから動かす。一覧に無い技・形の違う引数は動かさない（任意のコードは実行しない）。

export const VERSION = 1;
const NAME = /^[A-Za-z0-9_]{1,16}$/;        // マイクラのプレイヤー名
const BLOCK = /^[a-z0-9_]{1,64}$/;           // ブロック・持ち物の名前（oak_log など）
const CHAT_CHARS = 256;                      // マイクラのチャットの上限
const COLLECT_MAX = 64;
const DIG_MAX = 32;
const GIVE_MAX = 64 * 36;   // 持ち物の欄すべて
const COORD_MAX = 30_000_000;

// 技と、その引数の確かめ方。返すのは整えた引数か、だめな理由
export const SKILLS = {
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
  // 近くのブロックを掘って集める
  collect: (a) => {
    if (typeof a.block !== 'string' || !BLOCK.test(a.block)) return { error: 'bad_args' };
    const count = a.count === undefined ? 1 : a.count;
    if (!Number.isInteger(count) || count < 1 || count > COLLECT_MAX) return { error: 'bad_args' };
    return { args: { block: a.block, count } };
  },
  // 足元を掘って降りる。depth を省けば、木の上から地面まで（自然のブロックだけ掘る）
  dig_down: (a) => {
    if (a.depth === undefined) return { args: {} };
    return Number.isInteger(a.depth) && a.depth >= 1 && a.depth <= DIG_MAX ? { args: { depth: a.depth } } : { error: 'bad_args' };
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
      return r.error ? { error: r.error, id } : { cmd: { type: 'do', id, skill: m.skill, args: r.args } };
    }
    case 'stop':
      return { cmd: { type: 'stop' } };
    case 'chat': {
      if (typeof m.text !== 'string' || !m.text.trim()) return { error: 'bad_args' };
      // 改行や制御文字はコマンドの区切りにならないよう、空白にする。先頭の / はコマンドになるので送らない
      const text = m.text.replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, CHAT_CHARS);
      if (text.startsWith('/')) return { error: 'bad_args' };
      return { cmd: { type: 'chat', text } };
    }
    case 'state':
      return { cmd: { type: 'state' } };
    default:
      return { error: 'unknown_type' };
  }
}

export function message(type, fields = {}) {
  return JSON.stringify({ v: VERSION, type, ...fields });
}
