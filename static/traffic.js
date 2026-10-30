const trafficView={catalog:[],rendered:[],device:'all',port:'all',desired:null,page:0,revision:0,demo:false,loading:false,controller:null,start:0};
const trafficPageSize=6;
const trafficMoment=at=>new Date(at).toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});
const trafficTime=at=>new Date(at).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});

function trafficOptions(){
 const devices=new Map(trafficView.catalog.map(item=>[String(item.device_id),item.device_name]));
 if(trafficView.demo===state.data.demo)state.data.devices.filter(d=>d.kind==='datacom').forEach(d=>{if(!devices.has(String(d.id)))devices.set(String(d.id),d.name);});
 if(trafficView.device!=='all'&&!devices.has(trafficView.device))devices.set(trafficView.device,'Datacom selecionado');
 $('#traffic-device').innerHTML='<option value="all">Todos os Datacoms</option>'+[...devices].map(([id,name])=>`<option value="${esc(id)}">${esc(name)}</option>`).join('');
 $('#traffic-device').value=trafficView.device;
 const ports=trafficView.catalog.filter(item=>trafficView.device==='all'||String(item.device_id)===trafficView.device);
 if(trafficView.desired){
  const target=ports.find(item=>item.identity===trafficView.desired&&String(item.device_id)===trafficView.device);
  trafficView.port=target?String(target.id):'missing';
 }
 $('#traffic-port').innerHTML='<option value="all">Todas as portas</option>'+ports.map(item=>`<option value="${item.id}">${esc(item.display_name)} · ${esc(shortPortLabel(item.identity))}</option>`).join('')+(trafficView.port==='missing'?'<option value="missing">Porta selecionada · aguardando histórico</option>':'');
 if(!['all','missing'].includes(trafficView.port)&&!ports.some(item=>String(item.id)===trafficView.port))trafficView.port='all';
 $('#traffic-port').value=trafficView.port;
}

function filteredTraffic(){
 const search=$('#traffic-search').value.trim().toLowerCase(),includeZero=$('#traffic-include-zero').checked;
 return trafficView.catalog.filter(item=>(trafficView.device==='all'||String(item.device_id)===trafficView.device)
  &&(trafficView.port==='all'||String(item.id)===trafficView.port)
  &&(includeZero||item.last_positive_at>=trafficView.start)
  &&`${item.display_name} ${item.port} ${item.device_name} ${interfaceLabels[item.interface_type]||''}`.toLowerCase().includes(search));
}

function renderTrafficPlot(container,data,metadata){
 const points=data.points||[],valid=points.filter(point=>point[1]!=null);
 if(!valid.length){container.innerHTML='<div class="traffic-chart-empty">Aguardando leituras válidas para esta porta.</div>';return;}
 const w=Math.max(180,container.clientWidth),h=210,left=52,right=12,top=20,bottom=30;
 const peak=valid.reduce((max,p)=>Math.max(max,p[1]),1),[scale,unit]=peak>=1e9?[1e9,'Gbps']:peak>=1e6?[1e6,'Mbps']:peak>=1e3?[1e3,'Kbps']:[1,'bps'];
 const rawMax=peak/scale,step=10**Math.floor(Math.log10(rawMax)),maximum=Math.ceil(rawMax/step)*step;
 const x=at=>left+(w-left-right)*(at-data.start)/(data.end-data.start),y=value=>h-bottom-(h-top-bottom)*(value/scale)/maximum;
 const gap=(data.expected_interval||30)*3000;
 let grid=`<text x="${left}" y="11">${unit}</text>`;
 for(let i=0;i<4;i++){
  const value=maximum*i/3,py=y(value*scale);
  grid+=`<line class="traffic-axis" x1="${left}" x2="${w-right}" y1="${py}" y2="${py}"/><text x="${left-7}" y="${py+3}" text-anchor="end">${number(value,2)}</text>`;
 }
 const ticks=w<390?3:5;
 for(let i=0;i<ticks;i++){
  const at=data.start+(data.end-data.start)*i/(ticks-1);
  grid+=`<text x="${x(at)}" y="${h-8}" text-anchor="${i===0?'start':i===ticks-1?'end':'middle'}">${esc(trafficTime(at))}</text>`;
 }
 const runs=[];let run=[];let previous=null;
 for(const point of points){
  if(point[1]==null||(previous!=null&&point[0]-previous>gap)){if(run.length)runs.push(run);run=[];}
  if(point[1]!=null)run.push(point);
  previous=point[0];
 }
 if(run.length)runs.push(run);
 const lines=runs.map(segment=>segment.length===1?`<circle class="traffic-dot" cx="${x(segment[0][0])}" cy="${y(segment[0][1])}" r="2.5"/>`:`<path class="traffic-line" d="${segment.map((p,i)=>(i?'L':'M')+x(p[0]).toFixed(2)+','+y(p[1]).toFixed(2)).join(' ')}"/>`).join('');
 container.innerHTML=`<svg viewBox="0 0 ${w} ${h}" role="img" tabindex="0" aria-label="Consumo RX de ${esc(metadata.display_name)} nas últimas 24 horas. Use as setas para percorrer as leituras.">${grid}${lines}<g class="traffic-crosshair" hidden><line class="traffic-cursor" y1="${top}" y2="${h-bottom}"/><circle class="traffic-cursor-dot" r="4"/></g></svg><div class="traffic-tooltip" hidden></div>`;
 const svg=container.querySelector('svg'),cursor=container.querySelector('.traffic-crosshair'),dot=cursor.querySelector('circle'),line=cursor.querySelector('line'),tooltip=container.querySelector('.traffic-tooltip');
 let keyboardIndex=points.length;
 function show(point,at){
  const value=point?.[1],px=Math.min(w-right,Math.max(left,x(at)));
  cursor.removeAttribute('hidden');line.setAttribute('x1',px);line.setAttribute('x2',px);
  dot.setAttribute('cx',px);if(value!=null){dot.removeAttribute('hidden');dot.setAttribute('cy',y(value));}else dot.setAttribute('hidden','');
  tooltip.hidden=false;tooltip.innerHTML=`${esc(trafficMoment(at))}<strong>${value!=null?bandwidth(value):'Sem leitura neste horário'}</strong>`;
  tooltip.style.left=`${Math.max(0,Math.min(w-tooltip.offsetWidth,px+10))}px`;
 }
 function pointAt(at){
  let low=0,high=points.length;
  while(low<high){const mid=(low+high)>>1;if(points[mid][0]<at)low=mid+1;else high=mid;}
  const a=points[Math.max(0,low-1)],b=points[Math.min(points.length-1,low)];
  const nearest=Math.abs(a[0]-at)<Math.abs(b[0]-at)?a:b;
  return Math.abs(nearest[0]-at)<=gap?nearest:null;
 }
 function pointer(event){const rect=svg.getBoundingClientRect(),px=Math.min(w-right,Math.max(left,(event.clientX-rect.left)*w/rect.width));const at=data.start+(px-left)/(w-left-right)*(data.end-data.start),point=pointAt(at);show(point,point?point[0]:at);}
 svg.addEventListener('pointermove',pointer);svg.addEventListener('pointerdown',pointer);
 svg.addEventListener('pointerleave',event=>{if(event.pointerType!=='touch'){cursor.setAttribute('hidden','');tooltip.hidden=true;}});
 svg.addEventListener('blur',()=>{cursor.setAttribute('hidden','');tooltip.hidden=true;});
 svg.addEventListener('keydown',event=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  event.preventDefault();keyboardIndex=event.key==='Home'?0:event.key==='End'?points.length-1:Math.max(0,Math.min(points.length-1,keyboardIndex+(event.key==='ArrowLeft'?-1:1)));
  const point=points[keyboardIndex];show(point,point[0]);svg.setAttribute('aria-label',`${metadata.display_name} · ${trafficMoment(point[0])} · ${point[1]!=null?number(point[1],2)+' bits por segundo':'sem leitura'}`);
 });
}

function trafficCardHTML(metadata,data){
 const stats=data.stats;
 return `<h3>${esc(metadata.display_name)}</h3><p class="traffic-chart-context">${esc(metadata.device_name)} · ${esc(metadata.host)}<br>${esc(interfaceLabels[metadata.interface_type]||'Interface')} · ${esc(metadata.port)}</p><div class="traffic-chart-stats"><span>Última leitura<strong>${bandwidth(stats.last_bps)}</strong></span><span>Média das leituras<strong>${bandwidth(stats.mean_bps)}</strong></span><span>Pico em 24h<strong>${bandwidth(stats.peak_bps)}</strong></span></div><div class="traffic-plot"></div><div class="traffic-chart-foot"><span>${stats.count} leituras válidas · RX</span><span class="${!metadata.active||stats.last_bps==null?'traffic-stale':''}">${!metadata.active||stats.last_bps==null?'Sem leitura atual':stats.last_at?trafficMoment(stats.last_at):'Aguardando'}</span></div>`;
}

async function refreshTraffic(catalog=true){
 const revision=++trafficView.revision;
 trafficView.controller?.abort();const controller=new AbortController();trafficView.controller=controller;
 trafficView.loading=true;$('#refresh-traffic').disabled=true;$('#traffic-error').hidden=true;
 try{
  if(catalog){
   const result=await api(`/api/traffic/ports?include_zero=true&demo=${trafficView.demo}`,{signal:controller.signal});
   if(revision!==trafficView.revision||!$('#traffic-dialog').open)return;
   trafficView.catalog=result.series;trafficView.start=result.start;
   $('#traffic-period').textContent=`${trafficView.demo?'Demonstração · ':''}${trafficMoment(result.start)} — ${trafficMoment(result.end)} · atualização a cada 30s`;
  }
  trafficOptions();
  const filtered=filteredTraffic(),pages=Math.max(1,Math.ceil(filtered.length/trafficPageSize));
  trafficView.page=Math.min(trafficView.page,pages-1);
  const selected=filtered.slice(trafficView.page*trafficPageSize,(trafficView.page+1)*trafficPageSize);
  trafficView.rendered=[];
  $('#traffic-summary').textContent=filtered.length?`${trafficView.page*trafficPageSize+1}–${trafficView.page*trafficPageSize+selected.length} de ${filtered.length} portas · página ${trafficView.page+1}/${pages}`:'Nenhuma porta com histórico neste filtro';
  $('#traffic-prev').disabled=trafficView.page===0;$('#traffic-next').disabled=trafficView.page>=pages-1;
  $('#traffic-charts').innerHTML=selected.length?selected.map(item=>`<article class="traffic-chart-card" data-traffic-chart="${item.id}"><h3>${esc(item.display_name)}</h3><p class="traffic-chart-context">Carregando histórico…</p></article>`).join(''):`<p class="traffic-empty">${trafficView.port==='missing'?'O histórico desta porta começará após a próxima coleta válida de banda.':'Nenhuma porta com tráfego neste filtro. O histórico é formado conforme as leituras são coletadas. Você também pode incluir portas com consumo zero.'}</p>`;
  const results=await Promise.allSettled(selected.map(async metadata=>{
   const data=await api(`/api/traffic/ports/${metadata.id}?demo=${trafficView.demo}`,{signal:controller.signal});
   if(revision!==trafficView.revision||!$('#traffic-dialog').open)return;
   const node=$(`[data-traffic-chart="${metadata.id}"]`);if(!node)return;
   node.innerHTML=trafficCardHTML(metadata,data);const plot=node.querySelector('.traffic-plot');
   trafficView.rendered.push({plot,data,metadata});renderTrafficPlot(plot,data,metadata);
  }));
  if(revision!==trafficView.revision)return;
  results.forEach((result,index)=>{if(result.status==='rejected'&&!controller.signal.aborted){const node=$(`[data-traffic-chart="${selected[index].id}"]`);if(node)node.innerHTML=`<h3>${esc(selected[index].display_name)}</h3><p class="traffic-empty">${esc(result.reason.message)}</p>`;}});
 }catch(error){if(!controller.signal.aborted&&revision===trafficView.revision){$('#traffic-error').textContent=error.message;$('#traffic-error').hidden=false;}}
 finally{if(revision===trafficView.revision){trafficView.loading=false;$('#refresh-traffic').disabled=false;}}
}

function openTraffic(device=null,identity=null){
 trafficView.demo=state.demo;trafficView.device=device==null?'all':String(device);trafficView.port='all';trafficView.desired=identity;trafficView.page=0;
 trafficView.catalog=[];trafficView.rendered=[];trafficOptions();
 $('#traffic-charts').innerHTML='<p class="traffic-empty">Carregando histórico das portas…</p>';$('#traffic-summary').textContent='';
 $('#traffic-search').value='';$('#traffic-include-zero').checked=identity!=null;
 if(!$('#traffic-dialog').open)$('#traffic-dialog').showModal();refreshTraffic();
}
$('#open-traffic-dashboard').addEventListener('click',()=>openTraffic());
document.addEventListener('click',event=>{const button=event.target.closest('[data-traffic-device]');if(button)openTraffic(Number(button.dataset.trafficDevice),button.dataset.trafficIdentity);});
$('#close-traffic').addEventListener('click',()=>$('#traffic-dialog').close());
$('#traffic-dialog').addEventListener('close',()=>{trafficView.revision++;trafficView.controller?.abort();trafficView.loading=false;trafficView.rendered=[];});
$('#traffic-device').addEventListener('change',()=>{trafficView.device=$('#traffic-device').value;trafficView.port='all';trafficView.desired=null;trafficView.page=0;refreshTraffic(false);});
$('#traffic-port').addEventListener('change',()=>{trafficView.port=$('#traffic-port').value;trafficView.desired=null;trafficView.page=0;refreshTraffic(false);});
$('#traffic-include-zero').addEventListener('change',()=>{trafficView.page=0;refreshTraffic(false);});
let trafficSearchTimer;
$('#traffic-search').addEventListener('input',()=>{clearTimeout(trafficSearchTimer);trafficSearchTimer=setTimeout(()=>{trafficView.page=0;refreshTraffic(false);},200);});
$('#refresh-traffic').addEventListener('click',()=>refreshTraffic());
$('#traffic-prev').addEventListener('click',()=>{trafficView.page=Math.max(0,trafficView.page-1);refreshTraffic(false);});
$('#traffic-next').addEventListener('click',()=>{trafficView.page++;refreshTraffic(false);});
setInterval(()=>{if($('#traffic-dialog').open&&!trafficView.loading&&!window.getSelection()?.toString()&&!document.activeElement?.matches('input,select'))refreshTraffic();},30000);
let trafficResizeFrame;
window.addEventListener('resize',()=>{cancelAnimationFrame(trafficResizeFrame);trafficResizeFrame=requestAnimationFrame(()=>{if($('#traffic-dialog').open)trafficView.rendered.forEach(({plot,data,metadata})=>{if(plot.isConnected)renderTrafficPlot(plot,data,metadata);});});});
