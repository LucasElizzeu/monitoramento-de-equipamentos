/* Run: node tests/ui_preferences.test.cjs (requires Playwright and Chromium).
   Uses an ephemeral local static server and synthetic API responses. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const fixture=process.env.UI_FIXTURE?JSON.parse(fs.readFileSync(process.env.UI_FIXTURE,'utf8')):require('./ui-fixture.cjs');
 const http=require('node:http'),path=require('node:path');
 let server;
 if(!process.env.UI_BASE_URL){server=http.createServer((req,res)=>{const file=path.join(__dirname,'..',new URL(req.url,'http://local').pathname);fs.readFile(file,(err,data)=>{if(err){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':file.endsWith('.html')?'text/html':'application/octet-stream');res.end(data);});});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));}
 const base=process.env.UI_BASE_URL||'http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',route=>{const u=new URL(route.request().url());let body=u.pathname==='/api/backbone'?fixture.config:u.pathname==='/api/dashboard'?fixture.data:u.pathname.endsWith('/history')?[]:{};return route.fulfill({json:body});});
 try{
 async function auditColors(label){
  await page.waitForTimeout(220);
  const failures=await page.evaluate(()=>{
   const rgba=s=>{const a=s.match(/[\d.]+/g)?.map(Number);return a&&a.length>=3?[...a.slice(0,3),a[3]??1]:[0,0,0,0];};
   const blend=(fg,bg)=>fg.slice(0,3).map((v,i)=>v*fg[3]+bg[i]*(1-fg[3]));
   const bgOf=el=>{const chain=[];for(let n=el;n;n=n.parentElement)chain.unshift(n);let rgb=[255,255,255];for(const n of chain){const c=rgba(getComputedStyle(n).backgroundColor);rgb=blend(c,rgb);}return rgb;};
   const lum=c=>c.map(x=>x/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4).reduce((v,x,i)=>v+x*[.2126,.7152,.0722][i],0);
   const bad=[];
   for(const e of document.querySelectorAll('body *')){
    const css=getComputedStyle(e),text=[...e.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();
    if(!text||parseFloat(css.fontSize)===0||!e.getClientRects().length||css.visibility==='hidden'||Number(css.opacity)===0||e.matches(':disabled,option,script,style,title'))continue;
    const svg=e instanceof SVGElement;if(svg&&!e.matches('text,tspan'))continue;
    const bg=bgOf(e),fg=blend(rgba(svg?css.fill:css.color),bg),ratio=(Math.max(lum(bg),lum(fg))+.05)/(Math.min(lum(bg),lum(fg))+.05);
    const large=parseFloat(css.fontSize)>=24||(parseFloat(css.fontSize)>=18.66&&Number(css.fontWeight)>=700),min=large?3:4.5;
    if(ratio<min-.01)bad.push({element:e.tagName,classes:e.getAttribute('class'),text:text.slice(0,65),ratio:Math.round(ratio*100)/100,fg:css.color,fill:svg?css.fill:null,bg});
   }
   return bad;
  });
  assert.deepEqual(failures,[],`${label}: readable text contrast`);
 }
 await page.goto(base+'/static/index.html');
 await page.waitForFunction(()=>document.querySelectorAll('#device-rows .device-row').length>0);
 assert.equal(await page.locator('#theme-select').count(),1,'Tema deve estar disponível na barra superior');
 assert.equal(await page.locator('#sidebar-width,#menu-settings,#menu-preferences').count(),0,'Sem ajuste de pixels');
 for(const theme of ['light','dark']){
  await page.selectOption('#theme-select',theme);
  await page.locator('[data-page="backbone"]').click();
  await page.waitForSelector('.backbone-node');
  assert.equal(await page.locator('.node-label-card').count(),0,'Nomes sem quadros');
  assert.equal(await page.locator('.map-regions').count(),0,'Fundo uniforme sem faixas coloridas');
  const weights=await page.locator('.backbone-node text:not(.node-ip),.radio-site').evaluateAll(els=>els.map(e=>Number(getComputedStyle(e).fontWeight)));
  assert(weights.every(w=>w>=700),'Nomes das cidades em negrito');
  assert.equal(await page.locator('#backbone-zoom-level,#backbone-zoom-in,#backbone-zoom-out').count(),0,'Sem controles de porcentagem');
  const map=page.locator('#backbone-map'),before=(await map.boundingBox()).width;
  await page.locator('.backbone-scroll').hover({position:{x:600,y:200}});await page.mouse.wheel(0,-240);
  await page.waitForFunction(w=>document.querySelector('#backbone-map').getBoundingClientRect().width>w,before);
  const after=(await map.boundingBox()).width;assert(after>before,'Scroll amplia');
  await page.mouse.wheel(0,240);await page.waitForTimeout(120);assert((await map.boundingBox()).width<after,'Scroll reduz');
  await page.locator('#backbone-fit').click();
  await auditColors(`${theme}/backbone`);
  if(process.env.UI_SCREENSHOTS)await page.screenshot({path:process.env.UI_SCREENSHOTS+'/'+theme+'-map.png'});
  await page.reload();await page.waitForFunction(t=>document.documentElement.dataset.theme===t,theme);
  for(const tab of ['overview','bbus','datacoms','siae']){
   await page.locator(`[data-page="${tab}"]`).click();
   await page.waitForSelector('#city-filter');
   await page.selectOption('#city-filter','Coari');
   const selectors={overview:'#device-rows .device-row',bbus:'[data-bbu]',datacoms:'[data-datacom]',siae:'[data-siae]'};
   const ids=await page.locator(selectors[tab]).evaluateAll((els,tab)=>els.map(e=>tab==='overview'?Number(e.querySelector('[data-detail]')?.dataset.detail):Number(e.getAttribute({'bbus':'data-bbu','datacoms':'data-datacom','siae':'data-siae'}[tab]))),tab);
   assert(ids.length>0,`Há equipamentos em Coari: ${tab}`);
   const expected=fixture.data.devices.filter(d=>d.host==='10.200.9.1'||d.host==='192.168.20.1'||d.city==='Coari').map(d=>d.id);
   assert(ids.every(id=>expected.includes(id)),`Filtro por cidade não mistura localidades em ${tab}: ${ids}`);
   await page.selectOption('#city-filter','all');
   await auditColors(`${theme}/${tab}`);
   if(tab==='datacoms'&&process.env.UI_SCREENSHOTS)await page.screenshot({path:process.env.UI_SCREENSHOTS+'/'+theme+'-datacoms.png'});
  }
  await page.locator('[data-page="datacoms"]').click();
  for(const [city,count] of [['Manaus',2],['Tefé',2],['Coari',1]]){
   await page.selectOption('#city-filter',city);
   assert.equal(await page.locator('[data-datacom]').count(),count,`Datacoms em ${city}`);
  }
  await page.locator('#search').fill('192.0.2');
  assert.equal(await page.locator('[data-datacom]').count(),0,'Cidade e busca se combinam');
  await page.locator('#search').fill('');await page.selectOption('#state-filter','offline');
  assert.equal(await page.locator('[data-datacom]').count(),0,'Cidade e status se combinam');
  await page.selectOption('#state-filter','all');
  await page.locator('[data-page="bbus"]').click();
  assert.equal(await page.locator('#city-filter').inputValue(),'Coari','Cidade escolhida permanece ao mudar de aba');
  await page.selectOption('#city-filter','__none');assert.equal(await page.locator('[data-bbu]').count(),1);
  await page.selectOption('#city-filter','all');
  await page.locator('#bbu-content [data-edit="100"]').click();
  assert.equal(await page.locator('#device-form [name="city"]').inputValue(),'Coari','Editar preserva a cidade');
  await page.locator('#device-dialog .close-dialog').first().click();
  await page.locator('#add-device').click();assert.equal(await page.locator('#device-form [name="city"]').count(),1);
  await auditColors(`${theme}/device-form`);
  await page.locator('#device-dialog .close-dialog').first().click();
 }
 await page.setViewportSize({width:390,height:844});
 for(const theme of ['light','dark']){
  await page.selectOption('#theme-select',theme);
  for(const tab of ['overview','datacoms','bbus','siae','backbone']){
   await page.locator(`[data-page="${tab}"]`).click();
   await auditColors(`${theme}/mobile/${tab}`);
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
   assert(!overflow,`${theme}/${tab}: no page overflow on mobile`);
  }
 }
 assert.deepEqual(errors,[],'Nenhum erro JavaScript');
 console.log('OK: themes persist, map/wheel controls, bold names and city filters on all four equipment views.');
 }finally{await browser.close();if(server)await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
