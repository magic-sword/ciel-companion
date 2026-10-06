// Connect only to the dedicated local headless browser started for this check.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
const root = process.cwd();
const assets = path.join(root,'docs/assets/ciel/production');
const approvedEyes=process.argv.includes('--approved-eyes');
const pageFile=approvedEyes?'ciel-approved-eye-preview.html':'ciel-gaze-preview.html';
const previewSource=await fs.readFile(path.join(assets,pageFile),'utf8');
const artifactPrefix=previewSource.match(/load\('([a-z0-9-]+)-blink-atlas\.png'/)?.[1];
if(!artifactPrefix)throw Error('Preview does not declare a blink atlas');
const server = createServer(async(req,res)=>{try{const name=decodeURIComponent(new URL(req.url,'http://localhost').pathname).slice(1);if(!/^[a-z0-9.-]+$/.test(name)){res.writeHead(400).end();return;}const data=await fs.readFile(path.join(assets,name));res.setHeader('Content-Type',name.endsWith('.png')?'image/png':'text/html; charset=utf-8');res.end(data);}catch{res.writeHead(404).end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const page = `http://127.0.0.1:${server.address().port}/${pageFile}`;
const endpoint = 'http://127.0.0.1:9228';
const target = await (await fetch(`${endpoint}/json/new?${encodeURIComponent(page)}`, {method:'PUT'})).json();
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
let id=0;
const pending=new Map(), errors=[];
socket.addEventListener('message',event=>{const data=JSON.parse(event.data);if(data.id){const p=pending.get(data.id);if(p){pending.delete(data.id);clearTimeout(p.timeout);data.error?p.reject(Error(JSON.stringify(data.error))):p.resolve(data.result);}}else if(data.method==='Runtime.exceptionThrown'){errors.push(data.params.exceptionDetails);}});
function call(method,params={}){return new Promise((resolve,reject)=>{const n=++id;const timeout=setTimeout(()=>{pending.delete(n);reject(Error(`Timeout ${method}`));},method==='Runtime.evaluate'?180000:15000);pending.set(n,{resolve,reject,timeout});socket.send(JSON.stringify({id:n,method,params}));});}
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
    for(const id of ['blink','mouth']){
      const value=Number(document.getElementById(id).max);
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
  await evaluate("document.getElementById('speed').value='0.25';document.getElementById('once').click()");
  await delay(600);
  const slowBlinkActive=await evaluate("document.getElementById('blink').value > 0");
  await delay(1150);
  const slowBlinkReturned=await evaluate("document.getElementById('motion').toDataURL() === document.getElementById('normal').toDataURL()");
  if(!slowBlinkActive||!slowBlinkReturned)throw Error('Quarter-speed blink failed');
  await evaluate("document.getElementById('speed').value='1'");
  const combinations=await evaluate(`(async()=>{
    const canvas=document.getElementById('motion'),ctx=canvas.getContext('2d');
    const original=document.getElementById('normal').getContext('2d').getImageData(0,0,280,195).data;
    const manifest=await (await fetch('${artifactPrefix}-report.json')).json();
    const {gaze_frames:gazeLevels,blink_levels:blinkLevels,mouth_levels:mouthLevels}=manifest.expression_atlas;
    if(blinkLevels!==33||mouthLevels!==33||gazeLevels!==17)throw Error('Unexpected atlas levels');
    if(Number(document.getElementById('blink').max)!==blinkLevels-1)throw Error('Blink control/atlas mismatch');
    if(Number(document.getElementById('mouth').max)!==mouthLevels-1)throw Error('Mouth control/atlas mismatch');
    const eyes=new Set(manifest.browser_masks.eye_pixels),hair=new Set(manifest.browser_masks.hair_pixels);
    const fixedContours=new Set(Object.values(manifest.stationary_fold_pixels??{}).flat().map(([x,y])=>y*280+x));
    if(fixedContours.size!==520)throw Error('Missing separated stationary contours');
    if(hair.size<61||!eyes.size)throw Error('Missing semantic validation masks');
    const hairAlpha=manifest.hair_alpha_compositing;
    const sourceHair=new Set(manifest.browser_masks.source_hair_pixels);
    if(!hairAlpha||sourceHair.size!==manifest.foreground_source_pixels||hair.size+hairAlpha.pixels.length!==sourceHair.size||hairAlpha.underlays.length!==gazeLevels*blinkLevels)throw Error('Incomplete hair alpha evidence');
    if([...hair].some(pixel=>!sourceHair.has(pixel))||new Set(hairAlpha.pixels.map(p=>p.pixel)).size!==hairAlpha.pixels.length)throw Error('Invalid hair coverage');
    for(const {pixel,rgba} of hairAlpha.pixels){
      if(!sourceHair.has(pixel)||hair.has(pixel)||!eyes.has(pixel)||rgba[3]<=0||rgba[3]>=255)throw Error('Invalid translucent hair ownership');
    }
    document.getElementById('frame').value=8;document.getElementById('blink').value=blinkLevels-1;
    document.getElementById('mouth').value=0;document.getElementById('mouth').dispatchEvent(new Event('input'));
    const closed=ctx.getImageData(0,0,280,195).data;
    let count=0;
    for(let f=0;f<gazeLevels;f++)for(let b=0;b<blinkLevels;b++)for(let m=0;m<mouthLevels;m++){
      document.getElementById('frame').value=f;document.getElementById('blink').value=b;document.getElementById('mouth').value=m;
      document.getElementById('mouth').dispatchEvent(new Event('input'));
      const data=ctx.getImageData(0,0,280,195).data;
      for(let p=0;p<280*195;p++){
        const i=p*4,x=p%280,y=Math.floor(p/280);
        if(data[i+3]!==255)throw Error('Combination transparency');
        const mouth=y>=133&&y<157&&x>=116&&x<166;
        const same=(a,z)=>a[i]===z[i]&&a[i+1]===z[i+1]&&a[i+2]===z[i+2];
        if(!eyes.has(p)&&!mouth&&!same(data,original))throw Error('Change outside traced feature masks');
        if(hair.has(p)&&!same(data,original))throw Error('Foreground hair was covered');
        if(fixedContours.has(p)&&!same(data,original))throw Error('Stationary eyelid/hair contour changed');
        if(b===blinkLevels-1&&eyes.has(p)&&!same(data,closed))throw Error('Iris or highlight remains visible on full closure');
      }
      const underneath=hairAlpha.underlays[b*gazeLevels+f];
      for(let h=0;h<hairAlpha.pixels.length;h++){
        const {pixel,rgba}=hairAlpha.pixels[h],alpha=rgba[3]/255;
        for(let c=0;c<3;c++){
          const expected=Math.round(rgba[c]*alpha+underneath[h][c]*(1-alpha));
          if(Math.abs(data[pixel*4+c]-expected)>1)throw Error('Translucent hair compositing mismatch');
        }
      }
      if(b===0&&[0,8,16].includes(f))for(const [x,y] of [[87,68],[192,66]]){
        const source=4*(y*280+x),target=4*(y*280+x+(f-8)/2);
        for(let c=0;c<3;c++)if(data[target+c]!==original[source+c])throw Error('Primary highlight detached from iris');
      }
      count++;
    }
    document.getElementById('reset').click();return count;
  })()`);
  const out=path.join(root,approvedEyes?'.local/approved-eye-browser-results':'.local/gaze-browser-results');
  await fs.mkdir(out,{recursive:true});
  const screen=await call('Page.captureScreenshot',{format:'png'});
  await fs.writeFile(path.join(out,'preview.png'),Buffer.from(screen.data,'base64'));
  await evaluate("document.getElementById('frame').value=16;document.getElementById('blink').value=Number(document.getElementById('blink').max)*.75;document.getElementById('mouth').value=document.getElementById('mouth').max;document.getElementById('mouth').dispatchEvent(new Event('input'))");
  const expressionScreen=await call('Page.captureScreenshot',{format:'png'});
  await fs.writeFile(path.join(out,'expression-preview.png'),Buffer.from(expressionScreen.data,'base64'));
  await evaluate("document.getElementById('blink').value=document.getElementById('blink').max;document.getElementById('mouth').dispatchEvent(new Event('input'))");
  const closedScreen=await call('Page.captureScreenshot',{format:'png'});
  await fs.writeFile(path.join(out,'closed-preview.png'),Buffer.from(closedScreen.data,'base64'));
  const report={initialNormalExact:initial,playbackChangesFrame:animated,stopStable:true,resetNormalExact:reset,expressions,oneShotBlinkReturnsNormal:blinkReturned,quarterSpeedBlinkReturnsNormal:slowBlinkReturned,opaqueCombinationsWithUnchangedOutside:combinations,foregroundHoldoutsPreserved:true,closedEyesIndependentOfGaze:true,primaryHighlightsFollowIris:true,runtimeErrors:errors};
  report.artifactSha256={};
  report.estimatedHairAlphaCompositingVerified=true;
  report.stationaryContourPixelsPreserved=520;
  for(const name of [pageFile,`${artifactPrefix}-blink-atlas.png`,`${artifactPrefix}-mouth-atlas.png`,`${artifactPrefix}-report.json`]){
    report.artifactSha256[name]=createHash('sha256').update(await fs.readFile(path.join(assets,name))).digest('hex');
  }
  await fs.writeFile(path.join(out,'verification.json'),JSON.stringify(report,null,2));
  if(errors.length)throw Error('Browser runtime errors');
  console.log(JSON.stringify(report));
}finally{socket.close();await fetch(`${endpoint}/json/close/${target.id}`);server.closeAllConnections();server.close();}
