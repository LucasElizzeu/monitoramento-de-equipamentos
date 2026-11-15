const assert=require('node:assert/strict'),{palettes,valid}=require('../static/ui-theme.js');
const lum=hex=>{const c=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722;};
const contrast=(a,b)=>(Math.max(lum(a),lum(b))+.05)/(Math.min(lum(a),lum(b))+.05);
for(const [theme,p] of Object.entries(palettes)){
 for(const bg of ['bg','surface','inset','raised'])for(const text of ['ink','muted','dim','accent','success','red','amber','neutral','map-radio'])assert(contrast(p[text],p[bg])>=4.5,`${theme}: ${text}/${bg} >= 4.5`);
 for(const [text,bg] of [['success','success-bg'],['red','danger-bg'],['amber','warning-bg'],['neutral','neutral-bg'],['accent','accent-light'],['on-button','button-bg']])assert(contrast(p[text],p[bg])>=4.5,`${theme}: ${text}/${bg} >= 4.5`);
}
assert.equal(valid('unknown'),'light');assert.equal(valid(null),'light');assert.equal(valid('dark'),'dark');
console.log('OK: light/dark text, status badges and primary controls meet WCAG AA contrast.');
