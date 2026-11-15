/* A fresh successful OSPF query is required for every protocol-state indication. */
(function(root){
 function reading(monitor,peer,devices,at=Date.now(),connected=true){
  const device=devices.find(d=>d.host===monitor.source_host&&d.kind==='datacom'),snapshot=device?.ospf;
  const checked=Number(snapshot?.checked_at)*1000,age=at-checked;
  if(!connected)return {status:'unknown',label:'Sem conexão com o monitor'};
  if(!device)return {status:'unknown',label:'Escritório Tefé não cadastrado'};
  if(!snapshot||snapshot.status==='pending')return {status:'unknown',label:'Aguardando coleta'};
  if(!Number.isFinite(checked)||age>90000||age< -5000||snapshot.status==='stale')return {status:'unknown',label:'Leitura desatualizada'};
  if(snapshot.error||snapshot.status!=='ok')return {status:'unknown',label:snapshot.error||'Erro de coleta OSPF'};
  const rows=(snapshot.peers||[]).filter(p=>p.router_id===peer.router_id&&p.address===peer.address);
  if(rows.length!==1)return {status:'unknown',label:'Vizinho sem leitura'};
  const row=rows[0],valid=['full','down','attempt','init','2way','exstart','exchange','loading','missing'];
  if(!valid.includes(row.state))return {status:'unknown',label:'Estado OSPF não reconhecido'};
  return {status:row.state==='full'?'up':'down',label:row.state==='missing'?'Vizinho ausente':row.state.toUpperCase(),interface:row.interface||'',checked_at:checked};
 }
 const api={reading};if(typeof module==='object'&&module.exports)module.exports=api;else root.ospfState=api;
})(globalThis);
