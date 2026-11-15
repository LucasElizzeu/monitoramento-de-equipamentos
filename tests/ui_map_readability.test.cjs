/* Run: node tests/ui_map_readability.test.cjs (requires Playwright and Chromium).
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
 await page.addInitScript(()=>localStorage.setItem('alwaysup-map-display','full'));
 await page.goto(base+'/static/index.html');
 await page.locator('[data-page="backbone"]').click();
 await page.waitForSelector('.backbone-fiber .fiber-caption');
 await page.evaluate(()=>document.fonts.ready);
 assert.equal(await page.locator('#backbone-display').inputValue(),'traffic','Old full-detail preference migrates to the summary view');
 assert.equal(await page.locator('#backbone-display option[value="full"]').count(),0);
 const collisions=()=>page.evaluate(()=>{
  const visible=e=>getComputedStyle(e).display!=='none'&&getComputedStyle(e).visibility!=='hidden';
  const summaries=[...document.querySelectorAll('.fiber-caption')].filter(visible);
  const texts=[...document.querySelectorAll('.fiber-caption,.backbone-node text:not(.node-ip),.radio-site,.radio-caption,.radio-map-heading')].filter(e=>visible(e)&&e.textContent.trim());
  const hits=[];
  for(let i=0;i<texts.length;i++)for(let j=i+1;j<texts.length;j++){
   const a=texts[i].getBoundingClientRect(),b=texts[j].getBoundingClientRect();
   if(a.left<b.right-.5&&a.right>b.left+.5&&a.top<b.bottom-.5&&a.bottom>b.top+.5)hits.push([texts[i].textContent,texts[j].textContent]);
  }
  return {count:summaries.length,hits,rotated:summaries.some(e=>e.getAttribute('transform')?.includes('rotate'))};
 });
 for(const theme of ['light','dark']){
  await page.selectOption('#theme-select',theme);
  for(const width of [1536,1080]){
   await page.setViewportSize({width,height:1000});await page.locator('#backbone-fit').click();
   await page.waitForTimeout(100);
   const result=await collisions();assert.equal(result.count,fixture.config.links.length,'Every fiber has a placed summary');assert.deepEqual(result.hits,[],`No overlapping labels at ${width}/${theme}`);assert(!result.rotated,'All summaries are horizontal');
   if(process.env.UI_SCREENSHOTS)await page.screenshot({path:process.env.UI_SCREENSHOTS+'/'+theme+'-map-'+width+'.png'});
  }
 }
 const target=page.locator('[data-link="manaus-escritorio-infovia-1"]'),label=target.locator('.fiber-caption');
 await label.hover();await page.waitForTimeout(300);assert(await page.locator('#backbone-info').isHidden(),'Hover does not open details');
 await target.focus();assert(await page.locator('#backbone-info').isHidden(),'Focus alone does not open details');
 await page.keyboard.press('Enter');assert(await page.locator('#backbone-info').isVisible(),'Enter opens details');
 assert.equal(await target.getAttribute('aria-expanded'),'true');
 assert((await page.locator('#backbone-info').innerText()).includes('XGE0/0/23'));
 assert((await page.locator('#backbone-info').innerText()).includes('Tráfego RX'));
 assert((await page.locator('#backbone-info').innerText()).includes('Sinal RX'));
 await page.mouse.move(20,20);await page.waitForTimeout(300);assert(await page.locator('#backbone-info').isVisible(),'Panel stays open after leaving the link');
 await page.keyboard.press('Escape');assert(await page.locator('#backbone-info').isHidden());assert.equal(await target.getAttribute('aria-expanded'),'false');
 await label.click();assert(await page.locator('#backbone-info').isVisible(),'Click opens details');
 await page.locator('#backbone-info .backbone-dismiss').click();assert(await page.locator('#backbone-info').isHidden());
 await label.click();await page.locator('.backbone-toolbar').click({position:{x:10,y:10}});assert(await page.locator('#backbone-info').isHidden(),'Click outside closes details');
 await label.click();await label.click();assert(await page.locator('#backbone-info').isHidden(),'Clicking the selected link closes its panel');
 await page.selectOption('#backbone-display','clean');assert(await label.isHidden());
 await page.selectOption('#backbone-display','traffic');assert.deepEqual((await collisions()).hits,[]);
 assert.deepEqual(errors,[]);
 console.log('OK: dense traffic stays readable in both themes at 1536/1080 px; details open only on activation and remain pinned.');
 }finally{await browser.close();if(server)await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
