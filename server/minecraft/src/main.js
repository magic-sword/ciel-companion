// シエルの体：マイクラ（Java 版）にプレイヤーとして入り、会話サーバーの命令で動く。docs/games/minecraft/minecraft-design-ja.md。
// - 会話とは別に動き続ける。会話サーバーは MCP（http://BODY_HOST:CIEL_PORT/mcp、src/ciel/mcp.js）でつなぐ。
//   以前の WebSocket（ws://BODY_HOST:BODY_PORT）も、移り終えるまで残す（docs/games/game-environment-mcp-design-ja.md の 10 章）。
//   体を動かせる会話は、どちらの入口でも合わせて 1 つだけ。
// - MindcraftのAgentがCIEL中核APIをモデルとして使う。出来事と実行状態はMCPで会話ホストへ知らせる。
// - ゲームのチャットの中身はログに出さない（会話と同じ扱い）。
import { createMindcraftBot, MindcraftRunner } from './mindcraft/runtime.js';
import { randomUUID } from 'node:crypto';
import { WebSocketServer } from 'ws';

import { makeHub } from './ciel/hub.js';
import { startHttp } from './ciel/mcp.js';
import { message, parseCommand } from './protocol.js';
import { Eye } from './eye.js';
import { PlayerLocator } from './player-locator.js';
import { Pointing } from './pointing.js';
import { facing, isNight, nearbyBlocks, summarize } from './state.js';

const env = process.env;
const MC = {
  host: env.MC_HOST ?? '127.0.0.1',
  port: Number(env.MC_PORT ?? 25565),
  username: env.MC_USERNAME ?? 'Ciel',
  version: env.MC_VERSION ?? '1.21.11',
  auth: 'offline',   // 家の中だけのサーバー（online-mode=false・ホワイトリスト）に入る
  hideErrors: true,  // つなげないときの詳しいエラーは出さない（下の 'error' で短く出す）
};
const OWNER = env.MC_OWNER || null;
const pointing = new Pointing(env.CIEL_POINTING_FILE, OWNER);
const BODY_HOST = env.BODY_HOST ?? '127.0.0.1';   // 外から入る口は開かない
const BODY_PORT = Number(env.BODY_PORT ?? 8768);
const CIEL_PORT = Number(env.CIEL_PORT ?? 8771);   // MCP の入口（src/ciel/mcp.js）。BODY_HOST だけで開く
const CIEL_IDLE_MS = Number(env.CIEL_IDLE_MS ?? 60000);
const EYE_PORT = Number(env.EYE_PORT ?? 3007);   // 目（eye.js）の視点のページ。BODY_HOST だけで開く
const STATE_EVERY_MS = 2000;
const BLOCKS_EVERY_MS = 10000;
const RETRY_MIN_MS = 5000;
const RETRY_MAX_MS = 60000;

const log = (...a) => console.log(new Date().toISOString(), ...a);
const tenth = (v) => Math.round(v * 10) / 10;

// ---- 会話サーバーとのつながり（1 つだけ。WebSocket の会話か、MCP の会話の CielLink） ----
let link = null;

function send(type, fields) {
  if (fields?.command_scope && fields.command_scope !== link?.bodyScope) return;
  if (link?.readyState === 1) link.send(message(type, fields));
}

const runner = new MindcraftRunner(send, OWNER);
const eye = new Eye({ host: BODY_HOST, port: EYE_PORT, log });
let bot = null;

const wss = new WebSocketServer({ host: BODY_HOST, port: BODY_PORT });
wss.on('connection', (ws) => {
  if (link) {
    ws.send(message('busy'));
    ws.close(1013, 'busy');
    log('つなぐ会話がもうあるので断った');
    return;
  }
  link = ws;
  ws.bodyScope = randomUUID();
  log('会話とつながった');
  send('hello', { username: MC.username, version: MC.version, owner: OWNER, state: state() });
  ws.on('message', (raw) => { if (link === ws) command(raw.toString()); });
  ws.on('close', () => {
    if (link !== ws) return;
    link = null;
    runner.stop('unlinked');   // 会話を切ったら、その場で待つ（ログアウトしない）
    log('会話が切れた');
  });
  ws.on('error', () => {});
});
wss.on('listening', () => log(`会話を待つ ws://${BODY_HOST}:${BODY_PORT}`));

// 会話から届いた命令（形を確かめてから動かす。protocol.js）
function command(raw) {
  const r = parseCommand(raw);
  if (r.error) {
    send('error', { reason: r.error, ...(r.id !== undefined ? { id: r.id } : {}) });
    return;
  }
  const cmd = r.cmd;
  if (cmd.type === 'do') void runner.start({ ...cmd, scope: link?.bodyScope });
  else if (cmd.type === 'stop') void runner.stop('stopped', cmd.task, link?.bodyScope);
  else if (cmd.type === 'chat') {
    if (bot?.entity) bot.chat(cmd.text);
    else send('error', { reason: 'not_spawned' });
  } else if (cmd.type === 'state') send('state', state());
  else if (cmd.type === 'look') look(cmd.id);
}

// MCP の会話の受け持ち（src/ciel/hub.js・mcp.js）
const hub = makeHub({
  command,
  owner: OWNER,
  isBusy: () => link !== null && link !== hub.link,   // WebSocket の会話が使っている
  onClaim: (l) => {
    l.bindCore = (url, token) => runner.bindCore(url, token);
    link = l;
    l.bodyScope = randomUUID();
    send('hello', { username: MC.username, version: MC.version, owner: OWNER, state: state() });
  },
  onRelease: (l) => {
    void runner.unbindCore();
    runner.stop('unlinked');   // 会話を切ったら、その場で待つ（ログアウトしない）
    if (link === l) link = null;
  },
  log,
});
startHttp(hub, { host: BODY_HOST, port: CIEL_PORT, idleMs: CIEL_IDLE_MS, log });
hub.references = () => pointing.latest(bot);

// 景色を 1 枚撮って返す。向いている方角も添える（「北を向いている」）
async function look(id) {
  const started = Date.now();
  const r = await eye.look();
  if (r.error) {
    send('error', { id, reason: r.error });
    return;
  }
  log(`景色を撮った（${r.jpeg.length} バイト、${Date.now() - started} ms）`);
  send('seen', { id, jpeg: r.jpeg.toString('base64'), width: r.width, height: r.height, facing: facing(bot) });
}

let blocks = {};
const state = () => ({ ...summarize(bot, runner.doing(), blocks), body: runner.snapshot() });
setInterval(() => {
  if (link) send('state', state());
}, STATE_EVERY_MS);
setInterval(() => {
  if (!link) return;
  try {
    blocks = nearbyBlocks(bot);
  } catch {
    blocks = {};
  }
}, BLOCKS_EVERY_MS);

// ---- マイクラ ----
let retry = RETRY_MIN_MS;

function connect() {
  log(`マイクラへ入る ${MC.host}:${MC.port} 版 ${MC.version} 名前 ${MC.username}`);
  const b = createMindcraftBot(MC);
  b.pointing = pointing;
  b.playerLocator = new PlayerLocator(b);
  bot = b;
  let health = null;
  let night = null;

  b.once('spawn', () => {
    retry = RETRY_MIN_MS;
    runner.attach(b);
    eye.attach(b);
    log('入った');
    send('event', { kind: 'spawned' });
  });
  b.on('health', () => {
    // 体力は少しずつ回復するので、小数のまま比べる。送るのは小数 1 桁まで
    if (health !== null && b.health < health) send('event', { kind: 'hurt', amount: tenth(health - b.health), health: tenth(b.health) });
    health = b.health;
  });
  b.on('death', () => {
    log('倒れた');
    runner.stop('died');
    health = null;
    send('event', { kind: 'died' });
  });
  b.on('entityDead', (e) => {
    if (OWNER && e.type === 'player' && e.username === OWNER) send('event', { kind: 'owner_died' });
  });
  b.on('playerJoined', (p) => {
    if (p.username !== b.username) send('event', { kind: 'player_joined', name: p.username });
  });
  b.on('playerLeft', (p) => {
    if (p.username !== b.username) send('event', { kind: 'player_left', name: p.username });
  });
  b.on('chat', (who, text) => {
    if (who === b.username) return;
    send('event', { kind: 'chat', who, text, owner: who === OWNER });
  });
  b.on('rain', () => send('event', { kind: 'weather', raining: Boolean(b.isRaining) }));
  b.on('time', () => {
    const now = isNight(b.time.timeOfDay);
    if (night !== null && now !== night) send('event', { kind: now ? 'night' : 'day' });
    night = now;
  });
  b.on('kicked', (reason) => log('サーバーから外された', typeof reason === 'string' ? reason.slice(0, 200) : ''));
  b.on('error', (err) => log('マイクラの接続のエラー', err?.code ?? err?.name ?? err));
  b.on('end', () => {
    if (bot === b) {
      runner.stop('disconnected');
      runner.attach(null);
      eye.detach();
      bot = null;
    }
    send('event', { kind: 'disconnected' });
    log(`マイクラから出た。${retry / 1000} 秒後に入り直す`);
    setTimeout(connect, retry);
    retry = Math.min(retry * 2, RETRY_MAX_MS);
  });
}

connect();

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    log('終える');
    eye.close();
    bot?.quit();
    wss.close();
    process.exit(0);
  });
}
