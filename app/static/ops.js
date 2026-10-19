'use strict';
const el = (id) => document.getElementById(id);
let page = 1, totalPages = 1, busy = false;
const formatTime = (v) => v ? new Date(v).toLocaleString('es-ES', { timeZone: 'Europe/Madrid', timeZoneName: 'short' }) : '—';
const text = (id,v) => {el(id).textContent = v == null ? '—' : String(v);};
async function json(path) {
  const r = await fetch(path, {credentials:'same-origin', cache:'no-store', headers:{Accept:'application/json'}});
  if (r.status === 401) {location.assign('/login');throw Error('No autenticado');}
  if (!r.ok) throw Error('HTTP ' + r.status);
  return r.json();
}
async function refresh() {
  if(busy)return;busy=true;el('refresh').disabled=true;text('feedback','Consultando estado en Neon…');
  try {
    const qp = new URLSearchParams({page:String(page),page_size:'25'});
    if(el('severity').value)qp.set('severity',el('severity').value);
    if(el('service').value)qp.set('service',el('service').value);
    const [health, logs] = await Promise.all([json('/api/ops/status'),json('/api/ops/logs?'+qp)]);
    const w=health.worker||{};
    text('state',w.status||'SIN DATOS');el('state').dataset.status=w.status||'SIN DATOS';
    text('age',w.age_seconds==null?'Sin heartbeat':Math.round(w.age_seconds)+' segundos');
    text('heartbeat',formatTime(w.last_seen_at));text('success',formatTime(w.last_success_at));
    text('cycle',health.last_cycle?.status||'SIN DATOS');text('errors',health.errors_24h);
    el('rows').replaceChildren();
    for(const item of logs.items||[]) {
      const tr=document.createElement('tr');
      for(const value of [formatTime(item.created_at),item.service,item.severity,item.code,item.message]) {
        const td=document.createElement('td');td.textContent=value??'—';tr.append(td);
      }el('rows').append(tr);
    }
    if(!el('rows').children.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=5;td.textContent='Sin eventos para estos filtros';tr.append(td);el('rows').append(tr);}
    totalPages=Math.max(1,Math.ceil(logs.total/25));text('pagination','Página '+page+' de '+totalPages+' · '+logs.total+' eventos');
    el('prev').disabled=page<=1;el('next').disabled=page>=totalPages;
    text('feedback','Última consulta '+new Date().toLocaleTimeString('es-ES'));
  } catch(e){text('feedback','Error consultando logs: '+e.message);text('state','ERROR DE CONEXIÓN');el('state').dataset.status='ERROR';}
  finally{busy=false;el('refresh').disabled=false;}
}
el('refresh').addEventListener('click',refresh);
el('prev').addEventListener('click',()=>{if(page>1){page--;refresh();}});
el('next').addEventListener('click',()=>{if(page<totalPages){page++;refresh();}});
for(const id of ['service','severity']) el(id).addEventListener('change',()=>{page=1;refresh();});
refresh();setInterval(()=>{if(!document.hidden)refresh();},60_000);