// ゲーム環境のMCP入口。profile 2 / work 1。docs/games/game-environment-mcp-design-ja.md。
// - 会話サーバーは会話の始めに MCP でつなぎ、道具・遊び方の指示（prompt play）・決まり（resource game://profile）を読む。
//   つないだだけでは体を動かさない。アプリの設定でオンにしたら minecraft_link(on=true) で体を受け持つ（体を動かせる会話は 1 つだけ）。
// - 様子は resource game://state。変わったら、受け持っている会話へ notifications/resources/updated を送る。
// - 出来事（倒れた・技が終わった など）は、MCP のふつうの知らせ notifications/message（logger 'ciel.event'）で送る。
//   決まりの外の知らせ（notifications/ciel/event）は、会話サーバーの Python の SDK が捨てるので使わない。
// - 待ち受けは 127.0.0.1 だけ（体と同じく host のネットワークで動くので、全部のアドレスで開くと外から見える）。
// - 受け持っている会話から CIEL_IDLE_MS のあいだ何も届かなければ、離れたことにする（会話サーバーは 20 秒ごとに ping を送る）。
import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import http from 'node:http';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { SubscribeRequestSchema, UnsubscribeRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { z } from 'zod';

import { registerKnowledge } from '../knowledge/main.js';
import { CAPABILITIES, TASK_VERSION } from './tasks.js';
import { BUILD_BLOCKS } from '../spatial.js';
import { QUIET_REASONS, WHY_FAILED, facingJa, shortWhy, stateText } from './words.js';

export const PROFILE_VERSION = 2;
const GAME = 'minecraft';
const LABEL = 'マイクラ';
const MAX_BODY = 64 * 1024;
const ROUTES = JSON.parse(readFileSync(new URL('./routes.json', import.meta.url), 'utf8'));
const PLAY = readFileSync(new URL('./play.md', import.meta.url), 'utf8');
// 体を動かす・見る頼みの言葉（振り分けの 1 段目。会話サーバーは中身を知らずに使う）。「ついてきて」は短いので、
// 小脳に行くと、道具を持たない小脳が「はーい」と言うだけになる。「きて」「まって」だけでは「できて」「決まって」も当たるので入れない。
// 「ついてくるの止められないかな？」が当たらず、小脳が「『止まって』と言ってくれたら」と返した（2026-11-05）
export const ROUTE_WORDS = 'つい(て|と)(き|来|く|こ|い)|付いて|こっち|おいで|来て|止ま|止め|とまっ|待って|ストップ|やめて|'
  + '見え(る|て)|見て|何がある|なにがある|周り|まわり|大丈夫|体力|マイクラ|集め|取って|とって|掘って|掘る|ちょうだい|渡して|くれる|行って|降り|おり|'
  + '作って|つくって|作れる|クラフト|ツルハシ|つるはし|整地|床|壁|埋め|取り除|'
  // 進み具合を聞く言葉。「始めてる？」が小脳へ回り、道具も様子の続きも持たない小脳が「まだ始めていない」と答えた（2026-11-07）
  + '始めて|始めた|はじめて|進んで|進んだ|できた？|できそう|どうなって';

const json = (r) => ({ content: [{ type: 'text', text: JSON.stringify(r) }] });
const meta = (name, role, extra = {}) => ({ 'ciel/role': role, 'ciel/triggers': ROUTES.tools[name] ?? [], ...extra });
const ACT = (name, extra) => ({ annotations: { readOnlyHint: false }, _meta: meta(name, 'act', { 'ciel/from_comments': false, ...extra }) });

// 会話サーバーが読む決まり
export function profile() {
  const reasons = Object.fromEntries(Object.keys(WHY_FAILED).map((k) => [k, shortWhy(k)]));
  return {
    profile: PROFILE_VERSION, game: GAME, label: LABEL, reference_context: true,
    route_words: ROUTE_WORDS,
    speech_vocabulary: JSON.parse(readFileSync(new URL('./speech-vocabulary.json', import.meta.url), 'utf8')),
    link_tool: 'minecraft_link', stop_tool: 'minecraft_stop_moving',
    inference: { version: 1, bind_tool: 'minecraft_bind_core' },
    work: { version: TASK_VERSION, submit: 'minecraft_task_submit', status: 'minecraft_task_status',
      answer: 'minecraft_task_answer', cancel: 'minecraft_task_cancel', capabilities: CAPABILITIES },
    talker_examples: ROUTES.talker ?? [],
    reasons, quiet_reasons: QUIET_REASONS,
  };
}

// hub：体の受け持ち（main.js）。{ link（今受け持っている CielLink か null）, claim(id)→CielLink|null, release(id),
//        controller（受け持っている会話の id）, busy（WebSocket の会話が使っている）, fingerprint() }
// sessionId：この会話の id を返す関数（id は initialize の答えを作るときに決まる）
export function makeServer(hub, sessionId) {
  const server = new McpServer({ name: 'ciel-minecraft', version: '1.0.0' },
    { capabilities: { logging: {}, resources: { subscribe: true } }, instructions: 'シエルのゲームの決まり（版 1）。resource game://profile を読む。' });
  const mine = () => (hub.controller !== null && hub.controller === sessionId() ? hub.link : null);
  const body = async (fn) => {
    const l = mine();
    if (l?.work.active && !['succeeded', 'failed', 'cancelled'].includes(l.work.active.state)) return json({ status: 'busy' });
    if (l) return json(await fn(l));
    return json({ status: hub.controller || hub.busy ? 'busy' : 'unavailable' });
  };

  // ---- 受け持つ ----
  server.registerTool('minecraft_bind_core', {
    description: 'Host-only: bind the owning conversation to CIEL inference.',
    inputSchema: { url: z.string(), token: z.string().min(32) },
    _meta: { 'ciel/role': 'link' },
  }, async ({url, token}) => {
    const l = mine();
    if (!l) return json({status:'unavailable'});
    const endpoint = new URL(url);
    if (endpoint.protocol !== 'http:' || endpoint.hostname !== '127.0.0.1' || endpoint.username || endpoint.password)
      return json({status:'invalid_endpoint'});
    await l.bindCore(url, token);
    return json({status:'ready'});
  });
  server.registerTool('minecraft_link', {
    description: '体を受け持つ（on=true）・離す（on=false）。会話サーバーが、アプリの設定に合わせて呼ぶ（心には渡さない）',
    inputSchema: { on: z.boolean() },
    _meta: { 'ciel/role': 'link' },
  }, async ({ on }) => {
    if (!on) {
      hub.release(sessionId());
      return json({ status: 'off' });
    }
    return json(hub.claim(sessionId()) ? { status: 'linked' } : { status: 'busy' });
  });

  // ---- 体の技（以前の tools/minecraft.py） ----
  server.registerTool('minecraft_follow_me', { title: 'ついていく', description: 'Mindcraftの標準命令で持ち主についていく（止めるまで続く）。相手がゲーム内で認識できない場合の接近は未対応。', inputSchema: {},
    ...ACT('minecraft_follow_me', { 'ciel/long_running': true }) }, () => body((l) => l.do('follow')));
  server.registerTool('minecraft_come_here', { title: 'そばへ行く', description: 'Mindcraftの標準命令で持ち主のそばへ行く。相手がゲーム内で認識できない場合の接近は未対応。', inputSchema: {},
    ...ACT('minecraft_come_here', { 'ciel/long_running': true }) }, () => body((l) => l.do('come')));
  server.registerTool('minecraft_go_to_place', { title: '場所へ行く', description: 'マイクラで、座標（x, z）の場所へ歩いて行く（着いたら止まる）。',
    inputSchema: { x: z.number().int(), z: z.number().int() }, ...ACT('minecraft_go_to_place', { 'ciel/long_running': true,
      'ciel/target_binding': {kind:'axes',point:true,fields:{x:['x',0],z:['z',0]}} }) },
  ({ x, z: zz }) => body((l) => l.do('go_to', { x, z: zz })));
  server.registerTool('minecraft_find_blocks', {
    title: '探す',
    description: 'マイクラで、見える所に無いブロックを探す（見つけたら止まる。集めるのは minecraft_collect_blocks）。block は英語の ID か呼び名。'
      + 'how は walk（周りを歩いて見回す。木・花・砂など地面の上の物）・dig（階段状に掘り下げながら見る。石・鉱石など地中の物）・auto（体が選ぶ）。掘る探索では目的の鉱石に必要な道具を先に用意し、装備する。',
    inputSchema: { block: z.string(), how: z.string().optional() }, ...ACT('minecraft_find_blocks', { 'ciel/long_running': true }),
  }, ({ block, how }) => body((l) => l.do('find', { block, how: ['walk', 'dig', 'auto'].includes(how) ? how : 'auto' })));
  server.registerTool('minecraft_give_item', {
    title: '渡す',
    description: 'マイクラで、持ち物を持ち主に渡す（そばへ行って投げる）。item は英語の ID（oak_log など）。count を省けば持っている分すべて。',
    inputSchema: { item: z.string(), count: z.number().int().optional() }, ...ACT('minecraft_give_item', { 'ciel/long_running': true }),
  }, ({ item, count }) => body((l) => l.do('give', { item, ...(count != null ? { count } : {}) })));
  server.registerTool('minecraft_dig_down', {
    title: '足元を掘る',
    description: 'マイクラで、足元を depth ブロック（1〜32）掘って降りる。葉・原木・土・石など自然のブロックだけ掘る。',
    inputSchema: { depth: z.number().int() }, ...ACT('minecraft_dig_down', { 'ciel/long_running': true }),
  }, ({ depth }) => body((l) => l.do('dig_down', { depth })));
  server.registerTool('minecraft_stop_moving', {
    title: '止まる',
    description: 'マイクラで、今している技（ついていく・行く・集める）をやめて、その場で待つ。',
    inputSchema: { request_id: z.string().max(160).optional() },
    ...ACT('minecraft_stop_moving', { 'ciel/stops': true }),
  }, ({ request_id }) => {
    const l = mine();
    if (!l) return json({ status: 'unavailable' });
    return l.work.active ? l.work.cancel(l.work.active.id).then(json) : json(l.stop(undefined, request_id));
  });

  // ---- 見る ----
  server.registerTool('minecraft_look_around', {
    title: '様子を見る',
    description: 'マイクラで、今の様子（体力・持ち物・時刻・近くの人と敵・していること）を見る。', inputSchema: {},
    annotations: { readOnlyHint: true }, _meta: meta('minecraft_look_around', 'look', { 'ciel/from_comments': true }),
  }, () => body((l) => ({ status: 'ok', state: l.text() })));
  server.registerTool('minecraft_look_at_view', {
    title: '景色を見る',
    description: 'マイクラで、自分の目で今の景色を見る（向いている方向の 1 枚の絵。呼んだあと、その絵が見える）。', inputSchema: {},
    annotations: { readOnlyHint: true },
    // 景色の絵は 1 枚 0.3 円ほどかかるので、コメントからは見ない
    _meta: meta('minecraft_look_at_view', 'look', { 'ciel/from_comments': false }),
  }, async () => {
    const l = mine();
    if (!l) return json({ status: hub.controller || hub.busy ? 'busy' : 'unavailable' });
    const r = await l.look();
    if (!r.jpeg) return json(r);
    const facing = facingJa(r.facing);
    return { content: [{ type: 'image', data: r.jpeg, mimeType: 'image/jpeg' },
      { type: 'text', text: JSON.stringify({ status: 'seen', facing: facing || null, note: facing ? `${facing}を向いている` : '' }) }] };
  });

  // ---- 知識（以前の minecraft-knowledge の窓口） ----
  registerKnowledge(server, ROUTES.tools);

  // Work contract: only the owning MCP session can submit, inspect, decide or cancel.
  const WORK = { _meta: { 'ciel/role': 'work' } };
  const work = async fn => mine() ? json(await fn(mine().work)) : json({ status: 'unavailable' });
  server.registerTool('minecraft_task_submit', { description: '期限付きの作業を受け付ける。段の計画と実行はゲームが行う。',
    inputSchema: { request_id: z.string().min(1).max(160), capability: z.string(), arguments: z.record(z.string(), z.any()),
      budget_ms: z.number().int().min(100).max(120000), constraints: z.record(z.string(), z.any()) }, ...WORK },
  r => work(w => w.submit(r)));
  server.registerTool('minecraft_task_status', { description: '作業の最新状態と根拠を取得する。',
    inputSchema: { task_id: z.string() }, ...WORK },
  ({ task_id }) => work(w => w.tasks.has(task_id) ? w.view(w.tasks.get(task_id)) : { status: 'error', reason: 'unknown_task' }));
  server.registerTool('minecraft_task_answer', { description: 'ゲームからの判断要求に回答する。期限と制約は変更しない。',
    inputSchema: { task_id: z.string(), decision_id: z.string(), action: z.enum(['retry', 'cancel']) }, ...WORK },
  ({ task_id, decision_id, action }) => work(w => w.answer(task_id, decision_id, action)));
  server.registerTool('minecraft_task_cancel', { description: '作業を中止し、体の停止を確認する。',
    inputSchema: { task_id: z.string() }, ...WORK }, ({ task_id }) => work(w => w.cancel(task_id)));

  // ---- 様子・決まり・遊び方 ----
  server.registerResource('state', 'game://state', { mimeType: 'application/json', description: '今の体の様子（シエルが読む文）' },
    async (uri) => {
      const l = mine();
      const s = l ? { label: LABEL, linked: true, playing: l.playing(), reason: '', text: l.text(), fingerprint: hub.fingerprint(),
        body: l.body, work: l.work.view(), references: hub.references?.() ?? null }
        : { label: LABEL, linked: false, playing: false, reason: hub.controller || hub.busy ? 'busy' : 'off', text: stateText(null, null, false) };
      return { contents: [{ uri: uri.href, mimeType: 'application/json', text: JSON.stringify(s) }] };
    });
  server.registerResource('profile', 'game://profile', { mimeType: 'application/json', description: 'シエルのゲームの決まり' },
    async (uri) => ({ contents: [{ uri: uri.href, mimeType: 'application/json', text: JSON.stringify(profile()) }] }));
  server.registerPrompt('play', { description: 'マイクラで遊ぶあいだ、心に渡す遊び方の指示' },
    () => ({ messages: [{ role: 'user', content: { type: 'text', text: PLAY } }] }));
  server.server.setRequestHandler(SubscribeRequestSchema, async () => ({}));
  server.server.setRequestHandler(UnsubscribeRequestSchema, async () => ({}));
  return server;
}

async function readBody(req) {
  const chunks = [];
  let size = 0;
  for await (const c of req) {
    size += c.length;
    if (size > MAX_BODY) throw new Error('too_large');
    chunks.push(c);
  }
  const text = Buffer.concat(chunks).toString('utf8');
  return text ? JSON.parse(text) : undefined;
}

// MCP の HTTP の入口。sessions：会話の id → {server, transport, seen}
export function startHttp(hub, { host, port, idleMs, log }) {
  const sessions = new Map();
  hub.sessions = sessions;
  const httpServer = http.createServer(async (req, res) => {
    if (!req.url?.startsWith('/mcp')) {
      res.writeHead(404).end();
      return;
    }
    const sid = req.headers['mcp-session-id'];
    try {
      if (sid && sessions.has(sid)) {
        const s = sessions.get(sid);
        s.seen = Date.now();
        const body = req.method === 'POST' ? await readBody(req) : undefined;
        await s.transport.handleRequest(req, res, body);
        return;
      }
      if (req.method !== 'POST') {
        res.writeHead(sid ? 404 : 400).end();
        return;
      }
      const body = await readBody(req);
      if (sid) {   // 知らない会話（体を入れ直した）：つなぎ直してもらう
        res.writeHead(404).end();
        return;
      }
      let server = null;
      const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: () => randomUUID(),
        onsessioninitialized: (id) => {
          sessions.set(id, { server, transport, seen: Date.now() });
          log('会話が MCP でつながった');
        },
      });
      transport.onclose = () => {
        const id = transport.sessionId;
        if (id && sessions.delete(id)) {
          hub.release(id);
          log('会話の MCP が閉じた');
        }
      };
      server = makeServer(hub, () => transport.sessionId);
      await server.connect(transport);
      await transport.handleRequest(req, res, body);
    } catch (e) {
      log('MCP に答えられない', e?.message ?? e);
      if (!res.headersSent) res.writeHead(400).end();
    }
  });
  // 受け持っている会話が黙ったまま：離れたことにする
  setInterval(() => {
    const now = Date.now();
    for (const [id, s] of sessions) {
      if (now - s.seen > idleMs) {
        log('会話の MCP から長く何も届かないので閉じる');
        sessions.delete(id);
        hub.release(id);
        s.transport.close().catch(() => {});
      }
    }
  }, Math.min(idleMs, 10000)).unref();
  httpServer.listen(port, host, () => log(`会話を待つ（MCP） http://${host}:${port}/mcp`));
  return httpServer;
}
