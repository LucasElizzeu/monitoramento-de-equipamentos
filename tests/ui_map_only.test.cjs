/* Run: node tests/ui_map_only.test.cjs (requires Playwright and Chromium).
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
 let releaseMap,beginMap,backboneRequests=0;
 const gate=new Promise(resolve=>releaseMap=resolve),pending=new Promise(resolve=>beginMap=resolve);
 await page.route('**/api/**',async route=>{const u=new URL(route.request().url());if(u.pathname==='/api/backbone'&&++backboneRequests===2){beginMap();await gate;}let body=u.pathname==='/api/backbone'?fixture.config:u.pathname==='/api/dashboard'?fixture.data:u.pathname.endsWith('/history')?[]:{};return route.fulfill({json:body});});
 try{
 await page.goto(base+'/static/index.html');
 await page.locator('[data-page="datacoms"]').click();
 await page.locator('[data-page="backbone"]').click();await pending;
 await page.keyboard.press('Escape');assert.equal(await page.locator('body').getAttribute('data-view'),'datacoms');
 const response=page.waitForResponse(r=>r.url().includes('/api/backbone'));releaseMap();await response;await page.waitForTimeout(100);
 await page.locator('[data-page="backbone"]').click();await page.waitForSelector('.backbone-node');
 for(const size of [{width:1536,height:900},{width:390,height:844}]){
  await page.setViewportSize(size);await page.waitForTimeout(100);
  for(const selector of ['.sidebar','.topbar','.backbone-toolbar'])assert(await page.locator(selector).isHidden(),selector+' is hidden on the map screen');
  assert(await page.locator('#backbone-ospf').isVisible(),'Only OSPF indicators return below the map');
  for(const selector of ['.backbone-legend','#backbone-summary','.backbone-help'])assert(await page.locator(selector).isHidden(),selector+' remains hidden');
  assert.equal(await page.locator('#backbone-ospf .ospf-legend-item').count(),3);
  for(const city of ['Manaus','Coari','Tabatinga'])assert((await page.locator('#backbone-ospf').innerText()).includes(city));
  const box=await page.locator('.backbone-scroll').boundingBox();assert(Math.abs(box.x)<1&&Math.abs(box.y)<1,'Canvas starts at the viewport origin: '+JSON.stringify(box));
  const footer=await page.locator('.backbone-footer').boundingBox();
  assert(Math.abs(box.width-size.width)<1&&Math.abs(box.height+footer.height-size.height)<1,'Map and compact OSPF row fill the viewport');
  assert(footer.y>=box.y+box.height-1,'OSPF remains below the canvas');
  assert(await page.locator('#backbone-context-menu').isHidden(),'No menu overlays the map by default');
 }
 await page.setViewportSize({width:1536,height:900});
 const map=page.locator('#backbone-map'),width=(await map.boundingBox()).width;
 await page.locator('.backbone-scroll').hover({position:{x:600,y:250}});await page.mouse.wheel(0,-240);await page.waitForTimeout(100);assert((await map.boundingBox()).width>width,'Wheel zoom still works');
 const menu=page.locator('#backbone-context-menu');
 const openMenu=()=>page.locator('.backbone-scroll').click({button:'right',position:{x:600,y:250}});
 await openMenu();assert(await menu.isVisible());await page.keyboard.press('Escape');assert(await menu.isHidden());assert.equal(await page.locator('body').getAttribute('data-view'),'backbone');
 await openMenu();await page.locator('[data-map-action="fit"]').click();assert(await menu.isHidden());
 const theme=await page.locator('html').getAttribute('data-theme');await openMenu();await page.locator('[data-map-action="theme"]').click();assert.notEqual(await page.locator('html').getAttribute('data-theme'),theme);
 await openMenu();await page.locator('[data-map-action="readings"]').click();assert.equal(await map.getAttribute('data-display'),'clean');
 await openMenu();await page.locator('[data-map-action="readings"]').click();assert.equal(await map.getAttribute('data-display'),'traffic');
 const target=page.locator('[data-link="manaus-escritorio-infovia-1"]');await target.focus();await page.keyboard.press('Enter');assert(await page.locator('#backbone-info').isVisible());
 await page.keyboard.press('Escape');assert(await page.locator('#backbone-info').isHidden());assert.equal(await page.locator('body').getAttribute('data-view'),'backbone','Escape closes details before leaving the map');
 await page.keyboard.press('Escape');assert.equal(await page.locator('body').getAttribute('data-view'),'datacoms','Escape returns to the previous screen');assert(await page.locator('.topbar').isVisible());assert(await page.locator('.sidebar').isVisible());
 await page.locator('[data-page="backbone"]').click();await openMenu();await page.locator('[data-map-action="back"]').click();assert.equal(await page.locator('body').getAttribute('data-view'),'datacoms');
 await page.locator('[data-page="backbone"]').click();await page.setViewportSize({width:390,height:844});
 await page.locator('.backbone-scroll').dispatchEvent('pointerdown',{pointerId:55,pointerType:'touch',button:0,clientX:80,clientY:180});
 await menu.waitFor({state:'visible'});
 await page.locator('.backbone-scroll').dispatchEvent('pointerup',{pointerId:55,pointerType:'touch',button:0,clientX:80,clientY:180});
 await page.locator('[data-map-action="back"]').click();assert.equal(await page.locator('body').getAttribute('data-view'),'datacoms','Long press opens a way back on touch devices');
 assert.deepEqual(errors,[]);
 console.log('OK: map and OSPF-only row fill desktop/mobile viewport, supports wheel/click, and restores navigation with Escape or the context menu.');
 }finally{await browser.close();if(server)await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
