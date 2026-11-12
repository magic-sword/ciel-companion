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
