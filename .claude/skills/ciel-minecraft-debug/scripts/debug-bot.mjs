// デバッグ用のボット Ciel_Debug を、シエルの体のコンテナの中で動かし、体と同じ技（src/skills.js の Runner）を
// 中を記録しながら試す。run.sh がコンテナへ写して動かす（/app に置くと、体と同じ node_modules を使える）。
//   環境変数：SKILL（collect・craft・follow など）、ARGS（JSON）、WAIT_MS（入ってから技を始めるまで。tp を待つ）、
//            SECONDS_LIMIT（これを過ぎたら必ず終える）
// 記録は writeSync で出す（console.log は、処理が固まると出ないまま消える）。
// 行き先（goal）や世界の物を JSON.stringify しない（世界の地図まで文字にしようとして、この道具が固まった。2026-11-06）。
import { writeSync } from 'node:fs';
import mineflayer from 'mineflayer';
import pathfinderPkg from 'mineflayer-pathfinder';
import collectBlock from 'mineflayer-collectblock';
import { Runner } from './src/skills.js';
import { nearbyBlocks } from './src/state.js';

const NAME = 'Ciel_Debug';
const SKILL = process.env.SKILL ?? 'collect';
const ARGS = JSON.parse(process.env.ARGS ?? '{}');
const WAIT_MS = Number(process.env.WAIT_MS ?? 8000);
const LIMIT_MS = Number(process.env.SECONDS_LIMIT ?? 60) * 1000;

const log = (...a) => writeSync(1, [new Date().toISOString().slice(11, 23), ...a].join(' ') + '\n');
const inv = (bot) => JSON.stringify(Object.fromEntries(bot.inventory.items().map((i) => [i.name, i.count])));

// 固まっても必ず終える（タイマーは、処理が固まると動かない。そのときは run.sh が外から止める）
setTimeout(() => { log('LIMIT', LIMIT_MS / 1000, 's'); process.exit(0); }, LIMIT_MS + 10000).unref();

const bot = mineflayer.createBot({
  host: process.env.MC_HOST, port: Number(process.env.MC_PORT ?? 25565), username: NAME,
  version: process.env.MC_VERSION ?? '1.21.11', auth: 'offline',
});
bot.loadPlugin(pathfinderPkg.pathfinder);
bot.loadPlugin(collectBlock.plugin);
const runner = new Runner((type, f) => log('report', type, JSON.stringify(f).slice(0, 400)), null, null);

bot.once('spawn', async () => {
  log('入った', String(bot.entity.position));
  bot.pathfinder.thinkTimeout = 10000;
  // 中を覗く（呼び出しの前後を記録する）
  const wrap = (obj, key, show) => {
    const fn = obj[key].bind(obj);
    obj[key] = async (...a) => {
      log(key, 'start', show(...a));
      try {
        const r = await fn(...a);
        log(key, 'done');
        return r;
      } catch (e) {
        log(key, 'err', e?.name, e?.message);
        throw e;
      }
    };
  };
  wrap(bot.pathfinder, 'goto', (g) => `${g.constructor.name} ${g.pos ? String(g.pos) : ''}`);
  wrap(bot.collectBlock, 'collect', (t) => `${t?.name ?? ''} ${t?.position ? String(t.position) : ''}`);
  wrap(bot, 'craft', (r, n, t) => `${bot.registry.items[r.result.id]?.name} x${n} table=${t ? String(t.position) : '-'}`);
  const dig = bot.dig.bind(bot);
  bot.dig = async (b, ...a) => {
    log('dig', b?.name, String(b?.position), 'digTime', bot.digTime(b), 'onGround', bot.entity.onGround, 'inWater', bot.entity.isInWater,
      'held', bot.heldItem?.name ?? 'なし');
    return dig(b, ...a);
  };
  bot.on('path_update', (r) => log('path_update', r.status, r.path.length, 'visited', r.visitedNodes));
  bot.on('path_reset', (r) => log('path_reset', r));
  bot.on('goal_reached', () => log('goal_reached'));
  bot.on('diggingCompleted', (b) => log('diggingCompleted', String(b.position), 'now', bot.blockAt(b.position)?.name));
  bot.on('blockUpdate', (o, n) => {
    if (o && n && o.type !== n.type && n.position.distanceTo(bot.entity.position) < 8) log('blockUpdate', String(n.position), o.name, '->', n.name);
  });
  bot.on('playerCollect', (c) => { if (c === bot.entity) log('拾った', inv(bot)); });

  await new Promise((r) => setTimeout(r, WAIT_MS));   // run.sh の tp・give を待つ
  log('始める', SKILL, JSON.stringify(ARGS), 'pos', String(bot.entity.position), 'onGround', bot.entity.onGround, 'inv', inv(bot));
  log('見えるブロック', JSON.stringify(nearbyBlocks(bot)));
  runner.attach(bot);
  const stop = setTimeout(() => { log('時間切れ。技を止める'); runner.stop('stopped'); }, LIMIT_MS);
  await runner.start({ id: 1, skill: SKILL, args: ARGS });
  clearTimeout(stop);
  log('終わり', 'pos', String(bot.entity.position), 'inv', inv(bot));
  bot.quit();
  setTimeout(() => process.exit(0), 1000);
});
bot.on('kicked', (r) => { log('外された', JSON.stringify(r).slice(0, 200)); process.exit(0); });
bot.on('error', (e) => log('エラー', e?.message));
