import test from 'node:test';
import assert from 'node:assert/strict';
import {SessionModel} from '../src/mindcraft/session-model.js';

test('native memory cancellation resolves empty while genuine inference failures remain errors',async()=>{
  let reject;
  const token={cancelled:false},model={sendRequest:()=>new Promise((_,r)=>{reject=r;})};
  const session={model,token};
  const provider=new SessionModel(()=>session);
  const pending=provider.sendRequest([],'memory summary');
  token.cancelled=true;reject(new Error('HTTP409'));
  assert.equal(await pending,'');
  token.cancelled=false;
  const stale=provider.sendRequest([],'old conversation');
  session.model={};reject(new Error('session revoked'));
  assert.equal(await stale,'');
  session.model={sendRequest:async()=>{throw new Error('HTTP502');}};
  await assert.rejects(provider.sendRequest([],'real failure'),/HTTP502/);
});
