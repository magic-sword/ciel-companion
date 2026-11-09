// シエルの目：体（ボット）が今いる場所から見た景色を、1 枚の JPEG にする。docs/minecraft-design-ja.md。
// - prismarine-viewer の一人称の視点（Web のページ）を 127.0.0.1 だけで開き、同じコンテナの画面の無い Chromium で見る。
//   prismarine-viewer の mineflayer() は全部のアドレスで待ち受けるので使わず、同じ中身をここで 127.0.0.1 に開く。
// - 見る（look）たびに開き直さず、ページを開いたまま景色を描き続け、そのときの 1 コマを撮る（あとで画面共有へ広げる土台。
//   同じページを LiveKit の映像として流せば、ずっと見ている形になる）。
// - 撮らないあいだは、ページの描画の合図（requestAnimationFrame）を止める（HOLD_FRAMES）。描き続けると、画面の無い
//   Chromium がソフトウェア（SwiftShader）で描くので CPU を 17 コア分ほど使った（2026-11-06）。ページを凍らせる
//   （Page.setWebLifecycleState frozen）では下がらなかった。合図だけを止めれば、景色の変化の受け取りとブロックの形づくり
//   （ページの worker）は続くので、撮るときは合図を戻して少し描くだけでよい。
// - しばらく見なければ閉じる。体がマイクラから出たら閉じる。
// - 撮った絵は保存しない。
import { createRequire } from 'node:module';
import { EventEmitter } from 'node:events';

const require = createRequire(import.meta.url);
// prismarine-viewer の部品は、prismarine-viewer が使う版の express・socket.io で動かす
const pvRequire = createRequire(require.resolve('prismarine-viewer/lib/mineflayer.js'));

export const EYE_WIDTH = 768;
export const EYE_HEIGHT = 480;
const VIEW_DISTANCE = 6;          // 描くチャンクの範囲（6 で山・海が見えた）
const FIRST_DRAW_MS = 8000;       // 開いてから、まわりを描き終えるまで（試作で 7〜9 秒）
const MOVED_DRAW_MS = 1500;       // 向き・場所が変わってから描き直すまで（試作で 2 秒ほど）
const WAKE_DRAW_MS = 1000;        // 描画の合図を戻してから、今の景色を描き終えるまで
const IDLE_CLOSE_MS = 10 * 60_000;    // 止めていてもメモリーは使うので、しばらく見なければ閉じる
const JPEG_QUALITY = 80;
const CHROMIUM_ARGS = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// ページに入れる：window.__eyeAwake が false のあいだは requestAnimationFrame を呼ばずに預かり、__eyeWake() で戻す
function HOLD_FRAMES() {
  const raf = window.requestAnimationFrame.bind(window);
  let held = [];
  window.__eyeAwake = true;
  window.requestAnimationFrame = (cb) => {
    if (window.__eyeAwake) return raf(cb);
    held.push(cb);
    return 0;
  };
  window.__eyeWake = () => {
    window.__eyeAwake = true;
    const h = held;
    held = [];
    for (const cb of h) raf(cb);
  };
  window.__eyeSleep = () => { window.__eyeAwake = false; };
}

export class Eye {
  constructor({ host = '127.0.0.1', port = 3007, log = () => {} } = {}) {
    this.host = host;
    this.port = port;
    this.log = log;
    this.bot = null;
    this._open = null;        // 開いている間：{ http, io, browser, page, openedAt }
    this._opening = null;
    this._queue = Promise.resolve();
    this._idle = null;
    this._movedAt = 0;
    this._onMove = () => { this._movedAt = Date.now(); };
  }

  attach(bot) {
    this.detach();
    this.bot = bot;
    bot.on('move', this._onMove);
  }

  detach() {
    if (this.bot) this.bot.removeListener('move', this._onMove);
    this.bot = null;
    this.close();
  }

  /// 今の景色を 1 枚撮る。{ jpeg: Buffer, width, height } か、撮れない理由 { error }
  look() {
    const run = this._queue.then(() => this._look());
    this._queue = run.catch(() => {});
    return run;
  }

  async _look() {
    if (!this.bot?.entity) return { error: 'not_spawned' };
    let eye;
    try {
      eye = await this._ensureOpen();
    } catch (e) {
      this.log('目を開けない', e?.message ?? e);
      this.close();
      return { error: 'eye_unavailable' };
    }
    this._touch();
    try {
      let wokeAt = 0;
      if (eye.asleep) {
        await eye.page.evaluate(() => window.__eyeWake());
        eye.asleep = false;
        wokeAt = Date.now();
      }
      const now = Date.now();
      const ready = Math.max(eye.openedAt + FIRST_DRAW_MS, this._movedAt + MOVED_DRAW_MS, wokeAt + WAKE_DRAW_MS);
      if (ready > now) await wait(Math.min(ready - now, FIRST_DRAW_MS));
      const jpeg = await eye.page.screenshot({ type: 'jpeg', quality: JPEG_QUALITY });
      await eye.page.evaluate(() => window.__eyeSleep());
      eye.asleep = true;
      return { jpeg, width: EYE_WIDTH, height: EYE_HEIGHT };
    } catch (e) {
      this.log('景色を撮れない', e?.message ?? e);
      this.close();
      return { error: 'eye_unavailable' };
    }
  }

  async _ensureOpen() {
    if (this._open) return this._open;
    if (!this._opening) this._opening = this._openNow().finally(() => { this._opening = null; });
    return this._opening;
  }

  async _openNow() {
    const bot = this.bot;
    const { http, io } = await this._serve(bot);
    let browser;
    try {
      const { chromium } = await import('playwright');
      browser = await chromium.launch({ args: CHROMIUM_ARGS });
      const page = await browser.newPage({ viewport: { width: EYE_WIDTH, height: EYE_HEIGHT } });
      await page.addInitScript(HOLD_FRAMES);
      await page.goto(`http://${this.host}:${this.port}`);
      if (this.bot !== bot) throw new Error('bot changed');
      this._open = { http, io, browser, page, asleep: false, openedAt: Date.now() };
      this.log('目を開けた');
      this._touch();
      return this._open;
    } catch (e) {
      await browser?.close().catch(() => {});
      io.close();
      http.close();
      throw e;
    }
  }

  // prismarine-viewer の lib/mineflayer.js と同じ中身（一人称）。待ち受けるのは this.host だけ
  _serve(bot) {
    const express = pvRequire('express');
    const { setupRoutes } = pvRequire('./common');
    const { WorldView } = pvRequire('../viewer');
    const app = express();
    const http = require('node:http').createServer(app);
    const io = pvRequire('socket.io')(http, { path: '/socket.io' });
    setupRoutes(app, '');
    bot.viewer ??= new EventEmitter();
    io.on('connection', (socket) => {
      socket.emit('version', bot.version);
      const view = new WorldView(bot.world, VIEW_DISTANCE, bot.entity.position, socket);
      view.init(bot.entity.position);
      const position = () => {
        socket.emit('position', { pos: bot.entity.position, yaw: bot.entity.yaw, pitch: bot.entity.pitch, addMesh: true });
        view.updatePosition(bot.entity.position);
      };
      bot.on('move', position);
      view.listenToBot(bot);
      socket.on('disconnect', () => {
        bot.removeListener('move', position);
        view.removeListenersFromBot(bot);
      });
    });
    return new Promise((resolve, reject) => {
      http.once('error', reject);
      http.listen(this.port, this.host, () => resolve({ http, io }));
    });
  }

  _touch() {
    clearTimeout(this._idle);
    this._idle = setTimeout(() => {
      this.log('しばらく見ていないので、目を閉じる');
      this.close();
    }, IDLE_CLOSE_MS);
    this._idle.unref?.();
  }

  close() {
    clearTimeout(this._idle);
    const eye = this._open;
    this._open = null;
    if (!eye) return;
    eye.browser.close().catch(() => {});
    eye.io.close();
    eye.http.close();
  }
}
