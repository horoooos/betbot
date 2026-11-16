export const normalizeTeam=s=>String(s||'').toLowerCase().replace(/\b(team|gaming|esports)\b/g,'').replace(/[^\p{L}\p{N}]/gu,'');
export const pairKey=(a,b)=>[normalizeTeam(a),normalizeTeam(b)].sort().join('|');
export const gameClock=seconds=>{const n=Math.max(0,Math.floor(Number(seconds)||0));return Math.floor(n/60)+':'+String(n%60).padStart(2,'0');};
export function liveFrames(data,now=Date.now()/1000,requirePlayers=true){
  return Object.values(data?.games||{}).filter(g=>g.state===5&&now-g.at<50&&now-g.at>=-30&&g.teams?.length===2&&g.teams.every(t=>t.name?.trim()&&(!requirePlayers||t.players?.length===5)));
}
export function mergeDotaMatches(base,frames,now=Date.now()){
  const out=base.map(m=>({...m})),used=new Set();
  for(const g of frames){
    const key=pairKey(...g.teams.map(t=>t.name));
    const candidates=out.map((m,i)=>({m,i})).filter(({m,i})=>!used.has(i)&&m.div==='DOTA'&&!m.dotaGame&&m.state!=='post'&&pairKey(m.home,m.away)===key&&Math.abs(now-new Date(m.kickoff).getTime())<8*3600e3);
    candidates.sort((a,b)=>Math.abs(now-new Date(a.m.kickoff).getTime())-Math.abs(now-new Date(b.m.kickoff).getTime()));
    if(candidates.length){const {m,i}=candidates[0];used.add(i);Object.assign(m,{state:'in',dotaGame:g.match_id,dotaClock:gameClock(g.game_time),presenceId:'dota-'+g.match_id,
      url:'dota.html?d=DOTA&e='+encodeURIComponent(m.id)+'&game='+encodeURIComponent(g.match_id)});}
    else out.push({sport:'esports',div:'DOTA',id:'dota-'+g.match_id,dotaGame:g.match_id,presenceId:'dota-'+g.match_id,
      league:'Dota 2 · текущая карта',home:g.teams[0].name,away:g.teams[1].name,
      hs:g.teams[0].score,as:g.teams[1].score,hl:g.teams[0].logo||'',al:g.teams[1].logo||'',state:'in',scoreUnit:'убийства',dotaClock:gameClock(g.game_time),
      kickoff:new Date(now-Math.max(0,g.game_time)*1000).toISOString(),tip:'',path:'',url:'dota.html?d=DOTA&game='+encodeURIComponent(g.match_id)});
  }
  return out;
}
// Director chooses observed action (KDA changes or proximity), never invents spell events.
export function directorTarget(frame,previous,currentKey){
  const players=frame.teams.flatMap(t=>t.players.map(p=>({...p,team:t.team,key:t.team+':'+p.id})));
  const old=new Map((previous?.teams||[]).flatMap(t=>t.players.map(p=>[t.team+':'+p.id,p])));
  return players.map(p=>{const before=old.get(p.key);let score=0;
    if(before)score+=Math.max(0,(p.kills||0)-(before.kills||0))*40+Math.max(0,(p.assists||0)-(before.assists||0))*12+Math.max(0,(p.deaths||0)-(before.deaths||0))*18;
    const enemy=players.filter(a=>a.team!==p.team).map(a=>Math.hypot(a.x-p.x,a.y-p.y)*140);
    score+=Math.max(0,12-Math.min(...enemy))*2+(p.networth||0)/20000;
    if(p.key===currentKey)score-=2;
    return{key:p.key,score};}).sort((a,b)=>b.score-a.score)[0]?.key||null;
}
