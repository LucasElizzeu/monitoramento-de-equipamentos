/* Reserve space for summaries; never change the equipment or port bindings. */
(function(root){
 const overlaps=(a,b,gap=4)=>a.x<b.x+b.width+gap&&a.x+a.width+gap>b.x&&a.y<b.y+b.height+gap&&a.y+a.height+gap>b.y;
 const contains=(bounds,box)=>box.x>=bounds.x&&box.y>=bounds.y&&box.x+box.width<=bounds.x+bounds.width&&box.y+box.height<=bounds.y+bounds.height;
 function place(labels,obstacles,points,bounds,previous=new Map()){
  const occupied=[...obstacles],placed=new Map();
  const legal=box=>contains(bounds,box)&&!occupied.some(o=>overlaps(box,o))&&!points.some(p=>p.x>=box.x-3&&p.x<=box.x+box.width+3&&p.y>=box.y-3&&p.y<=box.y+box.height+3);
  for(const label of labels){
   const w=label.width,h=label.height,preferred={x:label.x-w/2,y:label.y,width:w,height:h};
   const old=previous.get(label.id);let box=old&&old.width===w&&old.height===h&&legal(old)?old:null;
   if(!box){
    const candidates=[];
    for(let dy=-160;dy<=160;dy+=16)for(let dx=-192;dx<=192;dx+=24)candidates.push({...preferred,x:preferred.x+dx,y:preferred.y+dy,cost:dx*dx*1.5+dy*dy});
    candidates.sort((a,b)=>a.cost-b.cost||a.y-b.y||a.x-b.x);
    box=candidates.find(legal);
   }
   if(!box){
    const candidates=[];
    for(let y=bounds.y;y+h<=bounds.y+bounds.height;y+=16)for(let x=bounds.x;x+w<=bounds.x+bounds.width;x+=24)candidates.push({x,y,width:w,height:h,cost:(x-preferred.x)**2*1.5+(y-preferred.y)**2});
    candidates.sort((a,b)=>a.cost-b.cost);box=candidates.find(legal);
   }
   if(box){const result={x:box.x,y:box.y,width:w,height:h};placed.set(label.id,result);occupied.push(result);}
  }
  return placed;
 }
 const api={place,overlaps,contains};if(typeof module==='object'&&module.exports)module.exports=api;else root.mapLabels=api;
})(globalThis);
