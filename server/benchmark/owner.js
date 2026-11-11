// A stationary fixture actor. Only the privileged scorer changes its position.
import mineflayer from 'mineflayer';
import { readFileSync, writeFileSync, renameSync, existsSync } from 'node:fs';
import { Vec3 } from 'vec3';
import {createHash} from 'node:crypto';
const SOURCE_SHA=createHash('sha256').update(readFileSync(new URL(import.meta.url))).digest('hex');
const bot = mineflayer.createBot({ host: '127.0.0.1', port: 25566, version: '1.21.11',
  username: 'Bench_Owner', auth: 'offline', hideErrors: true });
bot.on('error', error => { console.error(error.code ?? error.name); process.exitCode = 1; });
bot.on('end', () => process.exit(process.exitCode ?? 0));
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => bot.quit());
// The scorer positions this actor; it sends real look/use-item packets through the plugin.
let handled=null, busy=false;
setInterval(async () => {
  const path='/app/benchmark-data/point-command.json';
  if(busy || !bot.entity || !existsSync(path)) return;
  const cmd=JSON.parse(readFileSync(path,'utf8'));
  if(cmd.id===handled) return;
  busy=true; handled=cmd.id;
  const started=Date.now();
  try {
    if(cmd.action==='break_restore') {
      if(!Array.isArray(cmd.position)||cmd.position.length!==3||cmd.position.some(n=>!Number.isInteger(n)||Math.abs(n)>78))throw Error('Invalid calibration target');
      const p=new Vec3(...cmd.position),block=bot.blockAt(p);
      if(block?.name!=='dirt')throw Error('Calibration marker missing');
      const item=bot.inventory.items().find(i=>i.name==='dirt');
      if(!item)throw Error('Calibration supply missing');
      await bot.equip(item,'hand');await bot.dig(block);await bot.waitForTicks(3);
      await bot.placeBlock(bot.blockAt(p.offset(0,-1,0)),new Vec3(0,1,0));await bot.waitForTicks(3);
      if(bot.blockAt(p)?.name!=='dirt')throw Error('Calibration marker not restored');
    }
    else if(cmd.action==='flight') {bot.creative.startFlying();bot.entity.velocity.set(0,0,0);}
    else if(cmd.action==='look_away') await bot.look(0,0,true);
    else if(cmd.action==='gaze') {
      bot.chat('/cielpoint gaze');
      await bot.lookAt(new Vec3(...cmd.look),true);
      await bot.waitForTicks(10);
    }
    else {
      let item=bot.inventory.items().find(i=>i.name==='blaze_rod');
      if(!item) {
        bot.chat('/cielpoint');
        for(let n=0;n<30 && !item;n++) { await bot.waitForTicks(2); item=bot.inventory.items().find(i=>i.name==='blaze_rod'); }
      }
      if(!item) throw Error('Pointer missing');
      await bot.equip(item,'hand');
      bot.setControlState('sneak',Boolean(cmd.append));
      await bot.waitForTicks(3);
      await bot.lookAt(new Vec3(...cmd.look),true);
      await bot.waitForTicks(3);
      bot.activateItem();
      await bot.waitForTicks(4);
      bot.deactivateItem();
      bot.setControlState('sneak',false);
    }
    writeFileSync('/app/benchmark-data/point-ack.tmp',JSON.stringify({id:cmd.id,started,finished:Date.now(),source_sha256:SOURCE_SHA}));
    renameSync('/app/benchmark-data/point-ack.tmp','/app/benchmark-data/point-ack.json');
  } catch(error) { console.error('Point fixture:',error.message); }
  finally { busy=false; }
},100);
