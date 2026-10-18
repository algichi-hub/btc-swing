/* F5 SW: static shell only; no private/API/session caching, even when offline. */
'use strict';
const CACHE='btc-v5-static-f5-v1';
const SAFE=new Set(['/static/styles.css','/static/ops.css','/static/app.js','/static/ops.js','/static/login.js']);
self.addEventListener('install',e=>{e.waitUntil(self.skipWaiting());});
self.addEventListener('activate',e=>{e.waitUntil((async()=>{
  for(const key of await caches.keys()) await caches.delete(key);
  await self.clients.claim();
})());});
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(u.origin!==self.location.origin||e.request.method!=='GET'||!SAFE.has(u.pathname))return;
  // Network-first with no persistent storage: deliberately no Cache.put
  e.respondWith(fetch(e.request));
});
self.addEventListener('push',e=>{
  // No live subscriptions during F5-E0. Never show payload containing private trading data.
  const payload=(()=>{try{return e.data?.json()}catch{return null}})();
  if(!payload||payload.title!=='BTC Swing V5')return;
  if(payload.kind==='BTC_V5_TEST'){
    e.waitUntil(self.registration.showNotification('BTC Swing V5',{
      body:'Notificación de prueba',tag:'btc-v5-test',data:{url:'/login'}
    }));
    return;
  }
  if(payload.kind!=='TRADE_EVENT')return;
  const messages={OPEN:'Nueva señal de entrada',ENTRY:'Nueva señal de entrada',
    TP1:'Objetivo TP1 alcanzado',TP2:'Objetivo TP2 alcanzado',
    TP3:'Objetivo TP3 alcanzado',SL:'Stop loss ejecutado',
    CLOSED:'Operación cerrada',CLOSE:'Operación cerrada',
    STOP_LOSS:'Stop loss ejecutado',TAKE_PROFIT:'Objetivo alcanzado'};
  const event=String(payload.event||'');
  if(!Object.prototype.hasOwnProperty.call(messages,event))return;
  const tag='btc-v5-trade-'+String(payload.id||'').slice(0,16);
  e.waitUntil(self.registration.showNotification('BTC Swing V5',{
    body:messages[event],tag,data:{url:'/login'}
  }));
});
self.addEventListener('notificationclick',e=>{
  e.notification.close();
  e.waitUntil(self.clients.openWindow('/login'));
});
