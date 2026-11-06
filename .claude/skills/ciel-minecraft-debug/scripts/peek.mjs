// 動いているシエルの体（main.js）を、デバッガーで一度だけ止めて中を読み、すぐ続ける。peek.sh が使う。
// 体は事前に SIGUSR1 でデバッガーの入口（127.0.0.1:9229、コンテナの中だけ）を開いておく（peek.sh がする）。
//   WHERE=path（既定）：経路探索の毎回の処理（mineflayer-pathfinder の monitorMovement）で止める。歩く係の中が読める
//   WHERE=bot：mineflayer の物理の毎回の処理で止める。bot が読める
//   EXPR：読む式（止めた所で評価する。JSON の文字列を返す式にする）
import WebSocket from 'ws';

const WHERE = process.env.WHERE ?? 'path';
const SPOTS = {
  // monitorMovement の「道が無いとき」の行（index.js 456 行目あたり）。道を歩き終えて行き先に届いていないと、ここを通り続ける
  path: { urlRegex: 'mineflayer-pathfinder/index\\.js$', lineNumber: 456 },
  bot: { urlRegex: 'mineflayer/lib/plugins/physics\\.js$', lineNumber: 84 },
};
const EXPRS = {
  path: `JSON.stringify({ placing, placingBlock, digging, pathLen: path.length,
    next: path[0] && { x: path[0].x, y: path[0].y, z: path[0].z, toPlace: path[0].toPlace.length, toBreak: path[0].toBreak.length },
    goal: stateGoal && stateGoal.constructor.name, sinceNode: Math.round(performance.now() - lastNodeTime),
    pos: String(bot.entity.position), onGround: bot.entity.onGround, inWater: bot.entity.isInWater })`,
  bot: `JSON.stringify({ pos: String(bot.entity.position), onGround: bot.entity.onGround, inWater: bot.entity.isInWater,
    held: bot.heldItem && bot.heldItem.name, health: bot.health,
    targets: bot.collectBlock.targets.targets.map((t) => String(t.position) + ' ' + (t.name || t.constructor.name)),
    goal: bot.pathfinder.goal && bot.pathfinder.goal.constructor.name, moving: bot.pathfinder.isMoving(),
    digging: bot.targetDigBlock && String(bot.targetDigBlock.position),
    inv: Object.fromEntries(bot.inventory.items().map((i) => [i.name, i.count])) })`,
};
const EXPR = process.env.EXPR || EXPRS[WHERE];

const list = await (await fetch('http://127.0.0.1:9229/json/list')).json();
const ws = new WebSocket(list[0].webSocketDebuggerUrl);
let id = 0;
let bp = null;
const pending = new Map();
const call = (method, params = {}) => new Promise((resolve) => {
  const i = ++id;
  pending.set(i, resolve);
  ws.send(JSON.stringify({ id: i, method, params }));
});
const finish = async (code) => {
  if (bp) await call('Debugger.removeBreakpoint', { breakpointId: bp });
  await call('Debugger.resume');
  await call('Debugger.disable');
  ws.close();
  process.exit(code);
};
ws.on('message', async (raw) => {
  const m = JSON.parse(raw);
  if (m.id && pending.has(m.id)) {
    pending.get(m.id)(m.result ?? m.error);
    pending.delete(m.id);
    return;
  }
  if (m.method === 'Debugger.paused') {
    const r = await call('Debugger.evaluateOnCallFrame', { callFrameId: m.params.callFrames[0].callFrameId, expression: EXPR, returnByValue: true });
    console.log(r.result?.value ?? JSON.stringify(r).slice(0, 600));
    await finish(0);
  }
});
ws.on('open', async () => {
  await call('Debugger.enable');
  const r = await call('Debugger.setBreakpointByUrl', SPOTS[WHERE]);
  bp = r.breakpointId;
  if (!r.locations?.length) console.log('止める場所が見つからない（部品の版が変わって行がずれた？）', JSON.stringify(SPOTS[WHERE]));
});
// 止まらなかった：その処理を通っていない（WHERE=path なら、歩く係は道を持って歩いているか、何もしていない）
setTimeout(() => { console.log('15 秒止まらなかった'); finish(1); }, 15000);
