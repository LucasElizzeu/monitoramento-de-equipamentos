/* Run: node tests/ui_radio_access.test.cjs (requires Playwright and Chromium).
   Uses an ephemeral local static server and synthetic API responses. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const fixture=process.env.UI_FIXTURE?JSON.parse(fs.readFileSync(process.env.UI_FIXTURE,'utf8')):require('./ui-map-fixture.cjs');
 const http=require('node:http'),path=require('node:path');
 let server;
 if(!process.env.UI_BASE_URL){server=http.createServer((req,res)=>{const file=path.join(__dirname,'..',new URL(req.url,'http://local').pathname);fs.readFile(file,(err,data)=>{if(err){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':file.endsWith('.html')?'text/html':'application/octet-stream');res.end(data);});});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));}
 const base=process.env.UI_BASE_URL||'http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',route=>{const u=new URL(route.request().url());let body=u.pathname==='/api/backbone'?fixture.config:u.pathname==='/api/dashboard'?fixture.data:u.pathname.endsWith('/history')?[]:{};return route.fulfill({json:body});});
 try{
 const now=new Date().toISOString(),coari=fixture.data.devices.find(d=>d.host==='10.200.9.1'),claro=fixture.data.devices.find(d=>d.host==='10.200.19.1');
 const configure=(device,family,number,state='up')=>{
  const name='1/1/'+number;let port=device.port_data.find(p=>p.name===name&&p.interface_type===family);
  if(!port){port={name,interface_type:family,identity:family+':'+name,rx_bps:50000000,rx:-15};device.port_data.push(port);}
  Object.assign(port,{state,checked_at:now});return port;
 };
 const ten='ten-gigabit-ethernet',giga='gigabit-ethernet';
 const source1=configure(coari,ten,8),source2=configure(coari,ten,9);
 configure(coari,giga,8,'down'); // Same number on a different interface must not override Ten 8.
 const ports={};for(const n of [5,6,7,8])ports[n]=configure(claro,giga,n);
 for(const link of fixture.config.radio_links.filter(l=>l.route==='coari-tefe'))for(const side of ['a','b']){
  const d=fixture.data.devices.find(d=>d.host===link[side].host);if(d)Object.assign(d,{state:'offline',last_check:now,latency:null});
 }
 await page.goto(base+'/static/index.html');await page.locator('[data-page="backbone"]').click();await page.waitForSelector('.radio-access-port');
 const group=(network,side)=>page.locator(`[data-link="radio-access-${network}-${side}"]`);
 const stroke=(network,side,number)=>group(network,side).locator(`.radio-access-port[data-port="${side==='source'?ten:giga}:1/1/${number}"] .radio-access-stroke`);
 const refresh=()=>page.evaluate(async()=>{await load();});
 const expectStatus=async(network,side,number,status)=>{
  const line=stroke(network,side,number);assert.equal(await line.getAttribute('data-status'),status);
  const legend=status==='up'?'.up':status==='down'?'.down':status==='error'?'.error':null;
  if(legend){const color=await page.locator('.backbone-legend '+legend).evaluate(el=>getComputedStyle(el).color);assert.equal(await line.evaluate(el=>getComputedStyle(el).stroke),color);}
 };
 assert.equal(await group(1,'target').locator('.radio-access-port').count(),2);
 assert.equal(await group(2,'target').locator('.radio-access-port').count(),2);
 await expectStatus(1,'source',8,'up');await expectStatus(2,'source',9,'up');
 for(const n of [7,8])await expectStatus(1,'target',n,'up');for(const n of [5,6])await expectStatus(2,'target',n,'up');
 assert.equal(await page.locator('[data-link="radio-coari-tefe-1-4"]').getAttribute('data-status'),'down','Radio outage is still visible on the hop');
 ports[7].state='down';await refresh();await expectStatus(1,'target',7,'down');await expectStatus(1,'target',8,'up');
 ports[7].state='up';ports[8].checked_at=new Date(Date.now()-100000).toISOString();await refresh();await expectStatus(1,'target',7,'up');await expectStatus(1,'target',8,'unknown');
 ports[8].checked_at=new Date().toISOString();claro.ssh_error='Consulta SSH indisponível';await refresh();for(const n of [7,8])await expectStatus(1,'target',n,'error');
 claro.ssh_error=null;source1.state='down';source2.checked_at=new Date(Date.now()-100000).toISOString();await refresh();await expectStatus(1,'source',8,'down');await expectStatus(2,'source',9,'unknown');
 source1.state='up';source2.checked_at=new Date().toISOString();await refresh();
 for(const theme of ['light','dark']){
  await page.selectOption('#theme-select',theme);
  await expectStatus(1,'source',8,'up');await expectStatus(1,'target',7,'up');
 }
 await group(1,'target').focus();await page.keyboard.press('Enter');
 const detail=await page.locator('#backbone-info').innerText();assert(detail.includes('Giga 1/1/7')&&detail.includes('Giga 1/1/8'));assert(!detail.includes('a confirmar'));
 assert.equal(await page.locator('[data-link="radio-origin-tefe-tabatinga"]').getAttribute('data-status'),'unknown','Unconfirmed Tabatinga origin is not guessed from Giga 5–8');
 assert.deepEqual(errors,[]);
 console.log('OK: Coari Ten 8/9 and CLARO Giga 7/8, 5/6 use independent physical port colors, including stale/SSH failures and both themes.');
 }finally{await browser.close();if(server)await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
