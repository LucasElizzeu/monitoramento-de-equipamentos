/* Display preferences are local to this browser, not equipment configuration. */
(() => {
 const key='alwaysup-sidebar',toggle=$('#sidebar-toggle'),slider=$('#sidebar-width'),dialog=$('#menu-settings');
 let width=232,collapsed=matchMedia('(max-width:900px)').matches;
 try{const saved=JSON.parse(localStorage.getItem(key));if(saved&&typeof saved.collapsed==='boolean')collapsed=saved.collapsed;if(saved&&Number.isFinite(saved.width))width=Math.min(300,Math.max(180,saved.width));}catch{}
 function apply(save=false){
  document.body.dataset.sidebar=collapsed?'collapsed':'expanded';
  document.documentElement.style.setProperty('--sidebar-width',`${width}px`);
  toggle.setAttribute('aria-expanded',String(!collapsed));
  const label=collapsed?'Expandir menu':'Recolher menu';toggle.setAttribute('aria-label',label);toggle.title=label;
  slider.value=String(width);slider.setAttribute('aria-valuetext',`${width} pixels`);$('#sidebar-width-value').value=`${width} px`;
  if(save)try{localStorage.setItem(key,JSON.stringify({width,collapsed}));}catch{}
 }
 for(const item of document.querySelectorAll('.nav-item[data-page]')){
  const name=[...item.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join('').trim();
  item.setAttribute('aria-label',name);item.title=name;
 }
 toggle.onclick=()=>{collapsed=!collapsed;apply(true);};
 $('#menu-preferences').onclick=()=>dialog.showModal();
 $('#menu-settings-close').onclick=()=>dialog.close();
 slider.oninput=()=>{width=Number(slider.value);collapsed=false;apply(true);};
 $('#sidebar-reset').onclick=()=>{width=232;collapsed=false;apply(true);};
 apply();
})();
