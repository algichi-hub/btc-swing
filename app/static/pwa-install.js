/* F5: local opt-in Web Push, no private data in notifications */
'use strict';
const pushUI = () => {
 const ui=document.getElementById('push-settings');
 if(!ui) return;
 const feedback=document.getElementById('push-feedback');
 const devices=document.getElementById('push-devices');
 const enable=document.getElementById('push-enable');
 const msg=t=>{feedback.textContent=t;};
 async function csrf(){
   const r=await fetch('/api/auth/csrf',{credentials:'same-origin',cache:'no-store'});
   if(!r.ok) throw Error('Sesión no disponible');
   return (await r.json()).csrf_token;
 }
 const keyBytes = key => {
   const s=(key+'='.repeat((4-key.length%4)%4)).replace(/-/g,'+').replace(/_/g,'/');
   return Uint8Array.from(atob(s),c=>c.charCodeAt(0));
 };
 const post=async(path,data)=>{
   const r=await fetch(path,{method:'POST',credentials:'same-origin',cache:'no-store',
      headers:{'Content-Type':'application/json','X-CSRF-Token':await csrf()},
      body:JSON.stringify(data)});
   if(!r.ok) throw Error('La operación no se pudo completar (HTTP '+r.status+')');
   return r.json();
 };
 async function refresh(){
   const r=await fetch('/api/push/devices',{credentials:'same-origin',cache:'no-store'});
   if(!r.ok){msg('No disponible');return}
   const info=await r.json(); devices.replaceChildren();
   if(!info.enabled){enable.disabled=true;msg('Push todavía no está habilitado en Preview');return}
   for(const d of info.items){
     const li=document.createElement('li'); const name=document.createElement('span');
     name.textContent=d.label+' · '+new Date(d.created_at).toLocaleDateString('es-ES');
     const test=document.createElement('button');test.type='button';test.textContent='Enviar prueba';
     test.addEventListener('click',async()=>{try{await post('/api/push/test',{id:d.id});msg('Envío aceptado; revisa las notificaciones del dispositivo')}catch(e){msg(e.message)}});
     const revoke=document.createElement('button');revoke.type='button';revoke.textContent='Revocar';
     revoke.addEventListener('click',async()=>{try{await post('/api/push/revoke',{id:d.id});await refresh();msg('Suscripción revocada')}catch(e){msg(e.message)}});
     li.append(name,' ',test,' ',revoke);devices.append(li);
   }
   msg(info.items.length+' dispositivo(s) activo(s)');
 }
 enable.addEventListener('click',async()=>{
   enable.disabled=true;
   try{
     if(!('PushManager' in window)||!('serviceWorker' in navigator)||!window.isSecureContext) throw Error('Web Push no disponible');
     const r=await fetch('/api/push/config',{credentials:'same-origin',cache:'no-store'});
     if(!r.ok)throw Error('Configuración inaccesible');
     const config=await r.json();
     if(!config.enabled||!config.public_key) throw Error('Push no habilitado en servidor');
     const permission=await Notification.requestPermission();
     if(permission!=='granted')throw Error('Permiso no concedido');
     const reg=await navigator.serviceWorker.ready;
     const sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:keyBytes(config.public_key)});
     await post('/api/push/subscribe',{endpoint:sub.endpoint,keys:sub.toJSON().keys,device_label:navigator.userAgent.includes('Android')?'Android':'Navegador'});
     msg('Suscripción activa');await refresh();
   }catch(e){msg(e.message)}finally{enable.disabled=false}
 });
 document.getElementById('push-refresh').addEventListener('click',()=>refresh().catch(()=>msg('No disponible')));
 void refresh().catch(()=>msg('No disponible'));
};
if('serviceWorker' in navigator && window.isSecureContext){
 window.addEventListener('load',()=>{
   navigator.serviceWorker.register('/sw.js',{scope:'/'})
    .catch(()=>{ /* page remains usable */ });
 });
}
document.addEventListener('DOMContentLoaded',pushUI);
