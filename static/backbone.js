/* Physical fibers and radio hops are independent; topology never implies a live reading. */
(() => {
 let config=null, active=null, pinned=false, editing=null, pointer={x:20,y:100}, modality='mouse', dismissTimer, suppressFocus=false;
 const svg=$('#backbone-map'), info=$('#backbone-info');
 const display=$('#backbone-display');
 try{const saved=localStorage.getItem('alwaysup-map-display');if(['traffic','full','clean'].includes(saved))display.value=saved;}catch{}
 svg.dataset.display=display.value;
 display.onchange=()=>{svg.dataset.display=display.value;hideInfo();refresh();try{localStorage.setItem('alwaysup-map-display',display.value);}catch{}};
 const byId=id=>config.nodes.find(n=>n.id===id);
 const device=n=>state.data.devices.find(d=>d.host===n.host&&d.kind==='datacom')||state.data.devices.find(d=>d.host===n.host);
 const names={up:'Ativa',down:'Caída',error:'Erro de coleta',missing:'Sem leitura',maintenance:'Em reparo'};
 function reading(n,port){
  const d=device(n);
  if(!d||!port)return {label:!port?'Porta pendente': 'Equipamento não cadastrado',port:null};
  if(!$('#connection-error').hidden||d.ssh_error)return {label:'Erro de coleta',error:true,port:null};
  const p=(d.port_data||[]).find(p=>portIdentity(p,d)===makePortIdentity(port)||String(p.name).toLowerCase()===port.toLowerCase());
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
 function roundedRoute(points,radius=16){
  let d=`M${points[0].x},${points[0].y}`;
  for(let i=1;i<points.length-1;i++){
   const a=points[i-1],b=points[i],c=points[i+1],incoming=Math.hypot(b.x-a.x,b.y-a.y),outgoing=Math.hypot(c.x-b.x,c.y-b.y);
   if(!incoming||!outgoing)continue;
   const r=Math.min(radius,incoming/2,outgoing/2);
   const entry={x:b.x-(b.x-a.x)/incoming*r,y:b.y-(b.y-a.y)/incoming*r};
   const exit={x:b.x+(c.x-b.x)/outgoing*r,y:b.y+(c.y-b.y)/outgoing*r};
   d+=` L${entry.x},${entry.y} Q${b.x},${b.y} ${exit.x},${exit.y}`;
  }
  const end=points[points.length-1];return d+` L${end.x},${end.y}`;
 }
 function path(link){
  const a=byId(link.a),b=byId(link.b),dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy)||1;
  if(link.route==='rectangular'){
   const lane=link.routeLane??Math.max(a.y,b.y)+Math.abs(link.bend),offset=link.routeOffset??10;
   const start=a.x+offset,end=b.x-offset;
   const points=link.waypoints?[a,...link.waypoints,b]:[a,{x:start,y:a.y},{x:start,y:lane},{x:end,y:lane},{x:end,y:b.y},b];
   return {d:roundedRoute(points),x:(start+end)/2,y:lane,labelX:(start+end)/2,anchor:'middle'};
  }
  const direction=dx<0?-1:1,cx=(a.x+b.x)/2-dy/len*link.bend*2*direction,cy=(a.y+b.y)/2+dx/len*link.bend*2*direction;
  const x=(a.x+2*cx+b.x)/4,vertical=Math.abs(dx)<80;
  return {d:`M${a.x},${a.y} Q${cx},${cy} ${b.x},${b.y}`,x,y:(a.y+2*cy+b.y)/4,labelX:vertical?(x<960?x+25:x-10):x,anchor:vertical?(x<960?'start':'end'):'middle'};
 }
 // Keep each caption beside its own fiber, parallel to diagonal spans.
 function captionLayout(link,p){
  const a=byId(link.a),b=byId(link.b),vertical=Math.abs(b.x-a.x)<80;
  let angle=link.route==='rectangular'||vertical?0:Math.atan2(b.y-a.y,b.x-a.x)*180/Math.PI;
  if(angle>90)angle-=180;if(angle< -90)angle+=180;
  const above=link.route==='rectangular'?(link.routeLane??Infinity)<Math.min(a.y,b.y):link.bend<=0;
  return {x:vertical&&link.route!=='rectangular'?p.labelX:p.x,y:p.y,angle,
   offset:vertical&&link.route!=='rectangular'?-8:above?(display.value==='full'?-34:-22):link.route==='rectangular'?20:Math.abs(b.y-a.y)<20?45:35,
   anchor:vertical&&link.route!=='rectangular'?p.anchor:'middle',...link.caption};
 }
 const radioLinks=()=>config.radio_links||[];
 const radioReading=link=>radioMapState.link(link,state.data.devices,Date.now(),$('#connection-error').hidden);
 const radioStateNames={up:'Rádio ativo',high:'Ping acima de 200 ms',down:'Sem ping',unknown:'Sem leitura'};
 function radioTitle(link){return link.route==='tefe-tabatinga'?'Tefé → Tabatinga':`Rede ${link.network}`;}
 const radioGeometry=link=>backboneLayout.geometry(link);
 const radioSites=()=>backboneLayout.sites(config);
 const radioNetworks=()=>config.radio_networks||[];
 function accessId(network,side){return `radio-access-${network}-${side}`;}
 function findAccess(id){for(const network of radioNetworks())for(const side of ['source','target'])if(accessId(network.network,side)===id)return {network,side,binding:network[side]};}
 function accessReading(network,side){
  const links=radioLinks().filter(l=>l.network===network.network).sort((a,b)=>a.order-b.order),end=side==='source'?links[0]?.a:links.at(-1)?.b;
  const binding=network[side],node=byId(binding.node),port=reading(node,binding.port),radio=radioMapState.endpoint(end,state.data.devices,Date.now(),$('#connection-error').hidden);
  return {node,port,radio,status:binding.port?radioMapState.access(port,radio):'unknown'};
 }
 function routeOrigin(id){for(const [route,binding] of Object.entries(config.radio_route_origins||{}))if(id===`radio-origin-${route}`)return {route,binding};}
 function originReading(origin){const node=byId(origin.binding.node),link=radioLinks().filter(l=>l.route===origin.route).sort((a,b)=>a.order-b.order)[0],port=reading(node,origin.binding.port),radio=radioMapState.endpoint(link.a,state.data.devices,Date.now(),$('#connection-error').hidden);return {node,link,port,radio,status:origin.binding.port?radioMapState.access(port,radio):'unknown'};}
 function drawRouteOrigins(){
  let html='';
  for(const [route,binding]of Object.entries(config.radio_route_origins||{})){
   const origin={route,binding},v=originReading(origin),g=radioGeometry(v.link),node=v.node;
   const points=[{x:node.x,y:node.y+14},{x:node.x,y:node.y+62},{x:1888,y:node.y+62},{x:1888,y:g.y},{x:g.x1,y:g.y}],d=roundedRoute(points,14);
   html+=`<g class="radio-access radio-route-origin" data-link="radio-origin-${route}" data-status="${v.status}" tabindex="0" role="button" aria-label="Origem Tefé → Tabatinga no Datacom Tefé CLARO, porta a confirmar"><path class="radio-access-underlay" d="${d}"/><path class="radio-access-stroke" d="${d}"/><path class="fiber-hit" d="${d}"/><text class="radio-access-caption" x="${g.x1}" y="${g.y-50}" text-anchor="end">Tefé CLARO · porta a confirmar</text></g>`;
  }
  return html;
 }
 function originDetails(origin){
  const v=originReading(origin),port=origin.binding.port?esc(origin.binding.port):'Porta a confirmar';
  renderInfo(`<button class="icon-button backbone-dismiss" aria-label="Fechar detalhes">×</button><strong>Tefé → Tabatinga · origem no CLARO</strong><div><strong>${esc(v.node.name)}</strong><small>${v.node.host} · ${port}</small><p>${esc(v.port.label)}</p></div><div><strong>${esc(v.link.a.name)}</strong><small>${v.link.a.host}</small><p>${esc(v.radio.label)} · Ping ${number(v.radio.latency)} ms</p></div><button type="button" class="button secondary" data-access-node="${v.node.id}">Ver Datacom</button>`);
 }
 function drawRadioAccess(){
  let html='';
  for(const network of radioNetworks()){
   const links=radioLinks().filter(l=>l.network===network.network).sort((a,b)=>a.order-b.order);if(!links.length)continue;
   const first=radioGeometry(links[0]),last=radioGeometry(links.at(-1)),offset=network.network===1?-8:8;
   for(const side of ['source','target']){
    const node=byId(network[side].node),isSource=side==='source';
    const points=isSource?[{x:node.x-14,y:node.y+offset},{x:44-(network.network-1)*20,y:node.y+offset},{x:44-(network.network-1)*20,y:first.y},{x:first.x1,y:first.y}]:[{x:last.x2,y:last.y},{x:1860+(network.network-1)*16,y:last.y},{x:1860+(network.network-1)*16,y:node.y+30+(network.network-1)*16},{x:node.x+offset,y:node.y+30+(network.network-1)*16},{x:node.x+offset,y:node.y+14}];
    const d=roundedRoute(points,14),id=accessId(network.network,side),label=isSource?`Coari · Ten 1/1/${7+network.network}`:'Tefé CLARO · Giga 5–8 a confirmar';
    html+=`<g class="radio-access" data-link="${id}" data-network="${network.network}" data-end="${side}" tabindex="0" role="button" aria-label="${esc(label+' · Rede '+network.network)}"><path class="radio-access-underlay" d="${d}"/><path class="radio-access-stroke" d="${d}"/><path class="fiber-hit" d="${d}"/><text class="radio-access-caption" x="${isSource?first.x1:1805}" y="${first.y+80}" text-anchor="middle">${label}</text></g>`;
   }
  }
  return html;
 }
 function accessDetails(access){
  const {network,side,binding}=access,v=accessReading(network,side),isSource=side==='source';
  const port=binding.port?esc(binding.port):'Porta a confirmar · Giga 1/1/5, 1/1/6, 1/1/7 ou 1/1/8';
  renderInfo(`<button class="icon-button backbone-dismiss" aria-label="Fechar detalhes">×</button><strong>Rede ${network.network} · ${isSource?'Saída de Coari':'Chegada no CLARO'}</strong><div><strong>${esc(v.node.name)}</strong><small>${v.node.host} · ${port}</small><p>${esc(v.port.label)}${v.port.port?' · RX '+esc(rate(v.port)):''}</p></div><div><strong>${esc(v.radio.device?.name||'Rádio '+(isSource?'AP de Coari':'ST de Tefé'))}</strong><p>${esc(v.radio.label)} · Ping ${number(v.radio.latency)} ms</p></div><button type="button" class="button secondary" data-access-node="${v.node.id}">Ver Datacom</button>`);
 }
 function radioSiteReading(site){
  const readings=site.refs.map(ref=>({ref,...radioReading(ref.link)[ref.side]})),states=readings.map(r=>r.status);
  return {readings,status:states.includes('down')?'down':states.includes('unknown')?'unknown':states.includes('high')?'high':'up'};
 }
 function siteDetails(site){
  const {readings,status}=radioSiteReading(site);
  const sides=readings.map(r=>{const endpoint=r.ref.link[r.ref.side];return `<div><strong>${r.ref.side==='a'?'AP':'ST'} · ${esc(endpoint.name)}</strong><small>${endpoint.host}</small><p>${esc(r.label)} · Ping ${number(r.latency)} ms · RX ${bandwidth(r.bps)}</p><button type="button" class="button secondary" data-radio-endpoint="${r.ref.link.id}:${r.ref.side}">${r.device?'Ver rádio':'Cadastrar rádio'}</button></div>`;}).join('');
  renderInfo(`<button class="icon-button backbone-dismiss" aria-label="Fechar detalhes">×</button><strong>${esc(site.name)} · ${radioStateNames[status]}</strong><small>${esc(site.group.title)}</small>${sides}`);
 }
 function drawRadios(){
  let html='<g id="radio-map-layer"><text class="radio-map-heading" x="24" y="400">Rádio · Coari → Tefé</text><text class="radio-map-heading" x="24" y="670">Rádio · Tefé → Tabatinga</text>';
  for(const group of backboneLayout.groups){
   if(group.network)html+=`<text class="radio-network-label" x="10" y="${group.y+5}">${group.network}</text>`;
   for(const l of backboneLayout.linksFor(config,group)){const g=radioGeometry(l);html+=`<g class="backbone-radio" data-link="${l.id}" data-radio-route="${l.route}" tabindex="0" role="button"><path class="radio-stroke" d="M${g.x1},${g.y} H${g.x2}"/><path class="fiber-hit" d="M${g.x1},${g.y} H${g.x2}"/><text class="radio-caption" x="${(g.x1+g.x2)/2}" y="${g.y-18}" text-anchor="middle"></text></g>`;}
  }
  for(const site of radioSites()){
   const ips=site.refs.map((ref,i)=>`<tspan x="0" ${i?'dy="13"':''}>${ref.link[ref.side].host}</tspan>`).join('');
   html+=`<g class="radio-map-point radio-site-point" data-link="${site.id}" data-radio-site="${site.id}" transform="translate(${site.x} ${site.y})" tabindex="0" role="button" aria-label="${esc(site.name+' · '+site.group.title)}"><title>${esc(site.name+' · '+site.group.title+' · '+site.refs.length+' rádio(s)')}</title><circle r="13"/><image href="/static/icons/siae.png" x="-11" y="-11" width="22" height="22"/><text class="radio-site" y="32" text-anchor="middle">${esc(backboneLayout.shortName(site.name))}</text><text class="radio-ip" y="51" text-anchor="middle">${ips}</text></g>`;
  }
  return html+'</g>';
 }
 function refreshRadios(){
  for(const l of radioLinks()){
   const v=radioReading(l),g=svg.querySelector(`[data-link="${l.id}"]`),p=radioGeometry(l);
   g.dataset.status=v.status;g.setAttribute('aria-label',`${radioTitle(l)}, ${l.a.site} para ${l.b.site}, ${radioStateNames[v.status]}`);
   const primary=v.a.bps!=null?bandwidth(v.a.bps).replace(/<[^>]*>/g,''):v.status==='down'?'Sem ping':v.status==='unknown'?'Sem leitura':`Ping ${number(Math.max(v.a.latency,v.b.latency))} ms`;
   g.querySelector('text').innerHTML=`<tspan x="${(p.x1+p.x2)/2}">${esc(primary)}</tspan><tspan class="radio-endpoint-ping" x="${(p.x1+p.x2)/2}" y="${p.y+(display.value==='full'?80:64)}">AP ${number(v.a.latency)} / ST ${number(v.b.latency)} ms</tspan>`;
  }
  for(const site of radioSites()){const v=radioSiteReading(site),g=svg.querySelector(`[data-radio-site="${site.id}"]`);g.dataset.status=v.status;g.setAttribute('aria-label',`${site.name}, ${site.group.title}, ${site.refs.length} rádios, ${radioStateNames[v.status]}`);}
  for(const [route,binding]of Object.entries(config.radio_route_origins||{})){const g=svg.querySelector(`[data-link="radio-origin-${route}"]`);if(g)g.dataset.status=originReading({route,binding}).status;}
  for(const network of radioNetworks())for(const side of ['source','target']){const g=svg.querySelector(`[data-link="${accessId(network.network,side)}"]`);if(g)g.dataset.status=accessReading(network,side).status;}
 }
 function openRadio(link,side){
  hideInfo();const n=link[side],d=state.data.devices.find(d=>d.kind==='siae'&&d.host===n.host);if(d){openDetail(d.id);return;}
  openAdd();$('[name="kind"][value="siae"]').checked=true;$('#device-form [name="name"]').value=n.name;$('#device-form [name="host"]').value=n.host;
  $('[name="radio_route"]').value=link.route;$('[name="radio_network"]').value=link.network==null?'':String(link.network);syncDeviceKind();
 }
 function radioDetails(link){
  const v=radioReading(link),side=(key)=>{const n=link[key],r=v[key];return `<div><strong>${key==='a'?'AP':'ST'} · ${esc(n.site)}</strong><small>${esc(n.name)} · ${n.host}</small><p>${esc(r.label)} · Ping ${number(r.latency)} ms · RX ${bandwidth(r.bps)}</p><button type="button" class="button secondary" data-radio-endpoint="${link.id}:${key}">${r.device?'Ver rádio':'Cadastrar rádio'}</button></div>`;};
  renderInfo(`<button class="icon-button backbone-dismiss" aria-label="Fechar detalhes">×</button><strong>Rádio · ${radioTitle(link)} · ${radioStateNames[v.status]}</strong>${side('a')}${side('b')}`);
 }
 function draw(){
  applyMapScope();
  svg.innerHTML='<text class="radio-map-heading" x="24" y="16">Backbone · fibra</text>'+config.links.map(link=>{const p=path(link);return `<g class="backbone-fiber" data-link="${link.id}" tabindex="0" role="button"><path class="fiber-stroke" d="${p.d}"/><path class="fiber-hit" d="${p.d}"/><text class="fiber-caption" x="${p.labelX}" y="0" text-anchor="${p.anchor}"></text></g>`;}).join('')+config.nodes.map(n=>`<g class="backbone-node" data-node="${n.id}" transform="translate(${n.x} ${n.y})" tabindex="0" role="button" aria-label="${esc(n.name+' '+n.host)}"><circle r="14"/><image href="/static/icons/datacom.png" x="-12" y="-12" width="24" height="24"/><text x="${n.nodeLabel?.x??0}" y="${n.nodeLabel?.y??30}" text-anchor="${n.nodeLabel?.anchor||'middle'}">${esc(n.name)}</text><text class="node-ip" x="${n.nodeLabel?.x??0}" y="${(n.nodeLabel?.y??30)+16}" text-anchor="${n.nodeLabel?.anchor||'middle'}">${n.host}${n.kind==='huawei'?' · Huawei':''}</text></g>`).join('');
  svg.insertAdjacentHTML('beforeend',drawRadioAccess()+drawRouteOrigins()+drawRadios());
  if(!svg.style.width){if(viewport.clientWidth<640)applyZoom(.8,false);else fitMap();}refresh();
 }
 function refresh(){
  if(!config||state.page!=='backbone')return;
  const counts={up:0,down:0,error:0,missing:0,maintenance:0};
  for(const link of config.links){
   const v=values(link),g=svg.querySelector(`[data-link="${link.id}"]`),p=path(link);
   counts[v.status]++;g.dataset.status=v.status;g.setAttribute('aria-label',`${byId(link.a).name} para ${byId(link.b).name}, ${link.label||'fibra'}, ${names[v.status]}`);
   const t=g.querySelector('text'),layout=captionLayout(link,p),y=layout.offset;
   t.setAttribute('transform',`translate(${layout.x} ${layout.y}) rotate(${layout.angle})`);
   t.setAttribute('text-anchor',layout.anchor);
   const compact=display.value!=='full',primary=compact?(link.maintenance?'Em reparo':v.a.port?.rx_bps==null?'Sem leitura':rate(v.a)):`${rate(v.a)} / ${rate(v.b)}`;
   const caption=`<tspan x="0" y="${y}">${esc(link.label||'')} ${esc(primary)}</tspan><tspan class="fiber-optics" x="0" dy="14">RX ${esc(number(v.a.port?.rx,1))} / ${esc(number(v.b.port?.rx,1))} dBm</tspan>${link.maintenance&&!compact?'<tspan class="fiber-maintenance" x="0" dy="14">Em reparo</tspan>':''}`;
   if(t.innerHTML!==caption)t.innerHTML=caption;
  }
  for(const n of config.nodes){const d=device(n),el=svg.querySelector(`[data-node="${n.id}"]`);el.dataset.status=d?.state||'pending';el.setAttribute('aria-label',`${n.name}, ${n.host}, ${d?labels[d.state]||d.state:'não cadastrado'}`);}
  refreshRadios();
  const summary=`${config.links.length} fibras · ${counts.up} ativas${counts.down?` · ${counts.down} com queda`:''}${counts.error?' · erro de coleta':''}${counts.missing?' · leituras pendentes':''}${counts.maintenance?' · em manutenção':''}${radioLinks().length?' · '+radioLinks().length+' enlaces de rádio':''}`;
  if($('#backbone-summary').textContent!==summary)$('#backbone-summary').textContent=summary;
  if(active)details(active);
 }
 function details(id){
  const site=radioSites().find(s=>s.id===id);if(site){siteDetails(site);return;}
  const origin=routeOrigin(id);if(origin){originDetails(origin);return;}
  const access=findAccess(id);if(access){accessDetails(access);return;}
  const radio=radioLinks().find(l=>l.id===id);if(radio){radioDetails(radio);return;}
  const link=config.links.find(l=>l.id===id);if(!link)return;
  const v=values(link);
  const side=(n,port,r)=>`<div><strong>${esc(n.name)}</strong><small>${esc(n.host)} · ${esc(port||'Porta pendente')}</small><p>${esc(r.label)} · RX ${esc(rate(r))} · ${esc(signal(r))}</p></div>`;
  const html=`<button class="icon-button backbone-dismiss" aria-label="Fechar detalhes">×</button><strong>${esc(link.label||'Fibra óptica')} · ${names[v.status]}</strong>${side(byId(link.a),link.port_a,v.a)}${side(byId(link.b),link.port_b,v.b)}${link.note?`<p>${esc(link.note)}</p>`:''}<button class="button secondary" data-edit-fiber="${link.id}">Editar portas / manutenção</button>`;
  renderInfo(html);
 }
 function renderInfo(html){
  if(info.innerHTML!==html)info.innerHTML=html;
  info.hidden=false;info.style.left=Math.max(8,Math.min(innerWidth-info.offsetWidth-8,pointer.x+12))+'px';info.style.top=Math.max(8,Math.min(innerHeight-info.offsetHeight-8,pointer.y+12))+'px';
 }
 function hideInfo(){clearTimeout(dismissTimer);active=null;pinned=false;info.hidden=true;}
 function dismissInfo(){
  const restore=info.contains(document.activeElement),target=active&&svg.querySelector(`[data-link="${active}"]`);
  hideInfo();
  if(restore&&target){suppressFocus=true;try{target.focus({preventScroll:true});}finally{suppressFocus=false;}}
 }
 function scheduleHide(){clearTimeout(dismissTimer);dismissTimer=setTimeout(()=>{if(!pinned)hideInfo();},200);}
 function show(target,event,pin=false){clearTimeout(dismissTimer);active=target.dataset.link;pinned=pin;const rect=target.getBoundingClientRect();pointer={x:event.clientX??rect.x,y:event.clientY??rect.y};details(active);}
 document.addEventListener('keydown',()=>{modality='keyboard';},true);
 document.addEventListener('pointerdown',e=>{
  modality=e.pointerType==='touch'?'touch':'mouse';
  if(modality==='mouse')pinned=false;
  if(!$('#backbone-port-dialog').open&&!e.target.closest('[data-link], #backbone-info'))hideInfo();
 },true);
 svg.addEventListener('pointerover',e=>{const target=e.target.closest('[data-link]');if(target&&e.pointerType!=='touch'&&!drag)show(target,e);});
 svg.addEventListener('pointerout',e=>{
  const from=e.target.closest('[data-link]'),to=e.relatedTarget?.closest?.('[data-link]');
  if(from&&from!==to&&!info.contains(e.relatedTarget)&&!pinned)scheduleHide();
 });
 info.addEventListener('pointerenter',()=>clearTimeout(dismissTimer));
 info.addEventListener('pointerleave',()=>{if(!pinned)scheduleHide();});
 svg.addEventListener('focusin',e=>{const target=e.target.closest('[data-link]');if(target&&modality==='keyboard'&&!suppressFocus)show(target,{},true);});
 function focusLeaves(e){
  if(modality==='keyboard'&&!$('#backbone-port-dialog').open&&!info.contains(e.relatedTarget)&&!e.relatedTarget?.closest?.('[data-link]'))hideInfo();
 }
 svg.addEventListener('focusout',focusLeaves);info.addEventListener('focusout',focusLeaves);
 function activate(e){
  const fiber=e.target.closest('[data-link]');if(fiber){show(fiber,e,modality!=='mouse');return;}
  const target=e.target.closest('[data-node]');if(!target)return;
  const n=byId(target.dataset.node),d=device(n);if(d){if(n.kind==='huawei'&&d.kind==='ping'){openEdit(d.id);applyHuaweiPreset();}else openDetail(d.id);return;}
  openAdd();$('#device-form [name="name"]').value=n.name;$('#device-form [name="host"]').value=n.host;
  $(`#device-form [name="kind"][value="datacom"]`).checked=true;syncDeviceKind();if(n.kind==='huawei')applyHuaweiPreset();
 }
 svg.addEventListener('click',activate);
 svg.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();activate(e);}if(e.key==='Escape')dismissInfo();});
 info.addEventListener('click',e=>{
  if(e.target.closest('.backbone-dismiss')){dismissInfo();return;}
  const accessButton=e.target.closest('[data-access-node]');if(accessButton){const n=byId(accessButton.dataset.accessNode),d=device(n);hideInfo();if(d)openDetail(d.id);else{openAdd();$('#device-form [name="name"]').value=n.name;$('#device-form [name="host"]').value=n.host;$('[name="kind"][value="datacom"]').checked=true;syncDeviceKind();}return;}
  const radioButton=e.target.closest('[data-radio-endpoint]');if(radioButton){const [id,side]=radioButton.dataset.radioEndpoint.split(':');openRadio(radioLinks().find(l=>l.id===id),side);return;}
  const button=e.target.closest('[data-edit-fiber]');if(!button)return;
  editing=config.links.find(l=>l.id===button.dataset.editFiber);const f=$('#backbone-port-form');f.elements.port_a.value=editing.port_a||'';f.elements.port_b.value=editing.port_b||'';f.elements.maintenance.checked=editing.maintenance;
  $('#backbone-port-context').textContent=`${byId(editing.a).name} ↔ ${byId(editing.b).name}`;$('#backbone-port-error').hidden=true;hideInfo();$('#backbone-port-dialog').showModal();
 });
 $('#backbone-port-dialog').addEventListener('close',()=>{const target=editing&&svg.querySelector(`[data-link="${editing.id}"]`);if(target&&state.page==='backbone')target.focus();});
 $('#backbone-port-close').onclick=()=>$('#backbone-port-dialog').close();
 $('#backbone-port-form').onsubmit=async e=>{e.preventDefault();const f=e.target,button=f.querySelector('[type="submit"]');button.disabled=true;try{config=await api(`/api/backbone/links/${editing.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({port_a:f.elements.port_a.value,port_b:f.elements.port_b.value,maintenance:f.elements.maintenance.checked})});$('#backbone-port-dialog').close();draw();}catch(error){$('#backbone-port-error').textContent=error.message;$('#backbone-port-error').hidden=false;}finally{button.disabled=false;}};
 const viewport=$('.backbone-scroll');let zoom=1,drag=null,didDrag=false,autoFit=true;
 function applyZoom(next,center=true){
  autoFit=false;hideInfo();
  const oldW=svg.getBoundingClientRect().width||1500,oldH=svg.getBoundingClientRect().height||600;
  const cx=(viewport.scrollLeft+viewport.clientWidth/2)/oldW,cy=(viewport.scrollTop+viewport.clientHeight/2)/oldH;
  zoom=Math.min(3,Math.max(.1,next));svg.style.minWidth='0';svg.style.width=`${svg.viewBox.baseVal.width*zoom}px`;
  $('#backbone-zoom-level').value=`${Math.round(zoom*100)}%`;$('#backbone-zoom-in').disabled=zoom>=3;$('#backbone-zoom-out').disabled=zoom<=.1;
  if(center){viewport.scrollLeft=cx*svg.getBoundingClientRect().width-viewport.clientWidth/2;viewport.scrollTop=cy*svg.getBoundingClientRect().height-viewport.clientHeight/2;}
  else{viewport.scrollLeft=0;viewport.scrollTop=0;}
 }
 $('#backbone-zoom-in').onclick=()=>applyZoom(zoom+.2);
 $('#backbone-zoom-out').onclick=()=>applyZoom(zoom-.2);
 function fitMap(){
  applyZoom(viewport.clientWidth/svg.viewBox.baseVal.width,false);autoFit=true;
 }
 const scope=$('#backbone-scope'),mapScopes=backboneLayout.bounds;
 try{const saved=localStorage.getItem('alwaysup-backbone-scope');if(Object.hasOwn(mapScopes,saved))scope.value=saved;}catch{}
 function applyMapScope(){svg.setAttribute('viewBox',mapScopes[scope.value]||mapScopes.all);}
 scope.onchange=()=>{hideInfo();applyMapScope();if(config){if(viewport.clientWidth<640&&!autoFit)applyZoom(zoom,false);else fitMap();}try{localStorage.setItem('alwaysup-backbone-scope',scope.value);}catch{}};
 $('#backbone-fit').onclick=fitMap;
 const fullscreen=$('#backbone-fullscreen');
 fullscreen.onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{toast('O navegador não permitiu abrir a tela cheia.');}};
 document.addEventListener('fullscreenchange',()=>{const active=document.fullscreenElement===document.documentElement;document.body.dataset.mapFullscreen=String(active);fullscreen.textContent=active?'Sair da tela cheia':'Tela cheia';fullscreen.setAttribute('aria-pressed',String(active));});
 new ResizeObserver(()=>{if(autoFit&&config&&state.page==='backbone'){if(viewport.clientWidth<640)applyZoom(Math.max(zoom,.8),false);else fitMap();}}).observe(viewport);
 viewport.addEventListener('pointerdown',e=>{if(e.button!==0||drag)return;didDrag=false;drag={id:e.pointerId,x:e.clientX,y:e.clientY,left:viewport.scrollLeft,top:viewport.scrollTop};});
 viewport.addEventListener('pointermove',e=>{
  if(!drag||e.pointerId!==drag.id)return;
  const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
  if(!didDrag&&Math.hypot(dx,dy)<5)return;
  if(!didDrag){didDrag=true;viewport.setPointerCapture(e.pointerId);viewport.classList.add('is-dragging');hideInfo();}
  e.preventDefault();viewport.scrollLeft=drag.left-dx;viewport.scrollTop=drag.top-dy;
 });
 function finishDrag(e){if(!drag||drag.id!==e.pointerId)return;if(viewport.hasPointerCapture(e.pointerId))viewport.releasePointerCapture(e.pointerId);drag=null;viewport.classList.remove('is-dragging');}
 viewport.addEventListener('pointerup',finishDrag);viewport.addEventListener('pointercancel',finishDrag);
 viewport.addEventListener('click',e=>{if(didDrag){e.preventDefault();e.stopPropagation();didDrag=false;}},true);
 viewport.addEventListener('keydown',e=>{
  if(e.ctrlKey||e.metaKey||e.altKey)return;
  const moves={ArrowLeft:[-70,0],ArrowRight:[70,0],ArrowUp:[0,-70],ArrowDown:[0,70]};
  if(moves[e.key]){e.preventDefault();viewport.scrollBy(...moves[e.key]);}
  else if(['+','=','-','−'].includes(e.key)){e.preventDefault();applyZoom(zoom+(['-','−'].includes(e.key)?-.2:.2));}
 });

 async function start(){if(state.page!=='backbone'){hideInfo();if(document.body.dataset.mapFullscreen==='true'&&document.fullscreenElement)document.exitFullscreen().catch(()=>{});return;}if(config){refresh();return;}try{config=await api('/api/backbone');draw();$('#backbone-error').hidden=true;}catch(error){$('#backbone-error').hidden=false;$('#backbone-error').textContent=error.message;}}
 window.addEventListener('keydown',e=>{if(e.key==='Escape')dismissInfo();});
 $('#refresh').addEventListener('click',()=>{if(state.page==='backbone'&&!config)start();});
 window.addEventListener('monitor-page',start);window.addEventListener('monitor-data',refresh);setInterval(refresh,1500);
})();
