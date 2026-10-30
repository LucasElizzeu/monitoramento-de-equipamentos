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
 attention:'<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 17h.01"/>',
 flask:'<path d="M9 3h6M10 3v6L4 19q-1 2 2 2h12q3 0 2-2L14 9V3M7 15h10"/>',
 wifi:'<path d="M2 8a16 16 0 0 1 20 0M5 12a11 11 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0M12 20h.01"/>'
};
function icon(name){return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]||icons.server}</svg>`;}
function hydrateIcons(){document.querySelectorAll('[data-icon]').forEach(el=>{el.innerHTML=icon(el.dataset.icon);});}
const esc = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = (n,digits=1) => n==null?'—':Number(n).toLocaleString('pt-BR',{maximumFractionDigits:digits});
const interfaceLabels={'auto':'Automático','mixed':'Gigabit + Ten (portas selecionadas)','gigabit-ethernet':'Gigabit Ethernet','ten-gigabit-ethernet':'Ten Gigabit Ethernet','hundred-gigabit-ethernet':'Hundred Gigabit Ethernet'};
const labels = {online:'Online',offline:'Sem ping',unstable:'Instável',pending:'Aguardando',error:'Erro de coleta',up:'Ativa',down:'Inativa',unknown:'Não identificado'};
const previewParam=new URLSearchParams(location.search).get('design-preview');
const designPreview=['balanced','compact','list'].includes(previewParam)?previewParam:null;
if(designPreview){
 document.body.dataset.designPreview=designPreview;
 document.body.dataset.layout=designPreview;
 const sheet=document.createElement('link');sheet.rel='stylesheet';sheet.href='/static/design-preview.css';document.head.append(sheet);
}
const state = {demo:Boolean(designPreview)||localStorage.getItem('nexo-demo')==='true', page:'overview', data:{devices:[],alerts:[],samples:[]}, loading:false, selected:null, deleting:null, editing:null, portNaming:null, removingCircuit:null, metricCards:{}, metricView:null, dataRevision:0};
function badge(status){return `<span class="status-pill ${esc(status)}"><i></i>${esc(labels[status]||status)}</span>`;}
function formatTime(date){return date?new Date(date).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'Aguardando';}
function ago(date){if(!date)return 'Aguardando';const seconds=Math.max(0,Math.floor((Date.now()-new Date(date))/1000));return seconds<10?'Agora':seconds<60?`há ${seconds}s`:seconds<3600?`há ${Math.floor(seconds/60)}min`:`há ${Math.floor(seconds/3600)}h`;}
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').hidden=true,4500);}
async function api(path,options){if(designPreview&&options?.method&&!['GET','HEAD'].includes(options.method.toUpperCase()))throw new Error('Esta prévia usa dados de demonstração. Volte ao monitoramento para alterar sua rede.');const response=await fetch(path,options);if(!response.ok){let message='Não foi possível concluir a solicitação.';try{const result=await response.json();message=Array.isArray(result.detail)?result.detail.map(e=>e.msg.replace('Value error, ','')).join(' '):result.detail||message;}catch{}throw new Error(message);}if(options?.method&&!['GET','HEAD'].includes(options.method.toUpperCase()))state.dataRevision++;return response.status===204?null:response.json();}
async function load(){if(state.loading)return;state.loading=true;const revision=state.dataRevision;try{const data=await api(`/api/dashboard?demo=${state.demo}`);if(revision!==state.dataRevision)return;state.data=data;$('#connection-error').hidden=true;render();}catch(error){$('#connection-error').textContent='Conexão com o monitor interrompida. Os dados podem estar desatualizados. Tentaremos novamente automaticamente.';$('#connection-error').hidden=false;}finally{state.loading=false;}}
function orderedDatacoms(devices=state.data.devices){
 return devices.filter(d=>d.kind==='datacom').sort((a,b)=>(a.circuit_position??Infinity)-(b.circuit_position??Infinity)||a.id-b.id);
}
function pageDevices(page=state.page){
 if(page==='datacoms')return orderedDatacoms();
 if(page==='siae')return state.data.devices.filter(d=>d.kind==='siae');
 return page==='bbus'?state.data.devices.filter(d=>d.kind==='ping'):state.data.devices;
}
function deviceKindLabel(device){return device.kind==='datacom'?'Datacom':device.kind==='siae'?'Rádio SIAE':'BBU';}
function collectedPorts(devices){
 return orderedDatacoms(devices).filter(d=>!d.ssh_error).flatMap(device=>(device.port_data||[]).map(port=>({device,port})));
}
function metricEntries(key,devices){
 if(key==='down-ports')return collectedPorts(devices).filter(entry=>entry.port.state==='down');
 return devices.filter(d=>key==='all'||d.state===key).map(device=>({device}));
}
function renderMetrics(){const d=pageDevices();const online=metricEntries('online',d).length;const offline=metricEntries('offline',d).length;const downPorts=metricEntries('down-ports',d).length;
 const cards=[[state.page==='bbus'?"BBU's monitoradas":state.page==='datacoms'?'Datacoms monitorados':'Equipamentos monitorados',d.length,'server','',`${d.filter(x=>x.kind==='datacom').length} Datacoms`,`${d.filter(x=>x.kind==='ping').length} BBU's · ${d.filter(x=>x.kind==='siae').length} SIAE`],['Equipamentos online',online,'wifi','green',d.length?`${Math.round(online/d.length*100)}% da rede`:'Aguardando cadastro','Respondendo ao ping'],['Equipamentos sem ping',offline,'warning','red','Mais de 20 perdas','consecutivas'],['Portas inativas',downPorts,'ports','amber',`${collectedPorts(d).length} portas consultadas`,'via SSH']];
 if(['bbus','siae'].includes(state.page)){
  const subject=state.page==='siae'?'Rádios SIAE':"BBU's";
  cards[0][0]=state.page==='siae'?'Rádios SIAE monitorados':"BBU's monitoradas";
  cards[0].splice(4,2,'Monitoramento por ping','ICMP');
  cards[1][0]=`${subject} online`;cards[2][0]=`${subject} sem ping`;
  cards[3]=[`${subject} instáveis`,d.filter(x=>x.state==='unstable').length,'activity','amber','De 1 a 20 perdas','consecutivas'];
 }else if(state.page==='datacoms'){
  cards[0].splice(4,2,'Monitoramento SSH','ping e portas');
  cards[1][0]='Datacoms online';cards[2][0]='Datacoms sem ping';
 }
 const keys=['all','online','offline',['bbus','siae'].includes(state.page)?'unstable':'down-ports'];
 state.metricCards=Object.fromEntries(keys.map((key,index)=>[key,{title:cards[index][0],page:state.page,entries:metricEntries(key,d),at:state.data.updated_at,demo:state.demo,sshErrors:key==='down-ports'&&d.some(x=>x.kind==='datacom'&&x.ssh_error)}]));
 const focused=document.activeElement?.dataset.metric;
 $('#metrics').innerHTML=cards.map(([title,value,i,color,a,b],index)=>`<article class="metric-card ${color}"><div class="metric-title">${title}<button type="button" class="metric-icon metric-details" data-metric="${keys[index]}" title="Listar ${title.toLowerCase()}" aria-label="Listar ${title.toLowerCase()}" aria-haspopup="dialog" aria-controls="metric-dialog">${icon('attention')}</button></div><div class="metric-value">${value.toString().padStart(2,'0')}</div><div class="metric-bottom"><strong>${a}</strong><span>· ${b}</span></div></article>`).join('');
 if(focused)$(`[data-metric="${focused}"]`)?.focus({preventScroll:true});
 const errors=d.filter(x=>x.state==='error'||x.ssh_error||(x.circuits||[]).some(c=>c.state==='error')).length;const unstable=d.filter(x=>x.state==='unstable'||(x.circuits||[]).some(c=>c.state==='unstable')).length;const remoteOffline=d.some(x=>(x.circuits||[]).some(c=>c.state==='offline'));
 $('#network-status').textContent=!d.length?'Sua rede começa aqui':errors?'Há erros de coleta':offline||downPorts||remoteOffline?'Sua rede precisa de atenção':unstable?'Há equipamentos com perda de ping':'Sua rede está operando normalmente';
 $('#network-subtitle').textContent=!d.length?'Cadastre um equipamento para começar':`${d.length} equipamentos acompanhados`;
 $('#bbu-count').textContent=state.data.devices.filter(x=>x.kind==='ping').length;$('#datacom-count').textContent=state.data.devices.filter(x=>x.kind==='datacom').length;$('#siae-count').textContent=state.data.devices.filter(x=>x.kind==='siae').length;$('#alert-dot').hidden=!state.data.alerts.some(a=>a.level==='critical');
}
function renderMetricList(){
 const view=state.metricView;if(!view)return;
 const ports=view.key==='down-ports';const count=view.entries.length;
 $('#metric-dialog-title').textContent=view.title;
 $('#metric-dialog-description').textContent=`${pages[view.page][0]} · ${count} ${ports?(count===1?'porta':'portas'):(count===1?'equipamento':'equipamentos')} · ${view.demo?'Demonstração':'Leitura'} às ${formatTime(view.at)}`;
 $('#metric-dialog-note').hidden=!view.sshErrors;
 const emptyMessages={all:'Nenhum equipamento cadastrado nesta aba.',online:'Nenhum equipamento online nesta aba.',offline:'Nenhum equipamento sem ping nesta aba.',unstable:view.page==='siae'?'Nenhum rádio SIAE instável nesta aba.':"Nenhuma BBU instável nesta aba.",'down-ports':'Nenhuma porta inativa nas leituras disponíveis.'};
 $('#metric-dialog-results').innerHTML=count?`<ul class="metric-results">${view.entries.map(({device:d,port:p})=>{
  const name=p?(p.custom_name||p.display_name||p.description||`Porta ${p.name}`):d.name;
  const family=p?(interfaceLabels[p.interface_type||d.interface_type]||'Interface'):`${deviceKindLabel(d)} · ${d.kind==='datacom'?'SSH':'Ping'}`;
  const context=p?`${family} · Porta ${p.name}`:family;
  return `<li class="metric-result"><div class="metric-result-main"><strong class="metric-result-name">${esc(name)}</strong><p>${esc(p?`${d.name} · ${d.host}`:d.host)}</p><small>${esc(context)}${d.circuit_position!=null?` · Posição ${esc(d.circuit_position)}`:''}</small>${p?`<small>Leitura ${ago(p.checked_at)}</small>`:`<small>${d.failures} perdas consecutivas · ${ago(d.last_check)}</small>`}</div><div class="metric-result-actions">${badge(p?p.state:d.state)}<button type="button" class="button secondary" data-metric-device="${d.id}" aria-label="Ver equipamento ${esc(d.name)}">Ver equipamento ${icon('arrow')}</button></div></li>`;
 }).join('')}</ul>`:`<p class="metric-empty">${emptyMessages[view.key]}</p>`;
}
function openMetric(key){
 const snapshot=state.metricCards[key];if(!snapshot)return;
 state.metricView={...snapshot,key};renderMetricList();$('#metric-dialog').showModal();
}
$('#refresh-metric-list').addEventListener('click',async()=>{
 const view=state.metricView;if(!view)return;
 $('#refresh-metric-list').disabled=true;
 try{await load();if(state.metricView!==view)return;const devices=pageDevices(view.page);
  state.metricView={...view,entries:metricEntries(view.key,devices),at:state.data.updated_at,sshErrors:view.key==='down-ports'&&devices.some(d=>d.kind==='datacom'&&d.ssh_error)};renderMetricList();
 }finally{$('#refresh-metric-list').disabled=false;}
});
$('#close-metric-list').addEventListener('click',()=>$('#metric-dialog').close());
$('#metric-dialog').addEventListener('close',()=>{
 const key=state.metricView?.key;state.metricView=null;
 if(!document.querySelector('dialog[open]'))$(`[data-metric="${key}"]`)?.focus({preventScroll:true});
});
document.addEventListener('click',event=>{
 const metric=event.target.closest('[data-metric]');if(metric)openMetric(metric.dataset.metric);
 const device=event.target.closest('[data-metric-device]');if(!device)return;
 const id=Number(device.dataset.metricDevice);
 if(!state.data.devices.some(d=>d.id===id)){toast('Este equipamento foi removido. Atualize a lista.');return;}
 $('#metric-dialog').close();openDetail(id);
});
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
function deviceAddressHTML(device){
 if(!['ping','siae'].includes(device.kind))return esc(device.host);
 const host=device.host.includes(':')?`[${device.host}]`:device.host;
 const scheme=device.kind==='siae'?(device.siae_scheme||'http'):'http',port=device.kind==='siae'?(device.siae_port||(scheme==='https'?443:80)):80;
 const suffix=port===(scheme==='https'?443:80)?'':`:${port}`;
 return `<a class="device-web-link" href="${esc(scheme)}://${esc(host)}${suffix}/" target="_blank" rel="noopener noreferrer" title="Abrir site de ${esc(deviceKindLabel(device))} em nova aba" aria-label="Abrir site de ${esc(device.name)} (${esc(device.host)}) em nova aba"><span>${esc(device.host)}</span>${icon('arrow')}</a>`;
}
function renderDevices(){
 const q=$('#search').value.toLowerCase(),filter=$('#state-filter').value,all=pageDevices();
 const devices=all.filter(d=>(d.name.toLowerCase().includes(q)||d.host.includes(q))&&(filter==='all'||d.state===filter));
 $('#table-title').textContent=state.page==='bbus'?"BBU's":state.page==='datacoms'?'Datacoms':state.page==='siae'?'Rádios SIAE':'Equipamentos';
 $('#table-description').textContent=state.page==='bbus'?"Disponibilidade e latência das suas BBU's.":state.page==='datacoms'?'Disponibilidade dos Datacoms. Consulte circuitos e portas abaixo.':state.page==='siae'?'Disponibilidade dos rádios. Consulte o consumo dos TRX abaixo.':'Acompanhe a disponibilidade de cada ponto da rede.';
 $('#table-count').textContent=all.length;$('#table-summary').textContent=`Exibindo ${devices.length} de ${all.length} equipamentos`;
 $('#device-rows').innerHTML=devices.length?devices.map(d=>`<tr class="device-row"><td class="device-name-cell"><div class="device-cell"><span class="device-icon">${icon(d.kind==='datacom'?'ports':d.kind==='siae'?'wifi':'server')}</span><div><strong>${esc(d.name)}</strong><small>${d.kind==='datacom'?`DATACOM · SSH${d.circuit_position!=null?' · POSIÇÃO '+d.circuit_position:''}`:d.kind==='siae'?"SIAE · PING ICMP":"BBU · PING ICMP"}</small></div></div><span class="mobile-device-status">${badge(d.state)}</span></td><td class="ip" data-label="Endereço IP">${deviceAddressHTML(d)}</td><td class="device-state-cell">${badge(d.state)}</td><td class="latency" data-label="Latência">${d.latency!=null?`<span class="tiny-bars">▂▄▆</span>${number(d.latency)} <small>ms</small>`:'—'}</td><td data-label="Perdas consecutivas"><span class="loss-value ${d.failures>20?'critical':''}"><span class="loss-track"><i style="width:${Math.min(d.failures/21*100,100)}%"></i></span>${d.failures}<span class="muted">/ 21</span></span></td><td data-label="Última checagem">${ago(d.last_check)}</td><td class="device-actions-cell"><div class="device-actions"><button class="icon-button" data-edit="${d.id}" title="Editar equipamento" aria-label="Editar ${esc(d.name)}">${icon('edit')}<span class="action-label">Editar</span></button><button class="icon-button" data-detail="${d.id}" title="Ver detalhes" aria-label="Ver detalhes de ${esc(d.name)}">${icon('arrow')}<span class="action-label">Detalhes</span></button><button class="icon-button" data-remove="${d.id}" title="Remover equipamento" aria-label="Remover ${esc(d.name)}">${icon('trash')}<span class="action-label">Remover</span></button></div></td></tr>`).join(''):`<tr><td colspan="7">${empty(all.length?'Nenhum resultado encontrado':state.page==='bbus'?"Cadastre sua primeira BBU":state.page==='datacoms'?'Conecte seu primeiro Datacom':state.page==='siae'?'Cadastre seu primeiro rádio SIAE':'Sua rede, em um só lugar',all.length?'Tente outro nome, IP ou filtro.':'Adicione um equipamento ou explore a demonstração para conhecer o painel.',!all.length)}</td></tr>`;
}
function sshDiagnosticHTML(d){
 const diagnostic=d.ssh_diagnostic||{};
 const family=interfaceLabels[diagnostic.interface_type||d.interface_type]||'Automático';
 const metadata=`Tipo salvo: ${family}\nEtapa: ${diagnostic.stage||'Aguardando nova consulta'}`;
 const status=`Comando de portas: ${diagnostic.status_command||d.status_command||'—'}\n${diagnostic.status_output||'Nenhuma saída registrada nesta tentativa.'}`;
 const optics=`Comando de sinais: ${diagnostic.optics_command||d.optics_command||'—'}\n${diagnostic.optics_output||'Nenhuma saída registrada nesta tentativa.'}`;
 return `<details class="ssh-diagnostic" data-port-key="${d.id}:ssh-diagnostic"><summary>Ver diagnóstico da consulta SSH</summary><button type="button" class="button secondary output-copy" data-copy-output>${icon('copy')}Copiar diagnóstico</button><pre>${esc(metadata)}</pre><pre>${esc(status)}</pre><pre>${esc(optics)}</pre></details>`;
}
function bandwidth(value){
 if(value==null)return '—';
 const [scale,unit]=value>=1e9?[1e9,'Gbps']:value>=1e6?[1e6,'Mbps']:value>=1e3?[1e3,'Kbps']:[1,'bps'];
 return `${number(value/scale,2)} <small>${unit}</small>`;
}
function siaeDiagnosticHTML(device){
 const data=device.siae_consumption||{};
 if(data.status!=='error')return '';
 const mode=device.siae_auth_mode==='login'?'Login automático':'Sessão manual';
 const text=`Rádio: ${device.name}\nIP: ${device.host}\nAcesso: ${mode}\nWeb: ${device.siae_scheme||'http'} · porta ${device.siae_port||80}\nÚltima consulta: ${data.checked_at?new Date(data.checked_at).toLocaleString('pt-BR'):'—'}\n${data.error||'Falha de coleta sem diagnóstico.'}\nPróxima tentativa automática: após 30 segundos da falha.`;
 return `<details class="siae-diagnostic"><summary>Ver diagnóstico da banda</summary><button type="button" class="button secondary output-copy" data-copy-output>${icon('copy')}Copiar diagnóstico</button><pre>${esc(text)}</pre></details>`;
}
function siaeCardHTML(device){
 const consumption=device.siae_consumption||{};
 const pair=consumption.status==='demo'||device.siae_interfaces?.length===2;
 const note=consumption.status==='demo'?'Dados simulados · TRX A + TRX B':consumption.error||consumption.note||(consumption.total_bps==null?'Ative a leitura em Configurar banda.':pair?'RX total = TRX A + TRX B':'RX da interface TRX selecionada.');
 return `<article class="port-card siae-card" data-siae="${device.id}"><div class="port-card-header"><h3>${esc(device.name)}</h3>${badge(device.state)}</div><p class="siae-address ip">${deviceAddressHTML(device)}</p><div class="port-ping-values siae-ping"><span>Latência<strong>${number(device.latency,2)} <small>ms</small></strong></span><span>Perdas<strong>${device.failures} <small>/ 21</small></strong></span></div><small>Ping ${ago(device.last_check)}</small><div class="port-traffic"><div class="traffic-heading">Consumo total · RX</div><div class="traffic-values"><strong>${bandwidth(consumption.total_bps)}</strong></div></div>${pair?`<div class="siae-trx"><span>TRX A<strong>${bandwidth(consumption.trx_a_bps)}</strong></span><span>TRX B<strong>${bandwidth(consumption.trx_b_bps)}</strong></span></div>`:`<p class="siae-source">Interface TRX · índice ${esc((device.siae_interfaces||[3])[0])}</p>`}${consumption.checked_at?`<small>Banda ${ago(consumption.checked_at)}</small>`:''}<p class="siae-note ${consumption.total_bps==null?'pending':''} ${consumption.status==='error'?'error':''}">${esc(note)}</p>${siaeDiagnosticHTML(device)}<button type="button" class="button secondary siae-configure" data-configure-siae="${device.id}">${icon('edit')}${device.siae_enabled?'Editar banda':'Configurar banda'}</button></article>`;
}
function renderSiae(){
 const radios=pageDevices('siae'),q=$('#search').value.toLowerCase(),filter=$('#state-filter').value;
 const visible=radios.filter(d=>(d.name.toLowerCase().includes(q)||d.host.includes(q))&&(filter==='all'||d.state===filter));
 $('#siae-content').innerHTML=visible.length?visible.map(siaeCardHTML).join(''):empty(radios.length?'Nenhum rádio neste filtro':'Cadastre seu primeiro rádio SIAE',radios.length?'Tente outro nome, IP ou status.':'Adicione um rádio para acompanhar ping e banda pela consulta web do ALFOplus2.',!radios.length);
}
function utilizationHTML(p){
 if(p.utilization_enabled===false)return '';
 const note=p.utilization_error||(p.rx_bps==null&&p.rx_percent==null?'Consumo não informado ou formato não reconhecido.':'');
 return `<div class="port-traffic"><div class="traffic-heading">Consumo na porta</div><div class="traffic-values"><span><strong>${bandwidth(p.rx_bps)}</strong>${p.rx_percent!=null?`<small>${number(p.rx_percent,2)}%</small>`:''}</span></div>${note?`<p class="signal-note">${esc(note)}</p>`:''}</div>`;
}
function makePortIdentity(name,family='auto'){
 const match=String(name).match(/^(.*?)([0-9]+\/[0-9]+\/[0-9]+)$/);if(!match)return '';
 const prefix=match[1].toLowerCase().replace(/[^a-z0-9]/g,'');
 const aliases={'gigabit-ethernet':['gigabitethernet','1gigabitethernet','1ge','ge','gi','giga'],'ten-gigabit-ethernet':['tengigabitethernet','10gigabitethernet','10ge','xge','xgigabitethernet','xe','te','ten'],'hundred-gigabit-ethernet':['hundredgigabitethernet','100gigabitethernet','100ge','hu','ce']};
 for(const [type,names]of Object.entries(aliases))if(names.includes(prefix))family=type;
 if(!['gigabit-ethernet','ten-gigabit-ethernet','hundred-gigabit-ethernet'].includes(family))family='auto';
 return `${family}:${match[2]}`;
}
function portIdentity(port,device){return makePortIdentity(port.name,port.interface_type||device.interface_type);}
function shortPortLabel(identity){
 const [family,number]=identity.split(':');return `${number} · ${{'gigabit-ethernet':'Giga','ten-gigabit-ethernet':'Ten','hundred-gigabit-ethernet':'100G','auto':'Interface'}[family]||family}`;
}
function portPingHTML(c,d){
 return `<section class="port-ping" data-ping-id="${c.id}"><div class="port-ping-heading"><strong>Ping · ${esc(c.name)}</strong>${badge(c.state)}</div><div class="port-ping-meta"><code class="port-ping-ip">${esc(c.host)}</code><small class="port-ping-time">${ago(c.last_check)}</small></div><div class="port-ping-values"><span>Latência<strong>${number(c.latency,2)} <small>ms</small></strong></span><span>Perdas<strong>${c.failures} <small>/ 21</small></strong></span></div>${c.error?`<p class="signal-note">${esc(c.error)}</p>`:''}<details data-port-key="${d.id}:circuit:${c.id}"><summary>Detalhes do ping</summary><p class="port-ping-batch">${c.transmitted!=null?`${c.received} de ${c.transmitted} respostas`:'Aguardando resultado válido'} · intervalo ${c.interval}s</p><div class="port-ping-actions"><button type="button" class="button secondary" data-test-circuit="${c.id}" aria-label="Testar circuito ${esc(c.name)}">${icon('refresh')}Testar agora</button><button type="button" class="icon-button" data-edit-circuit="${c.id}" title="Configurar ping" aria-label="Configurar circuito ${esc(c.name)}">${icon('edit')}</button><button type="button" class="icon-button" data-remove-circuit="${c.id}" title="Remover ping" aria-label="Remover circuito ${esc(c.name)}">${icon('trash')}</button></div><button type="button" class="button secondary output-copy" data-copy-output>${icon('copy')}Copiar saída</button><pre>${esc(c.output||'Aguardando a primeira consulta pelo Datacom.')}</pre></details></section>`;
}
function datacomHTML(d){
 const ports=d.ssh_error?[]:d.port_data,circuits=d.circuits||[];
 return `<div class="port-device" data-datacom="${d.id}"><div class="datacom-heading"><div><div class="port-device-title"><span class="circuit-position" title="Posição no circuito">${d.circuit_position??'—'}</span><h3>${esc(d.name)}</h3></div><p class="datacom-meta"><span class="ip">${esc(d.host)}</span><span>${esc(interfaceLabels[d.interface_type]||'Automático')}</span></p></div><div class="datacom-port-counts">${d.ssh_error?badge('error'):`<span class="status-pill up">${ports.filter(p=>p.state==='up').length} ativas</span><span class="status-pill down">${ports.filter(p=>p.state==='down').length} inativas</span>`}</div></div><div class="datacom-section-heading ports-subheading"><div><h4>Portas, sinais e pings</h4><p>${ports.length} portas${circuits.length?` · ${circuits.length} ${circuits.length===1?'destino':'destinos'} de ping`:''}</p></div>${circuits.length?`<button type="button" class="button secondary" data-configure-circuits="${d.id}">${icon('edit')}Configurar IPs</button>`:''}</div>${portsHTML(d)}</div>`;
}
function findCircuit(id){
 for(const device of state.data.devices){const circuit=(device.circuits||[]).find(c=>c.id===id);if(circuit)return{device,circuit};}
 return null;
}
function updateCircuitDraftCount(){
 $('#device-circuit-count').textContent=$('#device-circuit-rows').children.length;
}
function circuitPortOptions(selected=''){
 const choices=new Map(),device=state.editing;
 for(const port of device?.port_data||[]){const key=portIdentity(port,device);if(key)choices.set(key,`${shortPortLabel(key)} · ${port.display_name||port.description||port.name}`);}
 const mode=$('[name="interface_type"]').value;
 const lists=mode==='mixed'?[...normalizedPorts($('[name="ten_ports"]').value).map(name=>[name,'ten-gigabit-ethernet']),...normalizedPorts($('[name="giga_ports"]').value).map(name=>[name,'gigabit-ethernet'])]:$('[name="ports"]').value.split(',').map(name=>[name.trim(),mode]);
 for(const [name,family]of lists){const key=makePortIdentity(name,family);if(key&&!key.startsWith('auto:')&&!choices.has(key))choices.set(key,shortPortLabel(key));}
 if(selected&&!choices.has(selected))choices.set(selected,`${shortPortLabel(selected)} · fora da lista atual`);
 return `<option value="">Sem vínculo · cartão separado</option>`+[...choices].map(([key,label])=>`<option value="${esc(key)}"${key===selected?' selected':''}>${esc(label)}</option>`).join('');
}
function refreshCircuitPortOptions(){
 $('#device-circuit-rows').querySelectorAll('[data-circuit-field="port_identity"]').forEach(select=>{select.innerHTML=circuitPortOptions(select.value);});
}
function appendCircuitDraft(circuit={}){
 const row=document.createElement('div');row.className='device-circuit-row';row.dataset.circuitId=circuit.id??'';
 row.innerHTML=`<div class="form-grid"><label class="field">IP do circuito<input data-circuit-field="host" required placeholder="Ex.: 10.91.0.2" autocomplete="off" value="${esc(circuit.host||'')}"></label><label class="field">Nome (opcional)<input data-circuit-field="name" maxlength="80" placeholder="Ex.: Circuito Anori" value="${esc(circuit.name||'')}"></label></div><div class="device-circuit-row-footer"><label class="field">Intervalo dos testes (segundos)<input data-circuit-field="interval" type="number" min="10" max="300" required value="${circuit.interval??30}"></label><button type="button" class="button secondary remove-device-circuit" aria-label="Remover IP desta configuração">${icon('trash')}Remover IP</button></div>`;
 const binding=document.createElement('label');binding.className='field';
 binding.innerHTML=`Porta do cartão (opcional)<select data-circuit-field="port_identity">${circuitPortOptions(circuit.port_identity||'')}</select><small>Escolha a porta para mostrar o ping junto dos sinais e do consumo. Sem vínculo, o ping fica em um cartão pequeno separado.</small>`;
 row.insertBefore(binding,row.querySelector('.device-circuit-row-footer'));
 row.querySelectorAll('input,select').forEach(input=>input.disabled=$('[name="kind"]:checked').value!=='datacom');
 $('#device-circuit-rows').append(row);updateCircuitDraftCount();return row;
}
function renderCircuitDrafts(circuits=[]){
 $('#device-circuit-rows').replaceChildren();circuits.forEach(appendCircuitDraft);updateCircuitDraftCount();$('#device-circuit-config').open=circuits.length>0;
}
function readCircuitDrafts(){
 return [...$('#device-circuit-rows').children].map(row=>{
  const host=row.querySelector('[data-circuit-field="host"]').value.trim();
  const name=row.querySelector('[data-circuit-field="name"]').value.trim()||`Circuito ${host}`;
  const interval=Number(row.querySelector('[data-circuit-field="interval"]').value);
  const port_identity=row.querySelector('[data-circuit-field="port_identity"]').value||null;
  return {...(row.dataset.circuitId?{id:Number(row.dataset.circuitId)}:{}),host,name,interval,port_identity};
 });
}
function configureCircuitIps(deviceId,circuitId=null){
 document.querySelectorAll('.port-ping details[open]').forEach(details=>details.open=false);
 openEdit(deviceId);if(!$('#device-dialog').open||state.editing?.id!==deviceId)return;
 $('#device-circuit-config').open=true;
 requestAnimationFrame(()=>{const row=circuitId?$(`#device-circuit-rows [data-circuit-id="${circuitId}"]`):null;const target=row?.querySelector('[data-circuit-field="host"]')||$('#device-circuit-config');target.scrollIntoView({block:'center'});if(row)target.focus({preventScroll:true});});
}
$('#add-device-circuit').addEventListener('click',()=>{
 if($('#device-circuit-rows').children.length>=20){toast('Limite de 20 IPs por Datacom.');return;}
 const row=appendCircuitDraft();row.querySelector('[data-circuit-field="host"]').focus();
});
$('#device-circuit-rows').addEventListener('click',event=>{const remove=event.target.closest('.remove-device-circuit');if(remove){remove.closest('.device-circuit-row').remove();updateCircuitDraftCount();}});
document.addEventListener('click',async event=>{
 const config=event.target.closest('[data-configure-circuits]');if(config)configureCircuitIps(Number(config.dataset.configureCircuits));
 const edit=event.target.closest('[data-edit-circuit]');if(edit){const target=findCircuit(Number(edit.dataset.editCircuit));if(target)configureCircuitIps(target.device.id,target.circuit.id);}
 const test=event.target.closest('[data-test-circuit]');if(test){if(state.demo){toast('Os circuitos da demonstração são exemplos.');return;}test.disabled=true;try{await api(`/api/circuits/${Number(test.dataset.testCircuit)}/check`,{method:'POST'});toast('Teste solicitado ao Datacom. Aguarde alguns segundos pelo resultado.');}catch(error){toast(error.message);}finally{test.disabled=false;}}
 const remove=event.target.closest('[data-remove-circuit]');if(remove){if(state.demo){toast('Os circuitos da demonstração são exemplos.');return;}const target=findCircuit(Number(remove.dataset.removeCircuit));if(!target)return;state.removingCircuit=target.circuit.id;state.deleting=null;$('#confirm-dialog h2').textContent='Remover circuito?';$('#confirm-description').textContent=`Remover ${target.circuit.name} (${target.circuit.host}) de ${target.device.name}?`;$('#confirm-note').textContent='O monitoramento deste circuito será removido. Os eventos anteriores serão preservados.';$('#confirm-dialog').showModal();}
});
function portCardHTML(d,p){
 const linked=(d.circuits||[]).filter(c=>c.port_identity===portIdentity(p,d));
 return `<article class="port-card" data-port-identity="${esc(portIdentity(p,d))}"><div class="port-card-header"><strong>${esc(p.name)}</strong>${badge(p.state)}</div>${p.interface_type&&p.interface_type!=='auto'?`<small class="port-family">${esc(interfaceLabels[p.interface_type]||p.interface_type)}</small>`:''}<div class="port-title-row"><p class="port-display-name">${esc(p.display_name||p.description||'Nomear porta')}</p><button type="button" class="icon-button" data-port-alias="${d.id}" data-port="${esc(p.name)}" data-family="${esc(p.interface_type||d.interface_type||'auto')}" title="Editar nome da porta" aria-label="Editar nome da porta ${esc(p.name)}">${icon('edit')}</button></div><div class="optical-heading">Sinal óptico</div><div class="optical"><span>RX · RECEPÇÃO<strong>${number(p.rx,2)} <small>dBm</small></strong></span><span>TX · TRANSMISSÃO<strong>${number(p.tx,2)} <small>dBm</small></strong></span></div>${utilizationHTML(p)}${p.rx_bps!=null||p.traffic_series_id?`<button type="button" class="port-traffic-history" data-traffic-device="${d.id}" data-traffic-identity="${esc(portIdentity(p,d))}">${icon('activity')}Ver gráfico 24h</button>`:''}<small>Leitura ${ago(p.checked_at)}</small>${p.rx==null&&p.tx==null?'<p class="signal-note">Sinal não informado ou formato não reconhecido.</p>':''}${linked.map(c=>portPingHTML(c,d)).join('')}<details data-port-key="${d.id}:${esc(p.interface_type||d.interface_type||'auto')}:${esc(p.name)}"><summary>Ver saída do equipamento</summary><button type="button" class="button secondary output-copy" data-copy-output>${icon('copy')}Copiar saída</button><pre>${esc(p.status_output)}</pre><pre>${esc(p.optics_output)}</pre><pre>${esc(p.utilization_output)}</pre></details></article>`;
}
function portsHTML(d){
 const ports=d.ssh_error?[]:(d.port_data||[]),keys=new Set(ports.map(p=>portIdentity(p,d)));
 const unbound=(d.circuits||[]).filter(c=>!c.port_identity||!keys.has(c.port_identity));
 const warning=d.ssh_error?`<p class="ssh-warning">${icon('warning')} ${esc(d.ssh_error)} As leituras anteriores não são exibidas como atuais.</p>${sshDiagnosticHTML(d)}`:!ports.length?'<p class="muted">Aguardando a primeira consulta SSH. Intervalo: 30 segundos.</p>':'';
 if(!ports.length&&!unbound.length)return warning;
 return `${warning}<div class="port-cards">${ports.map(p=>portCardHTML(d,p)).join('')}${unbound.map(c=>`<article class="port-card standalone-circuit">${c.port_identity?`<p class="unbound-port-note">${esc(shortPortLabel(c.port_identity))} · porta fora das leituras atuais</p>`:''}${portPingHTML(c,d)}</article>`).join('')}</div>`;
}
function readingOutput(){
 return (state.page==='datacoms'&&Boolean($('#ports-content').querySelector('details[open]')))
  ||(state.page==='siae'&&Boolean($('#siae-content').querySelector('details[open]')))
  ||($('#detail-dialog').open&&Boolean($('#detail-content').querySelector('details[open]')));
}
function render(){
 const paused=readingOutput()||Boolean(window.getSelection()?.toString());
 $('#reading-banner').hidden=!paused;
 if(paused)return;
 const {devices,alerts,samples}=state.data;$('#demo-banner').hidden=!state.demo;$('#demo-label').textContent=state.demo?'Sair da demonstração':'Ver demonstração';$('#last-update').textContent=`${state.demo?'Simulação':'Atualizado'} às ${formatTime(state.data.updated_at)}`;
 renderMetrics();renderDevices();renderSiae();const average=chart(samples,$('#latency-chart'));$('#chart-average').innerHTML=`${number(average)} <small>ms</small>`;
 $('#recent-events').innerHTML=alerts.length?alerts.slice(0,3).map(eventHTML).join(''):empty('Nenhum evento por aqui','Quedas e recuperações aparecerão neste espaço.');
 $('#alerts-content').innerHTML=alerts.length?alerts.map(eventHTML).join(''):empty('Sua linha do tempo começa aqui','Eventos serão registrados automaticamente quando houver uma mudança na rede.');
 const openPorts=new Set([...$('#ports-content').querySelectorAll('details[open]')].map(e=>e.dataset.portKey));
 const datacoms=orderedDatacoms(devices);$('#ports-content').innerHTML=datacoms.length?datacoms.map(datacomHTML).join(''):empty('Conecte seu primeiro Datacom','Cadastre uma conexão SSH para acompanhar portas, sinais e circuitos.',true);
 $('#ports-content').querySelectorAll('details').forEach(e=>e.open=openPorts.has(e.dataset.portKey));
 if(state.selected&&$('#detail-dialog').open){if(state.demo){state.detailSamples=samples.filter(s=>s.device_id===state.selected);renderDetail();}else{const selected=state.selected;api(`/api/devices/${selected}/history`).then(history=>{if(state.selected===selected){state.detailSamples=history;renderDetail();}}).catch(()=>{});}}
}
const pages={overview:['Visão geral','Tudo conectado. Tudo sob controle.'],bbus:["BBU's","Monitore o ping, a latência e as perdas das suas BBU's."],datacoms:['Datacoms','Disponibilidade, portas e sinais ópticos dos seus Datacoms.'],siae:['Rádios SIAE','Disponibilidade por ping e consumo real de banda do rádio.'],alerts:['Eventos','Cada mudança na rede, registrada em um só lugar.']};
function navigate(page){
 window.getSelection()?.removeAllRanges();state.page=page;
 document.querySelectorAll('[data-page]').forEach(e=>{
  e.classList.toggle('active',e.dataset.page===page);
  if(e.dataset.page===page)e.setAttribute('aria-current','page');else e.removeAttribute('aria-current');
 });
 $('#page-title').textContent=pages[page][0];$('#breadcrumb').textContent=pages[page][0];$('#page-description').textContent=pages[page][1];
 $('#add-device-label').textContent=page==='bbus'?'Adicionar BBU':page==='datacoms'?'Adicionar Datacom':page==='siae'?'Adicionar rádio SIAE':'Adicionar equipamento';
 $('#overview-charts').hidden=page!=='overview';
 $('#devices-section').hidden=!['overview','bbus','datacoms','siae'].includes(page);
 $('#ports-section').hidden=page!=='datacoms';$('#siae-section').hidden=page!=='siae';$('#alerts-section').hidden=page!=='alerts';
 $('#search').value='';$('#state-filter').value='all';
 render();
}
function toggleDemo(value){
 if(designPreview)return;
 document.querySelectorAll('.port-card details[open], .port-ping details[open], .ssh-diagnostic[open]').forEach(e=>e.open=false);
 window.getSelection()?.removeAllRanges();
 state.demo=value;state.selected=null;localStorage.setItem('nexo-demo',String(value));load();
}
function normalizedPorts(value){
 return value.split(/[,;\s]+/).map(port=>port.trim()).filter(Boolean).map(port=>/^\d+$/.test(port)?`1/1/${Number(port)}`:port);
}
function mixedPortLists(ports){
 const lists={ten:[],giga:[]};
 for(const port of ports){
  const match=port.match(/^(.+?)(\d+\/\d+\/\d+)$/);if(!match)continue;
  const prefix=match[1].toLowerCase().replace(/[^a-z0-9]/g,'');
  if(['ten','tengigabitethernet','10ge','10gigabitethernet','xge','xe','te'].includes(prefix))lists.ten.push(match[2]);
  if(['giga','gigabitethernet','1ge','ge','gi'].includes(prefix))lists.giga.push(match[2]);
 }
 return lists;
}
function syncInterfaceMode(carry=false){
 const selector=$('[name="interface_type"]');const mode=selector.value;const previous=selector.dataset.previousMode;
 if(carry&&mode==='mixed'&&['gigabit-ethernet','ten-gigabit-ethernet'].includes(previous)){
  const target=previous==='ten-gigabit-ethernet'?'ten_ports':'giga_ports';
  if(!$(`[name="${target}"]`).value)$(`[name="${target}"]`).value=normalizedPorts($('[name="ports"]').value).join(', ');
 }else if(carry&&previous==='mixed'&&mode!=='mixed'){
  const source=mode==='ten-gigabit-ethernet'?'ten_ports':mode==='gigabit-ethernet'?'giga_ports':null;
  $('[name="ports"]').value=source?normalizedPorts($(`[name="${source}"]`).value).join(', '):'';
 }
 $('#single-port-field').hidden=mode==='mixed';$('#mixed-port-fields').hidden=mode!=='mixed';selector.dataset.previousMode=mode;refreshCircuitPortOptions();
}
function syncDeviceKind(){
 const kind=$('[name="kind"]:checked').value,ssh=kind==='datacom';
 $('#siae-fields').hidden=kind!=='siae';syncSiaeFields();
 $('#ssh-fields').hidden=!ssh;
 for(const name of ['username','fingerprint'])$(`[name="${name}"]`).required=ssh;
 const keepPassword=state.editing?.kind==='datacom'&&state.editing.has_password;
 $('[name="password"]').required=ssh&&!keepPassword;
 $('[name="password"]').placeholder=keepPassword?'Deixe vazio para manter a senha atual':'';
 $('#password-help').textContent=keepPassword?'Deixe vazio para manter a senha atual. Preencha apenas para trocar.':'Armazenada de forma criptografada no servidor.';
 $('#device-dialog-title').textContent=`${state.editing?'Editar':'Adicionar'} ${kind==='datacom'?'Datacom':kind==='siae'?'rádio SIAE':'BBU'}`;
 $('#save-device').innerHTML=state.editing?`${icon('check')}Salvar alterações`:`${icon('plus')}Adicionar equipamento`;
 $('[name="name"]').placeholder=ssh?'Ex.: Datacom • Core principal':kind==='siae'?'Ex.: SIAE • Enlace Coari':'Ex.: BBU • Torre central';
 syncInterfaceMode();$('#device-circuit-rows').querySelectorAll('input,select').forEach(input=>input.disabled=!ssh);
}
function syncSiaeFields(){
 const radio=$('[name="kind"]:checked').value==='siae',enabled=$('[name="siae_enabled"]').checked;
 $('#siae-fields').querySelectorAll('input,select').forEach(input=>input.disabled=!radio||(input.name!=='siae_enabled'&&!enabled));
 const pair=$('[name="siae_mode"]').value==='pair';
 $('#siae-interface-b-field').hidden=!pair;
 $('[name="siae_interface_b"]').disabled=!radio||!enabled||!pair;
 $('#siae-interface-a-label').textContent=pair?'Índice da interface TRX A':'Índice da interface TRX';
 for(const name of ['siae_port','siae_poll_interval','siae_interface_a'])$(`[name="${name}"]`).required=radio&&enabled;
 $('[name="siae_interface_b"]').required=radio&&enabled&&pair;
 const saved=state.editing?.kind==='siae'&&state.editing.siae_auth_mode!=='login'&&state.editing.has_siae_session;
 const automatic=$('[name="siae_auth_mode"]').value==='login';
 $('#siae-login-fields').hidden=!automatic;$('#siae-session-field').hidden=automatic;
 for(const name of ['siae_username','siae_password'])$(`[name="${name}"]`).disabled=!radio||!enabled||!automatic;
 $('[name="siae_session"]').disabled=!radio||!enabled||automatic;
 $('[name="siae_session"]').required=radio&&enabled&&!automatic&&!saved;
 $('[name="siae_username"]').required=radio&&enabled&&automatic;
 const savedPassword=state.editing?.kind==='siae'&&state.editing.has_siae_password;
 $('[name="siae_password"]').required=radio&&enabled&&automatic&&!savedPassword;
 $('#siae-password-help').textContent=savedPassword?'Senha salva. Deixe vazio para mantê-la. Se alterar IP, protocolo, porta ou usuário, informe a senha novamente.':'Informe a senha diretamente aqui. O programa entra no rádio e renova a sessão quando necessário.';
 $('#siae-session-help').textContent=saved?'Já existe uma sessão salva. Deixe vazio para mantê-la ou cole um novo Id para renovar.':'Copie no seu navegador e cole aqui. Não precisa enviar a sessão no chat.';
}
function openAdd(){
 if(designPreview){toast('Esta prévia usa dados de demonstração. Volte ao monitoramento para adicionar equipamentos.');return;}
 state.editing=null;$('#device-form').reset();renderCircuitDrafts();
 $(`[name="kind"][value="${state.page==='datacoms'?'datacom':state.page==='siae'?'siae':'ping'}"]`).checked=true;
 syncDeviceKind();$('#form-error').hidden=true;$('#device-dialog').showModal();
}
function openEdit(id){
 if(state.demo){toast('Os equipamentos de demonstração são exemplos. Saia da demonstração para editar sua rede.');return;}
 const device=state.data.devices.find(d=>d.id===id);
 if(!device)return;
 state.editing=device;$('#device-form').reset();
 for(const name of ['name','host','interval','ping_timeout','interface_type','circuit_position','ssh_port','username','fingerprint','status_command','optics_command','utilization_command','siae_scheme','siae_port','siae_poll_interval']){
  $(`[name="${name}"]`).value=device[name]??(name==='ping_timeout'?4:name==='interface_type'?'auto':'');
 }
 $(`[name="kind"][value="${device.kind}"]`).checked=true;
 $('[name="siae_enabled"]').checked=Boolean(device.siae_enabled);$('#siae-config').open=Boolean(device.siae_enabled);
 $('[name="siae_auth_mode"]').value=device.siae_auth_mode||'session';$('[name="siae_username"]').value=device.siae_username||'';
 $('[name="siae_scheme"]').value=device.siae_scheme||'http';$('[name="siae_port"]').value=device.siae_port||80;$('[name="siae_poll_interval"]').value=device.siae_poll_interval||2;
 $('[name="siae_mode"]').value=device.siae_interfaces?.length===2?'pair':'single';$('[name="siae_interface_a"]').value=device.siae_interfaces?.[0]||3;$('[name="siae_interface_b"]').value=device.siae_interfaces?.[1]||'';
 $('[name="ports"]').value=device.ports.join(', ');$('[name="password"]').value='';
 const lists=mixedPortLists(device.ports);$('[name="ten_ports"]').value=lists.ten.join(', ');$('[name="giga_ports"]').value=lists.giga.join(', ');
 renderCircuitDrafts(device.circuits||[]);syncDeviceKind();$('#form-error').hidden=true;$('#device-dialog').showModal();
}
function renderDetail(){const d=state.data.devices.find(d=>d.id===state.selected);if(!d){$('#detail-dialog').close();state.selected=null;return;}
 const opened=[...$('#detail-content').querySelectorAll('details')].map(e=>e.open);
 $('#detail-content').innerHTML=`<div class="dialog-heading"><div><div class="eyebrow">${d.kind==='datacom'?'DATACOM · SSH + ICMP':d.kind==='siae'?'RÁDIO SIAE · ICMP':'MONITORAMENTO ICMP'}</div><h2>${esc(d.name)}</h2></div><button class="icon-button" data-close-detail aria-label="Fechar">${icon('close')}</button></div><p class="dialog-description">${esc(d.host)} · Intervalo ${d.interval}s ${state.demo?'· Demonstração':''}</p><div class="detail-summary"><div class="detail-stat">Disponibilidade<strong>${badge(d.state)}</strong></div><div class="detail-stat">Latência<strong>${number(d.latency)} <small>ms</small></strong></div><div class="detail-stat">Perdas consecutivas<strong>${d.failures} <small>/ 21</small></strong></div></div>${d.state==='error'?'<p class="ssh-warning">O coletor não conseguiu executar o ping. Veja o diagnóstico abaixo. Este erro não é contado como perda.</p>':''}<h2>Última tentativa de ping</h2><p class="dialog-description">${esc(d.ping_backend||'ICMP')} · espera máxima ${number(d.ping_timeout??4)}s</p><pre class="ping-diagnostic">${esc(d.ping_detail||'Aguardando a primeira tentativa.')}</pre><h2>Histórico de ping</h2><div class="chart-container detail-chart" id="detail-chart"></div>${d.kind==='datacom'?`<div class="section-divider">PORTAS, SINAIS E PINGS</div>${portsHTML(d)}`:d.kind==='siae'?`<div class="section-divider">CONSUMO DO RÁDIO</div>${siaeCardHTML(d)}`:''}`;
 $('#detail-content').querySelectorAll('details').forEach((e,i)=>e.open=Boolean(opened[i]));chart(state.detailSamples||[], $('#detail-chart'));
}
async function openDetail(id){state.selected=id;state.detailSamples=[];renderDetail();$('#detail-dialog').showModal();try{state.detailSamples=state.demo?state.data.samples.filter(s=>s.device_id===id):await api(`/api/devices/${id}/history`);if(state.selected===id)renderDetail();}catch(e){toast(e.message);}}
$('#device-form').addEventListener('input',event=>{if(event.target.matches('[name="ports"],[name="ten_ports"],[name="giga_ports"]'))refreshCircuitPortOptions();});
$('#device-form').addEventListener('invalid',event=>{if(event.target.closest('#device-circuit-config'))$('#device-circuit-config').open=true;if(event.target.closest('#siae-config'))$('#siae-config').open=true;},true);
$('#device-form').addEventListener('submit',async event=>{
 event.preventDefault();const form=new FormData(event.target);const d=Object.fromEntries(form);
 d.circuit_position=d.circuit_position===''?null:Number(d.circuit_position.trim().replace(',','.'));d.interval=Number(d.interval);d.ping_timeout=Number(d.ping_timeout);d.ssh_port=Number(d.ssh_port);d.ports=d.interface_type==='mixed'?[...normalizedPorts(d.ten_ports).map(port=>'ten:'+port),...normalizedPorts(d.giga_ports).map(port=>'giga:'+port)]:d.ports.split(',').map(p=>p.trim()).filter(Boolean);delete d.ten_ports;delete d.giga_ports;
 if(d.kind==='siae'){
  d.siae_enabled=$('[name="siae_enabled"]').checked;d.siae_scheme=$('[name="siae_scheme"]').value;d.siae_auth_mode=$('[name="siae_auth_mode"]').value;
  if(d.siae_auth_mode==='session')d.siae_session=$('[name="siae_session"]').value;
  for(const name of ['siae_port','siae_poll_interval'])d[name]=Number($(`[name="${name}"]`).value);
  d.siae_interfaces=[$('[name="siae_interface_a"]').value,...($('[name="siae_mode"]').value==='pair'?[$('[name="siae_interface_b"]').value]:[])].map(Number);
 }
 for(const name of ['siae_mode','siae_interface_a','siae_interface_b'])delete d[name];
 if(d.kind==='datacom'){d.circuits=readCircuitDrafts();d.circuits_snapshot=Object.fromEntries((state.editing?.circuits||[]).map(c=>[c.id,c.config_version]));}
 const editingId=state.editing?.id;$('#save-device').disabled=true;$('#form-error').hidden=true;
 try{
  await api(editingId?`/api/devices/${editingId}`:'/api/devices',{method:editingId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
  $('[name="siae_session"]').value='';$('[name="siae_password"]').value='';$('#device-dialog').close();state.editing=null;state.demo=false;localStorage.setItem('nexo-demo','false');
  navigate(d.kind==='datacom'?'datacoms':d.kind==='siae'?'siae':'bbus');toast(editingId?'Alterações salvas. O monitoramento será atualizado.':'Equipamento adicionado à sua rede.');await load();
 }catch(e){$('#form-error').textContent=e.message;$('#form-error').hidden=false;}finally{$('#save-device').disabled=false;}
});
 $('[name="interface_type"]').addEventListener('change',()=>syncInterfaceMode(true));
document.querySelectorAll('[name="kind"]').forEach(el=>el.addEventListener('change',syncDeviceKind));
for(const name of ['siae_enabled','siae_mode','siae_auth_mode'])$(`[name="${name}"]`).addEventListener('change',syncSiaeFields);
$('[name="siae_scheme"]').addEventListener('change',()=>{const port=$('[name="siae_port"]');if(['80','443'].includes(port.value))port.value=$('[name="siae_scheme"]').value==='https'?'443':'80';});
$('#device-dialog').addEventListener('close',()=>{for(const name of ['siae_session','siae_password'])$(`[name="${name}"]`).value='';});
document.addEventListener('click',event=>{const button=event.target.closest('[data-configure-siae]');if(!button)return;openEdit(Number(button.dataset.configureSiae));if($('#device-dialog').open){$('#siae-config').open=true;$('[name="siae_enabled"]').focus();}});
document.querySelectorAll('[data-page]').forEach(e=>e.addEventListener('click',()=>navigate(e.dataset.page)));
$('#all-events').addEventListener('click',()=>navigate('alerts'));
$('#add-device').addEventListener('click',openAdd);
$('#refresh').addEventListener('click',()=>load());
$('#demo-toggle').addEventListener('click',()=>toggleDemo(!state.demo));$('#exit-demo').addEventListener('click',()=>toggleDemo(false));
$('#search').addEventListener('input',()=>{renderDevices();renderSiae();});$('#state-filter').addEventListener('change',()=>{renderDevices();renderSiae();});
document.querySelectorAll('.close-dialog').forEach(e=>e.addEventListener('click',()=>$('#device-dialog').close()));
document.querySelectorAll('.close-confirm').forEach(e=>e.addEventListener('click',()=>$('#confirm-dialog').close()));
document.addEventListener('click',event=>{const alias=event.target.closest('[data-port-alias]');if(alias)openPortName(Number(alias.dataset.portAlias),alias.dataset.port,alias.dataset.family);const copy=event.target.closest('[data-copy-output]');if(copy)copyOutput(copy);const edit=event.target.closest('[data-edit]'),detail=event.target.closest('[data-detail]'),remove=event.target.closest('[data-remove]');if(edit)openEdit(Number(edit.dataset.edit));if(detail)openDetail(Number(detail.dataset.detail));if(event.target.closest('[data-close-detail]')){$('#detail-dialog').close();state.selected=null;}if(event.target.closest('[data-action="add"]'))openAdd();if(remove){if(state.demo){toast('Os equipamentos de demonstração são exemplos. Saia do modo demonstração para gerenciar sua rede.');return;}state.deleting=Number(remove.dataset.remove);state.removingCircuit=null;$('#confirm-dialog h2').textContent='Remover equipamento?';$('#confirm-note').textContent='O monitoramento e as amostras de ping serão removidos. O histórico de eventos será preservado.';const d=state.data.devices.find(d=>d.id===state.deleting);$('#confirm-description').textContent=`Deseja remover “${d.name}” (${d.host})?`;$('#confirm-dialog').showModal();}});
function openPortName(deviceId, port, family){
 if(state.demo){toast('Saia da demonstração para personalizar os nomes da sua rede.');return;}
 const device=state.data.devices.find(d=>d.id===deviceId);
 const reading=device?.port_data.find(p=>p.name===port&&(p.interface_type||device.interface_type||'auto')===family);
 if(!device||!reading)return;
 state.portNaming={deviceId,port,family};
 $('#port-name-context').textContent=`${device.name} · ${interfaceLabels[family]||'Interface'} · ${port}`;
 $('#port-display-name').value=reading.custom_name||'';
 $('#port-original-description').textContent=reading.description||'Sem descrição informada pelo equipamento.';
 $('#port-name-error').hidden=true;$('#port-name-dialog').showModal();$('#port-display-name').focus();
}
document.querySelectorAll('.close-port-name').forEach(el=>el.addEventListener('click',()=>$('#port-name-dialog').close()));
$('#port-name-form').addEventListener('submit',async event=>{
 event.preventDefault();const target=state.portNaming;if(!target)return;
 $('#save-port-name').disabled=true;$('#port-name-error').hidden=true;
 try{
  const updated=await api(`/api/devices/${target.deviceId}/port-name`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({port:target.port,interface_type:target.family,display_name:$('#port-display-name').value})});
  state.data.devices=state.data.devices.map(d=>d.id===updated.id?updated:d);
  document.querySelectorAll('[data-port-alias]').forEach(button=>{if(Number(button.dataset.portAlias)===updated.id&&button.dataset.port===target.port&&button.dataset.family===target.family){const port=updated.port_data.find(p=>p.name===target.port&&(p.interface_type||updated.interface_type||'auto')===target.family);if(port)button.closest('.port-title-row').querySelector('.port-display-name').textContent=port.display_name||port.description||'Nomear porta';}});
  $('#port-name-dialog').close();state.portNaming=null;render();toast('Nome da porta salvo.');
 }catch(error){$('#port-name-error').textContent=error.message;$('#port-name-error').hidden=false;}
 finally{$('#save-port-name').disabled=false;}
});
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
 document.querySelectorAll('.port-card details[open], .port-ping details[open], .ssh-diagnostic[open]').forEach(e=>e.open=false);
 window.getSelection()?.removeAllRanges();render();
});
document.addEventListener('toggle',event=>{
 if(event.target.matches('.port-card details, .port-ping details, .ssh-diagnostic'))render();
},true);
document.addEventListener('selectionchange',()=>{
 const selected=Boolean(window.getSelection()?.toString());
 if(selected)$('#reading-banner').hidden=false;
 else if(!$('#reading-banner').hidden&&!readingOutput())render();
});
$('#confirm-remove').addEventListener('click',async()=>{$('#confirm-remove').disabled=true;try{await api(state.removingCircuit?`/api/circuits/${state.removingCircuit}`:`/api/devices/${state.deleting}`,{method:'DELETE'});$('#confirm-dialog').close();toast(state.removingCircuit?'Circuito removido.':'Equipamento removido.');state.removingCircuit=null;state.deleting=null;await load();}catch(e){toast(e.message);}finally{$('#confirm-remove').disabled=false;}});
for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
if(designPreview){
 const names={balanced:'1 · Equilibrado',compact:'2 · Compacto',list:'3 · Em lista'};
 $('#demo-banner strong').textContent=`Prévia de visual: ${names[designPreview]}`;
 $('#demo-banner div>span').textContent='Dados de demonstração · compare os tamanhos dos cartões, das letras e dos valores.';
 $('#exit-demo').hidden=true;$('#demo-toggle').hidden=true;$('#add-device').hidden=true;
 navigate('datacoms');
}
hydrateIcons();load();setInterval(load,1000);
