import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { cacheLayout } from '../src/mindcraft/prompt-layout.js';

const upstream = JSON.parse(readFileSync(new URL('../src/vendor/mindcraft/profiles/defaults/_default.json', import.meta.url))).conversing;
const words = text => text.replace(/\s+/g, ' ').trim().split(' ').sort();

test('vendored conversing prompt keeps its wording and puts fixed lines first', () => {
  const { reference, template } = cacheLayout(upstream);
  assert.ok(template.startsWith(reference + '\n'));
  assert.deepEqual(words(template), words(upstream));
  assert.ok(reference.includes('$COMMAND_DOCS') && reference.includes('$NAME'));
  for (const changing of ['$SELF_PROMPT', '$MEMORY', '$STATS', '$INVENTORY', '$EXAMPLES', 'Conversation Begin:'])
    assert.ok(!reference.includes(changing), changing);
  const rest = template.slice(reference.length + 1).split('\n');
  assert.deepEqual(rest, ['$SELF_PROMPT', "Summarized memory:'$MEMORY'", '$STATS', '$INVENTORY', '$EXAMPLES', 'Conversation Begin:']);
});

test('templates without exactly one command docs placeholder are rejected', () => {
  assert.throws(() => cacheLayout('You are $NAME.\n$STATS'), /COMMAND_DOCS/);
  assert.throws(() => cacheLayout('$COMMAND_DOCS\n$COMMAND_DOCS'), /COMMAND_DOCS/);
});
