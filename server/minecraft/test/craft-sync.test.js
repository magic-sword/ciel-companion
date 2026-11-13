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

test('2x2 hand crafting confirms clicks, the output and the final inventory with the server',async()=>{
  const events=[],inventory={type:'minecraft:inventory',slots:[]};
  const bot={currentWindow:null,inventory,
    async _syncWindow(w){events.push(['sync',w.type]);w.slots[0]=w.serverOutput??null;},
    async clickWindow(slot){events.push(['click',slot]);},
    async putAway(slot){events.push(['take',slot]);},
    async craft(){
      await bot.clickWindow(36);inventory.slots[0]={name:'oak_planks',count:4};await bot.putAway(0);
    }};
  confirmedCrafting(bot);
  inventory.serverOutput={name:'oak_planks',count:4};
  await bot.craft({},1,null);
  assert.deepEqual(events,[['click',36],['sync','minecraft:inventory'],['sync','minecraft:inventory'],['take',0],['sync','minecraft:inventory']]);
  assert.equal(bot.__handCrafting,false);
  // The server did not produce the output: the predicted planks are never taken.
  events.length=0;inventory.serverOutput=null;
  await assert.rejects(bot.craft({},1,null),/craft_output_unverified/);
  assert.ok(!events.some(([kind])=>kind==='take'));
  assert.equal(bot.__handCrafting,false);
});

test('inventory clicks outside crafting are not synchronized',async()=>{
  const events=[];
  const bot={currentWindow:null,inventory:{type:'minecraft:inventory',slots:[]},
    async _syncWindow(){events.push('sync');},async clickWindow(){events.push('click');},async putAway(){events.push('take');}};
  confirmedCrafting(bot);
  await bot.clickWindow(36);await bot.putAway(0);
  assert.deepEqual(events,['click','take']);
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
