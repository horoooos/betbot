import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const out=new URL('../../work/growth-preview/',import.meta.url),base=process.env.SITE_URL||'http://127.0.0.1:8766';
const browser=await chromium.launch({channel:'chrome',headless:true});
const context=await browser.newContext({viewport:{width:1280,height:900}});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
const report={checks:[],mode:'Browser UI with simulated notification permission and persistence; no real subscriber created'};
try{
 await context.route('**/fb.js?*',r=>r.fulfill({contentType:'text/javascript',body:`export function navUser(){};export function track(){};export function countView(){};export function showViews(){};
 let saved={topics:{},events:{}};const api={getInterests:async()=>saved,pushInterests:async(topics,events)=>{saved={topics,events};window.__saved=saved;},growthEvent:async n=>{(window.__events??=[]).push(n);}};import('./growth.js?v=1').then(m=>m.mount(api));`}));
 await page.goto(base+'/follow.html',{waitUntil:'networkidle'});
 await page.getByRole('button',{name:'Сохранить и включить'}).waitFor();
 await page.getByRole('button',{name:'Сохранить и включить'}).click();assert((await page.locator('#interestStatus').innerText()).includes('выберите'));
 await page.locator('[data-topic]').first().check();await page.getByRole('button',{name:'Сохранить и включить'}).click();
 await page.waitForFunction(()=>window.__saved&&Object.keys(window.__saved.topics).length===1);
 assert.equal(await page.evaluate(()=>window.__events.includes('follow')),true);report.checks.push('explicit opt-in and selection validation');
 await page.screenshot({path:new URL('follow-desktop.png',out).pathname,fullPage:false});
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:new URL('follow-mobile.png',out).pathname,fullPage:false});
 await page.getByRole('button',{name:'Отключить подписки'}).click();await page.waitForFunction(()=>Object.keys(window.__saved.topics).length===0);report.checks.push('unsubscribe clears selected interests');
 const topics=await (await context.request.get(base+'/topics.json')).json();const team=topics.topics.find(t=>t.kind==='team');const league=topics.topics.find(t=>t.kind==='league');
 await page.goto(base+'/'+team.url,{waitUntil:'networkidle'});assert.equal(await page.getByRole('link',{name:'Следить за командой'}).count(),1);assert(await page.locator('meta[property="og:image"]').getAttribute('content'));await page.screenshot({path:new URL('team-mobile.png',out).pathname});
 await page.goto(base+'/'+league.url,{waitUntil:'networkidle'});assert(await page.locator('.grid .card').count()>0);report.checks.push('team and tournament navigation');
 await page.setViewportSize({width:1280,height:900});await page.goto(base+'/digest/',{waitUntil:'networkidle'});await page.locator('.grid a').first().click();assert(await page.locator('h1').innerText());assert(await page.locator('a').filter({hasText:'Читать новость полностью'}).count()>=3);await page.screenshot({path:new URL('digest-desktop.png',out).pathname,fullPage:true});report.checks.push('digest has complete links to original articles');
 const share=await page.evaluate(async()=>{const m=await import('./../growth.js?v=1');return m.shareURL(location.href+'?token=must-not-share#fragment');});assert(!share.includes('token='));assert(share.includes('utm_source=share'));report.checks.push('share URLs discard parameters and fragments');
 assert.deepEqual(errors,[]);
}catch(e){report.failure=e.stack;await page.screenshot({path:new URL('failure.png',out).pathname}).catch(()=>{});process.exitCode=1;}
finally{report.pageErrors=errors;await fs.writeFile(new URL('browser-report.json',out),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify(report));}
