/* Historical reports refresh independently, without interrupting monitor actions. */
(() => {
 let report = null, request = 0;
 const date = seconds => new Date(seconds * 1000).toLocaleDateString('pt-BR', {timeZone:'UTC'});
 const percent = value => value == null ? '—' : `${number(value, 2)}%`;
 function duration(value) {
  const seconds = Math.max(0, Math.round(value));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}min`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours}h ${minutes % 60}min` : `${Math.floor(hours / 24)}d ${hours % 24}h`;
 }
 function dailyBar(day) {
  const total = day.up + day.down + day.error + day.unmonitored;
  let edge = 0;
  const colors = ['#65deb3', '#fda4af', '#fcd58b', '#304259'];
  const gradient = ['up','down','error','unmonitored'].map((key,index) => {
   const start = edge;
   edge += total ? day[key] / total * 100 : index === 3 ? 100 : 0;
   return `${colors[index]} ${start}% ${edge}%`;
  }).join(',');
  const label = `${date(day.day)} UTC · com resposta ${duration(day.up)} · sem resposta ${duration(day.down)} · erro ${duration(day.error)} · sem medição ${duration(day.unmonitored)}`;
  return `<span class="availability-day" role="img" aria-label="${esc(label)}" title="${esc(label)}" style="background:linear-gradient(to top,${gradient})"></span>`;
 }
 function renderReport() {
  if (!report) return;
  const q = $('#availability-search').value.trim().toLowerCase();
  const devices = report.devices.filter(d => `${d.name} ${d.host}`.toLowerCase().includes(q));
  const up = devices.reduce((sum,d) => sum+d.up,0), down = devices.reduce((sum,d) => sum+d.down,0);
  const outages = devices.reduce((sum,d) => sum+d.outages,0);
  $('#availability-summary').innerHTML = `<article class="panel"><span>Disponibilidade do ping${q?' · filtro atual':''}</span><strong>${percent(up+down ? up/(up+down)*100 : null)}</strong><small>Tempo com resposta ÷ tempo de coleta válida</small></article><article class="panel"><span>Quedas confirmadas</span><strong>${outages}</strong><small>Entradas em 21 perdas consecutivas</small></article><article class="panel"><span>Equipamentos no relatório</span><strong>${devices.length}</strong><small>${report.days} datas UTC, incluindo o dia atual</small></article>`;
  $('#availability-results').innerHTML = devices.length ? devices.map(d => `<article class="panel availability-card"><header><div><h3>${esc(d.name)}</h3><span>${esc(deviceKindLabel(d))} · ${esc(d.host)}</span></div><strong class="availability-value">${percent(d.availability_pct)}</strong></header><div class="availability-timeline" aria-label="Histórico diário, do mais antigo ao mais recente">${d.daily.map(dailyBar).join('')}</div><div class="availability-range"><span>${date(report.start)}</span><span>${date(report.end)} · UTC</span></div><dl><div><dt>Tempo sem resposta</dt><dd>${duration(d.down)}</dd></div><div><dt>Quedas confirmadas</dt><dd>${d.outages}</dd></div><div><dt>Erros de coleta</dt><dd>${duration(d.error)}</dd></div><div><dt>Sem medição</dt><dd>${duration(d.unmonitored)}</dd></div></dl><p class="availability-coverage">Coleta válida: <strong>${percent(d.coverage_pct)}</strong> do período${d.availability_pct==null?' · aguardando medições':''}</p></article>`).join('') : `<div class="panel report-empty">${q?'Nenhum equipamento corresponde à busca.':'Cadastre equipamentos para começar a acumular seu histórico. Dados anteriores à atualização não são preenchidos.'}</div>`;
 }
 async function loadReport() {
  const ticket = ++request;
  const days = Number($('#availability-days').value), demo = state.demo;
  $('#availability-error').hidden = true;
  $('#refresh-availability').disabled = true;
  try {
   const result = await api(`/api/availability?days=${days}&demo=${demo}`);
   if (ticket !== request || state.page !== 'availability' || state.demo !== demo) return;
   report = result;
   $('#availability-period').textContent = `${date(report.start)} a ${date(report.end)} · datas UTC, incluindo hoje${demo?' · dados simulados':''}`;
   renderReport();
  } catch (error) {
   if (ticket !== request) return;
   $('#availability-error').textContent = `${error.message} O relatório pode estar desatualizado.`;
   $('#availability-error').hidden = false;
  } finally {
   if (ticket === request) $('#refresh-availability').disabled = false;
  }
 }
 async function loadBackups() {
  const ticket = ++request;
  $('#backups-error').hidden = true;
  $('#create-backup').disabled = state.demo || Boolean(designPreview);
  $('#backups-list').innerHTML = '<p class="report-empty">Carregando backups…</p>';
  if (state.demo) {
   $('#backups-status').textContent = 'Saia da demonstração para criar ou baixar backups da sua rede real.';
   $('#backups-list').innerHTML = '<p class="report-empty">A demonstração não acessa seus backups reais.</p>';
   return;
  }
  try {
   const result = await api('/api/backups');
   if (ticket !== request || state.page !== 'backups' || state.demo) return;
   $('#backups-status').textContent = result.error || 'Backup automático ativo enquanto o programa estiver ligado. As cópias são verificadas antes de serem guardadas.';
   if (result.error) { $('#backups-error').textContent = result.error; $('#backups-error').hidden = false; }
   $('#backups-list').innerHTML = result.backups.length ? result.backups.map(b => `<article class="backup-row"><div class="backup-symbol">${icon('shield')}</div><div class="backup-description"><strong>${b.automatic?'Backup automático':'Backup manual'}</strong><span>${esc(new Date(b.at).toLocaleString('pt-BR'))} · ${number(b.size/1024,1)} KB</span></div><a class="button secondary" download href="/api/backups/${encodeURIComponent(b.name)}" aria-label="Baixar backup de ${esc(new Date(b.at).toLocaleString('pt-BR'))}">Baixar ZIP</a></article>`).join('') : '<p class="report-empty">A primeira cópia automática será criada em até um minuto. Você também pode criar uma agora.</p>';
  } catch (error) {
   if (ticket !== request) return;
   $('#backups-error').textContent = error.message; $('#backups-error').hidden = false;
   $('#backups-list').innerHTML = '';
  }
 }
 function download(name) {
  const link = document.createElement('a');
  link.href = `/api/backups/${encodeURIComponent(name)}`; link.download = name;
  document.body.append(link); link.click(); link.remove();
 }
 $('#create-backup').addEventListener('click', async () => {
  if (state.demo || designPreview) return;
  const button = $('#create-backup'); button.disabled = true;
  $('#backups-error').hidden = true;
  try {
   const result = await api('/api/backups', {method:'POST'});
   // Recheck mode after a slow snapshot; never download real data in demo mode.
   if (!state.demo && state.page === 'backups') {
    download(result.name); await loadBackups(); toast('Backup criado. Guarde o ZIP em outro local protegido.');
   }
  } catch (error) {
   $('#backups-error').textContent = error.message; $('#backups-error').hidden = false;
  } finally { button.disabled = state.demo || Boolean(designPreview); }
 });
 window.addEventListener('monitor-page', () => {
  ++request;
  if (state.page === 'availability') {
   report = null; $('#availability-summary').innerHTML = '';
   $('#availability-results').innerHTML = '<p class="report-empty">Carregando histórico…</p>';
   loadReport();
  }
  if (state.page === 'backups') loadBackups();
 });
 $('#availability-days').addEventListener('change', loadReport);
 $('#availability-search').addEventListener('input', renderReport);
 $('#refresh-availability').addEventListener('click', loadReport);
 $('#refresh').addEventListener('click', () => {
  if (state.page === 'availability') loadReport();
  if (state.page === 'backups') loadBackups();
 });
 setInterval(() => {
  if (document.hidden || window.getSelection()?.toString() || readingOutput()) return;
  if (state.page === 'availability') loadReport();
  if (state.page === 'backups') loadBackups();
 }, 30000);
})();
