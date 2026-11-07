const assert=require('node:assert/strict'),fs=require('node:fs'),layout=require('../static/backbone-layout.js');
const config=JSON.parse(fs.readFileSync(require('node:path').join(__dirname,'../static/backbone.json'),'utf8'));
const sites=layout.sites(config);assert.equal(sites.length,26);assert.equal(sites.flatMap(s=>s.refs).length,46);assert.equal(new Set(sites.flatMap(s=>s.refs.map(r=>r.link[r.side].host))).size,46);
for(const site of sites){assert(site.x>=0&&site.x<=1920&&site.y<=900);assert(site.refs.length>=1&&site.refs.length<=2);for(const ref of site.refs)assert.equal(ref.link[ref.side].site,site.name);}
const tt=config.radio_links.filter(l=>l.route==='tefe-tabatinga');assert.equal(tt.length,15);for(const l of tt){const g=layout.geometry(l);assert.equal(g.y,790);assert(g.x1>g.x2);assert(g.x2>=120);assert(g.x1<=1824);}
assert.equal(layout.geometry(tt[0]).x1,1824);assert.equal(layout.geometry(tt.at(-1)).x2,120);assert.equal(layout.bounds.all,'0 0 1920 900');
for(const n of config.nodes)assert(n.x>=0&&n.x<=1920&&n.y>=0&&n.y<400);
console.log('OK: 26 pontos representam os 46 rádios sem perder vínculos; 15 enlaces de Tabatinga em uma linha; todas as coordenadas dentro da área legível.');
