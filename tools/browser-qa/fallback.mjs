import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const base=process.env.FALLBACK_SITE||'http://127.0.0.1:8768';
const report=JSON.parse(await fs.readFile(new URL('../../work/fallback-site/report.json',import.meta.url),'utf8'));
const out=new URL('../../work/fallback-proof/',import.meta.url);await fs.mkdir(out,{recursive:true});
const b=await chromium.launch({channel:'chrome'});const p=await b.newPage({viewport:{width:1280,height:900}});const errors=[];p.on('pageerror',e=>errors.push(e.message));
if(!process.env.FALLBACK_SITE)await p.route('**/fb.js?*',r=>r.fulfill({contentType:'text/javascript',body:'export function navUser(){};export function track(){};export function countView(){};export function showViews(){};'}));
try{
 for(const m of report){
  const r=await p.goto(base+'/'+m.url+'?check='+Date.now(),{waitUntil:'domcontentloaded'});assert.equal(r.status(),200);
  const body=await p.locator('main').innerText();assert(body.includes(m.home));assert(body.includes(m.away));assert(body.includes(m.tip));
  for(const s of ['Временный прогноз','временный режим',' · эксперимент'])assert(!body.includes(s));
  assert(await p.locator('a[href="https://t.me/aistavvit/'+m.message_id+'"]').count()>0,'Missing Telegram link');
 }
 if(process.env.FALLBACK_SITE){
  const matches=await (await p.request.get(base+'/matches.json?check='+Date.now())).json();
  for(const m of report){const found=matches.find(x=>String(x.id)===String(m.id));assert(found&&found.bot&&found.bot.main,'Prediction missing in matches.json: '+m.id);}
 }
 await p.screenshot({path:new URL('prediction-desktop.png',out).pathname,fullPage:true});
 await p.setViewportSize({width:390,height:844});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await p.screenshot({path:new URL('prediction-mobile.png',out).pathname,fullPage:true});
 await p.goto(base+'/predictions/?check='+Date.now(),{waitUntil:'domcontentloaded'});
 assert(await p.locator('a[href]').count()>0);await p.screenshot({path:new URL('predictions-list.png',out).pathname,fullPage:true});
 assert.deepEqual(errors,[]);
 await fs.writeFile(new URL('report.json',out),JSON.stringify({checked:report,errors},null,2));
}finally{await b.close();}
