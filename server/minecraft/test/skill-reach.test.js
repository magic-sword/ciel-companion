import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { test } from 'node:test';

// The body runs no code the model writes (!newAction is off), so a skill in skills.js is usable
// only when a command, a mode or a plan calls it. A skill that nothing calls cannot be used at
// all, as sowing on farmland once could not. Each skill is called from one of these, or is listed
// here with what covers it instead.
const AGENT = new URL('../src/vendor/mindcraft/src/agent/', import.meta.url);
const INTERNAL = {
  log: 'the output of every skill',
  goToGoal: 'the walking under goToPosition and the other movement skills',
  useToolOnBlock: 'the block half of useToolOn (!useOn)',
  useDoor: 'the pathfinder opens doors on the way; !useBlockAt opens or closes one',
  activateNearestBlock: '!useOn("hand", type) for the nearest, !useBlockAt for one place',
};

const read = path => readFileSync(new URL(path, AGENT), 'utf8');
const callers = [
  ...readdirSync(new URL('commands/', AGENT)).filter(f => f.endsWith('.js')).map(f => `commands/${f}`),
  'modes.js',
  ...readdirSync(new URL('library/', AGENT)).filter(f => f.endsWith('.js') && f !== 'skills.js').map(f => `library/${f}`),
].map(path => [path, read(path)]);

const skills = [...read('library/skills.js').matchAll(/^\s*export (?:async )?function (\w+)/gm)].map(m => m[1]);

test('every skill can be reached without code the model writes', () => {
  assert.ok(skills.length > 40);
  const unreached = skills.filter(name => !(name in INTERNAL)
    && !callers.some(([, text]) => new RegExp(`skills\\.${name}\\(`).test(text)));
  assert.deepEqual(unreached, [], `Skills no command, mode or plan calls: ${unreached.join(', ')}. `
    + 'Give each a command (commands/actions.js) or a plan step, or list it in INTERNAL with what covers it.');
});

test('the skills listed as covered elsewhere still exist', () => {
  assert.deepEqual(Object.keys(INTERNAL).filter(name => !skills.includes(name)), []);
});
