/* Shared palette and contrast contract; apply before paint, without server state. */
(function(root){
 const palettes={
  light:{bg:'#f5f7fa',navy:'#ffffff',surface:'#ffffff',raised:'#eef4f8',inset:'#f7f9fb',ink:'#1b293e',muted:'#526479',dim:'#57687c',line:'#dce3eb',accent:'#155d89','accent-light':'#eaf4fc',green:'#137443','green-light':'#edf9f1',red:'#b92f39',amber:'#925d08',success:'#137443','success-bg':'#edf9f1','danger-bg':'#fff0f1','warning-bg':'#fff8e9',neutral:'#57687c','neutral-bg':'#f0f3f6','map-radio':'#2465c7','map-pending':'#66758a','button-bg':'#155d89','on-button':'#ffffff','selection-bg':'#d8ebfa'},
  dark:{bg:'#101823',navy:'#182333',surface:'#182333',raised:'#25354a',inset:'#141e2c',ink:'#e5edf7',muted:'#b0c0d4',dim:'#9cacc2',line:'#3d5069',accent:'#8cc8ff','accent-light':'#213c55',green:'#71dba4','green-light':'#1a3a30',red:'#ff97a2',amber:'#f1c56a',success:'#71dba4','success-bg':'#1a3a30','danger-bg':'#422932','warning-bg':'#3c3424',neutral:'#b0c0d4','neutral-bg':'#273448','map-radio':'#8bb7ff','map-pending':'#9cacc2','button-bg':'#235f8b','on-button':'#ffffff','selection-bg':'#31536f'}
 };
 const valid=value=>Object.hasOwn(palettes,value)?value:'light';
 const api={palettes,valid};if(typeof module==='object'&&module.exports)module.exports=api;else root.uiTheme=api;
 if(typeof document==='undefined')return;
 function apply(value){
  const theme=valid(value),element=document.documentElement;element.dataset.theme=theme;element.style.colorScheme=theme;
  for(const [name,color] of Object.entries(palettes[theme]))element.style.setProperty('--'+name,color);
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content',palettes[theme].surface);
 }
 let saved;try{saved=localStorage.getItem('alwaysup-theme');}catch{}apply(saved);
 document.addEventListener('DOMContentLoaded',()=>{
  const select=document.getElementById('theme-select');select.value=document.documentElement.dataset.theme;
  select.addEventListener('change',()=>{apply(select.value);try{localStorage.setItem('alwaysup-theme',valid(select.value));}catch{}});
 });
})(globalThis);
