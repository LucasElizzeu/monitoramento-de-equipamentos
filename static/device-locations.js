/* Explicit city wins; known topology hosts fill older equipment automatically. */
(function(root){
 const key=value=>String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim().replace(/\s+/g,' ').toLowerCase();
 function index(config={}){
  const hosts=new Map();
  for(const n of config.nodes||[])hosts.set(n.host,n.city||(['manaus','manaus2'].includes(n.id)?'Manaus':['claro','escritorio'].includes(n.id)?'Tefé':n.name));
  for(const link of config.radio_links||[])for(const side of ['a','b'])if(link[side]?.site)hosts.set(link[side].host,link[side].site);
  return hosts;
 }
 function city(device,hosts=new Map()){
  const name=String(device.city||hosts.get(device.host)||'').trim().replace(/\s+/g,' ');
  if(!name)return '';
  return [...hosts.values()].find(c=>key(c)===key(name))||name;
 }
 function groups(devices,hosts){
  const grouped=new Map();
  for(const d of devices){const name=city(d,hosts),id=key(name);if(!grouped.has(id))grouped.set(id,{name:name||'Sem cidade',devices:[]});grouped.get(id).devices.push(d);}
  return [...grouped.values()].sort((a,b)=>a.name==='Sem cidade'?1:b.name==='Sem cidade'?-1:a.name.localeCompare(b.name,'pt-BR'));
 }
 const api={key,index,city,groups};if(typeof module==='object'&&module.exports)module.exports=api;else root.deviceLocations=api;
})(globalThis);
