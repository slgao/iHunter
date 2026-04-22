// --- State ---
let currentProductId = parseInt(localStorage.getItem('currentProductId')) || null;
let currentFilter = 'all';
let allLeads = [];
let suggestions = [];

const $ = id => document.getElementById(id);

// --- Utilities ---
function showToast(msg) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

function setLoading(btn, loading, text = '') {
  btn.disabled = loading;
  btn.innerHTML = loading ? `<span class="loading"></span> ${text || 'Working…'}` : btn._label || btn.innerHTML;
  if (!loading && btn._label) btn.innerHTML = btn._label;
}

function setBtnLabel(btn) { btn._label = btn.innerHTML; }

async function fetchJSON(url, opts = {}) {
  const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const err = new Error(body.detail || 'Request failed');
    err.status = res.status;
    throw err;
  }
  return res.json();
}

async function refreshStats() {
  try {
    const s = await fetchJSON('/api/stats');
    $('statLeads').textContent = `${s.total_leads} leads`;
    $('statContacted').textContent = `${s.contacted} contacted`;
    $('statEmails').textContent = `${s.total_outreaches} emails`;
  } catch {}
}

function normalizeUrl(url) {
  if (!url) return '';
  return /^https?:\/\//i.test(url) ? url : 'https://' + url;
}

function setCurrentProduct(id) {
  currentProductId = id;
  id ? localStorage.setItem('currentProductId', id) : localStorage.removeItem('currentProductId');
}

function showSections() {
  $('sectionAnalysis').classList.remove('hidden');
  $('sectionRealImport').classList.remove('hidden');
}

function hideSections() {
  ['sectionAnalysis','sectionRealImport','sectionLeads'].forEach(id => $(id).classList.add('hidden'));
}

function resetToStep1() {
  setCurrentProduct(null);
  hideSections();
  $('btnSaveProduct').innerHTML = '<span>Save Product &amp; Analyze Market</span>';
  $('btnSaveProduct').disabled = false;
  showToast('Database was reset — please re-save your product in Step 1.');
  $('sectionProduct').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function scrollSwitcher(dir) {
  const el = $('productList');
  el.scrollBy({ left: dir * 200, behavior: 'smooth' });
}

function updateSwitcherArrows() {
  const el = $('productList');
  const left = $('switcherLeft');
  const right = $('switcherRight');
  if (!el || !left || !right) return;
  left.disabled = el.scrollLeft <= 0;
  right.disabled = el.scrollLeft + el.clientWidth >= el.scrollWidth - 1;
}

function renderProductSwitcher(products) {
  const el = $('productList');
  if (!products.length) {
    el.innerHTML = '<span style="color:#ccc;font-size:13px">No products yet</span>';
    updateSwitcherArrows();
    return;
  }
  el.innerHTML = products.map(p => {
    const meta = [p.category, p.origin_city].filter(Boolean).join(' · ');
    return `<div class="switcher-tab ${p.id === currentProductId ? 'active' : ''}" onclick="selectProduct(${p.id})" title="${escapeHtml(p.name)}${meta ? ' — ' + escapeHtml(meta) : ''}">
      <span class="switcher-tab-name">${escapeHtml(p.name)}</span>
      ${meta ? `<span class="switcher-tab-meta">${escapeHtml(meta)}</span>` : ''}
      <span class="switcher-tab-del" onclick="deleteProduct(event,${p.id})" title="Delete product">×</span>
    </div>`;
  }).join('');
  el.removeEventListener('scroll', updateSwitcherArrows);
  el.addEventListener('scroll', updateSwitcherArrows);
  requestAnimationFrame(updateSwitcherArrows);
}

async function selectProduct(id) {
  setCurrentProduct(id);
  hideSections();
  allLeads = [];
  $('leadsTable').innerHTML = '';
  $('analysisContent').innerHTML = '';

  const products = await fetchJSON('/api/products');
  renderProductSwitcher(products);

  showSections();

  // Restore saved analysis
  const product = products.find(p => p.id === id);
  if (product?.analysis) {
    try {
      renderAnalysis(typeof product.analysis === 'string' ? JSON.parse(product.analysis) : product.analysis);
      $('sectionAnalysis').classList.remove('hidden');
    } catch (e) {}
  }

  const leads = await fetchJSON(`/api/leads?product_id=${id}`);
  if (leads.length > 0) {
    allLeads = leads;
    $('sectionLeads').classList.remove('hidden');
    renderLeads();
  }
  await refreshStats();
  $('sectionRealImport').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function deleteProduct(event, id) {
  event.stopPropagation();
  const products = await fetchJSON('/api/products');
  const p = products.find(x => x.id === id);
  if (!confirm(`Delete "${p ? p.name : 'this product'}" and all its leads? This cannot be undone.`)) return;
  await fetchJSON(`/api/products/${id}`, { method: 'DELETE' });
  if (currentProductId === id) {
    setCurrentProduct(null);
    hideSections();
    allLeads = [];
  }
  const updated = await fetchJSON('/api/products');
  renderProductSwitcher(updated);
  await refreshStats();
  showToast('Product deleted.');
}

$('btnNewProduct').addEventListener('click', () => {
  setCurrentProduct(null);
  hideSections();
  allLeads = [];
  // Clear form for new entry
  ['productName','productDesc','priceRange','moq'].forEach(id => $(id).value = '');
  $('productCategory').value = '';
  $('originCity').value = 'Shenzhen';
  $('btnSaveProduct').innerHTML = '<span>Save Product &amp; Analyze Market</span>';
  $('btnSaveProduct').disabled = false;
  $('sectionProduct').scrollIntoView({ behavior: 'smooth', block: 'start' });
  // Deselect all cards
  document.querySelectorAll('.product-card').forEach(c => c.classList.remove('active'));
});

// --- Step 1: Save product + analyze ---
$('productForm').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('btnSaveProduct');
  setLoading(btn, true, 'Saving & Analyzing…');

  const body = {
    name: $('productName').value.trim(),
    category: $('productCategory').value,
    description: $('productDesc').value.trim(),
    price_range: $('priceRange').value.trim() || 'N/A',
    moq: $('moq').value.trim() || 'N/A',
    origin_city: $('originCity').value.trim() || 'Shenzhen',
  };

  try {
    const product = await fetchJSON('/api/products', { method: 'POST', body: JSON.stringify(body) });
    setCurrentProduct(product.id);
    const [analysis, products] = await Promise.all([
      fetchJSON(`/api/products/${currentProductId}/analyze`, { method: 'POST' }),
      fetchJSON('/api/products'),
    ]);
    renderAnalysis(analysis);
    renderProductSwitcher(products);
    showSections();
    $('sectionAnalysis').scrollIntoView({ behavior: 'smooth', block: 'start' });
    showToast('Product saved! Market analysis complete.');
    btn.innerHTML = '✓ Product Saved';
  } catch (err) {
    showToast('Error: ' + err.message);
    btn.innerHTML = '<span>Save Product &amp; Analyze Market</span>';
    btn.disabled = false;
  }
});

// --- Market Analysis ---
function levelBadge(val) {
  if (!val) return '';
  const cls = val === 'high' ? 'green' : val === 'medium' ? 'orange' : 'red';
  return `<span class="badge ${cls}">${val}</span>`;
}

function renderAnalysis(a) {
  const sectors = (a.target_sectors || []).map(s => `<span class="badge">${s}</span>`).join('');
  const cities = (a.top_german_cities || []).map(c => `<span class="badge">${c}</span>`).join('');
  const competitors = (a.key_competitors || []).map(c => `<span class="badge orange">${c}</span>`).join('');

  $('analysisContent').innerHTML = `
    <div class="analysis-card">
      <h4>Market Fit Score</h4>
      <div class="score-big">${a.market_fit_score || '—'}<span style="font-size:20px">/10</span></div>
      <div class="score-label">Demand: ${levelBadge(a.demand_level)}</div>
    </div>
    <div class="analysis-card">
      <h4>B2B Potential</h4>
      <div style="margin:8px 0">${levelBadge(a.b2b_potential)}</div>
      <h4 style="margin-top:16px">B2C Potential</h4>
      <div style="margin-top:8px">${levelBadge(a.b2c_potential)}</div>
    </div>
    <div class="analysis-card">
      <h4>Price Positioning</h4>
      <div class="badge orange" style="font-size:14px;padding:6px 16px">${a.price_positioning || '—'}</div>
    </div>
    <div class="analysis-card wide">
      <h4>Target Sectors</h4>
      <div class="badge-list">${sectors}</div>
    </div>
    <div class="analysis-card">
      <h4>Top German Cities</h4>
      <div class="badge-list">${cities}</div>
    </div>
    <div class="analysis-card full">
      <h4>Key Competitors</h4>
      <div class="badge-list">${competitors}</div>
    </div>
    <div class="analysis-card full">
      <h4>Import Considerations</h4>
      <p class="insight-text">${a.import_considerations || '—'}</p>
    </div>
    <div class="analysis-card full">
      <h4>Market Insight</h4>
      <p class="insight-text">${a.market_insight || '—'}</p>
    </div>`;
}

// --- Step 2: Real Company Import ---
function switchImportTab(btn, tab) {
  document.querySelectorAll('.import-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  $('importSuggest').classList.toggle('hidden', tab !== 'suggest');
  $('importSingle').classList.toggle('hidden', tab !== 'single');
  $('importBulk').classList.toggle('hidden', tab !== 'bulk');
}

// AI Suggestions
$('btnSuggest').addEventListener('click', async () => {
  if (!currentProductId) return showToast('Please save a product first (Step 1)');
  const btn = $('btnSuggest');
  const count = $('suggestCount').value;
  const cities = $('suggestCities').value.trim();
  const citiesParam = cities ? `&cities=${encodeURIComponent(cities)}` : '';
  setLoading(btn, true, 'AI is finding real companies…');
  $('suggestResults').innerHTML = '';

  try {
    suggestions = await fetchJSON(
      `/api/products/${currentProductId}/suggest-companies?count=${count}${citiesParam}`,
      { method: 'POST' }
    );
    renderSuggestions(suggestions);
  } catch (err) {
    showToast('Error: ' + err.message);
  }
  btn.innerHTML = '✨ Get AI Suggestions';
  btn.disabled = false;
});

function renderSuggestions(list) {
  if (!list.length) {
    $('suggestResults').innerHTML = '<p style="color:#aaa;padding:16px 0">No suggestions returned.</p>';
    return;
  }

  const importedWebsites = new Set(
    allLeads.map(l => (l.website || '').toLowerCase().replace(/^https?:\/\//, '').replace(/\/$/, ''))
  );

  const isImported = c => {
    if (!c.website) return false;
    const norm = c.website.toLowerCase().replace(/^https?:\/\//, '').replace(/\/$/, '');
    return importedWebsites.has(norm);
  };

  const cards = list.map((c, i) => {
    const already = isImported(c);
    return `
    <div class="suggest-card${already ? ' suggest-already' : ''}" id="scard-${i}">
      <input type="checkbox" class="suggest-checkbox" id="schk-${i}" ${already ? '' : 'checked'} ${already ? 'disabled' : `onchange="toggleSuggestCard(${i})"`} />
      <div class="suggest-info">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <span class="suggest-name">${c.company_name}</span>
          <span class="suggest-type-badge">${c.type || 'company'}</span>
          <span class="suggest-type-badge" style="background:#f3e5f5;color:#6a1b9a">${c.size || ''}</span>
          ${already ? '<span class="suggest-type-badge" style="background:#e8f5e9;color:#2e7d32">✓ imported</span>' : ''}
        </div>
        <div class="suggest-meta">${c.city || ''}${c.industry ? ' · ' + c.industry : ''}</div>
        <div class="suggest-reason">${c.reason || ''}</div>
      </div>
      <span class="suggest-website">${c.website || '—'}</span>
    </div>`;
  }).join('');

  $('suggestResults').innerHTML = `
    <div class="suggest-sticky-bar">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <button class="btn btn-primary" onclick="importSelectedSuggestions()">
          ↓ Import Selected &amp; Find Emails
        </button>
        <button class="btn btn-outline btn-sm" onclick="selectAllSuggestions(true)">All</button>
        <button class="btn btn-outline btn-sm" onclick="selectAllSuggestions(false)">None</button>
        <span id="suggestImportStatus" style="font-size:13px;color:#888"></span>
      </div>
      <p class="suggest-disclaimer">
        ⚠️ AI knowledge has a training cutoff — well-known companies are reliable, but smaller niche ones may be outdated or hallucinated. Suggested domains can also be wrong (e.g. <code>.de</code> instead of <code>.eu</code>) — always click the link to verify before outreach. Emails are scraped from the real website, never generated by AI.
      </p>
    </div>
    <div class="suggest-grid" style="margin-top:12px">${cards}</div>`;
}

function toggleSuggestCard(i) {
  $(`scard-${i}`).classList.toggle('selected', $(`schk-${i}`).checked);
}

function selectAllSuggestions(val) {
  suggestions.forEach((_, i) => {
    const chk = $(`schk-${i}`);
    if (chk.disabled) return;
    chk.checked = val;
    $(`scard-${i}`).classList.toggle('selected', val);
  });
}

async function importSelectedSuggestions() {
  const selected = suggestions.filter((_, i) => $(`schk-${i}`) && $(`schk-${i}`).checked);
  if (!selected.length) return showToast('Select at least one company');

  const statusEl = $('suggestImportStatus');
  statusEl.textContent = `Importing ${selected.length} companies…`;
  const btn = document.querySelector('#suggestResults .btn-primary');
  if (btn) { btn.disabled = true; btn.innerHTML = `<span class="loading"></span> Importing…`; }

  const raw = selected.map(c =>
    `${c.company_name} | ${c.website || ''} | ${c.city || ''} | ${c.industry || ''} | ${c.reason || ''} | ${c.size || ''}`
  ).join('\n');

  try {
    const result = await fetchJSON('/api/real-leads/bulk-import', {
      method: 'POST',
      body: JSON.stringify({ raw_text: raw, product_id: currentProductId }),
    });

    let si = 0;
    suggestions.forEach((_, i) => {
      if (!$(`schk-${i}`) || !$(`schk-${i}`).checked) return;
      const r = result.results[si++];
      const card = $(`scard-${i}`);
      if (r?.email) {
        card.style.borderColor = '#2e7d32';
        card.style.background = '#f1f8f1';
        card.querySelector('.suggest-website').innerHTML = `<span style="color:#2e7d32;font-size:12px">✓ ${r.email}</span>`;
      } else if (r?.status === 'skipped') {
        card.style.borderColor = '#bbb';
        card.querySelector('.suggest-reason').textContent = '↩ Already imported';
      } else {
        card.querySelector('.suggest-website').innerHTML = `<span style="color:#999;font-size:12px">✗ no email</span>`;
      }
    });

    statusEl.textContent = `✓ ${result.imported} imported, ${result.total - result.imported} skipped`;
    if (btn) { btn.disabled = false; btn.innerHTML = '↓ Import Selected &amp; Find Emails'; }
    await loadLeads();
    $('sectionLeads').classList.remove('hidden');
    await refreshStats();
  } catch (err) {
    statusEl.textContent = 'Error: ' + err.message;
    if (btn) { btn.disabled = false; btn.innerHTML = '↓ Import Selected &amp; Find Emails'; }
  }
}

// Single entry
$('btnImportSingle').addEventListener('click', async () => {
  const company = $('importCompany').value.trim();
  const website = $('importWebsite').value.trim();
  if (!company) return showToast('Please enter a company name');
  if (!currentProductId) return showToast('Please save a product first (Step 1)');

  const btn = $('btnImportSingle');
  setLoading(btn, true, 'Scraping website…');

  try {
    const result = await fetchJSON('/api/real-leads/import', {
      method: 'POST',
      body: JSON.stringify({
        company_name: company,
        website: website || null,
        city: $('importCity').value.trim() || null,
        industry: $('importIndustry').value.trim() || null,
        contact_name: $('importContact').value.trim() || null,
        product_id: currentProductId,
      }),
    });

    const tag = result.hunter_used
      ? '<span class="source-tag hunter">Hunter.io</span>'
      : result.email ? '<span class="source-tag">Scraped</span>' : '';

    $('importSingleResult').innerHTML = `
      <div class="import-result-row ${result.email ? 'success' : 'error'}" style="margin:12px 28px 0">
        <span class="company">${company}</span>
        ${result.email
          ? `<span class="email-found">✓ ${result.email}</span> ${tag}
             ${result.source_page ? `<small style="color:#aaa">(${result.source_page})</small>` : ''}`
          : `<span class="no-email">✗ No email found${result.scrape_error ? ' — ' + result.scrape_error : ''}</span>`}
      </div>`;

    ['importCompany','importWebsite','importCity','importIndustry','importContact'].forEach(id => $(id).value = '');
    await loadLeads();
    $('sectionLeads').classList.remove('hidden');
    await refreshStats();
    showToast(result.email ? `Imported with email` : `Imported (no email found)`);
  } catch (err) {
    $('importSingleResult').innerHTML = `<div class="import-result-row error" style="margin:12px 28px 0">Error: ${err.message}</div>`;
  }
  btn.innerHTML = 'Find Email & Import';
  btn.disabled = false;
});

// Bulk paste
$('btnImportBulk').addEventListener('click', async () => {
  const raw = $('bulkText').value.trim();
  if (!raw) return showToast('Please paste some companies first');
  if (!currentProductId) return showToast('Please save a product first (Step 1)');

  const btn = $('btnImportBulk');
  const lines = raw.split('\n').filter(l => l.trim()).length;
  setLoading(btn, true, `Importing ${lines} companies…`);

  try {
    const result = await fetchJSON('/api/real-leads/bulk-import', {
      method: 'POST',
      body: JSON.stringify({ raw_text: raw, product_id: currentProductId }),
    });

    const rows = result.results.map(r => {
      const tag = r.hunter_used ? '<span class="source-tag hunter">Hunter.io</span>'
                : r.email ? '<span class="source-tag">Scraped</span>' : '';
      if (r.status === 'ok') {
        return `<div class="import-result-row success">
          <span class="company">${r.company}</span>
          ${r.email ? `<span class="email-found">✓ ${r.email}</span> ${tag}` : '<span class="no-email">✗ No email</span>'}
        </div>`;
      }
      return `<div class="import-result-row ${r.status}">
        <span class="company">${r.company}</span>
        <span class="no-email">${r.status === 'skipped' ? '↩ ' : '✗ '}${r.reason}</span>
      </div>`;
    }).join('');

    $('importBulkResult').innerHTML = `
      <div style="padding:12px 28px 0">
        <p style="margin-bottom:10px;font-size:13px;color:#666">${result.imported} imported · ${result.total - result.imported} skipped</p>
        ${rows}
      </div>`;

    await loadLeads();
    $('sectionLeads').classList.remove('hidden');
    await refreshStats();
    showToast(`Imported ${result.imported} of ${result.total} companies`);
  } catch (err) {
    $('importBulkResult').innerHTML = `<div class="import-result-row error" style="margin:12px 28px 0">Error: ${err.message}</div>`;
  }
  btn.innerHTML = 'Import All & Find Emails';
  btn.disabled = false;
});

// --- Step 3: Lead Dashboard ---
async function loadLeads() {
  const res = await fetchJSON(`/api/leads?product_id=${currentProductId}`);
  allLeads = res;
  renderLeads();
  await refreshStats();
}

let sortCol = null;
let sortDir = 1; // 1 = asc, -1 = desc

function sortLeads(col) {
  if (sortCol === col) sortDir *= -1;
  else { sortCol = col; sortDir = 1; }
  renderLeads();
}

function renderLeads() {
  let filtered = allLeads.filter(l =>
    currentFilter === 'all' ? true : l.status === currentFilter
  );

  if (sortCol) {
    filtered = [...filtered].sort((a, b) => {
      const av = (a[sortCol] || '').toString().toLowerCase();
      const bv = (b[sortCol] || '').toString().toLowerCase();
      return av < bv ? -sortDir : av > bv ? sortDir : 0;
    });
  }

  if (filtered.length === 0) {
    $('leadsTable').innerHTML = `<div class="empty-state"><div class="icon">🔍</div><p>No leads for this filter.</p></div>`;
    return;
  }

  const emailStatusLabel = s => {
    const map = {
      valid: '<span class="email-status valid">✓ valid</span>',
      invalid_format: '<span class="email-status invalid_format">✗ bad format</span>',
      invalid_domain: '<span class="email-status invalid_domain">✗ bad domain</span>',
      unverifiable: '<span class="email-status unverifiable">? DNS fail</span>',
      not_found: '<span class="email-status invalid_domain">✗ not found</span>',
    };
    return map[s] || '<span class="email-status unverified">unverified</span>';
  };

  const arrow = col => {
    if (sortCol !== col) return '<span class="sort-arrow">↕</span>';
    return `<span class="sort-arrow active">${sortDir === 1 ? '↑' : '↓'}</span>`;
  };

  const rows = filtered.map(l => {
    let allEmailsList = [];
    try { allEmailsList = l.all_emails ? JSON.parse(l.all_emails) : []; } catch {}
    const extras = allEmailsList.filter(e => e.email !== l.email);

    return `
    <tr>
      <td><span class="source-badge ${l.source === 'real_import' ? 'source-real' : 'source-ai'}">
        ${l.source === 'real_import' ? '✓ real' : 'AI'}
      </span></td>
      <td>
        <strong>${l.company_name || l.contact_name || '—'}</strong>
        ${l.website
          ? `<br><a href="${normalizeUrl(l.website)}" target="_blank" class="website-link">
               🔗 ${l.website}
             </a>`
          : ''}
      </td>
      <td>
        ${l.email
          ? (() => {
              const primaryMeta = allEmailsList.find(e => e.email === l.email);
              return `<a href="mailto:${l.email}" style="color:#1565c0;font-size:13px">${l.email}</a>`
                + (primaryMeta ? `<span class="email-page-label" title="Found on: ${primaryMeta.source_page}">${primaryMeta.page_label}</span>` : '');
            })()
          : l.scrape_error
            ? `<span class="scrape-error-hint" title="${l.scrape_error.replace(/"/g,'&quot;')}">⚠ ${l.scrape_error.length > 35 ? l.scrape_error.slice(0, 35) + '…' : l.scrape_error}</span>`
            : '<span style="color:#ccc">—</span>'}
        ${extras.length ? `<div class="extra-emails">${extras.map(e =>
          `<div class="extra-email-item">
             <a href="mailto:${e.email}" class="extra-email-link">${e.email}</a>
             <span class="email-page-label" title="Found on: ${e.source_page}">${e.page_label}</span>
           </div>`).join('')}</div>` : ''}
        <div style="margin-top:4px;display:flex;align-items:center;gap:6px">
          <span id="estatus-${l.id}">${emailStatusLabel(l.email_status)}</span>
          ${(!l.email_status || l.email_status === 'unverified') && l.email
            ? `<button class="btn-link" onclick="verifyEmail(${l.id}, document.getElementById('estatus-${l.id}'))">verify</button>`
            : ''}
        </div>
      </td>
      <td class="td-truncate" title="${(l.city || '').replace(/"/g,'&quot;')}">${l.city || '—'}</td>
      <td class="td-truncate" title="${(l.industry || '').replace(/"/g,'&quot;')}">${l.industry || '—'}</td>
      <td>${l.size ? `<span class="size-badge size-${l.size}">${l.size}</span>` : '—'}</td>
      <td class="td-truncate" style="color:#555" title="${(l.description || '').replace(/"/g,'&quot;')}">${l.description || '—'}</td>
      <td>
        <select class="status-select" onchange="updateStatus(${l.id}, this.value)">
          ${['new','contacted','replied','qualified','closed'].map(s =>
            `<option value="${s}" ${l.status===s?'selected':''}>${s}</option>`
          ).join('')}
        </select>
      </td>
      <td>
        <button class="btn btn-primary btn-sm" onclick="openOutreach(${l.id})">✉ Email</button>
      </td>
    </tr>`;
  }).join('');

  $('leadsTable').innerHTML = `
    <table>
      <colgroup>
        <col class="col-source"><col class="col-company"><col class="col-email">
        <col class="col-city"><col class="col-industry"><col class="col-size">
        <col class="col-about"><col class="col-status"><col class="col-action">
      </colgroup>
      <thead><tr>
        <th>Source</th>
        <th class="sortable" onclick="sortLeads('company_name')">Company ${arrow('company_name')}</th>
        <th class="sortable" onclick="sortLeads('email')">Email ${arrow('email')}</th>
        <th class="sortable" onclick="sortLeads('city')">City ${arrow('city')}</th>
        <th class="sortable" onclick="sortLeads('industry')">Industry ${arrow('industry')}</th>
        <th class="sortable" onclick="sortLeads('size')">Size ${arrow('size')}</th>
        <th>About</th>
        <th class="sortable" onclick="sortLeads('status')">Status ${arrow('status')}</th>
        <th></th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <p style="padding:12px 28px;color:#aaa;font-size:12px">
      ${filtered.length} of ${allLeads.length} leads
    </p>`;
}

document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.filter;
    renderLeads();
  });
});

async function updateStatus(id, status) {
  try {
    await fetchJSON(`/api/leads/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) });
    const lead = allLeads.find(l => l.id === id);
    if (lead) lead.status = status;
    await refreshStats();
  } catch (err) {
    showToast('Error: ' + err.message);
  }
}

// --- Email Verification ---
async function verifyEmail(leadId, badgeEl) {
  badgeEl.className = 'email-status verifying';
  badgeEl.textContent = 'checking…';
  try {
    const result = await fetchJSON(`/api/leads/${leadId}/verify-email`, { method: 'POST' });
    badgeEl.className = `email-status ${result.status}`;
    badgeEl.textContent = result.status === 'valid' ? '✓ valid' : `✗ ${result.status.replace(/_/g, ' ')}`;
    badgeEl.title = result.detail;
    const lead = allLeads.find(l => l.id === leadId);
    if (lead) lead.email_status = result.status;
  } catch {
    badgeEl.className = 'email-status unverifiable';
    badgeEl.textContent = '? error';
  }
}

$('btnVerifyAll').addEventListener('click', async () => {
  if (!currentProductId) return;
  const btn = $('btnVerifyAll');
  setLoading(btn, true, 'Verifying…');
  try {
    const result = await fetchJSON(`/api/products/${currentProductId}/verify-all-emails`, { method: 'POST' });
    result.results.forEach(r => {
      const lead = allLeads.find(l => l.id === r.lead_id);
      if (lead) lead.email_status = r.status;
    });
    renderLeads();
    showToast(`Verified ${result.verified} emails`);
  } catch (err) {
    showToast('Error: ' + err.message);
  }
  btn.innerHTML = '✔ Verify All Emails';
  btn.disabled = false;
});

// --- Outreach Modal ---
async function openOutreach(leadId) {
  $('outreachModal').classList.remove('hidden');
  $('outreachContent').innerHTML = `
    <div style="text-align:center;padding:40px">
      <span class="loading" style="border-color:#ccc;border-top-color:#1565c0;width:32px;height:32px"></span>
      <p style="margin-top:16px;color:#888">AI is writing your email…</p>
    </div>`;

  try {
    const data = await fetchJSON(`/api/leads/${leadId}/outreach`, { method: 'POST' });
    renderOutreach(data, leadId);
    await refreshStats();
  } catch (err) {
    $('outreachContent').innerHTML = `<p style="color:red;padding:24px">Error: ${err.message}</p>`;
  }
}

function renderOutreach(data, leadId) {
  $('outreachContent').innerHTML = `
    <div class="email-tabs">
      <button class="tab-btn active" onclick="switchTab(this,'de')">🇩🇪 German</button>
      <button class="tab-btn" onclick="switchTab(this,'en')">🇬🇧 English</button>
    </div>
    <div id="emailDe" class="email-panel">
      <div class="email-block">
        <div class="email-subject">Subject: <span>${escapeHtml(data.subject_de)}</span></div>
        <div class="email-body">${escapeHtml(data.body_de)}</div>
        <button class="btn btn-outline btn-sm copy-btn" onclick="copyText(\`${escapeBacktick(data.body_de)}\`)">Copy German Email</button>
      </div>
    </div>
    <div id="emailEn" class="email-panel" style="display:none">
      <div class="email-block">
        <div class="email-subject">Subject: <span>${escapeHtml(data.subject_en)}</span></div>
        <div class="email-body">${escapeHtml(data.body_en)}</div>
        <button class="btn btn-outline btn-sm copy-btn" onclick="copyText(\`${escapeBacktick(data.body_en)}\`)">Copy English Email</button>
      </div>
    </div>
    <div style="margin-top:8px;padding-top:16px;border-top:1px solid #f0f0f0;display:flex;gap:10px">
      <button class="btn btn-success btn-sm" onclick="markContacted(${leadId})">Mark as Contacted</button>
      <button class="btn btn-outline btn-sm" onclick="closeModal()">Close</button>
    </div>`;
}

function switchTab(btn, lang) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  $('emailDe').style.display = lang === 'de' ? 'block' : 'none';
  $('emailEn').style.display = lang === 'en' ? 'block' : 'none';
}

function escapeHtml(str) {
  return (str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeBacktick(str) {
  return (str || '').replace(/`/g, '\\`').replace(/\$/g, '\\$');
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => showToast('Copied to clipboard!'));
}

async function markContacted(leadId) {
  await updateStatus(leadId, 'contacted');
  renderLeads();
  closeModal();
}

function closeModal() { $('outreachModal').classList.add('hidden'); }
$('btnCloseModal').addEventListener('click', closeModal);
$('modalOverlay').addEventListener('click', closeModal);

// --- Init ---
async function init() {
  await refreshStats();
  try {
    const products = await fetchJSON('/api/products');
    renderProductSwitcher(products);

    if (!currentProductId) return;
    if (!products.some(p => p.id === currentProductId)) {
      resetToStep1();
      return;
    }
    showSections();
    const leads = await fetchJSON(`/api/leads?product_id=${currentProductId}`);
    if (leads.length > 0) {
      allLeads = leads;
      $('sectionLeads').classList.remove('hidden');
      renderLeads();
    }
  } catch {}
}

init();
