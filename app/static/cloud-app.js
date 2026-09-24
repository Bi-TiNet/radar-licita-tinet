import { createClient } from '@supabase/supabase-js';

const $ = (selector) => document.querySelector(selector);
const state = { view: 'opportunities', rows: new Map() };
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
const supabase = supabaseUrl && anonKey ? createClient(supabaseUrl, anonKey) : null;
const municipalities = [
  ['2929206', 'São Francisco do Conde'],
  ['2904902', 'Cachoeira'],
  ['2928604', 'Santo Amaro'],
  ['2929750', 'Saubara'],
];

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}

function money(value) {
  return value == null ? 'Valor não informado' : new Intl.NumberFormat('pt-BR', {
    style: 'currency', currency: 'BRL',
  }).format(Number(value));
}

function date(value) {
  if (!value) return 'Sem prazo';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short', timeZone: 'America/Bahia',
  }).format(parsed);
}

function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  setTimeout(() => element.classList.remove('show'), 3500);
}

function check(result) {
  if (result.error) throw result.error;
  return result;
}

function workflowStatus(item) {
  if (item.dismissed) return 'descartada';
  if (item.favorite) return 'favorita';
  if (item.viewed_at) return 'visualizada';
  if (item.notified_at) return 'notificada';
  return 'nova';
}

function card(item) {
  const status = workflowStatus(item);
  const labels = { nova: 'Nova', notificada: 'Notificada', visualizada: 'Visualizada', favorita: 'Favorita' };
  const score = Math.min(100, Math.max(0, Number(item.score) || 0));
  const description = String(item.description || '');
  const terms = (Array.isArray(item.matched_terms) ? item.matched_terms : [])
    .slice(0, 4).map((term) => `<span class="tag">${escapeHtml(term)}</span>`).join('');
  return `<article class="card">
    <div class="score-ring" style="--score:${score}"><strong>${score}%</strong></div>
    <div><div class="workflow-row"><span class="workflow-status status-${status}">${labels[status] || 'Nova'}</span></div>
      <h3>${escapeHtml(item.title)}</h3>
      <div class="meta"><span>📍 ${escapeHtml(item.municipality)}</span><span>🏛️ ${escapeHtml(item.agency || 'Órgão público')}</span><span>⏰ ${escapeHtml(date(item.proposal_end_at))}</span><span>💰 ${escapeHtml(money(item.estimated_value))}</span></div>
      <p class="details">${escapeHtml(description.slice(0, 240))}${description.length > 240 ? '…' : ''}</p>
      <div class="meta"><span class="tag">${escapeHtml(item.category || 'Correlato')}</span>${terms}</div>
    </div>
    <div class="card-actions">
      <button class="icon-btn ${item.favorite ? 'active' : ''}" title="Favoritar" data-action="favorite" data-id="${item.id}">★</button>
      ${item.url ? `<button class="icon-btn" title="Abrir fonte" data-action="source" data-id="${item.id}">↗</button>` : ''}
      <button class="icon-btn" title="Descartar" data-action="dismiss" data-id="${item.id}">×</button>
    </div>
  </article>`;
}

async function loadDashboard() {
  const { data } = check(await supabase.rpc('radar_dashboard'));
  const stats = data || {};
  $('#stats').innerHTML = [
    ['Oportunidades', stats.total || 0, 'na base monitorada'],
    ['Abertas agora', stats.open || 0, 'com prazo ativo'],
    ['Alta aderência', stats.hot || 0, '70% ou mais'],
    ['Favoritos', stats.favorites || 0, 'para acompanhar'],
  ].map(([label, count, caption]) => `<div class="stat"><small>${label}</small><strong>${count}</strong><em>${caption}</em></div>`).join('');
}

async function loadList() {
  if (state.view === 'notifications') {
    const { data } = check(await supabase.from('notifications').select('*,opportunities(title,municipality)').order('sent_at', { ascending: false }).limit(100));
    $('#viewTitle').textContent = 'Histórico de notificações';
    $('#viewDesc').textContent = 'Registro dos avisos gerados pelo sistema.';
    $('#count').textContent = `${data.length} registros`;
    $('#list').innerHTML = data.length ? data.map((item) => `<article class="card" style="grid-template-columns:1fr auto"><div><h3>${escapeHtml(item.opportunities?.title || 'Notificação do sistema')}</h3><div class="meta"><span>📍 ${escapeHtml(item.opportunities?.municipality || '-')}</span><span>◉ ${escapeHtml(item.channel)}</span><span>${escapeHtml(item.status)}</span><span>${escapeHtml(date(item.sent_at))}</span></div></div></article>`).join('') : '<div class="empty">Nenhuma notificação registrada.</div>';
    return;
  }

  if (state.view === 'sync') {
    const { data } = check(await supabase.from('sync_runs').select('*').order('started_at', { ascending: false }).limit(30));
    $('#viewTitle').textContent = 'Histórico de coletas';
    $('#viewDesc').textContent = 'Execuções automáticas da coleta na BLL.';
    $('#count').textContent = `${data.length} execuções`;
    $('#list').innerHTML = data.length ? data.map((item) => `<article class="card" style="grid-template-columns:1fr auto"><div><h3>Coleta ${escapeHtml(item.status)}</h3><div class="meta"><span>Fonte: ${escapeHtml(item.source)}</span><span>Encontradas: ${Number(item.found) || 0}</span><span>Novas: ${Number(item.inserted) || 0}</span><span>Atualizadas: ${Number(item.updated) || 0}</span></div><p class="details">${escapeHtml(item.detail || 'Sem erros registrados.')}</p></div><span class="tag">${escapeHtml(date(item.started_at))}</span></article>`).join('') : '<div class="empty">Nenhuma coleta executada ainda.</div>';
    return;
  }

  let query = supabase.from('radar_active_opportunities').select('*', { count: 'exact' });
  const city = $('#city').value;
  const status = $('#status').value;
  const chosenScore = Number($('#score').value || 0);
  if (city) query = query.eq('municipality_code', city);
  if (status) query = query.eq('status', status);
  if (state.view === 'general') query = query.lte('score', 39);
  else query = query.gte('score', state.view === 'opportunities' ? Math.max(40, chosenScore) : chosenScore);
  if (state.view === 'favorites') query = query.eq('favorite', true);
  const search = $('#search').value.trim().replace(/[(),.%\\"]/g, ' ').slice(0, 100);
  if (search) query = query.or(`title.ilike.%${search}%,description.ilike.%${search}%,agency.ilike.%${search}%`);
  const { data, count } = check(await query.order('favorite', { ascending: false }).order('score', { ascending: false }).order('proposal_end_at', { ascending: true, nullsFirst: false }).limit(100));
  state.rows = new Map(data.map((item) => [String(item.id), item]));
  const headings = {
    favorites: ['Oportunidades favoritas', 'Itens separados para acompanhamento.'],
    general: ['Outras oportunidades', 'Licitações gerais dos quatro municípios, separadas do radar principal de telecom.'],
    opportunities: ['Oportunidades priorizadas', 'Aderência de 40% ou mais ao negócio da Ti.Net.'],
  };
  [$('#viewTitle').textContent, $('#viewDesc').textContent] = headings[state.view];
  $('#count').textContent = `${count ?? data.length} encontradas`;
  $('#list').innerHTML = data.length ? data.map(card).join('') : '<div class="empty">Nenhuma oportunidade encontrada com estes filtros.</div>';
}

async function refresh() {
  await Promise.all([loadDashboard(), loadList()]);
}

async function handleCardAction(event) {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  const id = button.dataset.id;
  const item = state.rows.get(id);
  if (!item) return;
  try {
    if (button.dataset.action === 'source') {
      if (!/^https?:\/\//i.test(item.url || '')) throw new Error('Endereço da fonte inválido');
      window.open(item.url, '_blank', 'noopener,noreferrer');
      check(await supabase.from('opportunities').update({ viewed_at: item.viewed_at || new Date().toISOString(), updated_at: new Date().toISOString() }).eq('id', item.id));
    } else if (button.dataset.action === 'favorite') {
      check(await supabase.from('opportunities').update({ favorite: !item.favorite, updated_at: new Date().toISOString() }).eq('id', item.id));
      toast('Favorito atualizado');
    } else if (button.dataset.action === 'dismiss') {
      check(await supabase.from('opportunities').update({ dismissed: true, updated_at: new Date().toISOString() }).eq('id', item.id));
      toast('Oportunidade descartada');
    }
    await refresh();
  } catch (error) {
    toast(`Não foi possível atualizar: ${error.message}`);
  }
}

function showLogin(message = '') {
  $('#loginScreen').hidden = false;
  $('#mainApp').hidden = true;
  $('#loginError').textContent = message;
}

async function enter() {
  const { data: { session }, error } = await supabase.auth.getSession();
  if (error) throw error;
  if (!session) { showLogin(); return; }
  const access = check(await supabase.rpc('radar_is_authorized'));
  if (!access.data) {
    await supabase.auth.signOut();
    showLogin('Sua conta ainda não tem acesso ao Radar Licita.');
    return;
  }
  $('#loginScreen').hidden = true;
  $('#mainApp').hidden = false;
  await refresh();
}

$('#loginForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('#loginError').textContent = '';
  if (!supabase) { showLogin('Configuração do Supabase ausente.'); return; }
  const button = $('#loginForm button[type=submit]');
  button.disabled = true;
  try {
    check(await supabase.auth.signInWithPassword({
      email: $('#loginEmail').value.trim(), password: $('#loginPassword').value,
    }));
    await enter();
  } catch (error) {
    showLogin(`Não foi possível entrar: ${error.message}`);
  } finally {
    button.disabled = false;
  }
});

$('#logoutBtn').addEventListener('click', async () => {
  await supabase.auth.signOut();
  showLogin();
});
$('#list').addEventListener('click', handleCardAction);
document.querySelectorAll('.nav').forEach((button) => button.addEventListener('click', async () => {
  document.querySelectorAll('.nav').forEach((element) => element.classList.remove('active'));
  button.classList.add('active');
  state.view = button.dataset.view;
  $('#score').disabled = state.view === 'general';
  try { await loadList(); } catch (error) { toast(`Erro: ${error.message}`); }
}));
['city', 'score', 'status'].forEach((id) => $(`#${id}`).addEventListener('change', () => loadList().catch((error) => toast(error.message))));
let searchTimer;
$('#search').addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadList().catch((error) => toast(error.message)), 350);
});
for (const [code, name] of municipalities) {
  $('#city').insertAdjacentHTML('beforeend', `<option value="${code}">${escapeHtml(name)}</option>`);
}
if (!supabase) showLogin('Configure VITE_SUPABASE_URL e VITE_SUPABASE_ANON_KEY no Netlify.');
else enter().catch((error) => showLogin(`Erro ao carregar: ${error.message}`));
