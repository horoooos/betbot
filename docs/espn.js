// Данные о командах, игроках и турнирах — прямо из открытого API ESPN, с переводом на русский.
// Используется страницами team.html, player.html, league.html, leagues.html и поиском в шапке.

const SITE = "https://site.api.espn.com/apis/site/v2/sports/";
const WEB = "https://site.web.api.espn.com/apis/common/v3/sports/";
const STAND = "https://site.api.espn.com/apis/v2/sports/";
const RAW = "https://raw.githubusercontent.com/horoooos/betbot/main/docs/";
const onPages = location.hostname.endsWith("github.io");

export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
export const $ = s => document.querySelector(s);

/** GET с кэшем на 5 минут в sessionStorage (переходы по страницам — мгновенные). */
export async function api(url, ttl = 300) {
  const k = "es:" + url;
  try { const c = JSON.parse(sessionStorage.getItem(k) || "null"); if (c && Date.now() - c.t < ttl * 1000) return c.v; } catch (e) {}
  let last;
  for (let i = 0; i < 2; i++) {
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error("HTTP " + r.status);
      const v = await r.json();
      try { sessionStorage.setItem(k, JSON.stringify({ t: Date.now(), v })); } catch (e) {}
      return v;
    } catch (e) { last = e; }
  }
  throw last;
}
const local = async name => {
  const own = new URL(name, import.meta.url).href;
  try { return await api(onPages ? RAW + name : own, 900); } catch (e) { return api(own, 900).catch(() => null); }
};

// ── справочник бота: русские названия команд, теннисистов, турниры ──
let DIR = null, IDS = null, MATCHES = null;
export async function dir() { if (!DIR) DIR = (await local("dir.json")) || { teams: {}, players: {}, tr: [], leagues: [] }; return DIR; }
export async function teamIds() { if (!IDS) IDS = (await local("teamids.json")) || {}; return IDS; }
export async function ourMatches() { if (!MATCHES) MATCHES = (await local("matches.json")) || []; return MATCHES; }

const strip = s => String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "");
/** Латиница → кириллица (та же таблица, что у бота). */
export function translit(text) {
  const TR = (DIR && DIR.tr) || [];
  return strip(text).split(/(\W+)/).map(word => {
    const w = word.toLowerCase(); let res = "", i = 0;
    while (i < w.length) {
      if (w[i] === "y" && i > 0 && !"aeiou".includes(w[i - 1])) { res += "и"; i++; continue; }
      const hit = TR.find(([a]) => w.startsWith(a, i));
      if (hit) { res += hit[1]; i += hit[0].length; } else { res += w[i]; i++; }
    }
    if (w[0] === "e" && res[0] === "е") res = "э" + res.slice(1);   // Erling → Эрлинг
    if (w.endsWith("ie") && res.endsWith("ие") && w.length > 3) res = res.slice(0, -2) + "и";
    if (w.endsWith("ic") && res.endsWith("ик") && w.length > 4) res = res.slice(0, -2) + "ич";
    return word[0] && word[0] !== word[0].toLowerCase() ? res.charAt(0).toUpperCase() + res.slice(1) : res;
  }).join("");
}
/** Кириллица → латиница — чтобы искать «Овечкин» на ESPN. */
export function latin(text) {
  const M = { а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "yo", ж: "zh", з: "z", и: "i", й: "y", к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f", х: "kh", ц: "ts", ч: "ch", ш: "sh", щ: "shch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya" };
  return String(text).toLowerCase().split("").map(c => M[c] ?? c).join("");
}
export const teamRu = name => {
  if (DIR && DIR.teams[name]) return DIR.teams[name];
  const m = String(name || "").match(/^(.+?)(\s+(?:U-?\d\d|Women|Olympic))?$/);   // сборные: «Norway U19» → «Норвегия U19»
  return m && COUNTRY[m[1]] ? COUNTRY[m[1]] + (m[2] || "").replace("Women", "(жен.)").replace("Olympic", "(олимп.)") : name;
};
export const personRu = name => (DIR && DIR.players[name]) || translit(name);
export function leagueRu(slug, fallback = "") {
  const L = DIR && DIR.leagues.find(l => l.p.endsWith("/" + slug));
  return L ? `${["Сборные", "Европа", "Теннис", "США", "Южная Америка", "КОНКАКАФ"].includes(L.c) ? "" : L.c + " · "}${L.n}` : (LEAGUE_EN[fallback] || fallback || slug);
}
// флаги картинками: эмодзи-флаги Windows показывает буквами
const FLAG = { Англия: "eng", Шотландия: "sco", Испания: "esp", Италия: "ita", Германия: "ger", Франция: "fra", Нидерланды: "ned", Португалия: "por", Турция: "tur", Бельгия: "bel",
  Греция: "gre", Бразилия: "bra", Аргентина: "arg", США: "usa", Мексика: "mex", Япония: "jpn", Китай: "chn", Швеция: "swe", Норвегия: "nor", Дания: "den", Финляндия: "fin", Австрия: "aut",
  Швейцария: "sui", Польша: "pol", Румыния: "rou", Россия: "rus", Ирландия: "irl", "Саудовская Аравия": "ksa", Австралия: "aus", ЮАР: "rsa", Колумбия: "col", Чили: "chi", Уругвай: "uru",
  Перу: "per", Эквадор: "ecu", Парагвай: "par", "Коста-Рика": "crc", Чехия: "cze" };
/** Значок турнира: флаг страны картинкой или эмодзи (🏆 🌍 🎾). */
export function leagueIcon(L, size = 22) {
  if (!L) return "";
  const c = FLAG[L.c];
  return c ? `<img src="https://a.espncdn.com/i/teamlogos/countries/500/${c}.png" alt="" width="${size}" height="${size}" style="width:${size}px;height:${size}px;object-fit:contain;vertical-align:middle">`
    : `<span style="font-size:${Math.round(size * .9)}px">${L.s === "tennis" ? "🎾" : L.s === "hockey" ? "🏒" : L.s === "basketball" ? "🏀" : L.f}</span>`;
}
export const leagueBySlug = slug => DIR && DIR.leagues.find(l => l.p.endsWith("/" + slug));
const LEAGUE_EN = { "Club Friendly": "Товарищеские матчи", "UEFA Champions League": "Лига чемпионов", "UEFA Europa League": "Лига Европы",
  "UEFA Conference League": "Лига конференций", "English Carabao Cup": "Кубок английской лиги", "English FA Cup": "Кубок Англии",
  "English FA Community Shield": "Суперкубок Англии", "Spanish Supercopa": "Суперкубок Испании", "Italian Supercoppa": "Суперкубок Италии",
  "German DFL-Supercup": "Суперкубок Германии", "French Trophee des Champions": "Суперкубок Франции", "FIFA Club World Cup": "Клубный чемпионат мира",
  "UEFA Nations League": "Лига наций", "FIFA World Cup": "Чемпионат мира", "International Friendly": "Товарищеские матчи сборных",
  "Regular Season": "Регулярный чемпионат", "Champions League": "Лига чемпионов", "Europa League": "Лига Европы", "Conference League": "Лига конференций",
  "English Premier League": "Премьер-лига (Англия)", "Premier League": "Премьер-лига", "English League Championship": "Чемпионшип", "Spanish LaLiga": "Ла Лига", "LaLiga": "Ла Лига",
  "Italian Serie A": "Серия A", "German Bundesliga": "Бундеслига", "French Ligue 1": "Лига 1 (Франция)", "Dutch Eredivisie": "Эредивизи", "Portuguese Primeira Liga": "Примейра",
  "Turkish Super Lig": "Суперлига (Турция)", "Scottish Premiership": "Премьершип (Шотландия)", "Belgian Pro League": "Про-лига (Бельгия)", "Russian Premier League": "РПЛ",
  "MLS": "MLS", "Saudi Pro League": "Про-лига (Саудовская Аравия)", "Brazilian Serie A": "Серия A (Бразилия)", "Argentine Liga Profesional de Fútbol": "Примера (Аргентина)",
  "Spanish Copa del Rey": "Кубок Короля", "German DFB Pokal": "Кубок Германии", "Coppa Italia": "Кубок Италии", "Italian Coppa Italia": "Кубок Италии", "Coupe de France": "Кубок Франции",
  "UEFA Super Cup": "Суперкубок УЕФА", "Copa Libertadores": "Кубок Либертадорес", "FIFA World Cup Qualifying": "Отбор ЧМ", "UEFA European Championship": "Чемпионат Европы", "Preseason": "Предсезонка", "Postseason": "Плей-офф" };
export const trLeague = name => { const n = String(name || "").replace(/^\d{4}(-\d{2})?\s+/, "").replace(/\s+Stats$/, ""); return LEAGUE_EN[name] || LEAGUE_EN[n] || n; };

export const SPORT = { soccer: "football", hockey: "hockey", basketball: "basketball", tennis: "tennis" };
export const EMOJI = { football: "⚽️", hockey: "🏒", basketball: "🏀", tennis: "🎾" };

const POS = {
  soccer: { Goalkeeper: "Вратарь", Defender: "Защитник", Midfielder: "Полузащитник", Forward: "Нападающий", "Center Back": "Центральный защитник", "Left Back": "Левый защитник",
    "Right Back": "Правый защитник", "Defensive Midfielder": "Опорный полузащитник", "Attacking Midfielder": "Атакующий полузащитник", "Center Forward": "Центральный нападающий",
    "Left Wing": "Левый вингер", "Right Wing": "Правый вингер", "Striker": "Нападающий", G: "Вратарь", D: "Защитник", M: "Полузащитник", F: "Нападающий" },
  hockey: { Center: "Центральный нападающий", "Left Wing": "Левый нападающий", "Right Wing": "Правый нападающий", Defense: "Защитник", Goalie: "Вратарь", Forward: "Нападающий", Forwards: "Нападающие", Defenses: "Защитники", Goalies: "Вратари", Centers: "Центральные нападающие", "Left Wings": "Левые нападающие", "Right Wings": "Правые нападающие", Defensemen: "Защитники" },
  basketball: { Guard: "Защитник", "Point Guard": "Разыгрывающий", "Shooting Guard": "Атакующий защитник", "Small Forward": "Лёгкий форвард", "Power Forward": "Тяжёлый форвард", Forward: "Форвард", Center: "Центровой", "Guard-Forward": "Защитник-форвард", "Forward-Center": "Форвард-центровой" },
};
export const posRu = (sport, p) => (POS[sport] && POS[sport][p]) || p || "";
export const POS_ORDER = { soccer: ["Вратарь", "Защитник", "Полузащитник", "Нападающий"] };

const COUNTRY = { England: "Англия", Scotland: "Шотландия", Wales: "Уэльс", "Northern Ireland": "Северная Ирландия", Ireland: "Ирландия", "Republic of Ireland": "Ирландия", Spain: "Испания", Italy: "Италия",
  Germany: "Германия", France: "Франция", Netherlands: "Нидерланды", Portugal: "Португалия", Belgium: "Бельгия", Turkey: "Турция", "Türkiye": "Турция", Greece: "Греция", Russia: "Россия",
  Ukraine: "Украина", Belarus: "Беларусь", Kazakhstan: "Казахстан", Georgia: "Грузия", Armenia: "Армения", Azerbaijan: "Азербайджан", Uzbekistan: "Узбекистан", Poland: "Польша",
  "Czech Republic": "Чехия", Czechia: "Чехия", Slovakia: "Словакия", Hungary: "Венгрия", Austria: "Австрия", Switzerland: "Швейцария", Denmark: "Дания", Sweden: "Швеция", Norway: "Норвегия",
  Finland: "Финляндия", Iceland: "Исландия", Croatia: "Хорватия", Serbia: "Сербия", Slovenia: "Словения", "Bosnia and Herzegovina": "Босния и Герцеговина", Montenegro: "Черногория",
  "North Macedonia": "Северная Македония", Albania: "Албания", Kosovo: "Косово", Romania: "Румыния", Bulgaria: "Болгария", Moldova: "Молдова", Latvia: "Латвия", Lithuania: "Литва",
  Estonia: "Эстония", Israel: "Израиль", Cyprus: "Кипр", Malta: "Мальта", Luxembourg: "Люксембург", Brazil: "Бразилия", Argentina: "Аргентина", Uruguay: "Уругвай", Paraguay: "Парагвай",
  Chile: "Чили", Colombia: "Колумбия", Peru: "Перу", Ecuador: "Эквадор", Venezuela: "Венесуэла", Bolivia: "Боливия", Mexico: "Мексика", "United States": "США", USA: "США", Canada: "Канада",
  "Costa Rica": "Коста-Рика", Honduras: "Гондурас", Panama: "Панама", Jamaica: "Ямайка", Haiti: "Гаити", Morocco: "Марокко", Algeria: "Алжир", Tunisia: "Тунис", Egypt: "Египет",
  Nigeria: "Нигерия", Ghana: "Гана", Senegal: "Сенегал", "Ivory Coast": "Кот-д'Ивуар", "Côte d'Ivoire": "Кот-д'Ивуар", Cameroon: "Камерун", Mali: "Мали", "Guinea": "Гвинея",
  "DR Congo": "ДР Конго", "Congo DR": "ДР Конго", "South Africa": "ЮАР", "Burkina Faso": "Буркина-Фасо", "Cape Verde": "Кабо-Верде", Gabon: "Габон", Zambia: "Замбия", Angola: "Ангола",
  "Equatorial Guinea": "Экваториальная Гвинея", "Guinea-Bissau": "Гвинея-Бисау", Gambia: "Гамбия", Togo: "Того", Benin: "Бенин", Japan: "Япония", "South Korea": "Южная Корея",
  "Korea Republic": "Южная Корея", China: "Китай", "China PR": "Китай", Australia: "Австралия", "New Zealand": "Новая Зеландия", Iran: "Иран", Iraq: "Ирак", "Saudi Arabia": "Саудовская Аравия",
  Qatar: "Катар", "United Arab Emirates": "ОАЭ", India: "Индия", Taiwan: "Тайвань", "Chinese Taipei": "Тайвань", Thailand: "Таиланд", Philippines: "Филиппины", Indonesia: "Индонезия",
  "Hong Kong": "Гонконг", Suriname: "Суринам", Curacao: "Кюрасао", "Curaçao": "Кюрасао", "Great Britain": "Великобритания", "Dominican Republic": "Доминиканская Республика",
  "Puerto Rico": "Пуэрто-Рико", Cuba: "Куба", Tajikistan: "Таджикистан", Kyrgyzstan: "Киргизия", Monaco: "Монако" };
const ABBR = { CAN: "Канада", USA: "США", SWE: "Швеция", FIN: "Финляндия", RUS: "Россия", CZE: "Чехия", SVK: "Словакия", BLR: "Беларусь", SUI: "Швейцария", GER: "Германия",
  DEN: "Дания", LAT: "Латвия", AUT: "Австрия", NOR: "Норвегия", FRA: "Франция", SLO: "Словения", SVN: "Словения", KAZ: "Казахстан", UKR: "Украина", USSR: "СССР", URS: "СССР", GBR: "Великобритания",
  ENG: "Англия", AUS: "Австралия", ITA: "Италия", ESP: "Испания", SRB: "Сербия", CRO: "Хорватия", LTU: "Литва", EST: "Эстония", POL: "Польша", HUN: "Венгрия", NED: "Нидерланды", BEL: "Бельгия",
  GRE: "Греция", TUR: "Турция", BRA: "Бразилия", ARG: "Аргентина", NGA: "Нигерия", CMR: "Камерун", SEN: "Сенегал", JPN: "Япония", CHN: "Китай", KOR: "Южная Корея", DOM: "Доминикана",
  BAH: "Багамы", BIH: "Босния и Герцеговина", MNE: "Черногория", GEO: "Грузия", ISR: "Израиль", NZL: "Новая Зеландия", SSD: "Южный Судан", COD: "ДР Конго", MLI: "Мали", POR: "Португалия" };
export const countryRu = c => COUNTRY[c] || ABBR[c] || c || "";

// подписи статистики
const STAT = {
  soccer: { STRT: "В старте", "STRT-SUBIN": "Старт (замена)", APP: "Матчи", FC: "Фолы", FA: "Фолы на нём", YC: "Жёлтые", RC: "Красные", G: "Голы", A: "Передачи", SHOT: "Удары",
    SOG: "В створ", OFF: "Офсайды", SV: "Сейвы", GA: "Пропущено", CS: "На ноль", SUBIN: "Вышел на замену", MIN: "Минуты" },
  hockey: { GP: "Игры", G: "Голы", A: "Передачи", PTS: "Очки", "+/-": "+/−", PIM: "Штраф", SOG: "Броски", "S%": "% реализ.", SPCT: "% реализ.", PPG: "Голы в бол.", PPA: "Пас в бол.",
    SHG: "Голы в мен.", SHA: "Пас в мен.", GWG: "Победные", "TOI/G": "Время", PROD: "Продукт.", W: "Победы", L: "Пораж.", OTL: "Пораж. ОТ", GAA: "Пропуск. ср.", SA: "Броски", SV: "Сейвы",
    "SV%": "% сейвов", SO: "На ноль", GS: "В старте", TOI: "Время", FW: "Вбрас. выигр.", "FO%": "% вбрас.", BS: "Блоки", HT: "Силовые", TK: "Отборы", GV: "Потери" },
  basketball: { GP: "Игры", GS: "В старте", MIN: "Минуты", PTS: "Очки", REB: "Подборы", AST: "Передачи", STL: "Перехв.", BLK: "Блоки", TO: "Потери", PF: "Фолы", "FG%": "% с игры",
    "3P%": "% трёхочк.", "FT%": "% штрафн.", FG: "С игры", "3PT": "Трёхочк.", FT: "Штрафные", OR: "Подб. в нап.", DR: "Подб. в защ." },
};
export const statRu = (sport, l) => (STAT[sport] && STAT[sport][l]) || l;

export const roundRu = r => ({ Final: "Финал", Semifinal: "1/2 финала", Semifinals: "1/2 финала", Quarterfinal: "1/4 финала", Quarterfinals: "1/4 финала", "Round of 16": "1/8 финала",
  "Round 1": "1-й круг", "Round 2": "2-й круг", "Round 3": "3-й круг", "Round 4": "4-й круг", "Qualifying": "Квалификация" })[r] || String(r).replace(/^Round (\d+)$/, "$1-й круг").replace(/^Qualifying Round (\d+)$/, "Квалиф., $1-й круг");
export const flagUrl = abbr => abbr ? `https://a.espncdn.com/i/teamlogos/countries/500/${abbr.toLowerCase()}.png` : "";
export const cm = inch => inch ? Math.round(inch * 2.54) : null;
export const kg = lbs => lbs ? Math.round(lbs * 0.4536) : null;
export function parseHW(display) { // «6' 2"» → см; «183 lbs» → кг
  const m = String(display || "").match(/(\d+)'\s*(\d+)/); if (m) return Math.round((+m[1] * 12 + +m[2]) * 2.54) + " см";
  const w = String(display || "").match(/(\d+)\s*lbs/); if (w) return Math.round(+w[1] * 0.4536) + " кг";
  return "";
}
export const msk = (iso, o = { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) => new Date(iso).toLocaleString("ru-RU", { timeZone: "Europe/Moscow", ...o });
export const plural = (n, one, few, many) => { const a = n % 10, b = n % 100; return `${n} ${a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 10 || b >= 20) ? few : many}`; };
export const years = n => { const a = n % 10, b = n % 100; return `${n} ${a === 1 && b !== 11 ? "год" : a >= 2 && a <= 4 && (b < 10 || b >= 20) ? "года" : "лет"}`; };

// ── адреса страниц ──
export const teamUrl = (path, id) => `team.html?p=${encodeURIComponent(path)}&id=${encodeURIComponent(id)}`;
export const playerUrl = (path, id) => `player.html?p=${encodeURIComponent(path)}&id=${encodeURIComponent(id)}`;
export const leagueUrl = path => `league.html?p=${encodeURIComponent(path)}`;
export const sportOf = path => SPORT[String(path).split("/")[0]] || "football";

// ── запросы к ESPN ──
export const schedule = (path, id, fixture = false) => {
  const [sp] = path.split("/");
  const base = sp === "soccer" ? `${SITE}soccer/all/teams/${id}/schedule` : `${SITE}${path}/teams/${id}/schedule`;
  return api(base + (fixture ? "?fixture=true" : ""));
};
export const roster = (path, id) => api(`${SITE}${path}/teams/${id}/roster`, 1800);
export const standings = path => api(`${STAND}${path}/standings`, 600);
export const scoreboard = (path, dates) => api(`${SITE}${path}/scoreboard${dates ? "?dates=" + dates + "&limit=200" : ""}`, 120);
export const athlete = (path, id) => { const [sp, lg] = path.split("/"); return api(`${WEB}${sp}/${sp === "soccer" ? "" : lg + "/"}athletes/${id}`, 1800); };
export const overview = (path, id) => { const [sp, lg] = path.split("/"); return api(`${WEB}${sp}/${sp === "soccer" ? "" : lg + "/"}athletes/${id}/overview`, 600); };
export const gamelog = (path, id) => { const [sp, lg] = path.split("/"); return api(`${WEB}${sp}/${sp === "soccer" ? "" : lg + "/"}athletes/${id}/gamelog`, 600); };
export const rankings = path => api(`${SITE}${path}/rankings`, 3600);

/** id команды (side = h|a) по id матча — для ссылок из списка матчей, пока бот не прислал номера команд. */
export async function resolveSide(path, ev, side) {
  const pickC = cs => { const s = [...(cs || [])].sort((x, y) => (x.order || 0) - (y.order || 0));
    return (side === "a" ? cs.find(x => x.homeAway === "away") || s[1] : cs.find(x => x.homeAway === "home") || s[0]) || null; };
  if (!path.startsWith("tennis")) {
    try { const d = await api(`${SITE}${path}/summary?event=${ev}`, 600); const c = pickC(d.header.competitions[0].competitors); if (c) return String(c.id || c.team.id); } catch (e) {}
  }
  try { const sb = await api(`${SITE}${path}/scoreboard`, 120);
    for (const e of sb.events || []) for (const c of [...(e.competitions || []), ...(e.groupings || []).flatMap(g => g.competitions || [])])
      if (String(c.id) === String(ev) || String(e.id) === String(ev)) { const x = pickC(c.competitors); if (x) return String(x.id); }
  } catch (e) {}
  return null;
}

/** Матч из расписания команды → простая запись. */
export function game(e, teamId) {
  const c = e.competitions[0], st = c.status.type;
  const me = c.competitors.find(x => String(x.id) === String(teamId)) || c.competitors[0];
  const op = c.competitors.find(x => x !== me) || {};
  const sc = x => x.score == null ? null : typeof x.score === "object" ? (x.score.displayValue ?? x.score.value) : x.score;
  const lg = e.league || {};
  return { id: e.id, date: e.date, state: st.state, detail: st.shortDetail || st.detail, home: me.homeAway === "home",
    my: sc(me), op: sc(op), win: me.winner, lose: op.winner, opp: op.team || {}, oppId: op.id,
    so: me.shootoutScore != null ? `${me.shootoutScore}:${op.shootoutScore}` : null,
    league: lg.slug ? leagueRu(lg.slug, lg.name) : trLeague((e.seasonType && e.seasonType.name) || ""), slug: lg.slug || "", leagueName: lg.name || "" };
}
export const result = g => g.state !== "post" || g.my == null ? null : g.win ? "W" : g.lose ? "L" : +g.my > +g.op ? "W" : +g.my < +g.op ? "L" : "D";
export const RES = { W: ["В", "#2ecc71"], D: ["Н", "#9aa6cc"], L: ["П", "#ff5a5a"] };
export const chip = r => r ? `<span class="fchip" style="background:${RES[r][1]}">${RES[r][0]}</span>` : "";
export const logoOf = t => t.logo || (t.logos && t.logos[0] && t.logos[0].href) || "";
export const img = (src, size = 28, round = false) => src ? `<img src="${esc(src)}" alt="" loading="lazy" width="${size}" height="${size}" style="width:${size}px;height:${size}px;object-fit:contain;${round ? "border-radius:50%;object-fit:cover;background:#fff1;" : ""}flex:none" onerror="this.style.visibility='hidden'">` : `<span style="width:${size}px;flex:none"></span>`;

// ── поиск команд и игроков ──
const OK_LEAGUE = { hockey: ["nhl"], basketball: ["nba", "wnba"], tennis: ["atp", "wta"] };
export async function search(q) {
  q = q.trim(); if (q.length < 2) return [];
  await dir();
  const low = q.toLowerCase(), out = [], seen = new Set();
  // 1) наши команды с русскими названиями
  const ids = await teamIds();
  for (const [k, v] of Object.entries(ids)) {
    const [sport, ru] = k.split("|");
    if (ru.toLowerCase().includes(low) || (v[2] || "").toLowerCase().includes(low)) {
      const key = v[0].split("/")[0] + ":" + v[1]; if (seen.has(key)) continue; seen.add(key);
      out.push({ type: sport === "tennis" ? "player" : "team", name: ru, sub: (EMOJI[sport] || "") + " " + (leagueRu(v[0].split("/")[1]) || ""), url: sport === "tennis" ? playerUrl(v[0], v[1]) : teamUrl(v[0], v[1]),
        img: sport === "tennis" ? "" : null, path: v[0], id: v[1] });
    }
  }
  // 2) ESPN: по-английски, а русский запрос переводим в латиницу
  const qs = /[а-яё]/i.test(q) ? [q, latin(q)] : [q];
  const en = Object.entries(DIR.teams).filter(([e, r]) => r.toLowerCase().includes(low)).map(([e]) => e).slice(0, 2);
  for (const s of [...new Set([...en, ...qs.slice(1), qs[0]])]) {
    let j; try { j = await api(`https://site.web.api.espn.com/apis/search/v2?limit=10&query=${encodeURIComponent(s)}`, 600); } catch (e) { continue; }
    for (const grp of j.results || []) {
      if (grp.type !== "player" && grp.type !== "team") continue;
      for (const x of grp.contents || []) {
        const sp = x.sport, lg = String(x.defaultLeagueSlug || "").toLowerCase();
        if (!SPORT[sp] || (OK_LEAGUE[sp] && !OK_LEAGUE[sp].includes(lg))) continue;
        if (sp === "soccer" && /(\.w\.|women|\bu-?\d\d\b|\.youth|college|trophy)/i.test(lg + " " + x.subtitle + " " + x.displayName)) continue;
        const id = (String(x.uid).match(/[at]:(\d+)$/) || [])[1]; if (!id) continue;
        const path = `${sp}/${lg || "all"}`, key = sp + ":" + id; if (seen.has(key)) continue; seen.add(key);
        const t = grp.type === "team";
        out.push({ type: grp.type, name: t ? teamRu(x.displayName) : personRu(x.displayName), en: x.displayName,
          sub: `${EMOJI[SPORT[sp]]} ${t ? leagueRu(lg, x.subtitle) : (x.subtitle ? teamRu(x.subtitle) + " · " : "") + (sp === "tennis" ? lg.toUpperCase() : leagueRu(lg, x.description))}`,
          url: t ? teamUrl(path, id) : playerUrl(path, id), img: x.image && x.image.default, path, id });
      }
    }
    if (out.length >= 12) break;
  }
  return out.slice(0, 16);
}

// ── общий вид для страниц справочника ──
export const CSS = `
.hero{display:flex;gap:16px;align-items:center;margin:14px 0 6px}.hero .lg{width:84px;height:84px;border-radius:22px;background:#fff;display:grid;place-items:center;flex:none;overflow:hidden}
.hero .lg img{width:70px;height:70px;object-fit:contain}.hero .ph{width:96px;height:96px;border-radius:50%;background:linear-gradient(160deg,#28336b,#141c40);overflow:hidden;flex:none;display:grid;place-items:center;font-size:42px}
.hero .ph img{width:100%;height:100%;object-fit:cover}.hero h1{margin:0 0 4px}.hero .sub{color:var(--muted);font-size:14px;display:flex;gap:6px 12px;flex-wrap:wrap;align-items:center}
.facts{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin:12px 0}.facts div{background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:14px;padding:10px 12px}
.facts b{display:block;font-size:17px}.facts span{color:var(--muted);font-size:12px}
.fchip{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:7px;color:#071019;font:900 12px Montserrat,sans-serif}
.form{display:flex;gap:4px;flex-wrap:wrap}.tabs2{display:flex;gap:6px;overflow-x:auto;margin:18px 0 10px;scrollbar-width:none}.tabs2::-webkit-scrollbar{display:none}
.tabs2 button{flex:none;border:1px solid var(--line);background:rgba(255,255,255,.04);color:var(--muted);font:800 13px Montserrat,sans-serif;padding:8px 14px;border-radius:12px;cursor:pointer}
.tabs2 button.on{background:var(--gold);color:#1a1405;border-color:transparent}
.gl{display:flex;flex-direction:column}.gm{display:grid;grid-template-columns:86px minmax(0,1fr) auto;gap:10px;align-items:center;padding:10px 4px;border-bottom:1px solid var(--line);text-decoration:none}
.gm:last-child{border-bottom:0}.gm .d{color:var(--muted);font-size:12px;line-height:1.3}.gm .o{display:flex;align-items:center;gap:8px;min-width:0;font-weight:800}.gm .o span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gm .l{color:var(--muted);font-size:11px;font-weight:600}.gm .s{font-weight:900;white-space:nowrap;display:flex;gap:6px;align-items:center}.gm a{text-decoration:none}.gm a:hover{text-decoration:underline}
.tb{width:100%;border-collapse:collapse;font-size:13.5px}.tb th,.tb td{padding:8px 6px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}.tb th{color:var(--muted);font-size:11px;font-weight:700}
.tb td:first-child,.tb th:first-child{text-align:left}.tb .tm{text-align:left;display:flex;align-items:center;gap:8px;font-weight:800}.tb .tm a{text-decoration:none}.tb .tm a:hover{text-decoration:underline}
.tb tr.me td{background:rgba(255,196,0,.1)}.tb tr:last-child td{border-bottom:0}.wrapx{overflow-x:auto}
.pl{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:8px}.pl a{display:flex;gap:10px;align-items:center;padding:9px 10px;border-radius:14px;background:rgba(255,255,255,.04);border:1px solid var(--line);text-decoration:none}
.pl a:hover{background:rgba(255,255,255,.08)}.pl .n{font-weight:800;line-height:1.2}.pl .m{color:var(--muted);font-size:12px}.pl .j{width:30px;text-align:center;font-weight:900;color:var(--gold);flex:none}
.chips{display:flex;gap:6px;flex-wrap:wrap}.chips a{padding:7px 12px;border-radius:12px;background:rgba(255,255,255,.05);border:1px solid var(--line);text-decoration:none;font-weight:700;font-size:13px}
.chips a:hover{background:rgba(255,255,255,.1)}.load{color:var(--muted);padding:20px 0}.bar2{height:8px;border-radius:5px;background:rgba(255,255,255,.08);overflow:hidden}.bar2 i{display:block;height:100%;background:linear-gradient(90deg,#ffc400,#ff7a3d)}
.kv{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}.kv div{background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:14px;padding:10px 12px}
.kv b{font-size:20px}.kv span{display:block;color:var(--muted);font-size:12px;margin-bottom:6px}
@media(max-width:560px){.hero .lg{width:64px;height:64px;border-radius:18px}.hero .lg img{width:52px;height:52px}.hero .ph{width:72px;height:72px}.gm{grid-template-columns:64px minmax(0,1fr) auto}}`;

// ── турнирная таблица (футбол, НХЛ, НБА) ──
const GROUP = { "Eastern Conference": "Восточная конференция", "Western Conference": "Западная конференция", "League Phase": "Общий этап", "Overall": "Общая таблица",
  "Atlantic Division": "Атлантический дивизион", "Metropolitan Division": "Столичный дивизион", "Central Division": "Центральный дивизион", "Pacific Division": "Тихоокеанский дивизион" };
const groupRu = n => GROUP[n] || String(n || "").replace(/^Group /, "Группа ");
export function standingsHTML(data, path, hiId) {
  const sp = path.split("/")[0], sport = sportOf(path);
  const groups = (data.children && data.children.length ? data.children : [data]).filter(g => g.standings && g.standings.entries && g.standings.entries.length);
  if (!groups.length) return `<p class="muted">Таблицы для этого турнира нет — это кубок или турнир на выбывание.</p>`;
  const COLS = {
    football: [["И", "gamesPlayed"], ["В", "wins"], ["Н", "ties"], ["П", "losses"], ["Мячи", s => `${s.pointsFor ?? "–"}–${s.pointsAgainst ?? "–"}`], ["+/−", "pointDifferential"], ["О", "points", 1]],
    hockey: [["И", "gamesPlayed"], ["В", "wins"], ["П", "losses"], ["ПОТ", "otLosses"], ["Шайбы", s => `${s.pointsFor ?? "–"}–${s.pointsAgainst ?? "–"}`], ["Серия", "streak"], ["О", "points", 1]],
    basketball: [["В", "wins"], ["П", "losses"], ["%", "winPercent", 1], ["Отст.", "gamesBehind"], ["Дома", "Home"], ["В гостях", "Road"], ["Серия", "streak"]],
  }[sport];
  return groups.map(g => {
    const rows = g.standings.entries.map(e => { const s = {}; for (const x of e.stats || []) { s[x.name] = x.displayValue ?? x.value; s["#" + x.name] = x.value; } return { t: e.team, s, note: e.note }; });
    const has = k => rows.some(r => r.s["#" + k] != null && r.s["#" + k] !== 0);
    rows.sort((a, b) => has("rank") ? a.s["#rank"] - b.s["#rank"] : has("playoffSeed") ? a.s["#playoffSeed"] - b.s["#playoffSeed"] : (b.s["#points"] || 0) - (a.s["#points"] || 0));
    const head = `<tr><th>#</th><th style="text-align:left">Команда</th>${COLS.map(c => `<th>${c[0]}</th>`).join("")}</tr>`;
    const body = rows.map((r, i) => `<tr class="${String(r.t.id) === String(hiId) ? "me" : ""}"><td>${i + 1}${r.note && r.note.color ? `<i style="display:inline-block;width:4px;height:14px;border-radius:2px;margin-left:5px;vertical-align:-2px;background:${esc(r.note.color)}" title="${esc(r.note.description || "")}"></i>` : ""}</td>
      <td><div class="tm">${img(logoOf(r.t), 22)}<a href="${teamUrl(path, r.t.id)}">${esc(teamRu(r.t.displayName))}</a></div></td>
      ${COLS.map(c => `<td${c[2] ? ' style="font-weight:900"' : ""}>${esc(typeof c[1] === "function" ? c[1](r.s) : r.s[c[1]] ?? "–")}</td>`).join("")}</tr>`).join("");
    return `${groups.length > 1 ? `<h3 style="margin:14px 0 6px;font-size:15px">${esc(groupRu(g.name))}</h3>` : ""}<div class="card wrapx" style="padding:6px 10px"><table class="tb">${head}${body}</table></div>`;
  }).join("");
}

/** Строка матча: дата | соперник/команды | счёт или время. */
export function gameRow(g, path, opts = {}) {
  const sp = path.split("/")[0], r = result(g);
  const opPath = sp === "soccer" ? `soccer/${g.slug || "all"}` : path;
  const when = g.state === "pre" ? msk(g.date, { day: "numeric", month: "short" }) + "<br>" + msk(g.date, { hour: "2-digit", minute: "2-digit" }) : msk(g.date, { day: "numeric", month: "short", year: "2-digit" });
  const score = g.state === "pre" ? `<span class="muted small">${g.home ? "дома" : "в гостях"}</span>` : g.state === "in" ? `<span style="color:var(--live)">● ${esc(g.my)}:${esc(g.op)}</span>` : `${esc(g.my)}:${esc(g.op)}${g.so ? ` <span class="muted small">(пен. ${esc(g.so)})</span>` : ""} ${chip(r)}`;
  return `<div class="gm"><div class="d">${when}</div><div style="min-width:0"><div class="o">${img(logoOf(g.opp), 22)}<span>${g.home ? "" : "@ "}<a href="${teamUrl(opPath, g.oppId)}">${esc(teamRu(g.opp.displayName || g.opp.name || ""))}</a></span></div>
    <div class="l">${esc(g.league)}${opts.extra ? " · " + opts.extra : ""}</div></div><div class="s">${score}</div></div>`;
}
