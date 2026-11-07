/* The radio map reads only the explicitly mapped SIAE endpoints. */
(function(root){
 function endpoint(endpoint,devices,at=Date.now(),connected=true){
  const device=devices.find(d=>d.kind==='siae'&&d.host===endpoint.host);
  const unknown=label=>({device,status:'unknown',label,latency:null,bps:null});
  if(!device)return unknown('Rádio não cadastrado');
  if(!connected)return unknown('Conexão com o monitor interrompida');
  const age=at-Date.parse(device.last_check),limit=Math.max(90,(device.interval||1)*3+(device.ping_timeout||4))*1000;
  if(!Number.isFinite(age)||age>limit||age< -5000)return unknown('Leitura desatualizada');
  if(device.state==='offline')return {device,status:'down',label:'Sem ping',latency:null,bps:null};
  if(!['online','unstable'].includes(device.state)||!Number.isFinite(device.latency))return unknown('Sem resposta de ping atual');
  const status=device.latency>200?'high':'up',band=device.siae_consumption,bandAge=at-Date.parse(band?.checked_at);
  const bps=device.siae_enabled&&band?.status==='online'&&Number.isFinite(bandAge)&&bandAge>=-5000&&bandAge<=90000?band.total_bps:null;
  return {device,status,label:status==='high'?'Ping acima de 200 ms':'Respondendo',latency:device.latency,bps};
 }
 function link(link,devices,at=Date.now(),connected=true){
  const a=endpoint(link.a,devices,at,connected),b=endpoint(link.b,devices,at,connected),states=[a.status,b.status];
  return {a,b,status:states.includes('down')?'down':states.includes('unknown')?'unknown':states.includes('high')?'high':'up'};
 }
 function access(port,radio){
  if(port.port?.state==='down'||radio.status==='down')return 'down';
  if(port.port?.state!=='up'||radio.status==='unknown')return 'unknown';
  return radio.status;
 }
 const api={endpoint,link,access};if(typeof module==='object'&&module.exports)module.exports=api;else root.radioMapState=api;
})(globalThis);
