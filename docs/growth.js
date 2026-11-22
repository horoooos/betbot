let api;
const pushInterests=(...a)=>api.pushInterests(...a),getInterests=(...a)=>api.getInterests(...a),growthEvent=(...a)=>api.growthEvent(...a);
const root=new URL('./',import.meta.url),$=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function shareURL(url=location.href){const u=new URL(url);const keep={};for(const k of ['s','p','e','game','d','h','a'])if(u.searchParams.has(k))keep[k]=u.searchParams.get(k);u.search='';for(const [k,v] of Object.entries(keep))u.searchParams.set(k,v);u.hash='';u.searchParams.set('utm_source','share');u.searchParams.set('utm_medium','reader');return u.href;}
export async function mount(fb){
 if(fb)api=fb;
 if(!api)return;
 if($('#growthPreferences')&&!$('#growthPreferences').dataset.ready){$('#growthPreferences').dataset.ready='1';await preferences();}
 const controls=$('.watch-controls')||$('#cam')?.parentElement;
 if(controls&&!document.getElementById('growthMatchShare')){const b=document.createElement('button');b.id='growthMatchShare';b.className='pill';b.textContent='↗ Поделиться';b.onclick=async()=>{try{const url=shareURL();if(navigator.share)await navigator.share({title:document.title,url});else await navigator.clipboard.writeText(url);await growthEvent('share');b.textContent='Ссылка готова';}catch(e){if(e.name!=='AbortError')b.textContent='Не удалось скопировать';}};controls.append(b);const a=document.createElement('a');a.className='pill';a.href=new URL('follow.html',root);a.textContent='🔔 Мой спорт';controls.append(a);}
 if(document.getElementById('growthShare')||/\/(admin|profile|live|dota|esports|watch)\.html$/.test(location.pathname))return;
 const main=$('main');if(!main)return;
 const box=document.createElement('section');box.id='growthShare';box.className='card';box.style.cssText='margin:28px 0;display:flex;gap:12px;align-items:center;flex-wrap:wrap';
 box.innerHTML=`<div style="flex:1;min-width:180px"><b>Ваш спорт — без лишнего</b><p class="muted small" style="margin:6px 0">Следите за любимыми командами и делитесь интересными материалами.</p></div><a class="btn gold" href="${new URL('follow.html',root)}">Мой спорт</a><button class="btn" id="growthShareButton" type="button">Поделиться</button><span role="status" id="growthShareStatus"></span>`;
 main.insertBefore(box,main.querySelector('footer'));
 box.querySelector('button').onclick=async()=>{const url=shareURL(),title=document.title;try{if(navigator.share){await navigator.share({title,url});await growthEvent('share');}else{await navigator.clipboard.writeText(url);await growthEvent('share');$('#growthShareStatus').textContent='Ссылка скопирована';}}catch(e){if(e.name!=='AbortError')$('#growthShareStatus').textContent='Скопируйте адрес страницы из браузера';}};
}
async function preferences(){
 const box=$('#growthPreferences');if(!box)return;
 try{
  const r=await fetch(new URL('topics.json',root));if(!r.ok)throw Error('Не удалось загрузить список интересов');const {topics}=await r.json();const saved=await getInterests();const selected=new Set(Object.keys(saved.topics||{}));const initial=new URLSearchParams(location.search).get('topic');if(topics.some(t=>t.id===initial))selected.add(initial);
  box.innerHTML=`<label>Найти команду или турнир<input id="interestSearch" type="search" placeholder="Название команды, игрока, турнира" style="width:100%;padding:14px;margin:10px 0"></label><div id="interestTopics" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px;max-height:420px;overflow:auto"></div><h2>Какие события присылать?</h2><div style="display:flex;gap:18px;flex-wrap:wrap">${[['news','Новости'],['start','Начало матча'],['result','Результат матча']].map(([k,n])=>`<label><input type="checkbox" data-event="${k}" ${saved.events?.[k]!==false?'checked':''}> ${n}</label>`).join('')}</div><p class="muted small">Не больше 5 новостей в сутки; старты и результаты — только по выбранным интересам. Можно отключить всё одной кнопкой. Браузер запросит разрешение после нажатия «Сохранить».</p><div class="row"><button class="btn gold" id="saveInterests">Сохранить и включить</button><button class="btn" id="clearInterests">Отключить подписки</button></div><p role="status" id="interestStatus"></p>`;
  const draw=q=>{$('#interestTopics').innerHTML=topics.filter(t=>!q||t.label.toLocaleLowerCase().includes(q)).map(t=>`<label style="padding:10px;border:1px solid var(--line);border-radius:12px;display:flex;gap:8px;align-items:center"><input type="checkbox" data-topic="${t.id}" ${selected.has(t.id)?'checked':''}><span>${esc(t.label)}${t.url?` <a href="${new URL(t.url,root)}" aria-label="Открыть страницу">↗</a>`:''}</span></label>`).join('');};draw('');
  $('#interestTopics').onchange=e=>{if(!e.target.dataset.topic)return;e.target.checked?selected.add(e.target.dataset.topic):selected.delete(e.target.dataset.topic);};
  $('#interestSearch').oninput=e=>draw(e.target.value.trim().toLocaleLowerCase());
  $('#saveInterests').onclick=async()=>{const status=$('#interestStatus');if(!selected.size){status.textContent='Сначала выберите хотя бы один интерес.';return;}const events=Object.fromEntries([...box.querySelectorAll('[data-event]')].map(i=>[i.dataset.event,i.checked]));if(!Object.values(events).some(Boolean)){status.textContent='Выберите хотя бы один тип события.';return;}status.textContent='Сохраняем…';try{await pushInterests(Object.fromEntries([...selected].map(k=>[k,true])),events);await growthEvent('follow');status.textContent='Готово! Подписки включены для этого браузера.';}catch(e){status.textContent=e.message||'Не удалось сохранить. Попробуйте ещё раз.';}};
  $('#clearInterests').onclick=async()=>{try{await pushInterests({}, {news:false,start:false,result:false},false);selected.clear();draw($('#interestSearch').value.trim().toLocaleLowerCase());await growthEvent('unfollow');$('#interestStatus').textContent='Подписки по интересам отключены.';}catch(e){$('#interestStatus').textContent=e.message;}};
 }catch(e){box.textContent=e.message+' Попробуйте обновить страницу.';}
}

