/* Physical fibers are independent; no readings are inferred from topology. */
(() => {
 let config=null, active=null, pinned=false, editing=null, pointer={x:20,y:100};
 const svg=$('#backbone-map'), info=$('#backbone-info');
 const byId=id=>config.nodes.find(n=>n.id===id);
 const device=n=>state.data.devices.find(d=>d.host===n.host&&d.kind==='datacom')||state.data.devices.find(d=>d.host===n.host);
 const names={up:'Ativa',down:'Caída',error:'Erro de coleta',missing:'Sem leitura',maintenance:'Em reparo'};
 function reading(n,port){
  const d=device(n);
  if(!d||!port)return {label:!port?'Porta pendente': 'Equipamento não cadastrado',port:null};
  if(!$('#connection-error').hidden||d.ssh_error)return {label:'Erro de coleta',error:true,port:null};
  const p=(d.port_data||[]).find(p=>portIdentity(p,d)===port||String(p.name).toLowerCase()===port.toLowerCase());
  if(!p)return {label:'Porta sem leitura',port:null};
  const fresh=Number.isFinite(Date.parse(p.checked_at))&&Date.now()-Date.parse(p.checked_at)<90000&&Date.parse(p.checked_at)<=Date.now()+5000;
  if(!fresh)return {label:'Leitura desatualizada',port:null};
  return {label:labels[p.state]||'Sem leitura',port:p};
 }
 function values(link){
  const a=reading(byId(link.a),link.port_a),b=reading(byId(link.b),link.port_b);
  const status=link.maintenance?'maintenance':[a,b].some(r=>r.port?.state==='down')?'down':[a,b].some(r=>r.error)?'error':[a,b].every(r=>r.port?.state==='up')?'up':'missing';
  return {a,b,status};
 }
 const rate=r=>r.port?.rx_bps==null?'—':bandwidth(r.port.rx_bps).replace(/<[^>]*>/g,'');
 const signal=r=>r.port?.rx==null?'—':`${number(r.port.rx,2)} dBm`;
 function path(link){
  const a=byId(link.a),b=byId(link.b),dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy)||1;
  const cx=(a.x+b.x)/2-dy/len*link.bend*2,cy=(a.y+b.y)/2+dx/len*link.bend*2;
  const x=(a.x+2*cx+b.x)/4,vertical=Math.abs(dx)<80;
  return {d:`M${a.x},${a.y} Q${cx},${cy} ${b.x},${b.y}`,x,y:(a.y+2*cy+b.y)/4,labelX:vertical?(x<885?x+25:x-10):x,anchor:vertical?(x<885?'start':'end'):'middle'};
 }
 function captionOffset(link){return link.bend===0&&!link.label?-32:link.bend<0?-30:60;}
 function draw(){
  svg.innerHTML=config.links.map(link=>{const p=path(link);return `<g class="backbone-fiber" data-link="${link.id}" tabindex="0" role="button"><path class="fiber-stroke" d="${p.d}"/><path class="fiber-hit" d="${p.d}"/><text class="fiber-caption" x="${p.labelX}" y="${p.y+captionOffset(link)}" text-anchor="${p.anchor}"></text></g>`;}).join('')+config.nodes.map(n=>`<g class="backbone-node" data-node="${n.id}" transform="translate(${n.x} ${n.y})" tabindex="0" role="button" aria-label="${esc(n.name+' '+n.host)}"><circle r="20"/><image href="/static/icons/datacom.png" x="-18" y="-18" width="36" height="36"/><text y="36" text-anchor="middle">${esc(n.name)}</text><text class="node-ip" y="51" text-anchor="middle">${n.host}${n.kind==='huawei'?' · Huawei':''}</text></g>`).join('');
  refresh();
 }
 function refresh(){
  if(!config||state.page!=='backbone')return;
  for(const link of config.links){
   const v=values(link),g=svg.querySelector(`[data-link="${link.id}"]`),p=path(link);
   g.dataset.status=v.status;g.setAttribute('aria-label',`${byId(link.a).name} para ${byId(link.b).name}, ${link.label||'fibra'}, ${names[v.status]}`);
   const t=g.querySelector('text'),y=p.y+captionOffset(link);
   const caption=`<tspan x="${p.labelX}" y="${y}">${esc(link.label||'')} ${esc(rate(v.a))} / ${esc(rate(v.b))}</tspan><tspan x="${p.labelX}" dy="14">RX ${esc(number(v.a.port?.rx,1))} / ${esc(number(v.b.port?.rx,1))} dBm${link.maintenance?' · Em reparo':''}</tspan>`;
   if(t.innerHTML!==caption)t.innerHTML=caption;
  }
  for(const n of config.nodes){const d=device(n),el=svg.querySelector(`[data-node="${n.id}"]`);el.dataset.status=d?.state||'pending';el.setAttribute('aria-label',`${n.name}, ${n.host}, ${d?labels[d.state]||d.state:'não cadastrado'}`);}
  if(active)details(active);
 }
 function details(id){
  const link=config.links.find(l=>l.id===id);if(!link)return;
  const v=values(link);
  const side=(n,port,r)=>`<div><strong>${esc(n.name)}</strong><small>${esc(n.host)} · ${esc(port||'Porta pendente')}</small><p>${esc(r.label)} · RX ${esc(rate(r))} · ${esc(signal(r))}</p></div>`;
  const html=`<button class="icon-button backbone-dismiss" aria-label="Fechar detalhes">×</button><strong>${esc(link.label||'Fibra óptica')} · ${names[v.status]}</strong>${side(byId(link.a),link.port_a,v.a)}${side(byId(link.b),link.port_b,v.b)}<button class="button secondary" data-edit-fiber="${link.id}">Editar portas / manutenção</button>`;
  if(info.innerHTML!==html)info.innerHTML=html;
  info.hidden=false;info.style.left=Math.max(8,Math.min(innerWidth-info.offsetWidth-8,pointer.x+12))+'px';info.style.top=Math.max(8,Math.min(innerHeight-info.offsetHeight-8,pointer.y+12))+'px';
 }
 function show(target,event,pin=false){active=target.dataset.link;pinned=pin;const rect=target.getBoundingClientRect();pointer={x:event.clientX??rect.x,y:event.clientY??rect.y};details(active);}
 svg.addEventListener('pointerover',e=>{const target=e.target.closest('[data-link]');if(target&&!pinned)show(target,e);});
 svg.addEventListener('pointerout',e=>{if(!pinned&&!svg.contains(e.relatedTarget)&&!info.contains(e.relatedTarget)){active=null;info.hidden=true;}});
 svg.addEventListener('focusin',e=>{const target=e.target.closest('[data-link]');if(target)show(target,{},true);});
 function activate(e){
  const fiber=e.target.closest('[data-link]');if(fiber){show(fiber,e,true);return;}
  const target=e.target.closest('[data-node]');if(!target)return;
  const n=byId(target.dataset.node),d=device(n);if(d){openDetail(d.id);return;}
  openAdd();$('#device-form [name="name"]').value=n.name;$('#device-form [name="host"]').value=n.host;
  $(`#device-form [name="kind"][value="${n.kind==='huawei'?'ping':'datacom'}"]`).checked=true;syncDeviceKind();
 }
 svg.addEventListener('click',activate);
 svg.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();activate(e);}if(e.key==='Escape'){active=null;pinned=false;info.hidden=true;}});
 info.addEventListener('click',e=>{
  if(e.target.closest('.backbone-dismiss')){active=null;pinned=false;info.hidden=true;return;}
  const button=e.target.closest('[data-edit-fiber]');if(!button)return;
  editing=config.links.find(l=>l.id===button.dataset.editFiber);const f=$('#backbone-port-form');f.elements.port_a.value=editing.port_a||'';f.elements.port_b.value=editing.port_b||'';f.elements.maintenance.checked=editing.maintenance;
  $('#backbone-port-context').textContent=`${byId(editing.a).name} ↔ ${byId(editing.b).name}`;$('#backbone-port-error').hidden=true;$('#backbone-port-dialog').showModal();
 });
 $('#backbone-port-close').onclick=()=>$('#backbone-port-dialog').close();
 $('#backbone-port-form').onsubmit=async e=>{e.preventDefault();const f=e.target,button=f.querySelector('[type="submit"]');button.disabled=true;try{config=await api(`/api/backbone/links/${editing.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({port_a:f.elements.port_a.value,port_b:f.elements.port_b.value,maintenance:f.elements.maintenance.checked})});$('#backbone-port-dialog').close();draw();}catch(error){$('#backbone-port-error').textContent=error.message;$('#backbone-port-error').hidden=false;}finally{button.disabled=false;}};
 $('#backbone-fit').onclick=()=>{$('.backbone-scroll').scrollTo({left:0,top:0});svg.classList.toggle('fit-map');};
 async function start(){if(state.page!=='backbone'){active=null;pinned=false;info.hidden=true;return;}if(config){refresh();return;}try{config=await api('/api/backbone');draw();$('#backbone-error').hidden=true;}catch(error){$('#backbone-error').hidden=false;$('#backbone-error').textContent=error.message;}}
 window.addEventListener('keydown',e=>{if(e.key==='Escape'){active=null;pinned=false;info.hidden=true;}});
 $('#refresh').addEventListener('click',()=>{if(state.page==='backbone'&&!config)start();});
 window.addEventListener('monitor-page',start);window.addEventListener('monitor-data',refresh);setInterval(refresh,1500);
})();
