const $=s=>document.querySelector(s); const state={view:'opportunities'};
const money=v=>v?new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}).format(v):'Valor não informado';
const date=v=>v?new Intl.DateTimeFormat('pt-BR',{dateStyle:'short'}).format(new Date(v)):'Sem prazo';
function toast(t){const e=$('#toast');e.textContent=t;e.classList.add('show');setTimeout(()=>e.classList.remove('show'),2600)}
async function api(url,opt){const r=await fetch(url,opt);if(!r.ok)throw new Error(await r.text());return r.json()}
async function loadCities(){const data=await api('/api/municipalities');for(const c of data)$('#city').insertAdjacentHTML('beforeend',`<option value="${c.code}">${c.name}</option>`)}
async function loadDashboard(){const d=await api('/api/dashboard');const s=d.stats||{};$('#stats').innerHTML=`<div class="stat"><small>Oportunidades</small><strong>${s.total||0}</strong><em>na base monitorada</em></div><div class="stat"><small>Abertas agora</small><strong>${s.open||0}</strong><em>com prazo ativo</em></div><div class="stat"><small>Alta aderência</small><strong>${s.hot||0}</strong><em>70% ou mais</em></div><div class="stat"><small>Favoritos</small><strong>${s.favorites||0}</strong><em>para acompanhar</em></div>`}
function card(o){const terms=(o.matched_terms||[]).slice(0,4).map(t=>`<span class="tag">${t}</span>`).join('');return `<article class="card"><div class="score-ring" style="--score:${o.score}"><strong>${o.score}%</strong></div><div><div class="workflow-row"><span class="workflow-status status-${o.workflow_status||'nova'}">${({nova:'Nova',notificada:'Notificada',visualizada:'Visualizada',favorita:'Favorita',descartada:'Descartada'})[o.workflow_status||'nova']||'Nova'}</span></div><h3>${o.title}</h3><div class="meta"><span>📍 ${o.municipality}</span><span>🏛️ ${o.agency||'Órgão público'}</span><span>⏰ ${date(o.proposal_end_at)}</span><span>💰 ${money(o.estimated_value)}</span></div><p class="details">${(o.description||'').slice(0,240)}${(o.description||'').length>240?'…':''}</p><div class="meta"><span class="tag">${o.category||'Correlato'}</span>${terms}</div></div><div class="card-actions"><button class="icon-btn ${o.favorite?'active':''}" title="Favoritar" onclick="favorite(${o.id})">★</button>${o.url?`<button class="icon-btn" title="Abrir fonte" onclick="openSource(${o.id},'${o.url}')">↗</button>`:''}<button class="icon-btn" title="Notificar agora" onclick="notify(${o.id})">◉</button><button class="icon-btn" title="Descartar" onclick="dismiss(${o.id})">×</button></div></article>`}
async function loadList(){let url;if(state.view==='notifications'){const data=await api('/api/notifications');$('#viewTitle').textContent='Histórico de notificações';$('#viewDesc').textContent='Registro dos avisos gerados pelo sistema.';$('#count').textContent=`${data.length} registros`;$('#list').innerHTML=data.length?data.map(n=>`<article class="card" style="grid-template-columns:1fr auto"><div><h3>${n.title||'Notificação do sistema'}</h3><div class="meta"><span>📍 ${n.municipality||'-'}</span><span>◉ ${n.channel}</span><span>${n.status}</span><span>${date(n.sent_at)}</span></div></div></article>`).join(''):'<div class="empty">Nenhuma notificação registrada.</div>';return}
if(state.view==='sync'){const data=await api('/api/sync-runs');$('#viewTitle').textContent='Histórico de coletas';$('#viewDesc').textContent='Execuções de sincronização com as fontes públicas.';$('#count').textContent=`${data.length} execuções`;$('#list').innerHTML=data.length?data.map(r=>`<article class="card" style="grid-template-columns:1fr auto"><div><h3>Coleta ${r.status}</h3><div class="meta"><span>Fonte: ${r.source}</span><span>Encontradas: ${r.found}</span><span>Novas: ${r.inserted}</span><span>Atualizadas: ${r.updated}</span></div><p class="details">${r.detail||'Sem erros registrados.'}</p></div><span class="tag">${date(r.started_at)}</span></article>`).join(''):'<div class="empty">Nenhuma coleta executada ainda.</div>';return}
const p=new URLSearchParams();if($('#city').value)p.set('city',$('#city').value);if(state.view==='general'){p.set('min_score','0');p.set('max_score','39')}else if(state.view==='opportunities'){const selected=Number($('#score').value||0);p.set('min_score',String(Math.max(40,selected)))}else{p.set('min_score',$('#score').value)}if($('#status').value)p.set('status',$('#status').value);if($('#search').value)p.set('q',$('#search').value);if(state.view==='favorites')p.set('favorite','true');const data=await api('/api/opportunities?'+p);if(state.view==='favorites'){ $('#viewTitle').textContent='Oportunidades favoritas'; $('#viewDesc').textContent='Itens separados para acompanhamento.' }else if(state.view==='general'){ $('#viewTitle').textContent='Outras oportunidades'; $('#viewDesc').textContent='Licitações gerais dos 12 municípios monitorados, separadas do radar principal de telecom.' }else{ $('#viewTitle').textContent='Oportunidades priorizadas'; $('#viewDesc').textContent='Aderência de 40% ou mais ao negócio da Ti.Net.' }$('#count').textContent=`${data.length} encontradas`;$('#list').innerHTML=data.length?data.map(card).join(''):'<div class="empty">Nenhuma oportunidade encontrada com estes filtros.<br>Sincronize com o PNCP para atualizar a base.</div>'}
async function refresh(){await Promise.all([loadDashboard(),loadList()])}
window.openSource=async(id,url)=>{try{await api(`/api/opportunities/${id}/viewed`,{method:'PATCH'})}catch(e){}window.open(url,'_blank');setTimeout(refresh,400)};
window.favorite=async id=>{await api(`/api/opportunities/${id}/favorite`,{method:'PATCH'});toast('Favorito atualizado');refresh()};window.dismiss=async id=>{await api(`/api/opportunities/${id}/dismiss`,{method:'PATCH'});toast('Oportunidade descartada');refresh()};window.notify=async id=>{await api(`/api/opportunities/${id}/notify`,{method:'POST'});toast('Notificação registrada/enviada');refresh()};
$('#syncBtn').onclick=async()=>{const btn=$('#syncBtn');const original=btn.textContent;try{btn.disabled=true;btn.textContent='↻ Sincronizando...';toast('Coleta real em andamento');const r=await api('/api/sync?wait=true',{method:'POST'});if(r.status==='skipped'){toast('Já existe uma coleta em andamento')}else{toast(`Coleta concluída: ${r.inserted||0} novas, ${r.notified||0} notificadas`)}await refresh()}catch(e){toast('Erro na coleta: '+e.message)}finally{btn.disabled=false;btn.textContent=original}};$('#demoBtn').onclick=async()=>{await api('/api/demo/load',{method:'POST'});toast('Demonstração carregada');refresh()};
document.querySelectorAll('.nav').forEach(b=>b.onclick=()=>{document.querySelectorAll('.nav').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.view=b.dataset.view;$('#score').disabled=state.view==='general';loadList()});['city','score','status'].forEach(id=>$('#'+id).onchange=loadList);let timer;$('#search').oninput=()=>{clearTimeout(timer);timer=setTimeout(loadList,300)};
(async()=>{await loadCities();await refresh()})().catch(e=>toast('Erro: '+e.message));

// Teste manual dos canais de notificação
const testNotifyBtn = document.querySelector('#testNotifyBtn');
if (testNotifyBtn && !testNotifyBtn.dataset.ready) {
  testNotifyBtn.dataset.ready = '1';
  testNotifyBtn.onclick = async () => {
    const original = testNotifyBtn.textContent;
    testNotifyBtn.disabled = true;
    testNotifyBtn.textContent = '◉ Testando...';
    try {
      const result = await api('/api/notifications/test', { method: 'POST' });
      const sent = (result.results || []).filter(x => x.status === 'sent');
      const errors = (result.results || []).filter(x => x.status === 'error');
      const skipped = (result.results || []).filter(x => x.status === 'skipped');
      let msg = `${sent.length} envio(s) concluído(s)`;
      if (errors.length) msg += ` • ${errors.length} erro(s)`;
      if (skipped.length) msg += ` • ${skipped.length} canal(is) não configurado(s)`;
      toast(msg);
      console.table(result.results || []);
    } catch (e) {
      toast('Erro no teste: ' + e.message);
    } finally {
      testNotifyBtn.disabled = false;
      testNotifyBtn.textContent = original;
    }
  };
}
