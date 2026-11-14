import assert from 'node:assert/strict';
import { test } from 'node:test';
import { within } from '../src/vendor/mindcraft/src/agent/library/deadline.js';

const bot = () => ({ output: '', interrupt_code: false, stopDigging() {}, pathfinder: { stop() {} } });
// Work like a collecting loop: it goes on until the interrupt flag is raised.
const loop = (b, log) => async () => {
  while (!b.interrupt_code) { log.push(1); await new Promise(r => setTimeout(r, 20)); }
};

test('work past its time is stopped, not left running beside what comes next', async () => {
  const b = bot(), log = [];
  assert.equal(await within(b, loop(b, log), 0.1), false);
  const after = log.length;
  await new Promise(r => setTimeout(r, 100));
  assert.equal(log.length, after, 'the loop ended');
  assert.equal(b.interrupt_code, false, 'the plan can go on');
});

test('a real stop that comes while timed-out work is ending stays', async () => {
  const b = bot();
  const work = async () => { await new Promise(r => setTimeout(r, 300)); };
  const pending = within(b, work, 0.05);
  await new Promise(r => setTimeout(r, 100));
  b.deadlineStop = null;            // what requestInterrupt does
  b.interrupt_code = true;
  assert.equal(await pending, false);
  assert.equal(b.interrupt_code, true);
});
