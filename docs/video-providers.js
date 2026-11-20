export function videoInfo(value){
  try{const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password||u.port)return null;const host=u.hostname.replace(/^www\./,'');
    if(host==='twitch.tv'&&/^\/[a-zA-Z0-9_]{2,30}\/?$/.test(u.pathname))return{provider:'twitch',id:u.pathname.replaceAll('/',''),url:'https://www.twitch.tv/'+u.pathname.replaceAll('/','')};
    if(host==='youtube.com'||host==='youtu.be'){const id=host==='youtu.be'?u.pathname.slice(1):u.pathname.startsWith('/live/')?u.pathname.split('/')[2]:u.searchParams.get('v');if(/^[\w-]{11}$/.test(id||''))return{provider:'youtube',id,url:'https://www.youtube.com/watch?v='+id};}
    const r=host==='rutube.ru'&&u.pathname.match(/^\/(?:live\/)?video\/([a-f0-9]{32})\/(?:tvprogramm\/)?$/);if(r)return{provider:'rutube',id:r[1],url:'https://rutube.ru/video/'+r[1]+'/'};
    if(host==='espn.com'&&u.pathname.startsWith('/watch/'))return{provider:'external',url:u.href};
    if(/\.m3u8$/i.test(u.pathname))return{provider:'hls',url:u.href};
    if(/\.(mp4|webm)$/i.test(u.pathname))return{provider:'html5',url:u.href};
  }catch{}return null;
}
export function parentDomains(host,ancestors=[]){return[...new Set([host,...ancestors.map(s=>{try{return new URL(s).hostname;}catch{return'';}})].filter(Boolean))];}
export function playerUrl(value,origin,ancestors=[]){const v=videoInfo(value);if(!v)return null;const host=new URL(origin).hostname;
  if(v.provider==='twitch'){const q=new URLSearchParams({channel:v.id,autoplay:'false',muted:'true'});for(const p of parentDomains(host,ancestors))q.append('parent',p);return'https://player.twitch.tv/?'+q;}
  if(v.provider==='youtube')return'https://www.youtube.com/embed/'+v.id+'?'+new URLSearchParams({enablejsapi:'1',origin,playsinline:'1',autoplay:'0'});
  if(v.provider==='rutube')return'https://rutube.ru/play/embed/'+v.id+'/';return null;
}
export function youtubeError(code){return({2:'Некорректная ссылка.',5:'Источник не смог запустить видео.',100:'Видео удалено или недоступно.',101:'Автор запретил встраивание.',150:'Автор запретил встраивание.',153:'YouTube не смог проверить адрес сайта.'})[code]||'Ошибка воспроизведения.';}
