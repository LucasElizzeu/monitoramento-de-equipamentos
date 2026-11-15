/* Display preferences are local to this browser, not equipment configuration. */
(() => {
 const key='alwaysup-sidebar',toggle=$('#sidebar-toggle');
 let collapsed=true;
 try{const saved=JSON.parse(localStorage.getItem(key));if(saved&&typeof saved.collapsed==='boolean')collapsed=saved.collapsed;}catch{}
 function apply(save=false){
  document.body.dataset.sidebar=collapsed?'collapsed':'expanded';
  document.documentElement.style.setProperty('--sidebar-width','232px');
  toggle.setAttribute('aria-expanded',String(!collapsed));
  const label=collapsed?'Expandir menu':'Recolher menu';toggle.setAttribute('aria-label',label);toggle.title=label;
  if(save)try{localStorage.setItem(key,JSON.stringify({collapsed}));}catch{}
 }
 for(const item of document.querySelectorAll('.nav-item[data-page]')){
  const name=[...item.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join('').trim();
  item.setAttribute('aria-label',name);item.title=name;
 }
 toggle.onclick=()=>{collapsed=!collapsed;apply(true);};
 apply();
})();
