const assert=require('node:assert/strict');
const test=(name,run)=>{run();console.log('OK: '+name);};
const {link,endpoint}=require('../static/radio-map-state.js');
const at=Date.parse('2026-11-07T20:00:00Z'),hop={a:{host:'192.168.20.1'},b:{host:'192.168.30.2'}};
const radio=(host,latency=10,state='online',extra={})=>({host,kind:'siae',state,latency,interval:5,last_check:new Date(at).toISOString(),...extra});
test('both ends and the exact 200 ms boundary determine link colors',()=>{
 const devices=[radio(hop.a.host,200),radio(hop.b.host,200)];assert.equal(link(hop,devices,at).status,'up');
 devices[1].latency=200.01;assert.equal(link(hop,devices,at).status,'high');devices[0].state='offline';assert.equal(link(hop,devices,at).status,'down');
});
test('an unregistered, wrong-type, stale or failed endpoint cannot turn a link blue',()=>{
 const ap=radio(hop.a.host);
 for(const st of [null,radio(hop.b.host,10,'online',{kind:'ping'}),radio(hop.b.host,10,'error'),radio(hop.b.host,10,'online',{last_check:new Date(at-91000).toISOString()}),radio(hop.b.host,10,'online',{last_check:'invalid'}),radio(hop.b.host,10,'online',{last_check:new Date(at+10000).toISOString()})])assert.equal(link(hop,[ap,...(st?[st]:[])],at).status,'unknown');
 assert.equal(link(hop,[ap,radio(hop.b.host)],at,false).status,'unknown');
});
test('one confirmed offline endpoint is sufficient for a red link',()=>{assert.equal(link(hop,[radio(hop.a.host,null,'offline')],at).status,'down');});
test('a cached status cannot override current raw ping readings',()=>{assert.equal(endpoint(hop.a,[radio(hop.a.host,250,'online',{radio_status:'up'})],at).status,'high');});
test('bandwidth is displayed only while fresh and successful, including real zero',()=>{
 const telemetry={status:'online',checked_at:new Date(at).toISOString(),total_bps:0};
 const d=radio(hop.a.host,20,'online',{siae_enabled:true,siae_consumption:telemetry});assert.equal(endpoint(hop.a,[d],at).bps,0);
 d.siae_consumption={...telemetry,status:'error',total_bps:100};assert.equal(endpoint(hop.a,[d],at).bps,null);
 d.siae_consumption={...telemetry,checked_at:new Date(at-91000).toISOString()};assert.equal(endpoint(hop.a,[d],at).bps,null);
});
