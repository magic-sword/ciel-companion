import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseCommand } from '../src/protocol.js';

const p = (m) => parseCommand(JSON.stringify(m));

test('技の命令を整えて受ける', () => {
  assert.deepEqual(p({ v: 1, type: 'do', id: 3, skill: 'follow' }).cmd, { type: 'do', id: 3, skill: 'follow', args: {} });
  assert.deepEqual(p({ v: 1, type: 'do', id: 4, skill: 'collect', args: { block: 'oak_log', count: 10 } }).cmd.args,
    { block: 'oak_log', count: 10 });
  assert.deepEqual(p({ v: 1, type: 'do', id: 5, skill: 'go_to', args: { x: 10, z: -3.5 } }).cmd.args, { x: 10, z: -3.5 });
  assert.deepEqual(p({ v: 1, type: 'do', id: 6, skill: 'come', args: { player: 'Steve_1' } }).cmd.args, { player: 'Steve_1' });
  assert.deepEqual(p({ v: 1, type: 'do', id: 7, skill: 'craft', args: { item: 'wooden_pickaxe' } }).cmd.args, { item: 'wooden_pickaxe', count: 1 });
});

test('一覧に無い技は動かさない', () => {
  assert.deepEqual(p({ v: 1, type: 'do', id: 1, skill: 'eval', args: {} }), { error: 'unknown_skill', id: 1 });
  assert.deepEqual(p({ v: 1, type: 'do', id: 1, skill: 'constructor' }), { error: 'unknown_skill', id: 1 });
  assert.deepEqual(p({ v: 1, type: 'do', id: 1, skill: '__proto__' }), { error: 'unknown_skill', id: 1 });
});

test('探す技', () => {
  assert.deepEqual(p({ v: 1, type: 'do', id: 3, skill: 'find', args: { block: 'stone' } }).cmd.args, { block: 'stone', how: 'auto' });
  assert.deepEqual(p({ v: 1, type: 'do', id: 3, skill: 'find', args: { block: 'oak_log', how: 'walk' } }).cmd.args, { block: 'oak_log', how: 'walk' });
  assert.equal(p({ v: 1, type: 'do', id: 3, skill: 'find', args: { block: 'stone', how: 'fly' } }).error, 'bad_args');
  assert.equal(p({ v: 1, type: 'do', id: 3, skill: 'find', args: { block: 'stone', how: 'dig', max: 99 } }).error, 'bad_args');
});
test('目的の計画を頼む', () => {
  assert.equal(p({v:1,type:'plan',id:9,item:'stone_pickaxe'}).error,'unknown_type');
});
test('形の違う引数は動かさない', () => {
  const bad = [
    { skill: 'collect', args: { block: 'oak_log', count: 0 } },
    { skill: 'collect', args: { block: 'oak_log', count: 65 } },
    { skill: 'collect', args: { block: 'oak_log', count: 1.5 } },
    { skill: 'collect', args: { block: '../x' } },
    { skill: 'craft', args: { item: 'stick', count: 65 } },
    { skill: 'craft', args: {} },
    { skill: 'go_to', args: { x: 'a', z: 1 } },
    { skill: 'go_to', args: { x: 1, z: Infinity } },
    { skill: 'go_to', args: { x: 1e9, z: 1 } },
    { skill: 'follow', args: { player: 'a b' } },
    { skill: 'follow', args: [] },
  ];
  for (const m of bad) assert.equal(p({ v: 1, type: 'do', id: 2, ...m }).error, 'bad_args', JSON.stringify(m));
});

test('id・版・形の確かめ', () => {
  assert.equal(p({ v: 1, type: 'do', skill: 'follow' }).error, 'bad_id');
  assert.equal(p({ v: 2, type: 'stop' }).error, 'bad_version');
  assert.equal(parseCommand('{').error, 'bad_json');
  assert.equal(parseCommand('[1]').error, 'bad_json');
  assert.equal(p({ v: 1, type: 'shell' }).error, 'unknown_type');
});

test('チャットはコマンドにしない・改行を消す・長さを切る', () => {
  assert.equal(p({ v: 1, type: 'chat', text: '/op Steve' }).error, 'bad_args');
  assert.equal(p({ v: 1, type: 'chat', text: ' \n/op Steve' }).error, 'bad_args');
  assert.equal(p({ v: 1, type: 'chat', text: 'やあ\nみんな' }).cmd.text, 'やあ みんな');
  assert.equal(p({ v: 1, type: 'chat', text: 'あ'.repeat(300) }).cmd.text.length, 256);
  assert.equal(p({ v: 1, type: 'chat', text: '   ' }).error, 'bad_args');
});

test('渡す技の引数', () => {
  assert.deepEqual(p({ v: 1, type: 'do', id: 7, skill: 'give', args: { item: 'oak_log' } }).cmd.args, { item: 'oak_log' });
  assert.deepEqual(p({ v: 1, type: 'do', id: 7, skill: 'give', args: { item: 'oak_log', count: 5, player: 'Steve' } }).cmd.args,
    { player: 'Steve', item: 'oak_log', count: 5 });
  assert.equal(p({ v: 1, type: 'do', id: 7, skill: 'give', args: {} }).error, 'bad_args');
  assert.equal(p({ v: 1, type: 'do', id: 7, skill: 'give', args: { item: 'oak_log', count: 0 } }).error, 'bad_args');
});

test('足元を掘る技の引数', () => {
  assert.equal(p({ v: 1, type: 'do', id: 8, skill: 'dig_down' }).error, 'bad_args');   // 深さは要る
  assert.deepEqual(p({ v: 1, type: 'do', id: 8, skill: 'dig_down', args: { depth: 3 } }).cmd.args, { depth: 3 });
  assert.equal(p({ v: 1, type: 'do', id: 8, skill: 'dig_down', args: { depth: 100 } }).error, 'bad_args');
});

test('景色を見る命令には id が要る', () => {
  assert.deepEqual(parseCommand(JSON.stringify({ v: 1, type: 'look', id: 7 })), { cmd: { type: 'look', id: 7 } });
  assert.equal(parseCommand(JSON.stringify({ v: 1, type: 'look' })).error, 'bad_id');
});

test('オーナーの言葉を実行中の命令へ渡す', () => {
  assert.deepEqual(p({ v: 1, type: 'tell', task: 7, text: '  刈ってね ' }).cmd, { type: 'tell', task: 7, text: '刈ってね' });
  assert.equal(p({ v: 1, type: 'tell', text: 'x' }).error, 'bad_id');
  assert.equal(p({ v: 1, type: 'tell', task: 7, text: ' ' }).error, 'bad_args');
  assert.equal(p({ v: 1, type: 'tell', task: 7, text: 'x'.repeat(2001) }).error, 'bad_args');
});
