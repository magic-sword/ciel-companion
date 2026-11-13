import test from 'node:test';
import assert from 'node:assert/strict';
import { CielModel } from '../src/mindcraft/ciel-model.js';

test('Mindcraft sends context as data and uses the bound CIEL session', async () => {
  const model = new CielModel(null, 'http://localhost:8775', { token: 'session',
    fetch: async (url, options) => {
      assert.equal(options.headers.Authorization, 'Bearer session');
      const request = JSON.parse(options.body);
      assert.equal(request.messages[0].role, 'user');
      assert.equal(JSON.parse(request.messages[0].content).type, 'execution_context');
      return { ok: true, json: async () => ({ request_id: request.request_id, text: '!inventory' }) };
    } });
  assert.equal(await model.sendRequest([{ role: 'user', content: 'look' }], 'game context'), '!inventory');
});

test('a registered fixed prefix is prepared once and omitted from later requests', async () => {
  const calls = [];
  const model = new CielModel(null, 'http://localhost:8775', { token: 'session',
    fetch: async (url, options) => {
      calls.push([url.split('/v1/')[1], options.method, options.body]);
      if (url.endsWith('/reference')) return { ok: true, json: async () => ({ status: 'registered' }) };
      if (url.endsWith('/prepare')) return { ok: true, json: async () => ({ status: 'prepared', seconds: 12.5 }) };
      const request = JSON.parse(options.body);
      return { ok: true, json: async () => ({ request_id: request.request_id, text: 'ok' }) };
    } });
  assert.deepEqual(await model.prepareReference('rules\ndocs'), { status: 'prepared', reference_chars: 10, seconds: 12.5 });
  await model.sendRequest([], 'rules\ndocs\nstats');
  await model.sendRequest([], 'other prompt');
  const sent = calls.filter(c => c[0] === 'respond').map(c => JSON.parse(JSON.parse(c[2]).messages[0].content).text);
  assert.deepEqual(sent, ['stats', 'other prompt']);
  assert.deepEqual(calls.slice(0, 2).map(c => c.slice(0, 2)), [['reference', 'PUT'], ['prepare', 'POST']]);
});

test('without registration the full prompt is still sent; failed preparation keeps the registration', async () => {
  const sent = [];
  const reject = new CielModel(null, 'http://localhost:8775', { token: 'session',
    fetch: async (url, options) => {
      if (url.endsWith('/reference')) return { ok: false, status: 500 };
      const request = JSON.parse(options.body);
      sent.push(JSON.parse(request.messages[0].content).text);
      return { ok: true, json: async () => ({ request_id: request.request_id, text: 'ok' }) };
    } });
  assert.deepEqual(await reject.prepareReference('docs'), { status: 'unregistered' });
  await reject.sendRequest([], 'docs\nstats');
  assert.deepEqual(sent, ['docs\nstats']);
  const slow = new CielModel(null, 'http://localhost:8775', { token: 'session',
    fetch: async url => url.endsWith('/reference') ? { ok: true } : { ok: false, status: 504 } });
  const result = await slow.prepareReference('docs');
  assert.equal(result.status, 'failed');
  assert.equal(slow.reference, 'docs');
});

test('overlapping requests are sent at once with priorities; CIEL schedules them', async () => {
  const seen = [];
  const releases = [];
  const model = new CielModel(null, 'http://localhost:8775', { token: 'session',
    fetch: async (url, options) => {
      if (url.endsWith('/reference')) return { ok: true };
      if (url.endsWith('/prepare')) return { ok: true, json: async () => ({ status: 'prepared', seconds: 0 }) };
      const request = JSON.parse(options.body);
      seen.push(request.priority);
      await new Promise(resolve => releases.push(resolve));
      return { ok: true, json: async () => ({ request_id: request.request_id, text: 'ok' }) };
    } });
  const before = model.sendRequest([], 'anything');
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(seen, ['decision']);
  releases.shift()(); await before;
  await model.prepareReference('docs');
  const turn = model.sendRequest([], 'docs\nstats');
  const summary = model.sendRequest([], 'summarize the memory');
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(seen.slice(1), ['decision', 'background']);
  releases.splice(0).forEach(release => release());
  assert.deepEqual(await Promise.all([turn, summary]), ['ok', 'ok']);
});

test('cancelled requests reject a late successful HTTP response', async () => {
  let release;
  const model = new CielModel(null, 'http://localhost:8775', { token: 'session',
    fetch: async (url, options) => {
      if (options.method === 'DELETE') return { ok: true };
      const request = JSON.parse(options.body);
      await new Promise(resolve => { release = resolve; });
      return { ok: true, json: async () => ({ request_id: request.request_id, text: 'late' }) };
    } });
  const response = model.sendRequest([], 'game context');
  await model.cancel(); release();
  await assert.rejects(response, /cancelled/);
});

test('cancellation aborts the in-flight HTTP request before server acknowledgement', async () => {
  let acknowledge;
  const model = new CielModel(null, 'http://localhost:8775', { token: 'session',
    fetch: (url, options) => options.method === 'DELETE'
      ? new Promise(resolve => { acknowledge = () => resolve({ ok: true }); })
      : new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(options.signal.reason))) });
  const response = model.sendRequest([], 'context');
  const cancelled = assert.rejects(response, /cancelled/);
  const stop = model.cancel();
  await cancelled;
  acknowledge();
  await stop;
});
