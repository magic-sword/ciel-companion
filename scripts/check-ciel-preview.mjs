// Connect only to the dedicated local headless browser started for this check.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createServer} from 'node:http';
const root = process.cwd();
const assets = path.join(root,'docs/assets/ciel/production');
const server = createServer(async(req,res)=>{try{const name=decodeURIComponent(new URL(req.url,'http://localhost').pathname).slice(1);if(!/^[a-z0-9.-]+$/.test(name)){res.writeHead(400).end();return;}const data=await fs.readFile(path.join(assets,name));res.setHeader('Content-Type',name.endsWith('.png')?'image/png':'text/html; charset=utf-8');res.end(data);}catch{res.writeHead(404).end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const page = `http://127.0.0.1:${server.address().port}/ciel-gaze-preview.html`;
const endpoint = 'http://127.0.0.1:9228';
const target = await (await fetch(`${endpoint}/json/new?${encodeURIComponent(page)}`, {method:'PUT'})).json();
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
let id=0;
const pending=new Map(), errors=[];
socket.addEventListener('message',event=>{const data=JSON.parse(event.data);if(data.id){const p=pending.get(data.id);if(p){pending.delete(data.id);clearTimeout(p.timeout);data.error?p.reject(Error(JSON.stringify(data.error))):p.resolve(data.result);}}else if(data.method==='Runtime.exceptionThrown'){errors.push(data.params.exceptionDetails);}});
function call(method,params={}){return new Promise((resolve,reject)=>{const n=++id;const timeout=setTimeout(()=>{pending.delete(n);reject(Error(`Timeout ${method}`));},15000);pending.set(n,{resolve,reject,timeout});socket.send(JSON.stringify({id:n,method,params}));});}
async function evaluate(expression){const r=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
const delay=ms=>new Promise(r=>setTimeout(r,ms));
try{
  await call('Runtime.enable');
  await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride',{width:1100,height:1000,deviceScaleFactor:1,mobile:false});
  await call('Page.navigate',{url:page});
  for(let n=0;n<50;n++){if(await evaluate("!document.getElementById('play')?.disabled"))break;await delay(100);}
  if(!await evaluate("!document.getElementById('play').disabled"))throw Error('Preview not ready');
  const initial=await evaluate("document.getElementById('motion').toDataURL() === document.getElementById('normal').toDataURL()");
  if(!initial)throw Error('Normal preview mismatch');
  await evaluate("document.getElementById('play').click()");
  await delay(650);
  const animated=await evaluate("document.getElementById('motion').toDataURL() !== document.getElementById('normal').toDataURL()");
  if(!animated)throw Error('Playback did not advance');
  await evaluate("document.getElementById('play').click()");
  const still=await evaluate("document.getElementById('motion').toDataURL()");
  await delay(200);
  if(still!==await evaluate("document.getElementById('motion').toDataURL()"))throw Error('Stop failed');
  await evaluate("document.getElementById('reset').click()");
  const reset=await evaluate("document.getElementById('motion').toDataURL() === document.getElementById('normal').toDataURL()");
  if(!reset)throw Error('Reset mismatch');
  const expressions=await evaluate(`(()=>{
    const c=document.getElementById('motion'),n=document.getElementById('normal');
    const baseline=n.toDataURL(),checks={};
    for(const [id,value] of [['blink',4],['mouth',4]]){
      const el=document.getElementById(id);el.value=value;el.dispatchEvent(new Event('input'));
      checks[id]=c.toDataURL()!==baseline;
      const data=c.getContext('2d').getImageData(0,0,280,195).data;
      if(data.some((v,i)=>i%4===3&&v!==255))throw Error('Transparent expression pixels');
      document.getElementById('reset').click();
    }
    return checks;
  })()`);
  if(!expressions.blink||!expressions.mouth)throw Error('Expression control did not change the image');
  await evaluate("document.getElementById('once').click()");
  await delay(180);
  const blinkDuring=await evaluate("document.getElementById('blink').value > 0");
  await delay(400);
  const blinkReturned=await evaluate("document.getElementById('motion').toDataURL() === document.getElementById('normal').toDataURL()");
  if(!blinkDuring||!blinkReturned)throw Error('One-shot blink failed');
  const combinations=await evaluate(`(()=>{
    const canvas=document.getElementById('motion'),ctx=canvas.getContext('2d');
    const original=document.getElementById('normal').getContext('2d').getImageData(0,0,280,195).data;
    let count=0;
    for(let f=0;f<17;f++)for(let b=0;b<5;b++)for(let m=0;m<5;m++){
      document.getElementById('frame').value=f;document.getElementById('blink').value=b;document.getElementById('mouth').value=m;
      document.getElementById('mouth').dispatchEvent(new Event('input'));
      const data=ctx.getImageData(0,0,280,195).data;
      for(let p=0;p<280*195;p++){
        const i=p*4,x=p%280,y=Math.floor(p/280);
        if(data[i+3]!==255)throw Error('Combination transparency');
        const eyes=y>=47&&y<111&&((x>=37&&x<115)||(x>=164&&x<244));
        const mouth=y>=133&&y<157&&x>=116&&x<166;
        if(!eyes&&!mouth&&(data[i]!==original[i]||data[i+1]!==original[i+1]||data[i+2]!==original[i+2]))throw Error('Change outside face-feature bounds');
      }
      count++;
    }
    document.getElementById('reset').click();return count;
  })()`);
  const out=path.join(root,'.local/gaze-browser-results');
  await fs.mkdir(out,{recursive:true});
  const screen=await call('Page.captureScreenshot',{format:'png'});
  await fs.writeFile(path.join(out,'preview.png'),Buffer.from(screen.data,'base64'));
  await evaluate("document.getElementById('blink').value=2;document.getElementById('mouth').value=3;document.getElementById('mouth').dispatchEvent(new Event('input'))");
  const expressionScreen=await call('Page.captureScreenshot',{format:'png'});
  await fs.writeFile(path.join(out,'expression-preview.png'),Buffer.from(expressionScreen.data,'base64'));
  const report={initialNormalExact:initial,playbackChangesFrame:animated,stopStable:true,resetNormalExact:reset,expressions,oneShotBlinkReturnsNormal:blinkReturned,opaqueCombinationsWithUnchangedOutside:combinations,runtimeErrors:errors};
  await fs.writeFile(path.join(out,'verification.json'),JSON.stringify(report,null,2));
  if(errors.length)throw Error('Browser runtime errors');
  console.log(JSON.stringify(report));
}finally{socket.close();await fetch(`${endpoint}/json/close/${target.id}`);server.closeAllConnections();server.close();}
