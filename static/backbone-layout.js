/* Visual layout only. Host/port bindings remain in backbone.json. */
(function(root){
 const bounds={all:'0 0 1920 900',backbone:'0 0 1920 690','tefe-tabatinga':'0 680 1920 220'};
 const groups=[
  {id:'coari-1',route:'coari-tefe',network:1,title:'Rede 1',y:465,start:120,end:1824},
  {id:'coari-2',route:'coari-tefe',network:2,title:'Rede 2',y:575,start:120,end:1824},
  {id:'tefe-tabatinga',route:'tefe-tabatinga',network:null,title:'Tefé → Tabatinga',y:790,start:1824,end:120}
 ];
 const linksFor=(config,group)=>(config.radio_links||[]).filter(l=>l.route===group.route&&l.network===group.network).sort((a,b)=>a.order-b.order);
 function geometry(link){const group=groups.find(g=>g.route===link.route&&g.network===link.network),count=link.route==='tefe-tabatinga'?15:4,step=(group.end-group.start)/count;return {y:group.y,x1:group.start+(link.order-1)*step,x2:group.start+link.order*step};}
 function sites(config){return groups.flatMap(group=>{const links=linksFor(config,group);if(!links.length)return [];return Array.from({length:links.length+1},(_,i)=>({id:`radio-site-${group.id}-${i}`,name:i?links[i-1].b.site:links[0].a.site,x:group.start+(group.end-group.start)*i/links.length,y:group.y,group,refs:[...(i?[{link:links[i-1],side:'b'}]:[]),...(i<links.length?[{link:links[i],side:'a'}]:[])]}));});}
 function shortName(name){return {'Guariba / N. Progresso':'Guariba','Belém do Solimões':'Belém','Santo Antônio':'Sto. Antônio'}[name]||name;}
 const api={bounds,groups,linksFor,geometry,sites,shortName};if(typeof module==='object'&&module.exports)module.exports=api;else root.backboneLayout=api;
})(globalThis);
