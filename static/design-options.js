const models={balanced:'Modelo 1 · Equilibrado',compact:'Modelo 2 · Compacto',list:'Modelo 3 · Em lista'};
document.querySelectorAll('[data-model]').forEach(button=>{
 button.addEventListener('click',()=>{
  const model=button.dataset.model;
  document.querySelectorAll('[data-model]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
  document.querySelector('#model-description').textContent=models[model];
  document.querySelector('#full-preview').href=`/?design-preview=${model}`;
  const frame=document.querySelector('#design-frame');
  frame.title=`Prévia: ${models[model]}`;frame.src=`/?design-preview=${model}`;
 });
});
