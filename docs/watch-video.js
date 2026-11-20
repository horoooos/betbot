import {pairKey} from './dota-data.js?v=1';
const DB='https://aistavvit-default-rtdb.europe-west1.firebasedatabase.app/broadcasts.json';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function embedUrl(value,hostname=location.hostname){
  try{const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password||u.port)return null;
    if(u.hostname==='www.twitch.tv'&&/^\/[a-zA-Z0-9_]{2,30}\/?$/.test(u.pathname))return 'https://player.twitch.tv/?channel='+encodeURIComponent(u.pathname.replaceAll('/',''))+'&parent='+encodeURIComponent(hostname)+'&autoplay=false&muted=true';
    if(u.hostname==='www.youtube.com'&&u.pathname==='/watch'&&/^[\w-]{11}$/.test(u.searchParams.get('v')||''))return 'https://www.youtube-nocookie.com/embed/'+u.searchParams.get('v')+'?playsinline=1';
    const r=u.hostname==='rutube.ru'&&u.pathname.match(/^\/(?:live\/)?video\/([a-f0-9]{32})\/$/);if(r)return 'https://rutube.ru/play/embed/'+r[1]+'/';
  }catch{}return null;
}
let overlay=null,invoker=null;
function shell(title){
  if(!overlay){overlay=document.createElement('section');overlay.id='broadcastPlayer';overlay.setAttribute('role','dialog');overlay.setAttribute('aria-modal','true');document.body.append(overlay);}
  invoker=document.activeElement;overlay.hidden=false;document.body.classList.add('video-open');
  overlay.innerHTML='<header><button id="closeBroadcast">← Вернуться</button><strong>'+esc(title)+'</strong><a href="broadcasts.html">Все эфиры →</a></header><div class="video-body"></div>';
  overlay.querySelector('#closeBroadcast').onclick=closePlayer;overlay.querySelector('#closeBroadcast').focus();return overlay.querySelector('.video-body');
}
function closePlayer(){if(!overlay)return;overlay.hidden=true;overlay.querySelector('.video-body').replaceChildren();document.body.classList.remove('video-open');invoker?.focus();}
document.addEventListener('keydown',e=>{if(!overlay||overlay.hidden)return;if(e.key==='Escape')closePlayer();if(e.key==='Tab'){const nodes=[...overlay.querySelectorAll('button,a,iframe')].filter(n=>!n.hidden);const first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}});
export function openStream(stream,title){const src=embedUrl(stream.url);if(!src)return;const area=shell(title||stream.source||'Реальная трансляция');area.classList.add('has-video');area.innerHTML='<div class="video-help">Плеер вещателя. Эфир и доступность зависят от его настроек. <a href="'+esc(stream.url)+'" target="_blank" rel="noopener noreferrer">Открыть у источника ↗</a></div>';const iframe=document.createElement('iframe');iframe.src=src;iframe.title=title||'Прямая трансляция';iframe.allow='autoplay; fullscreen; picture-in-picture; encrypted-media';iframe.allowFullscreen=true;area.append(iframe);}
export async function loadRegistry(){const r=await fetch(DB,{cache:'no-store'});if(!r.ok)throw Error('Broadcast registry unavailable');return await r.json();}
let observedMatch=null;document.addEventListener('watch-match',e=>{observedMatch=e.detail;});
const q=new URLSearchParams(location.search),button=document.getElementById('videoButton');
if(button){button.onclick=async()=>{const area=shell('3D / Реальная трансляция');area.innerHTML='<p>Проверяем найденные источники этого матча…</p>';try{
  const data=await loadRegistry(),id=q.get('e')||'dota-'+q.get('game'),sport=q.get('s')||(location.pathname.includes('live.html')?'football':'esports');
  const rows=(data.matches||[]).filter(m=>(String(m.id)===id||(observedMatch&&pairKey(m.home,m.away)===pairKey(observedMatch.home,observedMatch.away)))&&m.sport===sport&&(!q.get('d')||m.div===q.get('d')));
  const sources=[...new Map(rows.flatMap(m=>m.streams||[]).filter(s=>Date.now()/1000-s.checked_at<86400).map(s=>[s.url,s])).values()];
  area.replaceChildren();const note=document.createElement('p');note.textContent=sources.length?'Выбери источник. Ссылка из каталога не гарантирует, что сейчас показывают именно этот матч.':'Подтверждённая ссылка для этого матча пока не найдена. Поиск продолжает обновляться.';area.append(note);
  for(const s of sources){if(!embedUrl(s.url))continue;const b=document.createElement('button');b.className='video-source';b.textContent=(s.source||s.provider)+(s.language?' · '+s.language:'')+' →';b.onclick=()=>openStream(s,rows[0].home+' — '+rows[0].away);area.append(b);}
  const channels=(data.channels||[]).filter(c=>c.sports?.includes(sport));if(channels.length){const p=document.createElement('p');p.textContent='Официальные спортивные телеканалы. Показ этого матча не подтверждён:';area.append(p);for(const c of channels){const b=document.createElement('button');b.className='video-source';b.textContent=c.source+' →';b.onclick=()=>openStream(c,c.source);area.append(b);}}
 }catch{area.innerHTML='<p>Не удалось обновить источники. <a href="broadcasts.html">Открыть поиск трансляций</a></p>';}};}
