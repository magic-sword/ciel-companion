// MCP の会話の、体の受け持ち。体を動かせる会話は 1 つだけ（WebSocket の会話も合わせて）。
// main.js が体の命令の入口（command）と、受け持ちが変わったときの始末（onClaim・onRelease）を渡す。
import { randomUUID } from 'node:crypto';
import { CielLink } from './link.js';
import { fingerprint } from './words.js';

export function makeHub({ command, owner = null, isBusy = () => false, onClaim = () => {}, onRelease = () => {}, log = () => {} }) {
  const hub = {
    link: null,         // 受け持っている会話の CielLink
    controller: null,   // その会話の id
    sessions: null,     // mcp.js が置く（id → {server, transport}）
    get busy() { return hub.link === null && isBusy(); },   // WebSocket の会話が使っている
    claim(id) {
      if (hub.controller === id) return hub.link;
      if (hub.link || isBusy()) return null;
      const server = () => hub.sessions?.get(id)?.server;
      const sourceEpoch = randomUUID();
      let eventSequence = 0;
      const l = new CielLink({
        command,
        owner,
        notice: (e) => server()?.sendLoggingMessage({ level: 'info', logger: 'ciel.event', data: { ...e, input_v: 1, event_id: `${sourceEpoch}:${++eventSequence}`,
          source_epoch: sourceEpoch, seq: eventSequence, occurred_at: Date.now() / 1000 } }, id)?.catch(() => {}),
        changed: () => server()?.server.sendResourceUpdated({ uri: 'game://state' })?.catch(() => {}),
      });
      hub.link = l;
      hub.controller = id;
      log('会話とつながった（MCP）');
      onClaim(l);
      return l;
    },
    release(id) {
      if (hub.controller !== id || !hub.link) return;
      const l = hub.link;
      onRelease(l);
      l.close();
      hub.link = hub.controller = null;
      log('会話が切れた（MCP）');
    },
    fingerprint: () => fingerprint(hub.link?.state),
  };
  return hub;
}
