// Read-only production smoke check: no mocked app modules, no subscriptions created.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const base='https://horoooos.github.io/betbot',out=new URL('../../work/growth-live/',import.meta.url);
await fs.mkdir(out,{recursive:true});const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1280,height:900}});const report={checks:[],errors:[]};page.on('pageerror',e=>report.errors.push(e.message));
try{
 await page.goto(base+'/follow.html?v='+Date.now(),{waitUntil:'domcontentloaded'});
 await page.getByRole('button',{name:'Сохранить и включить'}).waitFor({timeout:60000});
 assert((await page.locator('[data-topic]').count())>5);report.checks.push('production Firebase module and interests UI loaded');
 assert.equal(await page.evaluate(()=>Notification.permission),'default');report.checks.push('notification permission was not requested automatically');
 await page.screenshot({path:new URL('follow-desktop.png',out).pathname});
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:new URL('follow-mobile.png',out).pathname,fullPage:true});
 const data=await (await page.request.get(base+'/topics.json?v='+Date.now())).json();
 for(const kind of ['team','league']){
  const t=data.topics.find(t=>t.kind===kind&&t.url);assert(t);
  await page.goto(base+'/'+t.url,{waitUntil:'domcontentloaded'});await page.locator('#growthShareButton').waitFor({timeout:30000});
  assert((await page.locator('h1').innerText()).length>0);report.checks.push('production '+kind+' page and share control loaded');
 }
 await page.goto(base+'/digest/',{waitUntil:'domcontentloaded'});await page.locator('.grid a').first().click();assert(await page.getByRole('link',{name:'Читать новость полностью'}).count()>=3);report.checks.push('production digest and full-news links');
 assert.deepEqual(report.errors,[]);
}catch(e){report.failure=e.stack;await page.screenshot({path:new URL('failure.png',out).pathname}).catch(()=>{});process.exitCode=1;}
finally{await fs.writeFile(new URL('report.json',out),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify(report));}
