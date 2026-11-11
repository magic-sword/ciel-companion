import test from 'node:test';
import assert from 'node:assert/strict';
import {confirmedCrafting} from '../src/craft-sync.js';

test('crafting output is taken only after the server window replaces the prediction',async()=>{
  const events=[],window={type:'minecraft:crafting',output:'predicted',slots:[{name:'wooden_pickaxe',count:1}]},bot={currentWindow:window,
    async _syncWindow(w){events.push('sync');w.output='server';},
    async putAway(slot){events.push(window.output);return slot;}};
  confirmedCrafting(bot);confirmedCrafting(bot);
  assert.equal(await bot.putAway(0),0);assert.deepEqual(events,['sync','server']);
  events.length=0;await bot.putAway(10);assert.deepEqual(events,['server']);
});

test('a missing sync or failed server read cannot consume a predicted crafting output',async()=>{
  for(const sync of [undefined,async()=>{throw new Error('disconnected');},async()=>{}]){
    let taken=false;
    const bot={currentWindow:{type:'minecraft:crafting'},_syncWindow:sync,async putAway(){taken=true;}};
    confirmedCrafting(bot);await assert.rejects(bot.putAway(0));assert.equal(taken,false);
  }
});

test('each table click confirms the cursor before the next ingredient is placed',async()=>{
  const window={type:'minecraft:crafting',selectedItem:null},observed=[];
  let serverCursor=null;
  const bot={currentWindow:window,async putAway(){},
    async clickWindow(slot){observed.push(window.selectedItem);serverCursor=slot===9?'stick':null;window.selectedItem='stale planks';},
    async _syncWindow(w){w.selectedItem=serverCursor;}};
  confirmedCrafting(bot);await bot.clickWindow(9);await bot.clickWindow(8);
  assert.deepEqual(observed,[null,'stick']);assert.equal(window.selectedItem,null);
});
