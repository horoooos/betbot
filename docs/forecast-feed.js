(() => {
  const root = document.getElementById('feed'), more = document.getElementById('forecastMore');
  const sport = document.getElementById('forecastSport'), status = document.getElementById('forecastStatus'), search = document.getElementById('forecastSearch');
  const count = document.getElementById('forecastCount');
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icons = {football:'⚽', hockey:'🏒', basketball:'🏀', tennis:'🎾', esports:'🎮'};
  let all = [], shown = 15;
  function render() {
    const list = all.filter(m => (!sport.value || m.sport === sport.value) &&
      (!status.value || (status.value === 'settled' ? ['won','lost'].includes(m.status) : m.status === status.value)) &&
      (m.home + ' ' + m.away).toLocaleLowerCase('ru').includes(search.value.trim().toLocaleLowerCase('ru')));
    count.textContent = `Показано ${Math.min(shown, list.length)} из ${list.length} · всего в истории ${all.length}`;
    root.innerHTML = list.slice(0, shown).map(m => {
      const settled = ['won','lost'].includes(m.status), stamp = new Date(m.kickoff);
      const date = stamp.toLocaleDateString('ru-RU', {timeZone:'Europe/Moscow',day:'2-digit',month:'2-digit'});
      const state = settled ? m.score : m.status === 'in' ? '● Идёт' : 'Ждём итога';
      const title = esc(m.home + ' — ' + m.away);
      const links = `${m.url ? `<a href="${esc(m.url)}">Разбор</a>` : m.telegram ? `<a href="${esc(m.telegram)}">Прогноз</a>` : ''}${m.watch ? `<a href="${esc(m.watch)}">Смотреть матч →</a>` : ''}`;
      const odds = Number.isFinite(Number(m.odds)) ? Number(m.odds).toFixed(2) : '—';
      const lives = (m.lives || []).map(l => `<span class="lvline">⚡ LIVE: ${esc(l.label)} · кэф ${Number(l.odds).toFixed(2)} ${l.ok === null ? '⏳' : l.ok ? '✅' : '❌'}</span>`).join('');
      return `<div class="fr"><span class="ok">${settled ? m.status === 'won' ? '✅' : '❌' : m.status === 'in' ? '🔴' : '⏳'}</span><div class="m"><b>${m.url ? `<a href="${esc(m.url)}">${title}</a>` : title}</b><span>${icons[m.sport] || '🎯'} ${esc(m.label)} · кэф ${m.est?'≈':''}${odds}</span>${lives}<div class="forecast-links">${links}</div></div><div class="r"><b>${esc(state)}</b>${date}${!settled ? '<br>' + stamp.toLocaleTimeString('ru-RU',{timeZone:'Europe/Moscow',hour:'2-digit',minute:'2-digit'}) + ' МСК' : ''}</div></div>`;
    }).join('') || '<p class="muted">По выбранным условиям прогнозов нет.</p>';
    more.hidden = shown >= list.length;
    more.textContent = `Показать ещё ${Math.min(30, list.length - shown)}`;
  }
  [sport,status,search].forEach(el => el.addEventListener('input', () => {shown = 15; render();}));
  more.addEventListener('click', () => {shown += 30; render();});
  function load(){return fetch('forecast-feed.json?v=' + Date.now(), {cache:'no-store'}).then(r => {if(!r.ok) throw Error(); return r.json();})
    .then(data => {all = data; render();}).catch(() => {count.textContent = 'Не удалось обновить список. Ниже сохранены последние результаты.';});}
  load();setInterval(()=>{if(!document.hidden)load();},60000);
})();
