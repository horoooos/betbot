// Фоновые push-уведомления АИ СТАВИТ (голы, прогноз дня) — работают, даже когда сайт закрыт.
importScripts("https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js");
firebase.initializeApp({
  apiKey: "AIzaSyCijCZYGyEgmYNmb2GQMKkGpSHF2j_JZuA", authDomain: "aistavvit.firebaseapp.com",
  databaseURL: "https://aistavvit-default-rtdb.europe-west1.firebasedatabase.app", projectId: "aistavvit",
  storageBucket: "aistavvit.firebasestorage.app", messagingSenderId: "69507895892", appId: "1:69507895892:web:c2bb1f02969824e1dad3c1",
});
const messaging = firebase.messaging();
// уведомление с полем notification браузер показывает сам; здесь — только переход по клику
self.addEventListener("notificationclick", e => {
  const link = (e.notification.data && (e.notification.data.FCM_MSG?.notification?.click_action || e.notification.data.link)) || "/betbot/";
  e.notification.close();
  e.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then(ws => {
    for (const w of ws) if (w.url.includes(link) && "focus" in w) return w.focus();
    return clients.openWindow(link);
  }));
});
