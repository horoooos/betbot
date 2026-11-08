// Общий модуль сайта АИ СТАВИТ: вход (почта / Google), «кто смотрит» и чат трансляций — на Firebase.
// Ключи ниже не секретные: Firebase сам вставляет их в любой сайт, доступ ограничен правилами базы.
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth, onAuthStateChanged, GoogleAuthProvider, signInWithPopup, signInWithRedirect, getRedirectResult, signInWithEmailAndPassword,
  createUserWithEmailAndPassword, signOut, sendPasswordResetEmail } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";
import { getDatabase, ref, set, get, push, remove, update, onValue, onDisconnect, serverTimestamp, query, orderByChild, equalTo, limitToLast,
  endBefore, onChildAdded, onChildRemoved, onChildChanged, runTransaction } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-database.js";

const app = initializeApp({
  apiKey: "AIzaSyCijCZYGyEgmYNmb2GQMKkGpSHF2j_JZuA",
  authDomain: "aistavvit.firebaseapp.com",
  databaseURL: "https://aistavvit-default-rtdb.europe-west1.firebasedatabase.app",
  projectId: "aistavvit",
  storageBucket: "aistavvit.firebasestorage.app",
  messagingSenderId: "69507895892",
  appId: "1:69507895892:web:c2bb1f02969824e1dad3c1",
});
export const auth = getAuth(app);
auth.languageCode = "ru";   // письма (сброс пароля, подтверждение) и окно Google — на русском
export const db = getDatabase(app);
export { ref, get, set, push, remove, update, onValue, query, orderByChild, equalTo, limitToLast, endBefore, onChildAdded, onChildRemoved, onChildChanged };
export const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
export const getProfile = () => profile;

const ls = { get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} } };

// ── посетители: кто сейчас на сайте, откуда пришёл и с какого устройства ──
function visitorId() {
  let v = ls.get("aiv"); if (!v) { v = Math.random().toString(36).slice(2) + Date.now().toString(36); ls.set("aiv", v); }
  return v;
}
let skew = 0;   // разница часов браузера и сервера Firebase — чтобы «свежесть» считать по серверному времени
onValue(ref(db, ".info/serverTimeOffset"), s => { skew = s.val() || 0; });
const now = () => Date.now() + skew;
const FRESH = 90e3;   // человек «на сайте», если отмечался за последние 90 секунд

/** Откуда пришёл посетитель: Telegram, Яндекс, Google, ВКонтакте, прямой заход… */
export function source() {
  const ss = { get: k => { try { return sessionStorage.getItem(k); } catch (e) { return null; } }, set: (k, v) => { try { sessionStorage.setItem(k, v); } catch (e) {} } };
  const saved = ss.get("aisrc"); if (saved) return saved;
  const q = new URLSearchParams(location.search), utm = q.get("utm_source");
  let host = ""; try { host = new URL(document.referrer).hostname; } catch (e) {}
  const ua = navigator.userAgent || "";
  let src = utm ? utm.slice(0, 30)
    : /(^|\.)t\.me$|telegram/.test(host) || window.Telegram?.WebApp?.initData || /Telegram/i.test(ua) ? "Telegram"
    : /yandex\.|ya\.ru/.test(host) ? "Яндекс" : /google\./.test(host) ? "Google" : /vk\.com|vk\.ru/.test(host) ? "ВКонтакте"
    : /bing\./.test(host) ? "Bing" : /mail\.ru/.test(host) ? "Mail.ru" : /dzen\.ru|zen\.yandex/.test(host) ? "Дзен"
    : host && host !== location.hostname ? host.replace(/^www\./, "").slice(0, 30) : "Прямой заход";
  ss.set("aisrc", src); return src;
}
export const device = () => { const ua = navigator.userAgent || ""; return /iPad|Tablet/i.test(ua) ? "Планшет" : /Mobi|Android|iPhone/i.test(ua) ? "Телефон" : "Компьютер"; };

/** page — короткое имя страницы ("index", "matches", "live:401888371"); match — id матча, если это трансляция. */
export function track(page, match = null) {
  const vid = visitorId(), day = new Date().toISOString().slice(0, 10), src = source(), dev = device();
  if (ls.get("aiday") !== day) {   // один раз в день: уникальный посетитель + откуда пришёл
    set(ref(db, `visits/${day}/${vid}`), { t: Date.now(), r: src, d: dev, p: String(page).slice(0, 40) }).catch(() => {}); ls.set("aiday", day);
  }
  const conn = push(ref(db, "online")).key, started = Date.now();
  const me = ref(db, `online/${conn}`), pm = match ? ref(db, `presence/${match}/${conn}`) : null;
  const mark = () => {
    set(me, { p: String(page).slice(0, 40), t: serverTimestamp(), v: vid, r: src, d: dev, s: started }).catch(() => {});
    if (pm) set(pm, now()).catch(() => {});
  };
  onValue(ref(db, ".info/connected"), s => {
    if (s.val() !== true) return;
    onDisconnect(me).remove().catch(() => {}); if (pm) onDisconnect(pm).remove().catch(() => {});
    mark();
  });
  setInterval(() => { if (document.visibilityState === "visible") mark(); }, 30e3);   // «я ещё тут» каждые 30 секунд, пока вкладка открыта
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") mark(); });
  addEventListener("pagehide", () => { remove(me).catch(() => {}); if (pm) remove(pm).catch(() => {}); });
}
/** Сколько человек смотрят каждый матч: cb({ matchId: n }) — только «живые» отметки. */
export function watchPresence(cb) {
  onValue(ref(db, "presence"), s => { const out = {}, t = now();
    s.forEach(m => { let n = 0; m.forEach(c => { if (typeof c.val() === "number" && t - c.val() < FRESH) n++; }); if (n) out[m.key] = n; }); cb(out); }, () => cb({}));
}
/** Живые посетители: уникальные люди, отмечавшиеся последние 90 секунд. cb(n, list) */
export function watchOnline(cb) {
  let last = null; setInterval(() => { if (last) count(last); }, 30e3);   // пересчёт, даже если в базе тихо
  const count = s => {
    const t = now(), people = {}, stale = [];
    s.forEach(c => { const v = c.val() || {}; const age = t - (v.t || 0);
      if (age < FRESH) { const k = v.v || c.key; if (!people[k] || people[k].t < v.t) people[k] = { ...v, key: c.key }; }
      else if (age > 10 * 60e3) stale.push(c.key); });
    stale.slice(0, 20).forEach(k => remove(ref(db, `online/${k}`)).catch(() => {}));   // подчищаем «зависшие» записи
    cb(Object.keys(people).length, Object.values(people));
  };
  onValue(ref(db, "online"), s => { last = s; count(s); }, () => cb(0, []));
}

// ── аккаунт ──
let profile = null;
getRedirectResult(auth).catch(() => {});   // вход через Google в Telegram/мобильном браузере идёт переходом, а не окном
const listeners = [];
export function onUser(cb) { listeners.push(cb); cb(auth.currentUser, profile); }
onAuthStateChanged(auth, async u => {
  profile = null;
  if (u) { try { const s = await get(ref(db, `users/${u.uid}`)); profile = s.exists() ? s.val() : null; } catch (e) {} }
  listeners.forEach(cb => cb(u, profile));
});
export async function isAdmin() {
  const u = auth.currentUser; if (!u) return false;
  try { return (await get(ref(db, `admins/${u.uid}`))).exists(); } catch (e) { return false; }
}

const CSS = `
.fbm{position:fixed;inset:0;z-index:50;background:rgba(4,7,18,.7);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:16px;font-family:Montserrat,system-ui,sans-serif}
.fbm .bx{width:min(380px,100%);background:linear-gradient(170deg,#18224a,#0d1430);border:1px solid rgba(255,255,255,.12);border-radius:22px;padding:20px;color:#fff}
.fbm h3{font-size:20px;font-weight:900;margin:0 0 4px}.fbm p{color:#9aa6cc;font-size:13px;margin:0 0 14px}
.fbm input{width:100%;box-sizing:border-box;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);color:#fff;border-radius:12px;padding:11px 12px;font:600 14px Montserrat,sans-serif;margin-bottom:8px}
.fbm button{width:100%;border:0;border-radius:12px;padding:12px;font:800 14px Montserrat,sans-serif;cursor:pointer;margin-top:6px}
.fbm .g{background:#fff;color:#1a1a1a}.fbm .y{background:linear-gradient(90deg,#ffc400,#ff9f1a);color:#1a1405}.fbm .t{background:none;color:#9aa6cc;font-weight:700}
.fbm .or{text-align:center;color:#9aa6cc;font-size:12px;margin:12px 0 6px}.fbm .err{color:#ff6a6a;font-size:12px;min-height:16px;margin-top:6px}`;
function css() { if (!document.getElementById("fbcss")) { const s = document.createElement("style"); s.id = "fbcss"; s.textContent = CSS; document.head.appendChild(s); } }
const RU_ERR = { "auth/invalid-email": "Неверный адрес почты", "auth/missing-password": "Введите пароль", "auth/weak-password": "Пароль — минимум 6 символов",
  "auth/email-already-in-use": "Эта почта уже зарегистрирована — войдите", "auth/invalid-credential": "Неверная почта или пароль",
  "auth/too-many-requests": "Слишком много попыток, подождите минуту", "auth/popup-closed-by-user": "Окно входа закрыто", "auth/popup-blocked": "Браузер заблокировал окно входа",
  "auth/user-not-found": "Такой почты нет — зарегистрируйтесь", "auth/wrong-password": "Неверный пароль", "auth/network-request-failed": "Нет связи с сервером, проверьте интернет" };
const errText = e => RU_ERR[e?.code] || "Не получилось: " + (e?.code || e?.message || e);

/** Окно входа/регистрации. Возвращает Promise, который выполнится, когда есть пользователь с именем. */
export function login() {
  css();
  return new Promise(resolve => {
    const w = document.createElement("div"); w.className = "fbm";
    const close = () => w.remove();
    const askName = u => {
      w.innerHTML = `<div class="bx"><h3>Как вас подписать в чате?</h3><p>Имя видят все зрители. 2–24 символа.</p>
        <input id="fbn" maxlength="24" placeholder="Например, Дима" value="${esc((u.displayName || "").slice(0, 24))}"><button class="y" id="fbs">Готово</button><div class="err" id="fbe"></div></div>`;
      w.querySelector("#fbs").onclick = async () => {
        const name = w.querySelector("#fbn").value.trim();
        if (name.length < 2) { w.querySelector("#fbe").textContent = "Минимум 2 символа"; return; }
        try { profile = { name, created: Date.now() }; await set(ref(db, `users/${u.uid}`), profile); listeners.forEach(cb => cb(u, profile)); close(); resolve(u); }
        catch (e) { w.querySelector("#fbe").textContent = errText(e); }
      };
    };
    const done = async u => { const s = await get(ref(db, `users/${u.uid}`)).catch(() => null); if (s && s.exists()) { profile = s.val(); close(); resolve(u); } else askName(u); };
    w.innerHTML = `<div class="bx"><h3>Вход на АИ СТАВИТ</h3><p>Чтобы писать в чат трансляций. Бесплатно, без рассылок.</p>
      <button class="g" id="fbg">Войти через Google</button><div class="or">или по почте</div>
      <input id="fbm" type="email" placeholder="Почта" autocomplete="email"><input id="fbp" type="password" placeholder="Пароль (от 6 символов)" autocomplete="current-password">
      <button class="y" id="fbin">Войти</button><button class="y" id="fbup" style="background:rgba(255,196,0,.15);color:#ffc400">Зарегистрироваться</button>
      <button class="t" id="fbr">Забыли пароль?</button><button class="t" id="fbx">Закрыть</button><div class="err" id="fbe"></div></div>`;
    const E = t => { w.querySelector("#fbe").textContent = t; };
    const m = () => w.querySelector("#fbm").value.trim(), p = () => w.querySelector("#fbp").value;
    w.querySelector("#fbg").onclick = () => signInWithPopup(auth, new GoogleAuthProvider()).then(r => done(r.user)).catch(e => {
      // в Telegram и некоторых мобильных браузерах окна запрещены — входим переходом на страницу Google
      if (/popup-blocked|operation-not-supported|cancelled-popup/.test(e?.code || "")) return signInWithRedirect(auth, new GoogleAuthProvider());
      E(errText(e)); });
    w.querySelector("#fbin").onclick = () => signInWithEmailAndPassword(auth, m(), p()).then(r => done(r.user)).catch(e => E(errText(e)));
    w.querySelector("#fbup").onclick = () => createUserWithEmailAndPassword(auth, m(), p()).then(r => done(r.user)).catch(e => E(errText(e)));
    w.querySelector("#fbr").onclick = () => {
      if (!m()) return E("Сначала впишите почту в поле выше, потом нажмите «Забыли пароль?»");
      sendPasswordResetEmail(auth, m(), { url: location.href }).then(() => {
        w.querySelector("#fbe").style.color = "#7dffb0";
        E("✉️ Письмо отправлено на " + m() + ". Не видите — проверьте папку «Спам». Если вы входили через Google, пароля нет: нажмите «Войти через Google».");
      }).catch(e => E(errText(e))); };
    w.querySelector("#fbx").onclick = () => { close(); resolve(null); };
    w.onclick = e => { if (e.target === w) { close(); resolve(null); } };
    document.body.appendChild(w);
  });
}
export const logout = () => signOut(auth);

// ── чат трансляции ──
/** Подключает чат матча к контейнеру. onCount(n) — сколько сообщений (для бейджа). */
export function mountChat(match, box, onCount) {
  css();
  box.innerHTML = `<div class="chat-list" id="cl_${match}"></div>
    <form class="chat-form"><input maxlength="300" placeholder="Написать в чат…" autocomplete="off"><button>➤</button></form>
    <div class="chat-who"></div>`;
  const list = box.querySelector(".chat-list"), form = box.querySelector("form"), input = form.querySelector("input"), who = box.querySelector(".chat-who");
  let n = 0, admin = false;
  const q = query(ref(db, `chat/${match}`), orderByChild("t"), limitToLast(80));
  const color = s => `hsl(${[...String(s)].reduce((a, c) => a + c.charCodeAt(0), 0) * 47 % 360} 80% 70%)`;
  onChildAdded(q, s => {
    const v = s.val(); n++; onCount && onCount(n);
    const row = document.createElement("div"); row.className = "chat-msg"; row.id = "m_" + s.key;
    const tm = new Date(v.t).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    row.innerHTML = `<b style="color:${color(v.uid)}">${esc(v.name)}</b> <span>${esc(v.text)}</span> <i>${tm}</i>${admin ? ` <a href="#" data-k="${s.key}" title="Удалить">✕</a>` : ""}`;
    list.appendChild(row); list.scrollTop = list.scrollHeight;
  });
  onChildRemoved(q, s => { const el = document.getElementById("m_" + s.key); if (el) el.remove(); n = Math.max(0, n - 1); onCount && onCount(n); });
  list.onclick = e => { const k = e.target?.dataset?.k; if (k) { e.preventDefault(); remove(ref(db, `chat/${match}/${k}`)).catch(() => {}); } };
  onUser(async (u, prof) => {
    admin = await isAdmin();
    who.innerHTML = u && prof ? `Вы в чате как <b>${esc(prof.name)}</b> · <a href="#" class="lo">выйти</a>` : `<a href="#" class="li">Войдите</a>, чтобы писать в чат`;
    const lo = who.querySelector(".lo"), li = who.querySelector(".li");
    if (lo) lo.onclick = e => { e.preventDefault(); logout(); };
    if (li) li.onclick = e => { e.preventDefault(); login(); };
  });
  input.onfocus = async () => { if (!auth.currentUser || !profile) { input.blur(); await login(); } };
  form.onsubmit = async e => {
    e.preventDefault();
    const text = input.value.trim(); if (!text) return;
    if (!auth.currentUser || !profile) { await login(); if (!auth.currentUser || !profile) return; }
    try { await push(ref(db, `chat/${match}`), { uid: auth.currentUser.uid, name: profile.name, text: text.slice(0, 300), t: Date.now() }); input.value = ""; }
    catch (err) { who.innerHTML = /permission/i.test(String(err)) ? "Вы не можете писать в этот чат" : "Сообщение не отправилось, попробуйте ещё раз"; }
  };
}

/** Кнопка в меню: «Войти» или «👤 Имя» (ведёт в профиль). */
export function navUser(el) {
  if (!el) return;
  onUser((u, prof) => {
    if (u && prof) { el.classList.add("in"); el.title = "Мой профиль"; el.innerHTML = `<span style="width:24px;height:24px;display:grid;place-items:center;border-radius:50%;overflow:hidden;background:rgba(255,255,255,.08)">${prof.avatar ? avatarHTML(prof, 24) : esc(prof.emoji || "👤")}</span><span class="nm">${esc(prof.name)}</span>`; el.href = new URL(`profile.html?u=${u.uid}`, import.meta.url).href; el.onclick = null; }
    else { el.classList.remove("in"); el.title = ""; el.textContent = "Войти"; el.href = "#"; el.onclick = e => { e.preventDefault(); login(); }; }
  });
}

// ── аватарки: фото сжимается в браузере до 160×160 и хранится в профиле ──
/** Открывает выбор фото и возвращает data:image/jpeg (≈10–20 КБ) или null. */
export function pickAvatar() {
  return new Promise(resolve => {
    const inp = document.createElement("input"); inp.type = "file"; inp.accept = "image/*";
    inp.onchange = () => {
      const f = inp.files && inp.files[0]; if (!f) return resolve(null);
      const img = new Image(), url = URL.createObjectURL(f);
      img.onload = () => {
        const S = 160, c = document.createElement("canvas"); c.width = c.height = S; const g = c.getContext("2d");
        const k = Math.max(S / img.width, S / img.height), w = img.width * k, h = img.height * k;   // обрезаем по центру в квадрат
        g.drawImage(img, (S - w) / 2, (S - h) / 2, w, h); URL.revokeObjectURL(url);
        let q = .85, data = c.toDataURL("image/jpeg", q);
        while (data.length > 38000 && q > .4) { q -= .1; data = c.toDataURL("image/jpeg", q); }
        resolve(data);
      };
      img.onerror = () => resolve(null); img.src = url;
    };
    inp.click();
  });
}
/** HTML аватарки пользователя: фото или эмодзи. */
export const avatarHTML = (u, size = 40) => u && u.avatar && /^data:image\/(jpeg|png|webp);base64,/.test(u.avatar)
  ? `<img src="${u.avatar}" alt="" style="width:${size}px;height:${size}px;border-radius:50%;object-fit:cover;display:block">`
  : esc((u && u.emoji) || "👤");
const ucache = {};
/** Профиль любого пользователя (имя, аватарка) с кэшем. */
export async function userInfo(uid) {
  if (!ucache[uid]) ucache[uid] = get(ref(db, `users/${uid}`)).then(s => s.val() || {}).catch(() => ({}));
  return ucache[uid];
}

// ── «Поддержать проект»: кнопка в меню всех страниц ──
const PHONE = "+7 906 146-63-36";
function supportModal() {
  css();
  const w = document.createElement("div"); w.className = "fbm";
  w.innerHTML = `<div class="bx" style="text-align:center"><div style="font-size:44px">❤️</div><h3>Поддержать АИ СТАВИТ</h3>
    <p>Бот, сайт и прогнозы бесплатные. Если они вам помогают — поддержите проект переводом по номеру телефона (СБП) на любую сумму.</p>
    <div style="font-size:24px;font-weight:900;letter-spacing:1px;margin:6px 0 4px">${PHONE}</div>
    <div style="display:inline-flex;align-items:center;gap:8px;background:rgba(0,170,255,.14);border:1px solid rgba(0,170,255,.45);color:#7fd6ff;border-radius:999px;padding:6px 14px;font-weight:800;font-size:14px;margin:4px 0 10px">🏦 Банк получателя: Авито</div>
    <p style="font-size:12px;margin:0 0 6px">В приложении своего банка: «Перевод по номеру телефона» → вставьте номер → в списке банков выберите <b>Авито</b>.</p>
    <button class="y" id="spc">📋 Скопировать номер</button><button class="t" id="spx">Закрыть</button><div class="err" id="spm" style="color:#7dffb0"></div>
    <p style="margin-top:10px;font-size:11px">Спасибо! Каждый перевод идёт на развитие бота: новые виды спорта, точнее прогнозы, трансляции.</p></div>`;
  w.querySelector("#spc").onclick = async () => { try { await navigator.clipboard.writeText(PHONE.replace(/[\s-]/g, "")); w.querySelector("#spm").textContent = "Номер скопирован — вставьте его в «Перевод по телефону» и выберите банк Авито"; }
    catch (e) { w.querySelector("#spm").textContent = PHONE; } };
  w.querySelector("#spx").onclick = () => w.remove(); w.onclick = e => { if (e.target === w) w.remove(); };
  document.body.appendChild(w);
}
/** Правый блок шапки (поддержать, колокольчик, профиль). На старых страницах — переносим туда кнопку профиля. */
function navActs() {
  const nav = document.querySelector(".topnav"); if (!nav) return null;
  let box = nav.querySelector(".navacts");
  if (!box) { box = document.createElement("div"); box.className = "navacts"; nav.appendChild(box); const me = nav.querySelector(".links .me"); if (me) box.appendChild(me); }
  return box;
}
export function supportButton() {
  const box = navActs();
  if (!box || box.querySelector(".support")) return;
  const a = document.createElement("a"); a.href = "#"; a.className = "support"; a.title = "Поддержать проект";
  a.innerHTML = `<span>❤</span><span class="tx">Поддержать</span>`;
  a.onclick = e => { e.preventDefault(); supportModal(); };
  box.prepend(a);
}
/** «● 12 онлайн» в шапке рядом с логотипом — на всех страницах с меню. */
export function onlineBadge() {
  const nav = document.querySelector(".topnav"), logo = nav && nav.querySelector(".logo");
  if (!logo || nav.querySelector(".onl")) return;
  if (!document.getElementById("onlcss")) { const st = document.createElement("style"); st.id = "onlcss"; st.textContent = `
    .topnav .brandbox{display:flex;align-items:center;gap:10px;min-width:0}
    .onl{display:inline-flex;align-items:center;gap:6px;padding:4px 10px 4px 8px;border-radius:999px;font:800 12px Montserrat,system-ui,sans-serif;
      color:#7dffb0;background:rgba(46,204,113,.12);border:1px solid rgba(46,204,113,.35);white-space:nowrap;opacity:0;transition:opacity .4s}
    .onl i{width:8px;height:8px;border-radius:50%;background:#2ecc71;box-shadow:0 0 0 0 rgba(46,204,113,.7);animation:onlp 1.8s infinite}
    .onl b{font-weight:900;color:#fff;font-variant-numeric:tabular-nums}
    @keyframes onlp{0%{box-shadow:0 0 0 0 rgba(46,204,113,.7)}70%{box-shadow:0 0 0 7px rgba(46,204,113,0)}100%{box-shadow:0 0 0 0 rgba(46,204,113,0)}}
    @media (max-width:520px){.onl{font-size:11px;padding:3px 8px 3px 7px}}`; document.head.appendChild(st); }
  const box = document.createElement("div"); box.className = "brandbox"; logo.replaceWith(box); box.appendChild(logo);
  const b = document.createElement("span"); b.className = "onl"; b.title = "Сколько человек сейчас на сайте";
  box.appendChild(b);
  watchOnline(n => { const k = Math.max(1, n); b.innerHTML = `<i></i><b>${k}</b><span class="ot"> онлайн</span>`; b.style.opacity = 1; });
}

// ── турнир прогнозистов: расчёт ставок по итоговому счёту ──
export const MARKETS = {
  football: ["П1", "X", "П2", "1X", "X2", "12", "ТБ 1.5", "ТБ 2.5", "ТБ 3.5", "ТМ 1.5", "ТМ 2.5", "ТМ 3.5", "Обе забьют — да", "Обе забьют — нет", "Ф1 (−1.5)", "Ф2 (+1.5)"],
  hockey: ["П1", "П2", "ТБ 4.5", "ТБ 5.5", "ТБ 6.5", "ТМ 4.5", "ТМ 5.5", "ТМ 6.5", "Ф1 (−1.5)", "Ф2 (+1.5)"],
  basketball: ["П1", "П2", "ТБ 210.5", "ТБ 220.5", "ТБ 230.5", "ТМ 210.5", "ТМ 220.5", "ТМ 230.5", "Ф1 (−5.5)", "Ф2 (+5.5)"],
  tennis: ["П1", "П2", "Будет 3 сета", "Будет 2 сета"],
};
const DEFAULT_ODDS = 1.85;
/** Зашла ли ставка: true / false / null (не понять или возврат). s = [хозяева, гости] (теннис — сеты). */
export function settle(label, s) {
  if (!s) return null;
  const [h, a] = s.map(Number), L = String(label || "").toUpperCase().replace(/Х/g, "X").replace(/−/g, "-").replace(/\s+/g, " ").trim();
  let m;
  if (/^П1\b/.test(L) || L === "1") return h > a;
  if (/^П2\b/.test(L) || L === "2") return a > h;
  if (/^(X|НИЧЬЯ)$/.test(L)) return h === a;
  if (L === "1X") return h >= a;
  if (L === "X2") return a >= h;
  if (L === "12") return h !== a;
  if ((m = L.match(/^ТБ ?(\d+(?:[.,]\d+)?)/))) { const n = parseFloat(m[1].replace(",", ".")); return h + a === n ? null : h + a > n; }
  if ((m = L.match(/^ТМ ?(\d+(?:[.,]\d+)?)/))) { const n = parseFloat(m[1].replace(",", ".")); return h + a === n ? null : h + a < n; }
  if (/ОБЕ ЗАБЬЮТ/.test(L)) return /НЕТ/.test(L) ? !(h > 0 && a > 0) : (h > 0 && a > 0);
  if ((m = L.match(/^Ф([12]) ?\(?([+-]?\d+(?:[.,]\d+)?)\)?/))) { const n = parseFloat(m[2].replace(",", ".")), d = m[1] === "1" ? h + n - a : a + n - h; return d === 0 ? null : d > 0; }
  if (/3 СЕТА/.test(L)) return h + a === 3;
  if (/2 СЕТА/.test(L)) return h + a === 2;
  return null;
}
let scoresP = null;
/** Итоги завершённых матчей (бот обновляет docs/scores.json). */
export function scores() {
  if (!scoresP) {
    const local = new URL("scores.json", import.meta.url).href;
    const url = location.hostname.endsWith("github.io") ? "https://raw.githubusercontent.com/horoooos/betbot/main/docs/scores.json" : local;
    scoresP = fetch(url, { cache: "no-store" }).then(r => r.json()).catch(() => fetch(local).then(r => r.json()).catch(() => ({})));
  }
  return scoresP;
}
/** Рейтинг прогнозистов. posts — {id: пост}; from/to — по времени начала матча. */
export function board(posts, sc, from = 0, to = Infinity) {
  const out = {};
  for (const p of Object.values(posts || {})) {
    if (!p.match || !p.pick) continue;
    const k = new Date(p.match.kickoff).getTime();
    if (!(p.t < k) || k < from || k > to) continue;          // в зачёт только прогнозы, сделанные до начала матча
    const r = sc[p.match.id], res = r ? settle(p.pick, r.s) : undefined;
    const u = out[p.uid] || (out[p.uid] = { uid: p.uid, name: p.name, n: 0, w: 0, open: 0, profit: 0, last: 0 });
    u.name = p.name; u.last = Math.max(u.last, p.t);
    if (res === undefined) { u.open++; continue; }
    if (res === null) continue;
    u.n++; const o = p.odds > 1 ? p.odds : DEFAULT_ODDS;
    if (res) { u.w++; u.profit += o - 1; } else u.profit -= 1;
  }
  return Object.values(out).map(u => ({ ...u, profit: Math.round(u.profit * 100) / 100, pct: u.n ? Math.round(u.w / u.n * 100) : 0, roi: u.n ? Math.round(u.profit / u.n * 100) : 0 }))
    .sort((a, b) => b.profit - a.profit || b.pct - a.pct || b.n - a.n);
}

// ── «Бот против подписчиков»: согласны с прогнозом бота или нет ──
export function voteWidget(el, matchId, opts = {}) {
  if (!el || !matchId) return;
  const finished = !!opts.finished, botHit = opts.botHit ?? null;
  const key = () => (auth.currentUser && auth.currentUser.uid) || visitorId();
  const btn = (v, on, color, bg, text) => `<button data-v="${v}" style="flex:1;min-width:140px;border:1px solid ${on ? color : "rgba(255,255,255,.15)"};background:${on ? bg : "rgba(255,255,255,.05)"};color:#fff;border-radius:12px;padding:10px;font:800 14px Montserrat,sans-serif;cursor:pointer">${text}</button>`;
  const draw = s => {
    let a = 0, d = 0, mine = null;
    s.forEach(c => { if (c.val() === "a") a++; if (c.val() === "d") d++; if (c.key === key()) mine = c.val(); });
    const n = a + d, pa = n ? Math.round(a / n * 100) : 50;
    const res = finished && botHit !== null ? `<div style="margin-top:8px;font-weight:800">${botHit ? "✅ Бот оказался прав — правы те, кто был согласен" : "❌ Бот ошибся — правы те, кто был против"}</div>` : "";
    el.innerHTML = `<div style="font-weight:800;margin-bottom:8px">🤖 Бот против подписчиков: вы согласны с прогнозом?</div>`
      + (finished ? "" : `<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">${btn("a", mine === "a", "#2ecc71", "rgba(46,204,113,.2)", "👍 Согласен с ботом")}${btn("d", mine === "d", "#ff5a5a", "rgba(255,90,90,.18)", "👎 Я против")}</div>`)
      + `<div style="display:flex;height:28px;border-radius:10px;overflow:hidden;font:900 12px Montserrat,sans-serif">
        <div style="width:${pa}%;background:#2ecc71;display:flex;align-items:center;padding-left:8px">${n ? pa + "%" : ""}</div>
        <div style="flex:1;background:#ff5a5a;display:flex;align-items:center;justify-content:flex-end;padding-right:8px">${n ? 100 - pa + "%" : ""}</div></div>
      <div style="display:flex;justify-content:space-between;font-size:12px;color:#9aa6cc;margin-top:4px"><span>Согласны: ${a}</span><span>Против: ${d}</span></div>${res}`;
    el.querySelectorAll("button[data-v]").forEach(b => b.onclick = () => {
      const r = ref(db, `votes/${matchId}/${key()}`);
      (mine === b.dataset.v ? remove(r) : set(r, b.dataset.v)).catch(() => {});
    });
  };
  onValue(ref(db, `votes/${matchId}`), draw, () => {});
}

// ── «Угадай счёт дня» ──
/** Матч дня для викторины: «прогноз дня» бота сегодня, иначе первый футбольный матч с прогнозом. */
export function quizMatch(list) {
  const day = d => new Date(d).toLocaleDateString("ru-RU", { timeZone: "Europe/Moscow" }), today = day(Date.now());
  const todays = (list || []).filter(m => day(m.kickoff) === today && m.sport === "football");
  return todays.find(m => m.top) || todays.filter(m => m.tip).sort((a, b) => a.kickoff.localeCompare(b.kickoff))[0] || todays[0] || null;
}
export const quizPoints = (guess, s) => {
  if (!guess || !s) return null;
  const [gh, ga] = guess.split(":").map(Number), [h, a] = s;
  if (gh === h && ga === a) return 3;
  return Math.sign(gh - ga) === Math.sign(h - a) ? 1 : 0;
};
export function quizWidget(el, m) {
  if (!el) return;
  if (!m) { el.innerHTML = `<div class="muted">Сегодня матча для викторины нет — загляните завтра.</div>`; return; }
  const k = new Date(m.kickoff).getTime();
  const inp = (id, v) => `<input id="${id}" type="number" min="0" max="20" value="${v}" style="width:64px;text-align:center;font:900 22px Montserrat,sans-serif;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.15);color:#fff;border-radius:12px;padding:8px">`;
  const draw = async u => {
    const open = Date.now() < k;
    const snap = u ? await get(ref(db, `quiz/${m.id}/${u.uid}`)).catch(() => null) : null, mine = snap ? snap.val() : null;
    const sc = (await scores())[m.id];
    const t = new Date(m.kickoff).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Moscow" });
    let body;
    if (sc) body = `<div>Итог: <b>${sc.s.join(":")}</b>${mine ? ` · ваш ответ ${esc(mine.s)} → <b>+${quizPoints(mine.s, sc.s)} очк.</b>` : ""}</div>`;
    else if (open) body = `<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${inp("qh", mine ? mine.s.split(":")[0] : "")}<b style="font-size:22px">:</b>${inp("qa", mine ? mine.s.split(":")[1] : "")}
        <button id="qs" style="border:0;border-radius:12px;padding:12px 16px;background:linear-gradient(90deg,#ffc400,#ff9f1a);color:#1a1405;font:900 14px Montserrat,sans-serif;cursor:pointer">${mine ? "Изменить" : "Ответить"}</button></div>
        <div class="small muted" style="margin-top:6px">Точный счёт — 3 очка, угадан исход — 1 очко. Ответы принимаются до начала матча.${mine ? ` Ваш ответ: <b>${esc(mine.s)}</b>` : ""}</div>`;
    else body = `<div class="muted">Приём ответов закрыт — матч начался.${mine ? ` Ваш ответ: <b>${esc(mine.s)}</b>` : ""}</div>`;
    el.innerHTML = `<div style="font-weight:900;font-size:17px">🎯 Угадай счёт дня</div>
      <div style="margin:6px 0 10px"><b>${esc(m.home)} — ${esc(m.away)}</b> <span class="muted small">· ${esc(m.league)} · ${t} МСК</span></div>${body}
      <div class="small" id="qe" style="color:#ff6a6a;margin-top:4px"></div>`;
    const b = el.querySelector("#qs"); if (!b) return;
    b.onclick = async () => {
      if (!auth.currentUser || !profile) { await login(); if (!auth.currentUser || !profile) return; }
      const h = parseInt(el.querySelector("#qh").value, 10), a = parseInt(el.querySelector("#qa").value, 10);
      if (!(h >= 0 && a >= 0 && h < 21 && a < 21)) { el.querySelector("#qe").textContent = "Впишите счёт, например 2 : 1"; return; }
      try { await set(ref(db, `quiz/${m.id}/${auth.currentUser.uid}`), { s: `${h}:${a}`, t: serverTimestamp(), n: profile.name }); draw(auth.currentUser); }
      catch (e) { el.querySelector("#qe").textContent = "Не сохранилось, попробуйте ещё раз"; }
    };
  };
  onUser(u => draw(u));
}

// ── push-уведомления (Firebase Cloud Messaging): голы в выбранных матчах и прогноз дня ──
const VAPID = "BLB0-dN_T6rpAFTmzkNWKRUTalT7Ow8R0NRhVGN4zCiBFJByiMehYcqiwSmZSy_eQtwskfG9nzqt9frXfmrxzMc";
const pushKey = t => t.replace(/[.#$\[\]\/]/g, "_");
let pushTok = null;
/** Включает push: разрешение браузера + токен устройства. Возвращает токен или бросает понятную ошибку. */
export async function pushToken() {
  if (pushTok) return pushTok;
  const mm = await import("https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging.js");
  if (!(await mm.isSupported())) throw new Error(/iPhone|iPad/.test(navigator.userAgent) ? "На iPhone уведомления работают, если добавить сайт на экран «Домой» (Поделиться → На экран «Домой») и открыть его оттуда" : "Этот браузер не поддерживает уведомления");
  const perm = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
  if (perm !== "granted") throw new Error("Уведомления запрещены — разрешите их в настройках браузера для этого сайта");
  const reg = await navigator.serviceWorker.register(new URL("firebase-messaging-sw.js", import.meta.url).href, { scope: new URL("./", import.meta.url).pathname });
  pushTok = await mm.getToken(mm.getMessaging(app), { vapidKey: VAPID, serviceWorkerRegistration: reg });
  if (!pushTok) throw new Error("Не удалось получить разрешение на уведомления");
  ls.set("aipush", "1");
  return pushTok;
}
/** Подписка: daily — прогноз дня; match — следить за голами этого матча. */
export async function pushSubscribe({ daily = null, match = null, title = "" } = {}) {
  const t = await pushToken(), r = ref(db, `push/${pushKey(t)}`);
  const upd = { t, ts: serverTimestamp() };
  if (daily !== null) upd.d = !!daily;
  if (auth.currentUser) upd.u = auth.currentUser.uid;
  await update(r, upd);
  if (match) await set(ref(db, `push/${pushKey(t)}/m/${match}`), String(title || "1").slice(0, 80));
  return true;
}
export async function pushUnfollow(match) { if (!pushTok) await pushToken(); await remove(ref(db, `push/${pushKey(pushTok)}/m/${match}`)); }
export const pushEnabled = () => ls.get("aipush") === "1" && typeof Notification !== "undefined" && Notification.permission === "granted";

function pushModal() {
  css();
  const w = document.createElement("div"); w.className = "fbm";
  const on = pushEnabled();
  w.innerHTML = `<div class="bx" style="text-align:center"><div style="font-size:44px">🔔</div><h3>Уведомления АИ СТАВИТ</h3>
    <p>Приходят на телефон и компьютер, даже когда сайт закрыт.</p>
    <label style="display:flex;gap:10px;align-items:center;text-align:left;margin:8px 0;font-weight:700"><input type="checkbox" id="pd" checked style="width:20px;height:20px"> 🔥 Прогноз дня — один раз в день</label>
    <div style="text-align:left;font-size:13px;color:#9aa6cc;margin-bottom:8px">⚽ Голы, 🏒 шайбы, 🎾 сеты — нажмите 🔔 в трансляции нужного матча.</div>
    <button class="y" id="pon">${on ? "Сохранить" : "Включить уведомления"}</button><button class="t" id="px">Закрыть</button><div class="err" id="pe"></div></div>`;
  w.querySelector("#pon").onclick = async () => {
    const e = w.querySelector("#pe"); e.style.color = "#9aa6cc"; e.textContent = "Включаем…";
    try { await pushSubscribe({ daily: w.querySelector("#pd").checked }); e.style.color = "#7dffb0"; e.textContent = "✅ Готово! Уведомления включены."; paintBell(); }
    catch (x) { e.style.color = "#ff6a6a"; e.textContent = x.message || "Не получилось включить"; }
  };
  w.querySelector("#px").onclick = () => w.remove(); w.onclick = ev => { if (ev.target === w) w.remove(); };
  document.body.appendChild(w);
}
function paintBell() { const b = document.querySelector(".topnav .bell"); if (b) b.textContent = pushEnabled() ? "🔔" : "🔕"; }
export function bellButton() {
  const box = navActs();
  if (!box || box.querySelector(".bell") || typeof Notification === "undefined") return;
  const a = document.createElement("a"); a.href = "#"; a.className = "bell"; a.title = "Уведомления: голы, сеты и прогноз дня";
  a.onclick = e => { e.preventDefault(); pushModal(); };
  const me = box.querySelector(".me"); box.insertBefore(a, me || null); paintBell();
}

// запуск кнопок меню — в самом конце, когда все функции модуля уже объявлены
/** 🔍 в шапке — поиск команд и игроков (страница leagues.html). */
export function searchButton() {
  const box = navActs();
  if (!box || box.querySelector(".srch")) return;
  const a = document.createElement("a"); a.className = "srch bell"; a.title = "Поиск команд и игроков"; a.textContent = "🔍";
  a.href = new URL("leagues.html", import.meta.url).href;
  box.insertBefore(a, box.querySelector(".support") ? box.querySelector(".support").nextSibling : box.firstChild);
}
// ── просмотры новостей: +1 от посетителя (не чаще раза в сутки), счётчик на карточках ──
/** el — элемент с data-view="news:123" (страница новости). */
export async function countView(el) {
  const key = el && el.dataset && el.dataset.view; if (!key || !/^[a-z]+:[\w-]{1,60}$/.test(key)) return;
  const day = new Date().toISOString().slice(0, 10), mark = "vw:" + key;
  if (ls.get(mark) === day) return;
  try { await runTransaction(ref(db, `views/${key.replace(":", "/")}`), v => (typeof v === "number" ? v : 0) + 1); ls.set(mark, day); showViews(); } catch (e) {}
}
const fmtViews = n => n >= 1e6 ? (n / 1e6).toFixed(1).replace(".0", "") + " млн" : n >= 1e3 ? (n / 1e3).toFixed(1).replace(".0", "") + " тыс." : String(n);
/** Заполняет все [data-views="news:123"] числом просмотров (пустые — если просмотров ещё нет). */
export function showViews(root = document) {
  root.querySelectorAll("[data-views]").forEach(async el => {
    const key = el.dataset.views; if (!/^[a-z]+:[\w-]{1,60}$/.test(key)) return;
    try { const s = await get(ref(db, `views/${key.replace(":", "/")}`)); const n = s.val();
      if (typeof n === "number" && n > 0) { el.textContent = `👁 ${fmtViews(n)}`; el.title = `${n} просмотров`; } } catch (e) {}
  });
}

/** Карточки и секции плавно появляются при прокрутке. */
export function reveal() {
  if (typeof IntersectionObserver === "undefined" || document.documentElement.classList.contains("rv-on")) return;
  document.documentElement.classList.add("rv-on");
  const io = new IntersectionObserver(es => { for (const e of es) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }, { rootMargin: "0px 0px -6% 0px" });
  // анимируем только то, что ещё не видно: блоки, которые страница перерисовывает на экране (счёт, списки), не мигают
  let first = true, started = Date.now();
  const mark = () => { document.querySelectorAll("main .card:not(.rv):not(.rv-skip), main h2:not(.rv):not(.rv-skip), main .grid > *:not(.rv):not(.rv-skip), main .kpi:not(.rv):not(.rv-skip)").forEach((el, i) => {
    const r = el.getBoundingClientRect(), seen = r.top < innerHeight;
    if (seen && !(first || Date.now() - started < 600)) { el.classList.add("rv-skip"); return; }
    el.classList.add("rv");
    if (seen) { el.style.transitionDelay = Math.min(i, 8) * 40 + "ms"; requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add("in"))); } else io.observe(el); }); first = false; };
  mark(); new MutationObserver(() => mark()).observe(document.querySelector("main") || document.body, { childList: true, subtree: true });
}
// ── мини-приложение Telegram: сайт открыт внутри Telegram (из канала или меню бота) ──
export const inTelegram = () => { try { return sessionStorage.getItem("tgapp") === "1" || /tgWebApp/.test(location.hash + location.search); } catch (e) { return false; } };
function telegramApp() {
  if (!inTelegram()) return;
  try { sessionStorage.setItem("tgapp", "1"); } catch (e) {}
  const start = tg => {
    try { tg.ready(); tg.expand(); tg.setHeaderColor?.("#070b1a"); tg.setBackgroundColor?.("#070b1a"); tg.disableVerticalSwipes?.(); } catch (e) {}
    // «Назад» в шапке Telegram — на всех страницах, кроме первой
    const home = /\/betbot\/(index\.html)?$/.test(location.pathname) || location.pathname.endsWith("/app.html");
    if (tg.BackButton) { if (!home && history.length > 1) { tg.BackButton.show(); tg.BackButton.onClick(() => history.back()); } else tg.BackButton.hide(); }
    // внешние ссылки — средствами Telegram: t.me — внутри Telegram, остальное (BetBoom) — во внешнем браузере/приложении
    document.addEventListener("click", e => {
      const a = e.target.closest && e.target.closest("a[href]"); if (!a) return;
      const u = new URL(a.href, location.href);
      if (u.host === location.host) { if (a.target === "_blank") { e.preventDefault(); location.href = u.href; } return; }   // свои страницы — в том же окне мини-приложения
      e.preventDefault();
      if (/^(t\.me|telegram\.me)$/.test(u.host)) tg.openTelegramLink(u.href); else tg.openLink(u.href, { try_instant_view: false });
    }, true);
    document.documentElement.classList.add("tg");
  };
  if (window.Telegram && Telegram.WebApp) return start(Telegram.WebApp);
  const s = document.createElement("script"); s.src = "https://telegram.org/js/telegram-web-app.js?56"; s.onload = () => window.Telegram && start(Telegram.WebApp);
  document.head.appendChild(s);
}
const boot = () => { telegramApp(); supportButton(); searchButton(); onlineBadge(); bellButton(); reveal(); };
if (typeof document !== "undefined") { if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot(); }
