import assert from 'node:assert/strict';
import { test } from 'node:test';
import { makeHub } from '../src/ciel/hub.js';

test('reaction notifications carry issuing time, stable source epoch and ordered unique IDs', () => {
  const messages = [];
  const server = {
    sendLoggingMessage: (message) => { messages.push(message.data); return Promise.resolve(); },
    server: { sendResourceUpdated: () => Promise.resolve() },
  };
  const hub = makeHub({ command: () => {} });
  hub.sessions = new Map([['a', { server }], ['b', { server }]]);
  const first = hub.claim('a');
  first.send(JSON.stringify({ type: 'event', kind: 'hurt', amount: 6, health: 10 }));
  first.send(JSON.stringify({ type: 'event', kind: 'hurt', amount: 6, health: 4 }));
  const damage = messages.filter(e => e.kind === 'hurt');
  assert.equal(damage.length, 2);
  assert.equal(damage[0].input_v, 1);
  assert.equal(damage[0].source_epoch, damage[1].source_epoch);
  assert.notEqual(damage[0].event_id, damage[1].event_id);
  assert.ok(damage[1].seq > damage[0].seq);
  assert.ok(Math.abs(damage[0].occurred_at - Date.now() / 1000) < 2);
  hub.release('a');
  hub.claim('b').send(JSON.stringify({ type: 'event', kind: 'hurt', amount: 6, health: 10 }));
  assert.notEqual(messages.at(-1).source_epoch, damage[0].source_epoch);
  hub.release('b');
});
