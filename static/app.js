const $ = s => document.querySelector(s);
const icons = {
 grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
 server:'<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M16 6.5h2M16 17.5h2"/>',
 ports:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9v3h3V9m4 0v3h3V9M7 16h.01M12 16h.01M17 16h.01"/>',
 bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
 activity:'<path d="M2 12h4l3-8 5 16 3-8h5"/>',
 shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6"/>',
 refresh:'<path d="M20 7v5h-5M4 17v-5h5M5.5 7a7 7 0 0 1 12-2l2.5 7M4 12l2.5 7a7 7 0 0 0 12-2"/>',
 plus:'<path d="M12 5v14M5 12h14"/>',
 search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
 close:'<path d="m6 6 12 12M6 18 18 6"/>',
 arrow:'<path d="m7 17 10-10M7 7h10v10"/>',
 check:'<path d="m5 12 4 4L19 6"/><circle cx="12" cy="12" r="10"/>',
 warning:'<path d="m12 3 10 18H2zM12 9v5M12 17h.01"/>',
 copy:'<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
 edit:'<path d="m16 3 5 5M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15z"/>',
 trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
 info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
 flask:'<path d="M9 3h6M10 3v6L4 19q-1 2 2 2h12q3 0 2-2L14 9V3M7 15h10"/>',
 wifi:'<path d="M2 8a16 16 0 0 1 20 0M5 12a11 11 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0M12 20h.01"/>'
};
function icon(name){return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]||icons.server}</svg>`;}
function hydrateIcons(){document.querySelectorAll('[data-icon]').forEach(el=>{el.innerHTML=icon(el.dataset.icon);});}
const esc = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = (n,digits=1) => n==null?'—':Number(n).toLocaleString('pt-BR',{maximumFractionDigits:digits});
const interfaceLabels={'auto':'Automático','gigabit-ethernet':'Gigabit Ethernet','ten-gigabit-ethernet':'Ten Gigabit Ethernet','hundred-gigabit-ethernet':'Hundred Gigabit Ethernet'};
const labels = {online:'Online',offline:'Sem ping',unstable:'Instável',pending:'Aguardando',error:'Erro de coleta',up:'Ativa',down:'Inativa',unknown:'Não identificado'};
const state = {demo:localStorage.getItem('nexo-demo')==='true', page:'overview', data:{devices:[],alerts:[],samples:[]}, loading:false, selected:null, deleting:null, editing:null};
function badge(status){return `<span class="status-pill ${esc(status)}"><i></i>${esc(labels[status]||status)}</span>`;}
function formatTime(date){return date?new Date(date).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'Aguardando';}
function ago(date){if(!date)return 'Aguardando';const seconds=Math.max(0,Math.floor((Date.now()-new Date(date))/1000));return seconds<10?'Agora':seconds<60?`há ${seconds}s`:seconds<3600?`há ${Math.floor(seconds/60)}min`:`há ${Math.floor(seconds/3600)}h`;}
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').hidden=true,4500);}
async function api(path,options){const response=await fetch(path,options);if(!response.ok){let message='Não foi possível concluir a solicitação.';try{const result=await response.json();message=Array.isArray(result.detail)?result.detail.map(e=>e.msg.replace('Value error, ','')).join(' '):result.detail||message;}catch{}throw new Error(message);}return response.status===204?null:response.json();}
async function load(){if(state.loading)return;state.loading=true;try{state.data=await api(`/api/dashboard?demo=${state.demo}`);$('#connection-error').hidden=true;render();}catch(error){$('#connection-error').textContent='Conexão com o monitor interrompida. Os dados podem estar desatualizados. Tentaremos novamente automaticamente.';$('#connection-error').hidden=false;}finally{state.loading=false;}}
function pageDevices(){
 const kind=state.page==='bbus'?'ping':state.page==='datacoms'?'datacom':null;
 return kind?state.data.devices.filter(d=>d.kind===kind):state.data.devices;
}
function renderMetrics(){const d=pageDevices();const online=d.filter(x=>x.state==='online').length;const offline=d.filter(x=>x.state==='offline').length;const downPorts=d.flatMap(x=>x.port_data).filter(x=>x.state==='down').length;
 const cards=[[state.page==='bbus'?"BBU's monitoradas":state.page==='datacoms'?'Datacoms monitorados':'Equipamentos monitorados',d.length,'server','',`${d.filter(x=>x.kind==='datacom').length} Datacoms`,`${d.filter(x=>x.kind==='ping').length} BBU's`],['Equipamentos online',online,'wifi','green',d.length?`${Math.round(online/d.length*100)}% da rede`:'Aguardando cadastro','Respondendo ao ping'],['Equipamentos sem ping',offline,'warning','red','Mais de 20 perdas','consecutivas'],['Portas inativas',downPorts,'ports','amber',`${d.flatMap(x=>x.port_data).length} portas consultadas`,'via SSH']];
 if(state.page==='bbus'){
  cards[0].splice(4,2,'Monitoramento por ping','ICMP');
  cards[1][0]="BBU's online";cards[2][0]="BBU's sem ping";
  cards[3]=["BBU's instáveis",d.filter(x=>x.state==='unstable').length,'activity','amber','De 1 a 20 perdas','consecutivas'];
 }else if(state.page==='datacoms'){
  cards[0].splice(4,2,'Monitoramento SSH','ping e portas');
  cards[1][0]='Datacoms online';cards[2][0]='Datacoms sem ping';
 }
 $('#metrics').innerHTML=cards.map(([title,value,i,color,a,b])=>`<article class="metric-card ${color}"><div class="metric-title">${title}<span class="metric-icon">${icon(i)}</span></div><div class="metric-value">${value.toString().padStart(2,'0')}</div><div class="metric-bottom"><strong>${a}</strong><span>· ${b}</span></div></article>`).join('');
 const errors=d.filter(x=>x.state==='error'||x.ssh_error).length;const unstable=d.filter(x=>x.state==='unstable').length;
 $('#network-status').textContent=!d.length?'Sua rede começa aqui':errors?'Há erros de coleta':offline||downPorts?'Sua rede precisa de atenção':unstable?'Há equipamentos com perda de ping':'Sua rede está operando normalmente';
 $('#network-subtitle').textContent=!d.length?'Cadastre um equipamento para começar':`${d.length} equipamentos acompanhados`;
 $('#bbu-count').textContent=state.data.devices.filter(x=>x.kind==='ping').length;$('#datacom-count').textContent=state.data.devices.filter(x=>x.kind==='datacom').length;$('#alert-dot').hidden=!state.data.alerts.some(a=>a.level==='critical');
}
function chart(samples, target){
 const buckets=new Map();for(const s of samples){const key=Math.floor(new Date(s.at).getTime()/5000)*5000;const item=buckets.get(key)||{sum:0,n:0};if(s.success&&s.latency!=null){item.sum+=s.latency;item.n++;}buckets.set(key,item);}
 const points=[...buckets].sort((a,b)=>a[0]-b[0]).map(([t,v])=>({t,v:v.n?v.sum/v.n:null}));const valid=points.filter(p=>p.v!=null);
 if(!valid.length){target.innerHTML='<div class="chart-empty">O gráfico aparece após as primeiras respostas de ping.</div>';return null;}
 const w=600,h=160,left=36,right=15,top=12,bottom=26,max=Math.max(5,Math.ceil(Math.max(...valid.map(p=>p.v))*1.35));const x=i=>left+(w-left-right)*i/Math.max(1,points.length-1);const y=v=>top+(h-top-bottom)*(1-v/max);
 let paths=[],current=[];points.forEach((p,i)=>{if(p.v==null){if(current.length)paths.push(current);current=[];}else current.push([x(i),y(p.v)]);});if(current.length)paths.push(current);
 const unique=`gradient-${target.id}`;let lines='';for(let i=0;i<4;i++){const v=max*i/3;lines+=`<line x1="${left}" x2="${w-right}" y1="${y(v)}" y2="${y(v)}" stroke="#edf1f5" stroke-dasharray="3 5"/><text x="${left-10}" y="${y(v)+3}" text-anchor="end" fill="#a7b2bf" font-size="8">${number(v)}</text>`;}
 const pathsSVG=paths.map(p=>{const line=p.map((v,i)=>(i?'L':'M')+v.join(',')).join(' ');return `<path d="${line} L${p.at(-1)[0]},${h-bottom} L${p[0][0]},${h-bottom}Z" fill="url(#${unique})"/><path d="${line}" fill="none" stroke="#39ad8d" stroke-width="2" stroke-linejoin="round"/>`;}).join('');
 const end=valid.at(-1),ei=points.indexOf(end);let ticks='';for(let i=0;i<5;i++){const index=Math.round((points.length-1)*i/4);ticks+=`<text x="${left+(w-left-right)*i/4}" y="${h-5}" text-anchor="middle" fill="#a7b2bf" font-size="8">${esc(new Date(points[index].t).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'}))}</text>`;}
 target.innerHTML=`<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Gráfico de latência das últimas amostras"><defs><linearGradient id="${unique}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#70d1b3" stop-opacity=".22"/><stop offset="100%" stop-color="#70d1b3" stop-opacity=".01"/></linearGradient></defs>${lines}${pathsSVG}<circle cx="${x(ei)}" cy="${y(end.v)}" r="3" fill="#3aab8c" stroke="white" stroke-width="2"/>${ticks}</svg>`;
 return valid.reduce((s,p)=>s+p.v,0)/valid.length;
}
function eventHTML(event){const i=event.level==='success'?'check':'warning';return `<div class="event-item"><span class="event-icon ${esc(event.level)}">${icon(i)}</span><div class="event-body"><strong>${esc(event.message)}</strong><p>${esc(event.device_name)}</p></div><span class="event-time" title="${esc(new Date(event.at).toLocaleString('pt-BR'))}">${ago(event.at)}</span></div>`;}
function empty(title,description,action=false){return `<div class="empty-state">${icon('activity')}<h3>${title}</h3><p>${description}</p>${action?'<button class="button primary" data-action="add">Adicionar equipamento</button>':''}</div>`;}
function renderDevices(){const q=$('#search').value.toLowerCase();const filter=$('#state-filter').value;const all=pageDevices();const devices=all.filter(d=>(d.name.toLowerCase().includes(q)||d.host.includes(q))&&(filter==='all'||d.state===filter));
 $('#table-title').textContent=state.page==='bbus'?"BBU's":state.page==='datacoms'?'Datacoms':'Equipamentos';$('#table-description').textContent=state.page==='bbus'?"Disponibilidade e latência das suas BBU's.":state.page==='datacoms'?'Disponibilidade dos Datacoms. Consulte portas e sinais abaixo.':'Acompanhe a disponibilidade de cada ponto da rede.';
 $('#table-count').textContent=all.length;$('#table-summary').textContent=`Exibindo ${devices.length} de ${all.length} equipamentos`;
 $('#device-rows').innerHTML=devices.length?devices.map(d=>`<tr><td><div class="device-cell"><span class="device-icon">${icon(d.kind==='datacom'?'ports':'server')}</span><div><strong>${esc(d.name)}</strong><small>${d.kind==='datacom'?'DATACOM · SSH':"BBU · PING ICMP"}</small></div></div></td><td class="ip">${esc(d.host)}</td><td>${badge(d.state)}</td><td class="latency">${d.latency!=null?`<span class="tiny-bars">▂▄▆</span>${number(d.latency)} <small>ms</small>`:'—'}</td><td><span class="loss-value ${d.failures>20?'critical':''}"><span class="loss-track"><i style="width:${Math.min(d.failures/21*100,100)}%"></i></span>${d.failures}<span class="muted">/ 21</span></span></td><td>${ago(d.last_check)}</td><td><div class="device-actions"><button class="icon-button" data-edit="${d.id}" title="Editar equipamento" aria-label="Editar ${esc(d.name)}">${icon('edit')}</button><button class="icon-button" data-detail="${d.id}" title="Ver detalhes" aria-label="Ver detalhes de ${esc(d.name)}">${icon('arrow')}</button><button class="icon-button" data-remove="${d.id}" title="Remover equipamento" aria-label="Remover ${esc(d.name)}">${icon('trash')}</button></div></td></tr>`).join(''):`<tr><td colspan="7">${empty(all.length?'Nenhum resultado encontrado':state.page==='bbus'?"Cadastre sua primeira BBU":state.page==='datacoms'?'Conecte seu primeiro Datacom':'Sua rede, em um só lugar',all.length?'Tente outro nome, IP ou filtro.':state.page==='bbus'?"Adicione uma BBU para acompanhar ping, latência e perdas consecutivas.":state.page==='datacoms'?'Adicione um Datacom para acompanhar disponibilidade, portas e sinais ópticos.':'Adicione seu primeiro equipamento ou explore a demonstração para conhecer o painel.',!all.length)}</td></tr>`;
}
function portsHTML(d){if(d.ssh_error)return `<p class="ssh-warning">${icon('warning')} ${esc(d.ssh_error)} As leituras anteriores não são exibidas como atuais.</p>`;
 if(!d.port_data.length)return '<p class="muted">Aguardando a primeira consulta SSH. Intervalo: 30 segundos.</p>';
 return `<div class="port-cards">${d.port_data.map(p=>`<article class="port-card"><div class="port-card-header"><strong>${esc(p.name)}</strong>${badge(p.state)}</div>${p.interface_type&&p.interface_type!=='auto'?`<small class="port-family">${esc(interfaceLabels[p.interface_type]||p.interface_type)}</small>`:''}${p.description?`<p class="muted">${esc(p.description)}</p>`:''}<div class="optical"><span>RX · RECEPÇÃO<strong>${number(p.rx,2)} <small>dBm</small></strong></span><span>TX · TRANSMISSÃO<strong>${number(p.tx,2)} <small>dBm</small></strong></span></div><small>Leitura ${ago(p.checked_at)}</small>${p.rx==null&&p.tx==null?'<p class="signal-note">Sinal não informado ou formato não reconhecido.</p>':''}<details data-port-key="${d.id}:${esc(p.name)}"><summary>Ver saída do equipamento</summary><button type="button" class="button secondary output-copy" data-copy-output>${icon('copy')}Copiar saída</button><pre>${esc(p.status_output)}</pre><pre>${esc(p.optics_output)}</pre></details></article>`).join('')}</div>`;}
function readingOutput(){
 return (state.page==='datacoms'&&Boolean($('#ports-content').querySelector('details[open]')))
  ||($('#detail-dialog').open&&Boolean($('#detail-content').querySelector('details[open]')));
}
function render(){
 const paused=readingOutput()||Boolean(window.getSelection()?.toString());
 $('#reading-banner').hidden=!paused;
 if(paused)return;
 const {devices,alerts,samples}=state.data;$('#demo-banner').hidden=!state.demo;$('#demo-label').textContent=state.demo?'Sair da demonstração':'Ver demonstração';$('#last-update').textContent=`${state.demo?'Simulação':'Atualizado'} às ${formatTime(state.data.updated_at)}`;
 renderMetrics();renderDevices();const average=chart(samples,$('#latency-chart'));$('#chart-average').innerHTML=`${number(average)} <small>ms</small>`;
 $('#recent-events').innerHTML=alerts.length?alerts.slice(0,3).map(eventHTML).join(''):empty('Nenhum evento por aqui','Quedas e recuperações aparecerão neste espaço.');
 $('#alerts-content').innerHTML=alerts.length?alerts.map(eventHTML).join(''):empty('Sua linha do tempo começa aqui','Eventos serão registrados automaticamente quando houver uma mudança na rede.');
 const openPorts=new Set([...$('#ports-content').querySelectorAll('details[open]')].map(e=>e.dataset.portKey));
 const datacoms=devices.filter(d=>d.kind==='datacom');$('#ports-content').innerHTML=datacoms.length?datacoms.map(d=>`<div class="port-device"><h3>${esc(d.name)}</h3><p>${esc(d.host)} · ${esc(interfaceLabels[d.interface_type]||'Automático')} · ${d.ports.length||d.port_data.length} portas · ${d.ports.length?'seleção manual':'detecção automática'}</p>${portsHTML(d)}</div>`).join(''):empty('Conecte seu primeiro Datacom','Cadastre uma conexão SSH para acompanhar portas e sinais ópticos.',true);
 $('#ports-content').querySelectorAll('details').forEach(e=>e.open=openPorts.has(e.dataset.portKey));
 if(state.selected&&$('#detail-dialog').open){if(state.demo){state.detailSamples=samples.filter(s=>s.device_id===state.selected);renderDetail();}else{const selected=state.selected;api(`/api/devices/${selected}/history`).then(history=>{if(state.selected===selected){state.detailSamples=history;renderDetail();}}).catch(()=>{});}}
}
const pages={overview:['Visão geral','Tudo conectado. Tudo sob controle.'],bbus:["BBU's","Monitore o ping, a latência e as perdas das suas BBU's."],datacoms:['Datacoms','Disponibilidade, portas e sinais ópticos dos seus Datacoms.'],alerts:['Eventos','Cada mudança na rede, registrada em um só lugar.']};
function navigate(page){
 window.getSelection()?.removeAllRanges();state.page=page;
 document.querySelectorAll('[data-page]').forEach(e=>{
  e.classList.toggle('active',e.dataset.page===page);
  if(e.dataset.page===page)e.setAttribute('aria-current','page');else e.removeAttribute('aria-current');
 });
 $('#page-title').textContent=pages[page][0];$('#breadcrumb').textContent=pages[page][0];$('#page-description').textContent=pages[page][1];
 $('#add-device-label').textContent=page==='bbus'?'Adicionar BBU':page==='datacoms'?'Adicionar Datacom':'Adicionar equipamento';
 $('#overview-charts').hidden=page!=='overview';
 $('#devices-section').hidden=!['overview','bbus','datacoms'].includes(page);
 $('#ports-section').hidden=page!=='datacoms';$('#alerts-section').hidden=page!=='alerts';
 $('#search').value='';$('#state-filter').value='all';
 render();
}
function toggleDemo(value){
 document.querySelectorAll('.port-card details[open]').forEach(e=>e.open=false);
 window.getSelection()?.removeAllRanges();
 state.demo=value;state.selected=null;localStorage.setItem('nexo-demo',String(value));load();
}
function syncDeviceKind(){
 const ssh=$('[name="kind"]:checked').value==='datacom';
 $('#ssh-fields').hidden=!ssh;
 for(const name of ['username','fingerprint'])$(`[name="${name}"]`).required=ssh;
 const keepPassword=state.editing?.kind==='datacom'&&state.editing.has_password;
 $('[name="password"]').required=ssh&&!keepPassword;
 $('[name="password"]').placeholder=keepPassword?'Deixe vazio para manter a senha atual':'';
 $('#password-help').textContent=keepPassword?'Deixe vazio para manter a senha atual. Preencha apenas para trocar.':'Armazenada de forma criptografada no servidor.';
 $('#device-dialog-title').textContent=state.editing?(ssh?'Editar Datacom':'Editar BBU'):(ssh?'Adicionar Datacom':'Adicionar BBU');
 $('#save-device').innerHTML=state.editing?`${icon('check')}Salvar alterações`:`${icon('plus')}Adicionar equipamento`;
 $('[name="name"]').placeholder=ssh?'Ex.: Datacom • Core principal':'Ex.: BBU • Torre central';
}
function openAdd(){
 state.editing=null;$('#device-form').reset();
 $(`[name="kind"][value="${state.page==='datacoms'?'datacom':'ping'}"]`).checked=true;
 syncDeviceKind();$('#form-error').hidden=true;$('#device-dialog').showModal();
}
function openEdit(id){
 if(state.demo){toast('Os equipamentos de demonstração são exemplos. Saia da demonstração para editar sua rede.');return;}
 const device=state.data.devices.find(d=>d.id===id);
 if(!device)return;
 state.editing=device;$('#device-form').reset();
 for(const name of ['name','host','interval','ping_timeout','interface_type','ssh_port','username','fingerprint','status_command','optics_command']){
  $(`[name="${name}"]`).value=device[name]??(name==='ping_timeout'?4:name==='interface_type'?'auto':'');
 }
 $(`[name="kind"][value="${device.kind}"]`).checked=true;
 $('[name="ports"]').value=device.ports.join(', ');$('[name="password"]').value='';
 syncDeviceKind();$('#form-error').hidden=true;$('#device-dialog').showModal();
}
function renderDetail(){const d=state.data.devices.find(d=>d.id===state.selected);if(!d){$('#detail-dialog').close();state.selected=null;return;}
 const opened=[...$('#detail-content').querySelectorAll('details')].map(e=>e.open);
 $('#detail-content').innerHTML=`<div class="dialog-heading"><div><div class="eyebrow">${d.kind==='datacom'?'DATACOM · SSH + ICMP':'MONITORAMENTO ICMP'}</div><h2>${esc(d.name)}</h2></div><button class="icon-button" data-close-detail aria-label="Fechar">${icon('close')}</button></div><p class="dialog-description">${esc(d.host)} · Intervalo ${d.interval}s ${state.demo?'· Demonstração':''}</p><div class="detail-summary"><div class="detail-stat">Disponibilidade<strong>${badge(d.state)}</strong></div><div class="detail-stat">Latência<strong>${number(d.latency)} <small>ms</small></strong></div><div class="detail-stat">Perdas consecutivas<strong>${d.failures} <small>/ 21</small></strong></div></div>${d.state==='error'?'<p class="ssh-warning">O coletor não conseguiu executar o ping. Veja o diagnóstico abaixo. Este erro não é contado como perda.</p>':''}<h2>Última tentativa de ping</h2><p class="dialog-description">${esc(d.ping_backend||'ICMP')} · espera máxima ${number(d.ping_timeout??4)}s</p><pre class="ping-diagnostic">${esc(d.ping_detail||'Aguardando a primeira tentativa.')}</pre><h2>Histórico de ping</h2><div class="chart-container detail-chart" id="detail-chart"></div>${d.kind==='datacom'?`<div class="section-divider">PORTAS E SINAIS ÓPTICOS</div>${portsHTML(d)}`:''}`;
 $('#detail-content').querySelectorAll('details').forEach((e,i)=>e.open=Boolean(opened[i]));chart(state.detailSamples||[], $('#detail-chart'));
}
async function openDetail(id){state.selected=id;state.detailSamples=[];renderDetail();$('#detail-dialog').showModal();try{state.detailSamples=state.demo?state.data.samples.filter(s=>s.device_id===id):await api(`/api/devices/${id}/history`);if(state.selected===id)renderDetail();}catch(e){toast(e.message);}}
$('#device-form').addEventListener('submit',async event=>{
 event.preventDefault();const form=new FormData(event.target);const d=Object.fromEntries(form);
 d.interval=Number(d.interval);d.ping_timeout=Number(d.ping_timeout);d.ssh_port=Number(d.ssh_port);d.ports=d.ports.split(',').map(p=>p.trim()).filter(Boolean);
 const editingId=state.editing?.id;$('#save-device').disabled=true;$('#form-error').hidden=true;
 try{
  await api(editingId?`/api/devices/${editingId}`:'/api/devices',{method:editingId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
  $('#device-dialog').close();state.editing=null;state.demo=false;localStorage.setItem('nexo-demo','false');
  navigate(d.kind==='datacom'?'datacoms':'bbus');toast(editingId?'Alterações salvas. O monitoramento será atualizado.':'Equipamento adicionado à sua rede.');await load();
 }catch(e){$('#form-error').textContent=e.message;$('#form-error').hidden=false;}finally{$('#save-device').disabled=false;}
});
document.querySelectorAll('[name="kind"]').forEach(el=>el.addEventListener('change',syncDeviceKind));
document.querySelectorAll('[data-page]').forEach(e=>e.addEventListener('click',()=>navigate(e.dataset.page)));
$('#all-events').addEventListener('click',()=>navigate('alerts'));
$('#add-device').addEventListener('click',openAdd);
$('#refresh').addEventListener('click',()=>load());
$('#demo-toggle').addEventListener('click',()=>toggleDemo(!state.demo));$('#exit-demo').addEventListener('click',()=>toggleDemo(false));
$('#search').addEventListener('input',renderDevices);$('#state-filter').addEventListener('change',renderDevices);
document.querySelectorAll('.close-dialog').forEach(e=>e.addEventListener('click',()=>$('#device-dialog').close()));
document.querySelectorAll('.close-confirm').forEach(e=>e.addEventListener('click',()=>$('#confirm-dialog').close()));
document.addEventListener('click',event=>{const copy=event.target.closest('[data-copy-output]');if(copy)copyOutput(copy);const edit=event.target.closest('[data-edit]'),detail=event.target.closest('[data-detail]'),remove=event.target.closest('[data-remove]');if(edit)openEdit(Number(edit.dataset.edit));if(detail)openDetail(Number(detail.dataset.detail));if(event.target.closest('[data-close-detail]')){$('#detail-dialog').close();state.selected=null;}if(event.target.closest('[data-action="add"]'))openAdd();if(remove){if(state.demo){toast('Os equipamentos de demonstração são exemplos. Saia do modo demonstração para gerenciar sua rede.');return;}state.deleting=Number(remove.dataset.remove);const d=state.data.devices.find(d=>d.id===state.deleting);$('#confirm-description').textContent=`Deseja remover “${d.name}” (${d.host})?`;$('#confirm-dialog').showModal();}});
async function copyOutput(button){
 const text=[...button.closest('details').querySelectorAll('pre')].map(p=>p.textContent).join('\n\n');
 try{
  if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(text);
  else{
   const input=document.createElement('textarea');input.value=text;input.style.position='fixed';input.style.opacity='0';document.body.append(input);input.select();
   try{if(!document.execCommand('copy'))throw new Error('Clipboard denied');}finally{input.remove();}
  }
  toast('Saída copiada.');
 }catch{
  toast('O navegador bloqueou a cópia. A atualização está pausada; você pode selecionar o texto e usar Ctrl+C.');
 }
}
$('#resume-live').addEventListener('click',()=>{
 document.querySelectorAll('.port-card details[open]').forEach(e=>e.open=false);
 window.getSelection()?.removeAllRanges();render();
});
document.addEventListener('toggle',event=>{
 if(event.target.matches('.port-card details'))render();
},true);
document.addEventListener('selectionchange',()=>{
 const selected=Boolean(window.getSelection()?.toString());
 if(selected)$('#reading-banner').hidden=false;
 else if(!$('#reading-banner').hidden&&!readingOutput())render();
});
$('#confirm-remove').addEventListener('click',async()=>{$('#confirm-remove').disabled=true;try{await api(`/api/devices/${state.deleting}`,{method:'DELETE'});$('#confirm-dialog').close();toast('Equipamento removido.');await load();}catch(e){toast(e.message);}finally{$('#confirm-remove').disabled=false;}});
for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
hydrateIcons();load();setInterval(load,1000);
