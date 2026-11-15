/* Synthetic equipment only; the browser test never contacts the monitored network. */
const config=structuredClone(require('../static/backbone.json'));
const peers=[['10.200.1.1','10.10.1.81','Manaus','manaus-escritorio-infovia-1'],['10.200.9.1','10.10.20.1','Coari','coari-escritorio-infovia-1'],['10.200.30.1','10.10.20.10','Tabatinga',null]].map(([router_id,address,name,link_id])=>({router_id,address,name:'INFOVIA · '+name,link_id}));
config.ospf_monitor={source_host:'10.200.24.1',peers};
const now=new Date().toISOString(),base={kind:'ping',state:'online',failures:0,latency:12,last_check:now,interval:5,ports:[],port_data:[],ssh_error:null,circuits:[],ssh_diagnostic:{},city:'',has_password:false,ping_timeout:4,siae_interfaces:[3]};
const devices=config.nodes.map((n,i)=>({...base,id:i+1,name:n.name,host:n.host,kind:'datacom',circuit_position:i+1,status_command:'show interface link',optics_command:'show interface transceivers',utilization_command:'',interface_type:'auto',ssh_port:22,username:'',fingerprint:''}));
devices.push(...[['BBU Coari','192.0.2.1','Coari'],['BBU Manaus','192.0.2.2','Manaus'],['Sem local','192.0.2.3','']].map(([name,host,city],i)=>({...base,id:100+i,name,host,city})));
devices.push(...[['AP_COARI/BETANIA','192.168.20.1'],['ST_COARI/BETANIA','192.168.30.2'],['AP_TEFE/UARINI','192.168.60.1']].map(([name,host],i)=>({...base,id:200+i,name,host,kind:'siae',radio_route:i<2?'coari-tefe':'tefe-tabatinga',radio_network:i<2?1:null,siae_consumption:{},siae_enabled:false})));
// Exercise actual port badges, down-port warnings and optical/bandwidth labels.
const port=(number,state)=>({name:'1/1/'+number,identity:'ten-gigabit-ethernet:1/1/'+number,interface_type:'ten-gigabit-ethernet',state,rx:state==='up'?-15:-40,tx:-3,rx_bps:state==='up'?120000000:0,tx_bps:0,checked_at:now,description:'Porta de teste'});
const coari=devices.find(d=>d.host==='10.200.9.1');coari.ports=['1/1/7','1/1/8'];coari.port_data=[port(7,'up'),port(8,'down')];
const office=devices.find(d=>d.host===config.ospf_monitor.source_host);office.ospf={status:'ok',checked_at:Date.now()/1000,peers:peers.map((p,i)=>({...p,state:i===1?'init':'full',interface:'Infra-OSPF-INFOVIA'}))};
module.exports={config,data:{devices,alerts:[],samples:[],demo:false,updated_at:now}};
