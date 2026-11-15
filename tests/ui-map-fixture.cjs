/* Dense, synthetic traffic exercises the overlaps visible in the user's screenshots. */
const fixture=structuredClone(require('./ui-fixture.cjs')),now=new Date().toISOString();
for(const d of fixture.data.devices.filter(d=>d.kind==='datacom')){d.port_data=[];d.ports=[];}
let index=0;
for(const link of fixture.config.links)for(const side of ['a','b']){
 const port=link['port_'+side];if(!port)continue;
 const node=fixture.config.nodes.find(n=>n.id===link[side]),device=fixture.data.devices.find(d=>d.host===node.host),name=port.match(/\d+\/\d+\/\d+/)[0];
 const family=/^(XGE|ten-)/i.test(port)?'ten-gigabit-ethernet':'gigabit-ethernet';
 if(device.port_data.some(p=>p.name===name&&p.interface_type===family))continue;
 const rate=[0,198.72,11100,38590,101100000,885410000,1500000000,9876543210][index++%8];
 device.port_data.push({name,identity:family+':'+name,interface_type:family,state:index%13===0?'down':'up',rx_bps:rate,tx_bps:rate/4,rx:-24.8+(index%5),tx:-3.1,checked_at:now,description:'Porta de teste'});device.ports.push(name);
}
for(const link of fixture.config.radio_links)for(const side of ['a','b']){
 const endpoint=link[side];if(fixture.data.devices.some(d=>d.host===endpoint.host))continue;
 fixture.data.devices.push({id:1000+index++,name:endpoint.name,host:endpoint.host,kind:'siae',state:'online',latency:199,failures:0,interval:5,last_check:now,ping_timeout:4,siae_enabled:false,siae_interfaces:[3],siae_consumption:{},port_data:[],ports:[],circuits:[],city:'',radio_route:link.route,radio_network:link.network});
}
module.exports=fixture;
