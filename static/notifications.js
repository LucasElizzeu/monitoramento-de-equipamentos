(() => {
 const form = $('#notification-form');
 let generation = 0, revision = null, dirty = false, busy = false, saved = null;
 const fields = ['enabled','token','phone_number_id','recipient','template_name','language','api_version','batch_seconds','notify_ping','notify_ports','notify_circuits','notify_collection'];
 const statuses = {pending:'Na fila',sending:'Enviando',sent:'Aceito pela Meta',failed:'Falhou',cancelled:'Cancelado',expired:'Expirado'};
 function feedback(text) { $('#notification-feedback').textContent = text; }
 function failure(error) { $('#notification-error').textContent = error.message; $('#notification-error').hidden = false; }
 function buttons() {
  $('#notification-fields').disabled = busy || state.demo || Boolean(designPreview) || revision===null;
  $('#save-notification').disabled = busy;
  $('#test-notification').disabled = busy || dirty || !saved?.has_token;
  $('#remove-notification').disabled = busy || !saved?.has_token;
 }
 function renderStatus(data) {
  const label = $('#notification-enabled-status');
  label.textContent = data.blocked ? 'Envios pausados' : data.enabled ? 'Ativado' : 'Desativado';
  label.classList.toggle('active', data.enabled && !data.blocked);
  label.classList.toggle('blocked', data.blocked);
  $('#notification-stats').innerHTML = `<dl><div><dt>Eventos na fila</dt><dd>${(data.counts.pending||0)+(data.counts.sending||0)}</dd></div><div><dt>Eventos aceitos</dt><dd>${data.counts.sent||0}</dd></div><div><dt>Falhas</dt><dd>${data.counts.failed||0}</dd></div></dl>`;
  $('#notification-last-success').textContent = data.last_sent_at ? `Última aceitação pela Meta: ${new Date(data.last_sent_at*1000).toLocaleString('pt-BR')}` : 'Nenhum envio confirmado pela Meta ainda.';
  if (data.last_error) { $('#notification-error').textContent = data.last_error; $('#notification-error').hidden = false; }
  $('#notification-history').innerHTML = data.recent.length ? data.recent.map(event => `<article class="notification-event"><div><strong>${esc(event.device_name)}</strong><p>${esc(event.message)}</p><small>${esc(new Date(event.created_at*1000).toLocaleString('pt-BR'))} · ${event.attempts} tentativa(s)</small>${event.error?`<p>${esc(event.error)}</p>`:''}</div><span class="status-pill ${event.status==='sent'?'online':event.status==='failed'?'error':''}">${statuses[event.status]||esc(event.status)}</span></article>`).join('') : '<p class="report-empty">Novos eventos aparecerão aqui após ativar os alertas. Eventos antigos e demonstrações não entram na fila.</p>';
 }
 function fill(data) {
  saved = data; revision = data.revision; dirty = false;
  for (const name of fields) {
   const field = form.elements[name];
   const value = name==='enabled' ? data.enabled : data.config[name];
   if (field.type==='checkbox') field.checked = Boolean(value);
   else field.value = name==='token' ? '' : value ?? '';
  }
  form.elements.token.placeholder = data.has_token ? 'Token salvo · preencha somente para substituir' : 'Informe o token de acesso';
  $('#notification-token-help').textContent = data.has_token ? 'Há um token criptografado salvo. Deixe vazio para mantê-lo.' : 'O token fica criptografado e nunca é exibido novamente.';
  buttons();
 }
 async function loadSettings(refill=false) {
  refill = refill || revision===null;
  const ticket = ++generation;
  const demo = state.demo || Boolean(designPreview);
  $('#notification-demo-note').hidden = !demo;
  $('#notification-fields').disabled = demo || busy || refill;
  $('#notification-error').hidden = true;
  if (demo) {
   saved=null; revision=null; dirty=false; form.reset();
   form.elements.token.placeholder='Informe o token de acesso';
   $('#notification-token-help').textContent='O token fica criptografado e nunca é exibido novamente.';
   $('#notification-enabled-status').textContent='Demonstração';
   $('#notification-enabled-status').classList.remove('active','blocked');
   $('#notification-stats').innerHTML=''; $('#notification-last-success').textContent='';
   $('#notification-history').innerHTML='<p class="report-empty">Nenhuma mensagem real é enviada na demonstração.</p>';
   feedback('Saia da demonstração para configurar sua integração.');
   return;
  }
  try {
   const data = await api('/api/notifications');
   if (ticket!==generation || state.page!=='notifications' || state.demo) return;
   if (refill) { fill(data); feedback(''); }
   renderStatus(data);
   if (!data.worker_running) feedback('O serviço de notificações não está ativo. Reinicie o programa antes de testar os alertas automáticos.');
  } catch (error) { if (ticket===generation) failure(error); }
 }
 form.addEventListener('input', () => { dirty=true; buttons(); feedback('Há alterações não salvas. Salve antes de enviar o teste.'); });
 form.addEventListener('submit', async event => {
  event.preventDefault(); if (state.demo || designPreview || busy) return;
  const data = {revision};
  for (const name of fields) {
   const field = form.elements[name];
   data[name] = field.type==='checkbox' ? field.checked : name==='batch_seconds' ? Number(field.value) : field.value;
  }
  busy=true; buttons(); $('#notification-error').hidden=true;
  // Never keep a submitted token in the form, including after a failed request.
  form.elements.token.value='';
  try {
   const result = await api('/api/notifications',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
   if (state.page==='notifications' && !state.demo) {
    fill(result); renderStatus(result); feedback('Configuração salva. Use Enviar teste para verificar o destino.');
   }
  } catch (error) { failure(error); }
  finally { data.token=''; busy=false; buttons(); }
 });
 $('#test-notification').addEventListener('click',async () => {
  if (state.demo || designPreview || busy || dirty) return;
  busy=true; buttons(); $('#notification-error').hidden=true;
  feedback('Enviando uma mensagem de teste ao WhatsApp configurado…');
  try {
   const result=await api('/api/notifications/test',{method:'POST'});
   if (state.page==='notifications' && !state.demo) { await loadSettings(); feedback(result.message); }
  } catch (error) { if (!state.demo) { failure(error); feedback('O teste não foi confirmado. Confira o diagnóstico acima.'); } }
  finally { busy=false; buttons(); }
 });
 $('#remove-notification').addEventListener('click',async () => {
  if (state.demo || designPreview || busy || !confirm('Desativar os alertas, remover o token e cancelar os envios que ainda não começaram?')) return;
  busy=true; buttons();
  try { await api('/api/notifications',{method:'DELETE'}); await loadSettings(true); feedback('Notificações desativadas e credenciais removidas.'); }
  catch (error) { failure(error); }
  finally { busy=false; buttons(); }
 });
 window.addEventListener('monitor-page',() => {
  ++generation; form.elements.token.value='';
  if (state.page==='notifications') loadSettings(true);
 });
 $('#refresh-notifications').addEventListener('click',() => loadSettings(false));
 $('#refresh').addEventListener('click',() => {if(state.page==='notifications') loadSettings(false);});
 setInterval(() => {
  if (state.page==='notifications' && !document.hidden && !busy && !window.getSelection()?.toString()) loadSettings(false);
 },15000);
})();
