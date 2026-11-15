const assert=require('node:assert/strict'),{place,overlaps,contains}=require('../static/map-labels.js');
const bounds={x:0,y:0,width:800,height:300},obstacles=[{x:350,y:140,width:100,height:40}];
const labels=Array.from({length:14},(_,i)=>({id:String(i),x:70+(i%7)*105,y:100+Math.floor(i/7)*90,width:100,height:24}));
const points=Array.from({length:120},(_,i)=>({x:i*7,y:150}));
const result=place(labels,obstacles,points,bounds);
assert.equal(result.size,labels.length);
for(const [id,box] of result){assert(contains(bounds,box));assert(!obstacles.some(o=>overlaps(box,o)));assert(!points.some(p=>p.x>=box.x-3&&p.x<=box.x+box.width+3&&p.y>=box.y-3&&p.y<=box.y+box.height+3));for(const [otherId,other]of result)if(id!==otherId)assert(!overlaps(box,other));}
assert.deepEqual(place(labels,obstacles,points,bounds,result),result,'Stable placement when telemetry width stays in its slot');
assert.equal(place([{id:'wide',x:0,y:0,width:1000,height:50}],[],[],bounds).size,0,'Unplaceable summaries never overlap');
console.log('OK: summaries avoid node labels, other summaries and fiber paths; positions stay stable across updates.');
