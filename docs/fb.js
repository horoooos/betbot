// Общий модуль сайта АИ СТАВИТ: вход (почта / Google), «кто смотрит» и чат трансляций — на Firebase.
// Ключи ниже не секретные: Firebase сам вставляет их в любой сайт, доступ ограничен правилами базы.
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth, onAuthStateChanged, GoogleAuthProvider, signInWithPopup, signInWithRedirect, getRedirectResult, signInWithEmailAndPassword,
  createUserWithEmailAndPassword, signOut, sendPasswordResetEmail } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";
import { getDatabase, ref, set, get, push, remove, update, onValue, onDisconnect, serverTimestamp, query, orderByChild, equalTo, limitToLast,
  endBefore, onChildAdded, onChildRemoved, onChildChanged } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-database.js";

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

// ── посетители: кто сейчас на сайте и сколько уникальных за день ──
function visitorId() {
  let v = ls.get("aiv"); if (!v) { v = Math.random().toString(36).slice(2) + Date.now().toString(36); ls.set("aiv", v); }
  return v;
}
/** page — короткое имя страницы ("index", "matches", "live:401888371"); match — id матча, если это трансляция. */
export function track(page, match = null) {
  const vid = visitorId(), day = new Date().toISOString().slice(0, 10);
  if (ls.get("aiday") !== day) { set(ref(db, `visits/${day}/${vid}`), Date.now()).catch(() => {}); ls.set("aiday", day); }   // повтор за день правила всё равно не пустят
  const conn = push(ref(db, "online")).key;
  onValue(ref(db, ".info/connected"), s => {
    if (s.val() !== true) return;
    const me = ref(db, `online/${conn}`);
    onDisconnect(me).remove().then(() => set(me, { p: String(page).slice(0, 40), t: serverTimestamp() })).catch(() => {});
    if (match) { const pm = ref(db, `presence/${match}/${conn}`); onDisconnect(pm).remove().then(() => set(pm, Date.now())).catch(() => {}); }
  });
}
/** Сколько человек смотрят каждый матч: cb({ matchId: n }) */
export function watchPresence(cb) {
  onValue(ref(db, "presence"), s => { const out = {}; s.forEach(m => { out[m.key] = m.size; }); cb(out); }, () => cb({}));
}
/** Сколько человек сейчас на сайте: cb(n) */
export function watchOnline(cb) { onValue(ref(db, "online"), s => cb(s.size), () => cb(0)); }

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
    if (u && prof) { el.innerHTML = `${esc(prof.emoji || "👤")} ${esc(prof.name)}`; el.href = `profile.html?u=${u.uid}`; el.onclick = null; }
    else { el.textContent = "Войти"; el.href = "#"; el.onclick = e => { e.preventDefault(); login(); }; }
  });
}
