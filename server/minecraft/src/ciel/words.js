// シエル向けの言葉：体の機械の言葉（reason: 'needs_tool'・oak_log）を、シエルが話せる言葉に直す。
// docs/games/game-environment-mcp-design-ja.md の 4 章。以前は会話サーバーの minecraft.py が持っていた（会話サーバーはゲームを知らない形にした）。

// うまくいかなかった理由（体の done・error の reason）。（ ）の前が付箋の短いひとこと
export const WHY_FAILED = {
  stop_timeout: '前の作業の停止を確認できない（次の作業は開始していない）',
  player_not_visible: '相手が見えない（遠い・別の場所にいる）',
  player_search_timeout: '方向の手掛かりを頼りに探したが、時間内に相手を見つけられない（座標や集合場所を教えてほしい）',
  no_owner: '相手が分からない（持ち主のプレイヤー名が設定されていない）',
  not_found: '見える所に無い（今いる所から見えない・まだ見ていない。地中に埋まっている物は分からない）',
  cannot_harvest: '掘れない（その道具を持っていない）',
  needs_tool: '掘る道具が無い（素手では取れない）',
  unknown_block: 'そういう名前のブロックが無い',
  unknown_item: 'そういう名前の物が無い',
  cannot_craft: '作れない物（作り方が無い）',
  missing_materials: '材料が足りない',
  no_table: '作業台が要る（近くに無く、持ってもいない）',
  no_room: '作業台を置く場所が無い',
  no_path: 'そこまでの道が見つからない（遠い・高い・水や崖の向こう）',
  not_spawned: 'マイクラに入っていない',
  not_have: 'その物を持っていない',
  not_received: '投げたが相手が受け取らなかった（落ちた物は拾い直した）',
  cannot_dig: '掘れないブロックに当たった（建物に使うもの・素手では掘れないもの）',
  danger: '掘った先に溶岩か水があって危ない',
  died: '途中で倒れた',
  unlinked: '体から切れた',
  stopped: '止められた',
  replaced: 'ほかの頼みに替えた',
  mind_failed: '自分では進められなかった',
  no_answer: '体から返事が無い',
  disconnected: 'マイクラから出た',
  busy: 'ほかの会話が体を使っている',
  bad_args: '頼み方の形が違う',
  error: 'うまくいかなかった',
};
// 止めた・替えた・切れた：うまくいかなかったことにしない（言わない）
export const QUIET_REASONS = ['stopped', 'replaced', 'unlinked', 'disconnected'];
// うまくいかなかったときの次の手（道具の返事と知らせに添える）。心が「石を探してから」と言うだけで探す道具を呼ばなかった・
// 足りない物を集めずに同じ物を作り直した（2026-11-07）
export const NEXT_STEP = {
  missing_materials: '公開する能力をsubmit_game_taskで頼むと、ゲーム側が不足分を調達する',
  needs_tool: '公開する能力をsubmit_game_taskで頼むと、ゲーム側が必要な道具を用意する',
  not_found: 'minecraft_find_blocks で探せる（地中の物は how=dig、地面の上の物は how=walk）',
};
export const SKILL_NAMES = {
  follow: 'ついていく', come: 'そばへ行く', go_to: '場所へ行く', collect: '集める', give: '渡す',
  dig_down: '足元を掘って降りる', craft: '作る', find: '探す',
};
const FACING = {
  north: '北', northwest: '北西', west: '西', southwest: '南西', south: '南', southeast: '南東', east: '東', northeast: '北東',
};
const BIG_HURT = 4;     // 一度にこれだけ減ったら言う（体力は 20 まで）
const LOW_HEALTH = 6;
const BLOCKS_SHOWN = 8;

// よく使う物の日本語の呼び名（見せる言葉。無ければ英語の ID を読みやすくする）
export const JA_NAMES = {
  oak_log: 'オークの原木', birch_log: 'シラカバの原木', spruce_log: 'トウヒの原木', jungle_log: 'ジャングルの原木',
  acacia_log: 'アカシアの原木', dark_oak_log: 'ダークオークの原木', cherry_log: 'サクラの原木', mangrove_log: 'マングローブの原木',
  log: '原木', oak_planks: 'オークの板材', stick: '棒', crafting_table: '作業台', furnace: 'かまど', chest: 'チェスト',
  cobblestone: '丸石', stone: '石', dirt: '土', sand: '砂', gravel: '砂利', coal: '石炭', charcoal: '木炭',
  raw_iron: '鉄の原石', iron_ingot: '鉄インゴット', raw_copper: '銅の原石', copper_ingot: '銅インゴット',
  raw_gold: '金の原石', gold_ingot: '金インゴット', diamond: 'ダイヤモンド', wheat: '小麦', bread: 'パン',
  torch: '松明', flower: '花', string: '糸', wool: '羊毛', white_wool: '白い羊毛', bed: 'ベッド',
  wooden_pickaxe: '木のツルハシ', stone_pickaxe: '石のツルハシ', iron_pickaxe: '鉄のツルハシ', diamond_pickaxe: 'ダイヤのツルハシ',
  wooden_axe: '木の斧', stone_axe: '石の斧', iron_axe: '鉄の斧', wooden_sword: '木の剣', stone_sword: '石の剣',
  iron_sword: '鉄の剣', wooden_shovel: '木のシャベル', stone_shovel: '石のシャベル', iron_shovel: '鉄のシャベル',
  shield: '盾', bucket: 'バケツ', boat: 'ボート', oak_boat: 'オークのボート',
};

export const ja = (item) => JA_NAMES[item] ?? String(item).replaceAll('_', ' ');
export const facingJa = (f) => FACING[f] ?? '';

// 付箋の題（「oak_log を 10 個集める」）
export function title(skill, args = {}) {
  const who = args.player ?? '持ち主';
  switch (skill) {
    case 'follow': return `${who}についていく`;
    case 'come': return `${who}のそばへ行く`;
    case 'go_to': return args.player !== undefined ? `${who}のところへ行く` : `（${args.x}, ${args.z}）へ行く`;
    case 'collect': return `${args.block} を ${args.count ?? 1} 個集める`;
    case 'dig_down': return `足元を ${args.depth} ブロック掘る`;
    case 'craft': return `${args.item} を ${args.count ?? 1} 個作る`;
    case 'find': return `${args.block} を探す`;
    case 'give': return `${args.item} を${args.count !== undefined ? ` ${args.count} 個` : ''}${who}に渡す`;
    default: return skill;
  }
}

// うまくいかなかった理由の文（足りない材料・要る道具も添える）
export function reasons(reason, note = {}) {
  let why = WHY_FAILED[reason] ?? WHY_FAILED.error;
  if (note.needs && Object.keys(note.needs).length) why += '（足りない物：' + Object.entries(note.needs).map(([k, n]) => `${k}×${n}`).join('、') + '）';
  if (note.tool) why += `（要る道具：${note.tool} 以上）`;
  return why;
}

export const shortWhy = (reason, note = {}) => reasons(reason, note).split('（')[0];

// 体が始める前に断った（error）。理由の文と次の手も添え、心が道具の返事を見て、その場で正直に言って次へ進めるようにする
export function refused(m) {
  const reason = m.reason ?? 'error';
  const r = { status: 'error', reason };
  if (WHY_FAILED[reason]) r.why = reasons(reason, m.note ?? {});
  if (NEXT_STEP[reason]) r.next = NEXT_STEP[reason];
  return r;
}

const counts = (o) => Object.entries(o ?? {}).sort((a, b) => b[1] - a[1]);

// 心と小脳へ渡す様子の文（見出しは会話サーバーが付ける）
export function stateText(s, owner, linked = true) {
  if (!linked) return 'シエルの体とつながっていない（マイクラの中のことは分からない）';
  if (!s || !s.connected) return 'シエルはマイクラに入っていない（入り直しているところ）';
  const inv = counts(s.inventory);
  const doing = s.doing;
  const me = [`体力 ${Math.round(s.health ?? 0)}/20`, `空腹 ${s.food}/20`,
    '持ち物 ' + (inv.length ? inv.map(([k, n]) => `${k}×${n}`).join('、') : 'なし'),
    'していること ' + (doing ? (SKILL_NAMES[doing.skill] ?? doing.skill) : 'なし')];
  const when = (s.night ? '夜（敵が出る）' : '昼') + (s.raining ? '・雨' : '');
  const players = s.players ?? [];
  const near = players.map((p) => `${p.name}${p.name === owner ? '（持ち主）' : ''} ${p.distance} ブロック`)
    .concat((s.hostiles ?? []).map((h) => `${h.name} ${h.distance} ブロック`));
  const lines = ['シエル：' + me.join('・'), `時刻：${when}`, '近く：' + (near.length ? near.join('、') : 'だれもいない')];
  if (s.footing?.on) lines.push(`足元：${s.footing.on}`);
  const blocks = counts(s.blocks).slice(0, BLOCKS_SHOWN);
  if (blocks.length) lines.push('近くのブロック：' + blocks.map(([k, n]) => `${k}×${n}`).join('、'));
  if (owner && !players.some((p) => p.name === owner)) lines.push(`${owner}（持ち主）は近くにいない`);
  return lines.join('\n');
}

// 目的の係が「前後で何か変わったか」を見る値（持ち物と、ブロック単位の場所）。会話サーバーは中身を読まない
export function fingerprint(s) {
  const p = s?.pos ?? {};
  const pos = ['x', 'y', 'z'].map((k) => Math.round(p[k] ?? 0)).join(',');
  const inv = Object.entries(s?.inventory ?? {}).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)).map(([k, n]) => `${k}:${n}`).join(',');
  return `${pos}|${inv}`;
}

// 体の出来事を、シエルへの知らせにする。言わないものは null（様子に入るだけ）。
// urgency：urgent（すぐの切れ目で短く）・normal（相手がだまったら）。key は間引きの鍵。memorable は日記に残す一文
export function eventFor(m, owner) {
  switch (m.kind) {
    case 'died':
      return { kind: 'died', urgency: 'urgent', key: 'died', memorable: 'マイクラで倒れた',
        say: '[マイクラ：シエルが倒れた（初めの場所で生き返った。持ち物は落とした）]' };
    case 'owner_died':
      return { kind: 'owner_died', urgency: 'urgent', key: 'owner_died', say: `[マイクラ：${owner ?? '持ち主'}が倒れた]` };
    case 'flee':
      return { kind: 'flee', urgency: 'urgent', key: 'flee', say: `[マイクラ：${m.from}から逃げている（体力 ${m.health}/20）]` };
    case 'hurt': {
      const amount = m.amount ?? 0, health = m.health ?? 0;
      if (amount >= BIG_HURT || (health <= LOW_HEALTH && amount > 0)) {
        return { kind: 'hurt', urgency: 'urgent', key: 'hurt', say: `[マイクラ：${amount} のダメージを受けた（体力 ${health}/20）]` };
      }
      return null;
    }
    case 'defeated':
      return { kind: 'defeated', urgency: 'normal', key: 'defeated', memorable: `マイクラで ${m.name} を倒した`,
        say: `[マイクラ：${m.name}を倒した]` };
    default:
      return null;   // 夜・天気・プレイヤーの出入り・チャットは様子に入るだけ（チャットは B4）
  }
}

// 頼まれた技の終わり（体の done）を、知らせと付箋の閉じ方にする。
// うまくいかなかったら、理由・途中までの成果・次の手を心へ知らせ、呼び直すか相談するかを心が決める（play.md）。
// 「同じ頼みで何回目か」は会話サーバーが題で数えて足す（どのゲームでも同じ）
export function doneFor(m, name) {
  const note = m.note ?? {};
  let got = Object.entries(note.gained ?? {}).map(([k, n]) => `${k}×${n}`).join('、');
  if (note.found) got = [got, `${note.found} を見つけた`].filter(Boolean).join('、');
  if (note.descended) got = [got, `${note.descended} ブロック降りた`].filter(Boolean).join('、');
  const reason = m.reason ?? 'error';
  const out = { ok: Boolean(m.ok) && !note.short, title: name, reason: m.ok ? (note.short ?? null) : reason };
  // 付箋の閉じ方
  if (m.ok || reason === 'stopped' || reason === 'replaced') {
    out.card = 'done';
    out.card_note = m.ok && note.short ? '途中まで' : ({ stopped: 'やめた', replaced: 'ほかの頼みに替えた' }[reason] ?? null);
  } else {
    out.card = 'failed';
    out.card_note = shortWhy(reason);
  }
  if (m.ok && !note.short) {
    // 集め終えた。そばへ行く・場所へ行くは、着いたのが見えるので言わない。
    // 目的の途中（原木を集めた → ツルハシを作る）なら、心が次の段を呼ぶ。言うだけで止まった（2026-11-07）
    if (got) out.say = `[マイクラ：頼まれた「${name}」ができた（${got}）。目的の途中なら、次の段の道具を呼んで続ける]`;
    return out;
  }
  if (!m.ok && (QUIET_REASONS.includes(reason) || reason === 'died')) return out;   // 倒れたことは died の出来事で言う
  out.failed = true;
  let why = reasons(note.short ?? reason, note);
  if (reason === 'error' && m.detail) why += `（体のエラー：${m.detail}）`;
  out.say = m.ok
    ? `[マイクラ：頼まれた「${name}」は途中まで（できたところ：${got}）。残りの理由：${why}]`
    : `[マイクラ：頼まれた「${name}」ができなかった。理由：${why}。できたところ：${got || 'なし'}]`;
  const hint = NEXT_STEP[note.short ?? reason];
  if (hint) out.say = out.say.slice(0, -1) + `。次の手：${hint}]`;
  return out;
}
