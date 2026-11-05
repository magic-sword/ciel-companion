import assert from 'node:assert/strict';
import { test } from 'node:test';

import { pickFood } from '../src/care.js';

const foods = { bread: { foodPoints: 5 }, cooked_beef: { foodPoints: 8 }, rotten_flesh: { foodPoints: 4 }, apple: { foodPoints: 4 } };
const items = [{ name: 'bread' }, { name: 'rotten_flesh' }, { name: 'cooked_beef' }, { name: 'oak_log' }];

test('おなかが減ったら、いちばんおなかがふくれるものを食べる', () => {
  assert.equal(pickFood(items, foods, 10, 20).name, 'cooked_beef');
});

test('満腹・まだ大丈夫なら食べない', () => {
  assert.equal(pickFood(items, foods, 20, 5), null);
  assert.equal(pickFood(items, foods, 16, 18), null);
});

test('体力が減っていれば、空腹が満タンでなくても食べる（体力を戻すため）', () => {
  assert.equal(pickFood(items, foods, 17, 10).name, 'cooked_beef');
});

test('具合が悪くなるものは食べない', () => {
  assert.equal(pickFood([{ name: 'rotten_flesh' }, { name: 'oak_log' }], foods, 5, 20), null);
});
