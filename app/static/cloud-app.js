import { createClient } from '@supabase/supabase-js';
import { classifyFocus, normalize } from '../focus.js';

const $ = (selector) => document.querySelector(selector);
const state = { view: 'opportunities', rows: new Map(), opportunities: [] };
const initialHash = new URLSearchParams(window.location.hash.slice(1));
let authFlow = initialHash.get('type');
const linkError = initialHash.get('error_code');
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || import.meta.env.VITE_SUPABASE_ANON_KEY;
const supabase = supabaseUrl && publishableKey ? createClient(supabaseUrl, publishableKey) : null;
const collectorEmails = new Set(['bi@tinettecnologia.com.br', 'diegosmfranca@hotmail.com']);
const regions = [
  {
    id: 'santo-amaro',
    label: 'Santo Amaro e entorno',
    cities: [
      ['2928604', 'Santo Amaro'],
      ['2929206', 'São Francisco do Conde'],
      ['2904902', 'Cachoeira'],
      ['2929750', 'Saubara'],
    ],
  },
  {
    id: 'petrolina-juazeiro',
    label: 'Petrolina, Juazeiro e região',
    cities: [
      ['2611101', 'Petrolina (PE)'],
      ['2918407', 'Juazeiro (BA)'],
      ['2608750', 'Lagoa Grande (PE)'],
      ['2609808', 'Orocó (PE)'],
      ['2612604', 'Santa Maria da Boa Vista (PE)'],
      ['2907202', 'Casa Nova (BA)'],
      ['2909901', 'Curaçá (BA)'],
      ['2930774', 'Sobradinho (BA)'],
    ],
  },
];

async function fetchFocusedOpportunities() {
  const rows = [];
  for (let start = 0; ; start += 500) {
    const { data } = check(await supabase.from('radar_active_opportunities').select('*').order('id').range(start, start + 499));
    rows.push(...data);
    if (data.length < 500) break;
  }
  state.opportunities = rows.map((item) => ({ ...item, focus: classifyFocus(item) })).filter((item) => item.focus);
}

function scopedOpportunities() {
  const region = selectedRegion();
  const city = $('#city').value;
  const company = $('#company').value;
  const regionCodes = region && new Set(region.cities.map(([code]) => code));
  return state.opportunities.filter((item) =>
    (!regionCodes || regionCodes.has(item.municipality_code))
    && (!city || item.municipality_code === city)
    && (!company || item.focus.company === company));
}

function selectedRegion() {
  return regions.find((region) => region.id === $('#region').value);
}

function populateCitySelect() {
  const citySelect = $('#city');
  citySelect.replaceChildren(new Option('Todas as cidades', ''));
  for (const region of regions) {
    if (selectedRegion() && selectedRegion().id !== region.id) continue;
    const group = document.createElement('optgroup');
    group.label = region.label;
    for (const [code, name] of region.cities) group.append(new Option(name, code));
    citySelect.append(group);
  }
}

function updateCompanySelect() {
  const regionalOnly = selectedRegion()?.id === 'petrolina-juazeiro';
  const companySelect = $('#company');
  const tinetOption = [...companySelect.options].find((option) => option.value === 'Ti.Net');
  tinetOption.disabled = regionalOnly;
  companySelect.options[0].textContent = regionalOnly ? 'AutoControl · Monitoramento' : 'Ti.Net + AutoControl';
  if (regionalOnly && companySelect.value === 'Ti.Net') companySelect.value = '';
}

function renderRegionalCards(items) {
  if (selectedRegion()) return items.map(card).join('');
  return regions.map((region) => {
    const codes = new Set(region.cities.map(([code]) => code));
    const regionalItems = items.filter((item) => codes.has(item.municipality_code));
    if (!regionalItems.length) return '';
    return `<section class="region-group"><div class="region-heading"><h3>${escapeHtml(region.label)}</h3><span>${regionalItems.length} exibidas</span></div><div class="region-cards">${regionalItems.map(card).join('')}</div></section>`;
  }).join('');
}

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
  const score = item.focus.score;
  const description = String(item.description || '');
  const terms = item.focus.terms
    .slice(0, 4).map((term) => `<span class="tag">${escapeHtml(term)}</span>`).join('');
  return `<article class="card">
    <div class="score-ring" style="--score:${score}"><strong>${score}%</strong></div>
    <div><div class="workflow-row"><span class="workflow-status status-${status}">${labels[status] || 'Nova'}</span></div>
      <h3>${escapeHtml(item.title)}</h3>
      <div class="meta"><span>📍 ${escapeHtml(item.municipality)}</span><span>🏛️ ${escapeHtml(item.agency || 'Órgão público')}</span><span>⏰ ${/credenciamento/i.test(item.modality || '') ? 'Fim do credenciamento' : 'Prazo'}: ${escapeHtml(date(item.proposal_end_at))}</span><span>💰 ${escapeHtml(money(item.estimated_value))}</span></div>
      <p class="details">${escapeHtml(description.slice(0, 240))}${description.length > 240 ? '…' : ''}</p>
      <div class="meta"><span class="tag company-tag">${escapeHtml(item.focus.company)}</span><span class="tag">${escapeHtml(item.focus.category)}</span>${terms}</div>
    </div>
    <div class="card-actions">
      <button class="icon-btn ${item.favorite ? 'active' : ''}" title="Favoritar" data-action="favorite" data-id="${item.id}">★</button>
      ${item.url ? `<button class="icon-btn" title="Abrir fonte" data-action="source" data-id="${item.id}">↗</button>` : ''}
      <button class="icon-btn" title="Descartar" data-action="dismiss" data-id="${item.id}">×</button>
    </div>
  </article>`;
}

async function loadDashboard() {
  const region = selectedRegion();
  const city = $('#city').value;
  const items = scopedOpportunities();
  const stats = {
    total: items.length,
    open: items.filter((item) => item.status === 'aberta').length,
    hot: items.filter((item) => item.focus.score >= 70).length,
    favorites: items.filter((item) => item.favorite).length,
  };
  const scope = city ? 'na cidade selecionada' : region ? 'na região selecionada' : 'nas duas regiões';
  $('#stats').innerHTML = [
    ['Oportunidades', stats.total || 0, scope],
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

  let data = scopedOpportunities();
  const region = selectedRegion();
  const status = $('#status').value;
  if (status) data = data.filter((item) => item.status === status);
  if (state.view === 'favorites') data = data.filter((item) => item.favorite);
  const search = normalize($('#search').value.trim().slice(0, 100));
  if (search) data = data.filter((item) => normalize(`${item.title} ${item.description} ${item.agency}`).includes(search));
  data.sort((a, b) => Number(b.favorite) - Number(a.favorite)
    || b.focus.score - a.focus.score
    || String(a.proposal_end_at || '9999').localeCompare(String(b.proposal_end_at || '9999')));
  state.rows = new Map(data.map((item) => [String(item.id), item]));
  const headings = {
    favorites: ['Oportunidades favoritas', 'Itens separados para acompanhamento.'],
    opportunities: ['Oportunidades no foco', 'Ti.Net: telecom perto de Santo Amaro. AutoControl: monitoramento veicular nas duas regiões.'],
  };
  [$('#viewTitle').textContent, $('#viewDesc').textContent] = headings[state.view];
  if (region) $('#viewDesc').textContent += ` Região: ${region.label}.`;
  $('#count').textContent = `${data.length} encontradas`;
  $('#list').innerHTML = data.length ? renderRegionalCards(data) : '<div class="empty">Nenhuma oportunidade encontrada com estes filtros.</div>';
}

async function refresh() {
  await fetchFocusedOpportunities();
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
  $('#passwordScreen').hidden = true;
  $('#mainApp').hidden = true;
  $('#loginError').textContent = message;
}

function showPasswordSetup() {
  $('#loginScreen').hidden = true;
  $('#passwordScreen').hidden = false;
  $('#mainApp').hidden = true;
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
  if (authFlow === 'invite' || authFlow === 'recovery') {
    showPasswordSetup();
    return;
  }
  $('#loginScreen').hidden = true;
  $('#passwordScreen').hidden = true;
  $('#mainApp').hidden = false;
  $('#collectNowBtn').hidden = !collectorEmails.has(session.user.email?.toLowerCase());
  await refresh();
}

$('#collectNowBtn').addEventListener('click', async () => {
  const button = $('#collectNowBtn');
  button.disabled = true;
  button.textContent = 'Solicitando…';
  try {
    const { data: { session }, error } = await supabase.auth.getSession();
    if (error || !session) throw new Error('Sua sessão expirou. Entre novamente.');
    const response = await fetch('/.netlify/functions/collect-now', {
      method: 'POST',
      headers: { Authorization: `Bearer ${session.access_token}` },
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Não foi possível iniciar a coleta.');
    toast(result.message);
    const collectionsTab = document.querySelector('.nav[data-view="sync"]');
    collectionsTab.click();
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = 'Coletar agora';
  }
});

$('#passwordForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const password = $('#newPassword').value;
  if (password !== $('#confirmPassword').value) {
    $('#passwordError').textContent = 'As senhas não coincidem.';
    return;
  }
  const button = $('#passwordForm button[type=submit]');
  button.disabled = true;
  $('#passwordError').textContent = '';
  try {
    check(await supabase.auth.updateUser({ password }));
    $('#newPassword').value = '';
    $('#confirmPassword').value = '';
    authFlow = null;
    window.history.replaceState(null, '', window.location.pathname);
    await enter();
  } catch (error) {
    $('#passwordError').textContent = `Não foi possível salvar a senha: ${error.message}`;
  } finally {
    button.disabled = false;
  }
});

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

$('#resetPasswordBtn').addEventListener('click', async () => {
  const email = $('#loginEmail').value.trim();
  if (!email) { $('#loginError').textContent = 'Informe seu e-mail primeiro.'; return; }
  if (!supabase) { $('#loginError').textContent = 'O painel ainda não foi configurado.'; return; }
  const button = $('#resetPasswordBtn');
  button.disabled = true;
  try {
    check(await supabase.auth.resetPasswordForEmail(email));
    $('#loginError').textContent = 'Se esta conta estiver ativa, você receberá um novo link no e-mail.';
  } catch (error) {
    $('#loginError').textContent = `Não foi possível solicitar o link: ${error.message}`;
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
  try { await loadList(); } catch (error) { toast(`Erro: ${error.message}`); }
}));
$('#region').addEventListener('change', () => {
  populateCitySelect();
  updateCompanySelect();
  Promise.all([loadDashboard(), loadList()]).catch((error) => toast(error.message));
});
$('#city').addEventListener('change', () => Promise.all([loadDashboard(), loadList()]).catch((error) => toast(error.message)));
$('#company').addEventListener('change', () => Promise.all([loadDashboard(), loadList()]).catch((error) => toast(error.message)));
$('#status').addEventListener('change', () => loadList().catch((error) => toast(error.message)));
let searchTimer;
$('#search').addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadList().catch((error) => toast(error.message)), 350);
});
populateCitySelect();
updateCompanySelect();
if (!supabase) showLogin('Configure VITE_SUPABASE_URL e VITE_SUPABASE_PUBLISHABLE_KEY no Netlify.');
else if (linkError) showLogin('Este link expirou. Solicite um novo convite de acesso.');
else enter().catch((error) => showLogin(`Erro ao carregar: ${error.message}`));
