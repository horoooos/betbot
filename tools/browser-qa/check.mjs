import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const root=new URL('../../',import.meta.url),out=new URL('work/browser-qa/',root),base=process.env.SITE_URL||'http://localhost:8765';
await fs.mkdir(out,{recursive:true});const report={checks:[],players:[],pageErrors:[]};
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
const context=await browser.newContext({viewport:{width:1280,height:900}});
await context.route('**/fb.js?*',r=>r.fulfill({contentType:'text/javascript',body:'export function track(){};export function navUser(){};export function watchPresence(){};'}));
const page=await context.newPage();report.codecs=await page.evaluate(()=>{const v=document.createElement('video');return{h264:v.canPlayType('video/mp4; codecs="avc1.42E01E"'),webm:v.canPlayType('video/webm; codecs="vp8,vorbis"')};});page.on('pageerror',e=>report.pageErrors.push({message:e.message,stack:e.stack}));
try{
  await page.goto(base+'/broadcasts.html',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelectorAll('#broadcastGrid .broadcast-card').length>0,undefined,{timeout:30000});
  assert.equal(await page.locator('#nativeMaps').count(),0);assert(!(await page.locator('.topnav a').allTextContents()).includes('Эфиры'));
  const cards=await page.locator('#broadcastGrid .broadcast-card').count();assert(cards>0);
  const primary=await page.locator('#broadcastGrid [data-match]').count();assert(primary<=cards);
  await page.screenshot({path:new URL('broadcasts-desktop.png',out).pathname,fullPage:false});report.checks.push({name:'layout',cards,primary});
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:new URL('broadcasts-mobile.png',out).pathname,fullPage:false});await page.setViewportSize({width:1280,height:900});
  const registry=await (await context.request.get('https://aistavvit-default-rtdb.europe-west1.firebasedatabase.app/broadcasts.json')).json();
  const active=registry.matches.filter(m=>m.state==='in').flatMap(m=>m.streams||[]);const twitch=(active.find(s=>s.provider==='twitch')||registry.matches.flatMap(m=>m.streams||[]).find(s=>s.provider==='twitch'))?.url;
  const sources=[{name:'hls',url:'https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8'},{name:'youtube',url:'https://www.youtube.com/watch?v=M7lc1UVf-VE'},{name:'twitch',url:twitch},{name:'rutube',url:registry.channels?.find(c=>c.provider==='rutube')?.url}].filter(s=>s.url);
  for(const source of sources){
    await page.evaluate(async s=>{const m=await import('./watch-video.js?v=2');m.openStream({url:s.url},'Проверка плеера · '+s.name);},source);
    await page.waitForSelector('#broadcastPlayer iframe,#broadcastPlayer video',{timeout:35000}).catch(()=>{});
    await page.waitForFunction(()=>['ready','playing','error','slow','blocked'].includes(document.querySelector('#broadcastPlayer')?.dataset.playerState),undefined,{timeout:40000}).catch(()=>{});
    if(await page.locator('#playBroadcast').isVisible())await page.locator('#playBroadcast').click();
    await page.waitForTimeout(source.name==='twitch'?30000:8000);
    const state=await page.locator('#broadcastPlayer').evaluate(n=>({state:n.dataset.playerState,time:n.dataset.playerTime,rate:n.dataset.playbackRate,status:n.querySelector('#videoStatus').textContent,frame:n.querySelector('iframe')?.getBoundingClientRect().toJSON(),referrer:n.querySelector('iframe')?.referrerPolicy}));
    const media=[];for(const f of page.frames().filter(f=>f===page.mainFrame()||/youtube|twitch|rutube/.test(f.url()))){try{media.push(...await f.locator('video').evaluateAll(vs=>vs.map(v=>({time:v.currentTime,ready:v.readyState,paused:v.paused,width:v.videoWidth,height:v.videoHeight}))));}catch{}}
    report.players.push({provider:source.name,...state,media});assert(await page.locator('#externalBroadcast').isVisible());if(state.frame)assert(state.frame.height>=200&&state.frame.width>=200);
    await page.screenshot({path:new URL('player-'+source.name+'.png',out).pathname,fullPage:false});await page.locator('#closeBroadcast').click();assert.equal(await page.locator('#broadcastPlayer iframe').count(),0);
  }
  const decoded=report.players.some(p=>p.media.some(v=>!v.paused&&v.ready>=2&&v.width>0&&v.time>1));report.checks.push({name:'decodedPlayback',passed:decoded});
  const fixture=JSON.parse(await fs.readFile(new URL('tests/fixtures/dota-motion.json',root),'utf8')),frames=fixture.frames;let count=0;const start=Date.now()/1000;
  await page.route('**/esportsLive/**',async route=>{const index=route.request().url().includes('/index.json'),frame=structuredClone(frames[index?count%frames.length:(count++)%frames.length]);frame.at=start+Math.max(0,count-1)*10;frame.state=5;await route.fulfill({json:index?{at:frame.at,games:{[frame.match_id]:frame}}:frame});});
  await page.goto(base+'/dota.html?d=DOTA&game='+frames[0].match_id+'&debug=1',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>window.__dotaProbe?.().loaded>=2,undefined,{timeout:180000});
  await page.waitForTimeout(21000);const positions=[];for(let i=0;i<30;i++){positions.push(await page.evaluate(()=>window.__dotaProbe()));await page.waitForTimeout(100);}
  let maxStep=0,total=0;for(let i=1;i<positions.length;i++){for(let j=0;j<positions[i].units.length;j++){const a=positions[i-1].units[j],b=positions[i].units[j],step=Math.hypot(b.x-a.x,b.z-a.z);maxStep=Math.max(maxStep,step);total+=step;assert(Number.isFinite(b.x)&&Number.isFinite(b.z)&&Number.isFinite(b.y));}}
  const poseChanged=positions.some((p,i)=>i>0&&p.units.some((u,j)=>u.model?.pose?.some((v,k)=>Math.abs(v-(positions[i-1].units[j].model?.pose?.[k]??v))>1e-6)));report.checks.push({name:'dota',maxStep,total,poseChanged,last:positions.at(-1)});assert(poseChanged,'No skeletal animation changed in the character sample');assert(maxStep<8,'Unexpected instantaneous movement');assert(total>.01,'Characters never moved during the recorded motion test');
  await page.screenshot({path:new URL('dota-desktop.png',out).pathname,fullPage:false});for(let i=0;i<10;i++){await page.locator('#radiantRoster [data-player],#direRoster [data-player]').nth(i).click();await page.waitForTimeout(700);await page.screenshot({path:new URL('hero-'+i+'.png',out).pathname,fullPage:false});}await page.setViewportSize({width:390,height:844});await page.screenshot({path:new URL('dota-mobile.png',out).pathname,fullPage:false});
  assert(decoded,'No provider produced actual decoded video playback');
  const ownErrors=report.pageErrors.filter(e=>/(localhost:8765|horoooos.github.io).*\/(dota-|esports-3d|broadcasts|watch-video)/.test(e.stack||''));assert.equal(ownErrors.length,0,JSON.stringify(ownErrors));
}catch(e){report.failure=e.stack;await page.screenshot({path:new URL('failure.png',out).pathname,fullPage:false}).catch(()=>{});process.exitCode=1;}
finally{await fs.writeFile(new URL('report.json',out),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify({failure:report.failure,checks:report.checks.map(c=>({name:c.name,cards:c.cards,maxStep:c.maxStep,total:c.total})),players:report.players.map(p=>({provider:p.provider,state:p.state,media:p.media})),pageErrors:report.pageErrors}));}
