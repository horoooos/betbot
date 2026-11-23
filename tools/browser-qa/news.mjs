import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const base=process.env.NEWS_SITE||'http://127.0.0.1:8767',out=new URL('../../work/news-proof/',import.meta.url);
await fs.mkdir(out,{recursive:true});const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1280,height:900}});const report={checks:[],errors:[]};page.on('pageerror',e=>report.errors.push(e.message));
try{
 if(!process.env.NEWS_SITE)await page.route('**/fb.js?*',r=>r.fulfill({contentType:'text/javascript',body:'export function navUser(){};export function track(){};export function countView(){};export function showViews(){};'}));
 await page.goto(base+'/news/?verify='+Date.now(),{waitUntil:'domcontentloaded'});
 await page.locator('.arch-f').waitFor();
 const text=await page.locator('body').innerText();for(const s of ['@media','grid-template-columns','overflow-wrap','аккуратные переносы'])assert(!text.includes(s),'CSS visible in news: '+s);
 await page.getByRole('heading',{name:'📚 Архив новостей'}).scrollIntoViewIfNeeded();if(process.env.NEWS_SITE)await page.waitForFunction(()=>[...document.querySelectorAll('.arch img')].some(i=>i.complete&&i.naturalWidth>0&&!i.src.startsWith('data:')),undefined,{timeout:20000});await page.screenshot({path:new URL('news-desktop.png',out).pathname});report.checks.push('desktop archive has no visible CSS');
 await page.setViewportSize({width:390,height:844});await page.locator('.arch-f').scrollIntoViewIfNeeded();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:new URL('news-mobile.png',out).pathname});report.checks.push('mobile archive fits viewport');
 const chips=page.locator('.arch-f button');if(await chips.count()>1){await chips.nth(1).click();assert(await page.locator('.arch a:visible').count()>0);report.checks.push('archive sport filter works');}
 assert.deepEqual(report.errors,[]);
}catch(e){report.failure=e.stack;await page.screenshot({path:new URL('failure.png',out).pathname}).catch(()=>{});process.exitCode=1;}
finally{await fs.writeFile(new URL('report.json',out),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify(report));}
