// シエルの体：マイクラ（Java 版）にプレイヤーとして入り、会話サーバーの命令で動く。docs/minecraft-design-ja.md。
// - 会話とは別に動き続ける。会話サーバーは ws://BODY_HOST:BODY_PORT へつなぐ（体を動かせる会話は 1 つだけ）。
// - 会話モデルは使わない。出来事は全部送り、どれを話すかは会話サーバーが選ぶ。
// - ゲームのチャットの中身はログに出さない（会話と同じ扱い）。
import mineflayer from 'mineflayer';
import pathfinderPkg from 'mineflayer-pathfinder';
import collectBlock from 'mineflayer-collectblock';
import { WebSocketServer } from 'ws';

import { message, parseCommand } from './protocol.js';
import { Guard } from './guard.js';
import { carefulMovements } from './movements.js';
import { Runner } from './skills.js';
import { isNight, summarize } from './state.js';

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
const BODY_HOST = env.BODY_HOST ?? '127.0.0.1';   // 外から入る口は開かない
const BODY_PORT = Number(env.BODY_PORT ?? 8768);
const STATE_EVERY_MS = 2000;
const RETRY_MIN_MS = 5000;
const RETRY_MAX_MS = 60000;

const log = (...a) => console.log(new Date().toISOString(), ...a);
const tenth = (v) => Math.round(v * 10) / 10;

// ---- 会話サーバーとのつながり（1 つだけ） ----
let link = null;

function send(type, fields) {
  if (link?.readyState === 1) link.send(message(type, fields));
}

const guard = new Guard(send, OWNER);
const runner = new Runner(send, OWNER, guard);
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
  log('会話とつながった');
  send('hello', { username: MC.username, version: MC.version, owner: OWNER, state: summarize(bot, runner.doing()) });
  ws.on('message', (raw) => {
    const r = parseCommand(raw.toString());
    if (r.error) {
      send('error', { reason: r.error, ...(r.id !== undefined ? { id: r.id } : {}) });
      return;
    }
    const cmd = r.cmd;
    if (cmd.type === 'do') runner.start(cmd);
    else if (cmd.type === 'stop') runner.stop('stopped');
    else if (cmd.type === 'chat') {
      if (bot?.entity) bot.chat(cmd.text);
      else send('error', { reason: 'not_spawned' });
    } else if (cmd.type === 'state') send('state', summarize(bot, runner.doing()));
  });
  ws.on('close', () => {
    if (link !== ws) return;
    link = null;
    runner.stop('unlinked');   // 会話を切ったら、その場で待つ（ログアウトしない）
    log('会話が切れた');
  });
  ws.on('error', () => {});
});
wss.on('listening', () => log(`会話を待つ ws://${BODY_HOST}:${BODY_PORT}`));

setInterval(() => {
  if (link) send('state', summarize(bot, runner.doing()));
}, STATE_EVERY_MS);

// ---- マイクラ ----
let retry = RETRY_MIN_MS;

function connect() {
  log(`マイクラへ入る ${MC.host}:${MC.port} 版 ${MC.version} 名前 ${MC.username}`);
  const b = mineflayer.createBot(MC);
  bot = b;
  b.loadPlugin(pathfinderPkg.pathfinder);
  b.loadPlugin(collectBlock.plugin);
  let health = null;
  let night = null;

  b.once('spawn', () => {
    retry = RETRY_MIN_MS;
    runner.attach(b);
    guard.attach(b);
    b.pathfinder.setMovements(carefulMovements(b));
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
      guard.detach();
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
    bot?.quit();
    wss.close();
    process.exit(0);
  });
}
