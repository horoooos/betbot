const q=new URLSearchParams(location.search),id=q.get('e'),div=q.get('d'),native=q.get('game');
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const DB='https://aistavvit-default-rtdb.europe-west1.firebasedatabase.app/esportsLive.json';
let match=null,matches=[],arena=null,selected=null,lastId=null,busy=false;
let heroes={};
try {const r=await fetch("dota-heroes.json");if(r.ok)heroes=await r.json();}catch(e){}
const normalized=s=>String(s||'').toLowerCase().replace(/\b(team|gaming|esports)\b/g,'').replace(/[^\p{L}\p{N}]/gu,'');
const number=v=>v!==null&&v!==undefined&&Number.isFinite(Number(v))?Number(v).toFixed(2):'—';
const pair=frame=>(frame.teams||[]).map(t=>normalized(t.name)).sort().join('|');
function titleAndScore(m){
  $('esTitle').textContent=m.home+' — '+m.away;document.title=m.home+' — '+m.away+' · АИ СТАВИТ';
  const team=(name,logo)=>`<div class="es-team">${logo?`<img src="${esc(logo)}" alt="" onerror="this.hidden=true">`:`<span class="es-avatar">${esc(name.slice(0,1))}</span>`}<strong>${esc(name)}</strong></div>`;
  const status={pre:'Ожидается начало',in:'● Серия идёт',post:'Серия завершена'}[m.state]||'Ожидаем обновления';
  const score=['in','post'].includes(m.state)?`${esc(m.hs??'—')} : ${esc(m.as??'—')}`:m.state==='pre'?'VS':'— : —';
  $('scoreboard').innerHTML=`<div class="es-meta"><span>🎮 ${esc(m.league||'Dota 2')}${m.bo?' · BO'+esc(m.bo):''}</span><span>${m.kickoff?new Date(m.kickoff).toLocaleString('ru-RU',{timeZone:'Europe/Moscow',day:'numeric',month:'long',hour:'2-digit',minute:'2-digit'})+' МСК':'Живая карта'}</span></div><div class="es-versus">${team(m.home,m.hl)}<div class="es-number">${score}<small>${native?'УБИЙСТВА':'СЧЁТ ПО КАРТАМ'}</small></div>${team(m.away,m.al)}</div><div class="es-status">${status}</div><div class="es-row es-actions" style="margin-top:18px"><span class="es-muted">${native?'Позиции героев по данным Valve':'Прогноз и трансляция в одном месте'}</span><div class="es-row">${m.prediction?`<a href="${esc(m.prediction)}">Полный разбор →</a>`:''}${m.bb?`<a class="primary" href="${esc(m.bb)}" target="_blank" rel="noopener sponsored">Линия матча ↗</a>`:''}</div></div>`;
  const bot=m.bot,main=bot?.main;
  $('prediction').innerHTML=main?`<h2>🎯 Прогноз бота</h2><p class="es-tip">${esc(main.label)}</p><div class="es-row"><span class="es-pill">Коэффициент ${main.est?'≈':''}${number(main.odds)}</span><span class="es-pill">Шанс ${Math.round(main.p*100)}%</span></div><p class="es-muted" style="margin-top:12px">Оценка модели не гарантирует исход матча.</p>`:`<h2>🎯 Прогноз бота</h2><p class="es-muted">${m.tip?esc(m.tip):'Для этого матча прогноз ещё не опубликован.'}</p>`;
  const bar=bot?.bar;if(bar?.length>=2){const home=Number(bar[0]),away=Number(bar.at(-1));if(Number.isFinite(home)&&Number.isFinite(away))$('prediction').innerHTML+=`<div class="es-probs"><span style="width:${Math.round(home*100)}%"></span><span style="flex:1"></span></div><div class="es-prob-labels"><span>П1 ${Math.round(home*100)}%</span><span>П2 ${Math.round(away*100)}%</span></div>`;}
  $('markets').innerHTML='<h2>Оценка исходов</h2>'+(bot?.markets?.length?bot.markets.map(([label,p,odds])=>`<div class="es-market"><span>${esc(label)}<br><small class="es-muted">Шанс ${Math.round(p*100)}%</small></span><b>${odds?number(odds):'—'}</b></div>`).join(''):'<p class="es-muted">Появится вместе с опубликованным разбором.</p>');
}
async function schedule(){
  try {const r=await fetch('matches.json?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error();matches=(await r.json()).filter(m=>m.sport==='esports');match=matches.find(m=>m.id===id&&(!div||m.div===div));
    if(id&&!match){const history=await fetch('forecast-feed.json?v='+Date.now(),{cache:'no-store'});if(history.ok){const old=(await history.json()).find(m=>m.sport==='esports'&&m.id===id&&(!div||m.div===div));if(old)match={...old,league:old.div==='CS2'?'Киберспорт · CS2':'Киберспорт · Dota 2',state:['won','lost'].includes(old.status)?'post':'unknown',hs:old.score?.split(':')[0],as:old.score?.split(':')[1],tip:old.label+' · '+number(old.odds),prediction:old.url};}}
    if(!native){if(match)titleAndScore(match);else{$('esTitle').textContent=id?'Матч временно недоступен':'Киберспорт онлайн';$('scoreboard').innerHTML='<p class="es-muted">'+(id?'Этот матч отсутствует в текущем расписании. Разборы и результаты сохранены в разделе прогнозов.':'Выбери матч из расписания или открой одну из доступных живых карт Dota 2.')+'</p>';}}
    $('schedule').innerHTML=matches.map(m=>`<a class="es-game" href="${esc(m.url)}"><span>${esc(m.league)} · ${new Date(m.kickoff).toLocaleString('ru-RU',{timeZone:'Europe/Moscow',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}</span><strong>${esc(m.home)} — ${esc(m.away)}</strong><span>${esc(m.tip||'Открыть матч →')}</span></a>`).join('')||'<p class="es-muted">Новые матчи появятся после обновления расписания.</p>';
  }catch(e){$('esTitle').textContent='Киберспорт онлайн';$('scoreboard').innerHTML='<p class="es-muted">Не удалось обновить расписание. Попробуем снова через минуту.</p>';}
}
function empty(title,text){$('empty').hidden=false;$('emptyTitle').textContent=title;$('emptyText').textContent=text;$('roster').innerHTML='';arena?.freeze();$('telemetry').textContent='Ожидание данных';}
async function positions(){
  if(busy||document.hidden)return;busy=true;
  try {
    const r=await fetch(DB,{cache:'no-store'});if(!r.ok)throw Error();const data=await r.json(),games=Object.values(data?.games||{});
    const fresh=games.filter(g=>Date.now()/1000-g.at<50);
    $('available').innerHTML=fresh.map(g=>`<a class="es-game" href="esports.html?d=DOTA&game=${encodeURIComponent(g.match_id)}"><span class="es-live-dot">● Dota 2 · живая карта</span><strong>${esc(g.teams.map(t=>t.name).join(' — '))}</strong><span>${Math.floor(Math.max(0,g.game_time)/60)} мин · ${g.teams.map(t=>t.score??'—').join(' : ')} убийств</span></a>`).join('')||'<p class="es-muted">Сейчас нет доступных свежих карт. Проверяем каждые 10 секунд.</p>';
    if((match?.div||div)==='CS2'){empty('Координаты CS2 пока недоступны','Счёт серии и прогноз доступны выше. Живая карта появится при подключении потока CSTV этого турнира.');return;}
    const target=match?[normalized(match.home),normalized(match.away)].sort().join('|'):null;
    selected=native?fresh.find(g=>g.match_id===native):target?fresh.find(g=>pair(g)===target):null;
    if(!selected){empty(native?'Карта завершилась или данные задерживаются':match?'Ждём координаты этого матча':'Выбери живую карту ниже',native?'Старые позиции не выдаём за прямую трансляцию. Ниже доступны другие текущие карты.':'Как только Valve предоставит позиции обеих команд, карта включится автоматически. Доступные сейчас карты — ниже.');return;}
    if(native){titleAndScore({home:selected.teams[0].name,away:selected.teams[1].name,league:'Dota 2',state:'in',hs:selected.teams[0].score,as:selected.teams[1].score});}
    if(!arena){const {createArena}=await import('./esports-3d.js?v=1');arena=createArena($('arena'),heroes);}
    if(lastId!==selected.match_id){lastId=selected.match_id;}
    arena.update(selected);$('empty').hidden=true;
    $('telemetry').textContent='● '+Math.floor(Math.max(0,selected.game_time)/60)+':'+String(Math.max(0,selected.game_time)%60).padStart(2,'0')+' · координаты обновлены';
    $('roster').innerHTML=selected.teams.map(t=>`<div><h3 style="color:${t.team===2?'#42e6a4':'#ff7d88'}">${esc(t.name)} · ${esc(t.score??'—')} убийств</h3>${t.players.map(p=>`<div class="es-player"><span><b>${esc(p.name)}</b> · ${esc(heroes[p.hero]?.name||'герой '+p.hero)}</span><span>${p.kills??0}/${p.deaths??0}/${p.assists??0} · ур. ${p.level??'—'}</span></div>`).join('')}</div>`).join('');
  }catch(e){empty('Не удалось обновить живую карту','Проверяем соединение. Счёт серии и разбор остаются доступны.');}finally{busy=false;}
}
$('camera').onclick=()=>arena?.camera();$('rotate').onclick=()=>arena?.rotate();$('zoom').onclick=()=>arena?.zoom();$('fullscreen').onclick=()=>{const view=$('arena');if(document.fullscreenElement)document.exitFullscreen();else view.requestFullscreen?.().catch(()=>{});};
await schedule();await positions();
setInterval(()=>{if(!document.hidden)schedule();},60000);setInterval(positions,10000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)positions();});
