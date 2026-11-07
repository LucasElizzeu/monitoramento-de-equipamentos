/* Approved compact overview. All values come from current monitoring data. */
(() => {
 const workspace=$('#overview-workspace'),table=$('#devices-section'),aside=$('#overview-charts');
 const originalHead=table.querySelector('thead').innerHTML,locations=new Map();
 const latencyTypes=document.createElement('div');latencyTypes.className='overview-latency-types';latencyTypes.setAttribute('role','group');latencyTypes.setAttribute('aria-label','Tipo para a latência média');
 latencyTypes.innerHTML=[['ping','BBU'],['siae','Rádio SIAE'],['datacom','Datacom']].map(([kind,label])=>`<button type="button" data-latency-type="${kind}" aria-pressed="false">${label}</button>`).join('');
 $('.chart-panel .panel-heading').append(latencyTypes);
 const syncLatencyTypes=()=>latencyTypes.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.latencyType===$('#latency-kind').value)));
 $('#latency-kind').addEventListener('change',syncLatencyTypes);
 latencyTypes.addEventListener('click',e=>{const button=e.target.closest('[data-latency-type]');if(button){$('#latency-kind').value=button.dataset.latencyType;$('#latency-kind').dispatchEvent(new Event('change'));}});
 syncLatencyTypes();
 let sortKey=null,ascending=true;
 const columns=[['name','Nome'],['location','Localidade'],['state','Estado'],['latency','Latência'],['ports','Portas']];
 function location(d){return locations.get(d.host)||'—';}
 function portSummary(d){const ports=d.ssh_error?[]:(d.port_data||[]);return ports.length?{up:ports.filter(p=>p.state==='up').length,total:ports.length}:null;}
 function issue(d){
  if(d.state==='offline')return {text:'Sem resposta',tone:'critical',rank:0};
  if(d.ssh_error||d.state==='error'||d.siae_consumption?.status==='error')return {text:'Coleta indisponível',tone:'warning',rank:1};
  if(d.state==='unstable')return {text:'Perda de pacotes',tone:'warning',rank:2};
  const down=(d.port_data||[]).filter(p=>p.state==='down').length;
  if(down)return {text:`${down} ${down===1?'porta inativa':'portas inativas'}`,tone:'warning',rank:3};
  if((d.circuits||[]).some(c=>['offline','error','unstable'].includes(c.state)))return {text:'Circuito com alerta',tone:'warning',rank:4};
  return null;
 }
 function tableState(d){return d.state==='offline'?badge('offline','Sem resposta'):issue(d)?badge('unstable','Atenção'):badge(d.state);}
 function sortValue(d){return sortKey==='location'?location(d):sortKey==='ports'?portSummary(d)?.up??null:d[sortKey];}
 function orderedRows(){
  const rows=filteredDevices();
  if(!sortKey)return rows;
  return rows.sort((a,b)=>{const x=sortValue(a),y=sortValue(b);if(x==null)return y==null?a.id-b.id:1;if(y==null)return -1;return (typeof x==='number'?x-y:String(x).localeCompare(String(y),'pt-BR',{numeric:true}))*(ascending?1:-1)||a.id-b.id;});
 }
 window.setupOverview=page=>{
  workspace.hidden=page!=='overview';
  if(page==='overview'){workspace.append(table,aside);}
  else{$('#devices-home').after(table);table.querySelector('thead').innerHTML=originalHead;$('.status-strip .live-dot').innerHTML='';$('#network-status').removeAttribute('title');}
 };
 window.renderOverview=()=>{
  if(state.page!=='overview')return;
  const devices=state.data.devices,problems=devices.map(d=>({d,problem:issue(d)})).filter(x=>x.problem).sort((a,b)=>a.problem.rank-b.problem.rank||a.d.id-b.d.id);
  const focused=document.activeElement?.dataset.metric;
  const metrics=[['all',devices.length,'Equipamentos',''],['online',devices.filter(d=>d.state==='online').length,'Online','green'],['offline',devices.filter(d=>d.state==='offline').length,'Sem resposta','red'],['down-ports',collectedPorts(devices).filter(p=>p.port.state==='down').length,'Portas inativas','amber']];
  $('#metrics').innerHTML=metrics.map(([key,count,name,tone])=>`<button type="button" class="overview-metric ${tone}" data-metric="${key}" aria-haspopup="dialog" aria-controls="metric-dialog" aria-label="${count} ${name.toLowerCase()}, ver lista"><strong>${count}</strong><span>${name}</span></button>`).join('');
  if(focused)$(`[data-metric="${focused}"]`)?.focus({preventScroll:true});
  const offline=metrics[2][1],status=$('.status-strip');status.dataset.tone=problems.length?'warning':'success';
  $('#network-status').textContent=offline?`${offline} ${offline===1?'equipamento sem resposta':'equipamentos sem resposta'}`:problems.length?`${problems.length} ${problems.length===1?'equipamento precisa':'equipamentos precisam'} de atenção`:devices.length?'Sua rede está operando normalmente':'Adicione seu primeiro equipamento';
  $('#network-status').title=`${devices.length} equipamentos · ${$('#last-update').textContent}`;
  status.querySelector('.live-dot').innerHTML=icon(problems.length?'warning':'check');
  $('#add-device-label').textContent='Adicionar';
  $('#recent-events').innerHTML=problems.length?problems.slice(0,2).map(({d,problem})=>`<button type="button" class="overview-attention" data-detail="${d.id}" aria-label="Ver detalhes de ${esc(d.name)}: ${esc(problem.text)}"><span class="overview-attention-icon ${problem.tone}">${icon('warning')}</span><span><strong>${esc(d.name)}</strong><small>${esc(problem.text)}</small></span><span class="overview-chevron" aria-hidden="true">›</span></button>`).join(''):'<div class="overview-healthy">'+icon('check')+'<span>Nenhum alerta ativo</span></div>';
  $('#all-events').textContent='Ver todos os eventos →';
  const rows=orderedRows(),selected=document.activeElement?.dataset.overviewSort;
  table.querySelector('thead').innerHTML='<tr>'+columns.map(([key,name])=>`<th scope="col" ${sortKey===key?`aria-sort="${ascending?'ascending':'descending'}"`:''}><button type="button" data-overview-sort="${key}">${name}<span aria-hidden="true">${sortKey===key?(ascending?'↑':'↓'):'↕'}</span></button></th>`).join('')+'<th scope="col"><span class="sr-only">Ações</span></th></tr>';
  if(selected)$(`[data-overview-sort="${selected}"]`)?.focus({preventScroll:true});
  $('#device-rows').innerHTML=rows.length?rows.map(d=>{const ports=portSummary(d);return `<tr class="device-row"><td class="device-name-cell"><button type="button" class="overview-device-name" data-detail="${d.id}">${equipmentIcon(d.kind)}<strong>${esc(d.name)}</strong></button></td><td data-label="Localidade">${esc(location(d))}</td><td data-label="Estado">${tableState(d)}</td><td class="latency" data-label="Latência">${d.latency==null?'—':`${number(d.latency)} <small>ms</small>`}</td><td class="overview-ports" data-label="Portas">${ports?`${ports.up} / ${ports.total}`:'—'}</td><td class="device-actions-cell"><button type="button" class="icon-button overview-more" data-overview-actions="${d.id}" aria-label="Ações de ${esc(d.name)}" aria-haspopup="dialog" aria-controls="overview-actions">···</button></td></tr>`;}).join(''):`<tr><td colspan="6"><div class="overview-table-empty">${devices.length?'Nenhum equipamento neste filtro.':'Adicione um equipamento para começar o monitoramento.'}</div></td></tr>`;
 };
 table.querySelector('thead').addEventListener('click',e=>{const button=e.target.closest('[data-overview-sort]');if(!button)return;ascending=sortKey===button.dataset.overviewSort?!ascending:true;sortKey=button.dataset.overviewSort;window.renderOverview();});
 document.addEventListener('click',e=>{const button=e.target.closest('[data-overview-actions]');if(!button)return;const d=state.data.devices.find(d=>d.id===Number(button.dataset.overviewActions));if(!d)return;$('#overview-actions-title').textContent=d.name;$('#overview-actions-buttons').innerHTML=`<button type="button" class="button secondary" data-detail="${d.id}">${icon('activity')}Ver detalhes</button><button type="button" class="button secondary" data-edit="${d.id}">${icon('edit')}Editar equipamento</button><button type="button" class="button secondary" data-remove="${d.id}">${icon('trash')}Remover equipamento</button>`;$('#overview-actions').showModal();});
 $('#overview-actions-close').onclick=()=>$('#overview-actions').close();
 $('#overview-actions').addEventListener('close',()=>{const id=$('#overview-actions-buttons [data-detail]')?.dataset.detail;if(!document.querySelector('dialog[open]'))$(`[data-overview-actions="${id}"]`)?.focus({preventScroll:true});});
 $('.event-panel h2').textContent='Atenção agora';
 window.setupOverview(state.page);window.renderOverview();
 api('/api/backbone').then(config=>{for(const n of config.nodes)locations.set(n.host,n.id==='manaus2'?'Manaus':['claro','escritorio'].includes(n.id)?'Tefé':n.name);window.renderOverview();}).catch(()=>{/* Unknown locations remain explicitly unavailable. */});
})();
