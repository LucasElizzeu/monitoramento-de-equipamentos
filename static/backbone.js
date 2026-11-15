/* Physical fibers and radio hops are independent; topology never implies a live reading. */
(() => {
 let config=null,active=null,editing=null,labelPositions=new Map(),labelSignature='';
 const svg=$('#backbone-map'), info=$('#backbone-info');
 const display=$('#backbone-display');
 try{const saved=localStorage.getItem('alwaysup-map-display');if(['traffic','clean'].includes(saved))display.value=saved;else if(saved==='full')localStorage.setItem('alwaysup-map-display','traffic');}catch{}
 svg.dataset.display=display.value;
 display.onchange=()=>{svg.dataset.display=display.value;labelSignature='';hideInfo();refresh();try{localStorage.setItem('alwaysup-map-display',display.value);}catch{}};
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
 // Summary labels stay horizontal; detailed measurements live in the selected link panel.
 function captionLayout(link,p){
  const a=byId(link.a),b=byId(link.b),vertical=Math.abs(b.x-a.x)<80;
  const above=link.route==='rectangular'?(link.routeLane??Infinity)<Math.min(a.y,b.y):link.bend<=0;
  return {x:vertical?p.labelX:p.x,y:p.y,offset:vertical?-8:above?-28:link.route==='rectangular'?18:32,anchor:vertical?p.anchor:'middle',...link.caption,angle:0};
 }
 function mapBox(element){
  const b=element.getBBox(),matrix=svg.getCTM().inverse().multiply(element.getCTM());
  const p=new DOMPoint(b.x,b.y).matrixTransform(matrix),q=new DOMPoint(b.x+b.width,b.y+b.height).matrixTransform(matrix);
  return {x:p.x,y:p.y,width:q.x-p.x,height:q.y-p.y};
 }
 function layoutSummaries(){
  if(!svg.getCTM()||display.value==='clean')return;
  const labels=config.links.map(link=>{
   const text=svg.querySelector(`[data-link="${link.id}"] .fiber-caption`),bbox=text.getBBox(),p=path(link),preferred=captionLayout(link,p);
   // Reserve stable widths so changing traffic does not make labels move every poll.
   const width=Math.max(link.label?160:104,Math.ceil(bbox.width/16)*16),height=link.label?36:20;
   return {id:link.id,width,height,x:preferred.x+(preferred.anchor==='end'?-width/2:preferred.anchor==='start'?width/2:0),y:preferred.y+preferred.offset-13,text,bbox};
  });
  const signature=labels.map(l=>`${l.id}:${l.width}`).join('|');
  if(signature===labelSignature)return;
  const obstacles=[...svg.querySelectorAll('.backbone-node circle:not(.node-halo),.backbone-node text:not(.node-ip),.radio-map-heading')].map(mapBox);
  const points=[];
  for(const stroke of svg.querySelectorAll('.fiber-stroke')){
   const length=stroke.getTotalLength();for(let at=0;at<=length;at+=6){const p=stroke.getPointAtLength(at);points.push({x:p.x,y:p.y});}
  }
  labelPositions=mapLabels.place(labels,obstacles,points,{x:64,y:8,width:1816,height:454},labelPositions);
  labelSignature=signature;
  for(const label of labels){
   const box=labelPositions.get(label.id),group=label.text.parentElement,leader=group.querySelector('.fiber-label-leader');
   label.text.style.visibility=box?'visible':'hidden';
   if(!box){leader.setAttribute('d','');continue;}
   const tx=box.x+box.width/2,ty=box.y-label.bbox.y;
   label.text.setAttribute('transform',`translate(${tx} ${ty})`);label.text.setAttribute('text-anchor','middle');
   const stroke=group.querySelector('.fiber-stroke'),length=stroke.getTotalLength(),center={x:tx,y:box.y+box.height/2};
   let anchor=null,distance=Infinity;
   for(let at=0;at<=length;at+=6){const p=stroke.getPointAtLength(at),d=(p.x-center.x)**2+(p.y-center.y)**2;if(d<distance){distance=d;anchor=p;}}
   const end={x:Math.max(box.x,Math.min(box.x+box.width,anchor.x)),y:Math.max(box.y,Math.min(box.y+box.height,anchor.y))};
   leader.setAttribute('d',Math.hypot(end.x-anchor.x,end.y-anchor.y)>12?`M${anchor.x},${anchor.y} L${end.x},${end.y}`:'');
  }
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
 const bindingPorts=binding=>binding.ports||[binding.port].filter(Boolean);
 const bindingPortLabel=port=>port?port.replace('ten-gigabit-ethernet:','Ten ').replace('hundred-gigabit-ethernet:','Hundred ').replace('gigabit-ethernet:','Giga '):'Porta a confirmar';
 function accessReading(network,side){
  const links=radioLinks().filter(l=>l.network===network.network).sort((a,b)=>a.order-b.order),end=side==='source'?links[0]?.a:links.at(-1)?.b;
  const binding=network[side],node=byId(binding.node),ports=bindingPorts(binding).map(name=>({name,...reading(node,name)}));
  const radio=radioMapState.endpoint(end,state.data.devices,Date.now(),$('#connection-error').hidden);
  return {node,ports,radio,status:radioMapState.accessPorts(ports)};
 }
 function routeOrigin(id){for(const [route,binding] of Object.entries(config.radio_route_origins||{}))if(id===`radio-origin-${route}`)return {route,binding};}
 function originReading(origin){const node=byId(origin.binding.node),link=radioLinks().filter(l=>l.route===origin.route).sort((a,b)=>a.order-b.order)[0],port=reading(node,origin.binding.port),radio=radioMapState.endpoint(link.a,state.data.devices,Date.now(),$('#connection-error').hidden);return {node,link,port,radio,status:origin.binding.port?radioMapState.access(port):'unknown'};}
 function drawRouteOrigins(){
  let html='';
  for(const [route,binding]of Object.entries(config.radio_route_origins||{})){
   const origin={route,binding},v=originReading(origin),g=radioGeometry(v.link),node=v.node;
   const points=[{x:node.x,y:node.y+14},{x:node.x,y:node.y+62},{x:1904,y:node.y+62},{x:1904,y:g.y},{x:g.x1,y:g.y}],d=roundedRoute(points,14);
   html+=`<g class="radio-access radio-route-origin" data-link="radio-origin-${route}" data-status="${v.status}" tabindex="0" role="button" aria-label="Origem Tefé → Tabatinga no Datacom Tefé CLARO, porta a confirmar"><path class="radio-access-underlay" d="${d}"/><path class="radio-access-stroke" data-status="${v.status}" d="${d}"/><path class="fiber-hit" d="${d}"/><text class="radio-access-caption" x="${g.x1}" y="${g.y-50}" text-anchor="end">Tefé CLARO · porta a confirmar</text></g>`;
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
    const binding=network[side],node=byId(binding.node),isSource=side==='source',v=accessReading(network,side);
    const configured=bindingPorts(binding),ports=configured.length?configured:[null];
    const paths=ports.map((port,i)=>{
     const portStatus=radioMapState.access(v.ports[i]||{port:null}),rail=1856+(network.network-1)*24+i*8,spread=(i-(ports.length-1)/2)*6;
     const points=isSource?[{x:node.x-14,y:node.y+offset},{x:44-(network.network-1)*20,y:node.y+offset},{x:44-(network.network-1)*20,y:first.y},{x:first.x1,y:first.y}]:[{x:last.x2,y:last.y},{x:last.x2+22,y:last.y+spread},{x:rail,y:last.y+spread},{x:rail,y:node.y+30+(network.network-1)*20+i*8},{x:node.x+offset+spread,y:node.y+30+(network.network-1)*20+i*8},{x:node.x+offset+spread,y:node.y+14}];
     const d=roundedRoute(points,10);
     return `<g class="radio-access-port" data-port="${esc(port||'')}" data-status="${portStatus}"><path class="radio-access-underlay" d="${d}"/><path class="radio-access-stroke" data-status="${portStatus}" d="${d}"/><path class="fiber-hit" d="${d}"/></g>`;
    }).join('');
    const id=accessId(network.network,side),label=`Rede ${network.network} · ${node.name} · ${ports.map(bindingPortLabel).join(', ')}`;
    html+=`<g class="radio-access" data-link="${id}" data-network="${network.network}" data-end="${side}" data-status="${v.status}" tabindex="0" role="button" aria-label="${esc(label)}">${paths}</g>`;
   }
  }
  return html;
 }
 function accessDetails(access){
  const {network,side}=access,v=accessReading(network,side),isSource=side==='source';
  const ports=v.ports.length?v.ports.map(r=>`<div><strong>${esc(bindingPortLabel(r.name))} · ${esc(r.label)}</strong><p>Tráfego RX: ${esc(rate(r))}<br>Sinal RX: ${esc(signal(r))}</p></div>`).join(''):'<p>Porta a confirmar.</p>';
  renderInfo(`<button class="icon-button backbone-dismiss" aria-label="Fechar detalhes">×</button><strong>Rede ${network.network} · ${isSource?'Saída de Coari':'Chegada no CLARO'}</strong><small>${esc(v.node.name)} · ${esc(v.node.host)}</small><p>Conexão física monitorada por porta.</p>${ports}<div><strong>${esc(v.radio.device?.name||'Rádio '+(isSource?'AP de Coari':'ST de Tefé'))}</strong><p>${esc(v.radio.label)} · Ping ${number(v.radio.latency)} ms</p></div><button type="button" class="button secondary" data-access-node="${v.node.id}">Ver Datacom</button>`);
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
  let html='<g id="radio-map-layer"><text class="radio-map-heading" x="24" y="500">Rádio · Coari → Tefé</text><text class="radio-map-heading" x="24" y="790">Rádio · Tefé → Tabatinga</text>';
  for(const group of backboneLayout.groups){
   if(group.network)html+=`<text class="radio-network-label" x="10" y="${group.y+5}">R${group.network}</text>`;
   for(const l of backboneLayout.linksFor(config,group)){const g=radioGeometry(l);html+=`<g class="backbone-radio" data-link="${l.id}" data-radio-route="${l.route}" tabindex="0" role="button"><path class="radio-stroke" d="M${g.x1},${g.y} H${g.x2}"/><path class="fiber-hit" d="M${g.x1},${g.y} H${g.x2}"/><text class="radio-caption" x="${(g.x1+g.x2)/2}" y="${g.y-18}" text-anchor="middle"></text></g>`;}
  }
  for(const site of radioSites()){
   html+=`<g class="radio-map-point radio-site-point" data-link="${site.id}" data-radio-site="${site.id}" transform="translate(${site.x} ${site.y})" tabindex="0" role="button" aria-label="${esc(site.name+' · '+site.group.title)}"><circle class="radio-halo" r="20"/><circle r="13"/><image href="/static/icons/siae.png" x="-11" y="-11" width="22" height="22"/><text class="radio-site" y="32" text-anchor="middle">${esc(backboneLayout.shortName(site.name))}</text></g>`;
  }
  return html+'</g>';
 }
 function refreshRadios(){
  for(const l of radioLinks()){
   const v=radioReading(l),g=svg.querySelector(`[data-link="${l.id}"]`),p=radioGeometry(l);
   g.dataset.status=v.status;g.setAttribute('aria-label',`${radioTitle(l)}, ${l.a.site} para ${l.b.site}, ${radioStateNames[v.status]}`);
   const primary=v.a.bps!=null?bandwidth(v.a.bps).replace(/<[^>]*>/g,''):v.status==='down'?'Sem ping':v.status==='unknown'?'Sem leitura':`Ping ${number(Math.max(v.a.latency,v.b.latency))} ms`;
   g.querySelector('text').textContent=primary;
  }
  for(const site of radioSites()){const v=radioSiteReading(site),g=svg.querySelector(`[data-radio-site="${site.id}"]`);g.dataset.status=v.status;g.setAttribute('aria-label',`${site.name}, ${site.group.title}, ${site.refs.length} rádios, ${radioStateNames[v.status]}`);}
  for(const [route,binding]of Object.entries(config.radio_route_origins||{})){
   const g=svg.querySelector(`[data-link="radio-origin-${route}"]`);if(g){const status=originReading({route,binding}).status;g.dataset.status=status;g.querySelector('.radio-access-stroke').dataset.status=status;}
  }
  for(const network of radioNetworks())for(const side of ['source','target']){
   const g=svg.querySelector(`[data-link="${accessId(network.network,side)}"]`);if(!g)continue;
   const v=accessReading(network,side);g.dataset.status=v.status;
   g.querySelectorAll('.radio-access-port').forEach((port,i)=>{const status=radioMapState.access(v.ports[i]||{port:null});port.dataset.status=status;port.querySelector('.radio-access-stroke').dataset.status=status;});
  }
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
  svg.innerHTML='<text class="radio-map-heading" x="24" y="24">Backbone · fibra</text>'+config.links.map(link=>{const p=path(link);return `<g class="backbone-fiber" data-link="${link.id}" tabindex="0" role="button"><path class="fiber-underlay" d="${p.d}"/><path class="fiber-stroke" d="${p.d}"/><path class="fiber-hit" d="${p.d}"/><path class="fiber-label-leader" d=""/><text class="fiber-caption" x="${p.labelX}" y="0" text-anchor="${p.anchor}"></text></g>`;}).join('')+config.nodes.map(n=>`<g class="backbone-node" data-node="${n.id}" transform="translate(${n.x} ${n.y})" tabindex="0" role="button" aria-label="${esc(n.name+' '+n.host)}"><circle class="node-halo" r="22"/><circle r="16"/><image href="/static/icons/datacom.png" x="-12" y="-12" width="24" height="24"/><text x="${n.nodeLabel?.x??0}" y="${n.nodeLabel?.y??30}" text-anchor="${n.nodeLabel?.anchor||'middle'}">${esc(n.name)}</text></g>`).join('');
  svg.insertAdjacentHTML('beforeend',drawRadioAccess()+drawRouteOrigins()+drawRadios());
  svg.querySelectorAll('[data-link]').forEach(g=>{g.setAttribute('aria-controls','backbone-info');g.setAttribute('aria-expanded','false');});
  labelSignature='';labelPositions=new Map();
  if(!svg.style.width){if(viewport.clientWidth<640)applyZoom(.8,false);else fitMap();}refresh();
 }
 function ospfReading(peer){return ospfState.reading(config.ospf_monitor,peer,state.data.devices,Date.now(),$('#connection-error').hidden);}
 function ospfPeer(link){return config.ospf_monitor?.peers.find(p=>p.link_id===link.id);}
 function ospfDetails(link){
  const peer=ospfPeer(link);if(!peer)return '';
  const r=ospfReading(peer);
  return `<div class="ospf-detail" data-status="${r.status}"><strong>OSPF · ${esc(r.label)}</strong><small>Coleta: Escritório Tefé · ${esc(config.ospf_monitor.source_host)}</small><small>Router ID ${esc(peer.router_id)} · Endereço ${esc(peer.address)}</small>${r.interface?`<small>Interface ${esc(r.interface)}</small>`:''}${r.checked_at?`<small>Consulta: ${esc(new Date(r.checked_at).toLocaleTimeString())}</small>`:''}</div>`;
 }
 function refreshOspf(){
  const panel=$('#backbone-ospf'),monitor=config.ospf_monitor;if(!panel||!monitor)return;
  const html='<strong class="ospf-legend-title">OSPF</strong>'+monitor.peers.map(peer=>{
   const r=ospfReading(peer),name=peer.name.replace(/^INFOVIA\s*[·-]\s*/i,''),value=r.status==='unknown'?'Sem leitura':r.label==='Vizinho ausente'?'Ausente':r.label;
   return `<span class="ospf-legend-item" data-status="${r.status}" aria-label="${esc(peer.name+' · OSPF '+r.label)}"><i class="ospf-dot" aria-hidden="true"></i><span>${esc(name)}</span><strong class="ospf-legend-value">${esc(value)}</strong></span>`;
  }).join('');if(panel.innerHTML!==html)panel.innerHTML=html;
 }
 function refresh(){
  if(!config||state.page!=='backbone')return;
  refreshOspf();
  const counts={up:0,down:0,error:0,missing:0,maintenance:0};
  for(const link of config.links){
   const v=values(link),g=svg.querySelector(`[data-link="${link.id}"]`);
   counts[v.status]++;g.dataset.status=v.status;g.setAttribute('aria-label',`${byId(link.a).name} para ${byId(link.b).name}, ${link.label||'fibra'}, ${names[v.status]}`);
   const t=g.querySelector('.fiber-caption');
   const primary=link.maintenance?'Em reparo':v.a.port?.rx_bps==null?'Sem leitura':rate(v.a);
   const rendered=(link.label?`<tspan class="fiber-route-name" x="0" y="0">${esc(link.label)}</tspan><tspan x="0" dy="17">${esc(primary)}</tspan>`:`<tspan x="0" y="0">${esc(primary)}</tspan>`);
   if(t.innerHTML!==rendered)t.innerHTML=rendered;
  }
  for(const n of config.nodes){const d=device(n),el=svg.querySelector(`[data-node="${n.id}"]`);el.dataset.status=d?.state||'pending';el.setAttribute('aria-label',`${n.name}, ${n.host}, ${d?labels[d.state]||d.state:'não cadastrado'}`);}
  refreshRadios();layoutSummaries();
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
  const side=(n,port,r)=>`<div><strong>${esc(n.name)}</strong><small>${esc(n.host)} · ${esc(port||'Porta pendente')}</small><p>${esc(r.label)}</p><p>Tráfego RX: <strong>${esc(rate(r))}</strong><br>Sinal RX: <strong>${esc(signal(r))}</strong></p></div>`;
  const html=`<button class="icon-button backbone-dismiss" aria-label="Fechar detalhes">×</button><strong>${esc(link.label||'Fibra óptica')} · ${names[v.status]}</strong><p class="backbone-link-direction">${esc(byId(link.a).name)} → ${esc(byId(link.b).name)}</p>${side(byId(link.a),link.port_a,v.a)}${side(byId(link.b),link.port_b,v.b)}${ospfDetails(link)}${link.note?`<p>${esc(link.note)}</p>`:''}<button class="button secondary" data-edit-fiber="${link.id}">Editar portas / manutenção</button>`;
  renderInfo(html);
 }
 function renderInfo(html){
  if(info.innerHTML!==html){
   const focused=[...info.querySelectorAll('button,a')].indexOf(document.activeElement);
   info.innerHTML=html;if(focused>=0)info.querySelectorAll('button,a')[focused]?.focus({preventScroll:true});
  }
  const title=info.querySelector('strong');if(title)info.setAttribute('aria-label',title.textContent);
  info.hidden=false;
  const top=Math.max(8,Math.min(viewport.getBoundingClientRect().top+8,innerHeight-220));
  const target=active&&svg.querySelector(`[data-link="${active}"]`),rect=target?.getBoundingClientRect(),onRight=rect&&(rect.left+rect.right)/2>innerWidth/2;
  info.style.top=`${top}px`;info.style.right=onRight?'auto':'16px';info.style.left=onRight?`${Math.max(8,viewport.getBoundingClientRect().left+12)}px`:'auto';info.style.maxHeight=`${innerHeight-top-16}px`;
 }
 function hideInfo(){
  svg.querySelector('[aria-expanded="true"]')?.setAttribute('aria-expanded','false');
  active=null;info.hidden=true;
 }
 function dismissInfo(){
  const target=active&&svg.querySelector(`[data-link="${active}"]`);
  hideInfo();target?.focus({preventScroll:true});
 }
 function show(target){
  if(active===target.dataset.link){dismissInfo();return;}
  hideInfo();active=target.dataset.link;target.setAttribute('aria-expanded','true');details(active);
 }
 document.addEventListener('pointerdown',e=>{
  if(!$('#backbone-port-dialog').open&&!e.target.closest('[data-link],#backbone-info'))hideInfo();
 },true);
 function activate(e){
  const fiber=e.target.closest('[data-link]');if(fiber){show(fiber);return;}
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
 function applyZoom(next,center=true,anchor=null){
  autoFit=false;hideInfo();
  const oldW=svg.getBoundingClientRect().width||1500,oldH=svg.getBoundingClientRect().height||600;
  const ax=anchor?.x??viewport.clientWidth/2,ay=anchor?.y??viewport.clientHeight/2;
  const cx=(viewport.scrollLeft+ax)/oldW,cy=(viewport.scrollTop+ay)/oldH;
  zoom=Math.min(3,Math.max(.1,next));svg.style.minWidth='0';svg.style.width=`${svg.viewBox.baseVal.width*zoom}px`;
  if(center){viewport.scrollLeft=cx*svg.getBoundingClientRect().width-ax;viewport.scrollTop=cy*svg.getBoundingClientRect().height-ay;}
  else{viewport.scrollLeft=0;viewport.scrollTop=0;}
 }
 viewport.addEventListener('wheel',e=>{
  if(e.ctrlKey||e.metaKey||!config||state.page!=='backbone'||drag||!e.deltaY)return;
  e.preventDefault();
  const rect=viewport.getBoundingClientRect(),delta=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?viewport.clientHeight:1);
  applyZoom(zoom*Math.exp(-Math.max(-600,Math.min(600,delta))*.0015),true,{x:e.clientX-rect.left-viewport.clientLeft,y:e.clientY-rect.top-viewport.clientTop});
 },{passive:false});
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
 document.fonts.ready.then(()=>{labelSignature='';if(config&&state.page==='backbone')refresh();});
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
