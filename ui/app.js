/**
 * ui/app.js - Calibration Trending System Desktop Application Engine.
 * Supports centralized decimal formatting, multi-point characterization matrix,
 * alerts & reviews workspace, 33622A factor inspection, and calculation traceability.
 */

const state = {
  currentView: 'dashboard',
  dashboardData: null,
  activeAssetId: null,
  activeTestPointId: null,
  activeAssetDetail: null,
  htbasicContext: null,
  activeTheme: 'dark',
  chartMode: 'primary',
  chartInstance: null,
  preflightFilter: 'all',
  filters: {
    status: 'all',
    category: 'all',
    set: 'all',
    query: ''
  }
};

const api = () => window.pywebview.api;

window.pendingMultiPointImport = null;

// -----------------------------------------------------------------------------
// Centralized Metrology Decimal & Uncertainty Formatter
// -----------------------------------------------------------------------------
function formatMeasured(val, nominal, category, unit) {
  if (val === null || val === undefined || isNaN(val)) return '—';
  const num = parseFloat(val);

  if (category === 'dcv_reference' || unit === 'V') {
    return `${num.toFixed(9)} V`;
  }
  if (category === 'waveform_generator' || unit === 'dB') {
    const sign = num > 0 ? '+' : '';
    return `${sign}${num.toFixed(5)} dB`;
  }
  if (category === 'ac_divider' || unit === 'Ratio') {
    return num.toFixed(5);
  }

  // Standard Resistors by Decade
  // Use the actual number magnitude (num) directly so units like "100 mΩ" don't parse as 100 Ω
  const nom = Math.abs(num);
  if (nom < 0.5) return `${num.toFixed(9)} Ω`;       // 0.1 Ω -> 9 decimals
  if (nom < 5.0) return `${num.toFixed(8)} Ω`;       // 1 Ω   -> 8 decimals
  if (nom < 50.0) return `${num.toFixed(7)} Ω`;      // 10 Ω  -> 7 decimals
  if (nom < 500.0) return `${num.toFixed(6)} Ω`;     // 100 Ω -> 6 decimals
  if (nom < 5000.0) return `${num.toFixed(5)} Ω`;    // 1 kΩ  -> 5 decimals
  if (nom < 50000.0) return `${num.toFixed(4)} Ω`;   // 10 kΩ -> 4 decimals
  if (nom < 500000.0) return `${num.toFixed(3)} Ω`;  // 100 kΩ -> 3 decimals
  return `${Math.round(num).toLocaleString('en-US')} Ω`; // 1 MΩ to 1 GΩ -> 0 decimals
}

function formatBound(val, nominal, category, unit) {
  if (val === null || val === undefined || isNaN(val)) return '—';
  const num = parseFloat(val);
  if (category === 'dcv_reference' || unit === 'V') return num.toFixed(9);
  if (category === 'waveform_generator' || unit === 'dB') return `${num > 0 ? '+' : ''}${num.toFixed(5)}`;
  if (category === 'ac_divider' || unit === 'Ratio') return num.toFixed(5);

  const nom = nominal !== undefined && nominal !== null ? Math.abs(parseFloat(nominal)) : Math.abs(num);
  if (nom < 0.5) return num.toFixed(9);
  if (nom < 5.0) return num.toFixed(8);
  if (nom < 50.0) return num.toFixed(7);
  if (nom < 500.0) return num.toFixed(6);
  if (nom < 5000.0) return num.toFixed(5);
  if (nom < 50000.0) return num.toFixed(4);
  if (nom < 500000.0) return num.toFixed(3);
  return Math.round(num).toLocaleString('en-US');
}

function formatUncertainty(c, category, nominal) {
  if (category === 'dcv_reference') {
    if (c.uncertainty !== null && c.uncertainty !== undefined) return `${parseFloat(c.uncertainty).toFixed(1)} nV`;
    if (c.mu_relative && Number(nominal) === 10) return `${(c.mu_relative * 10.0 * 1e9).toFixed(1)} nV`;
    return '—';
  }
  if (category === 'ac_divider') {
    if (c.uncertainty !== null && c.uncertainty !== undefined) return `${parseFloat(c.uncertainty).toFixed(1)} ppm`;
    if (c.mu_relative) return `${(c.mu_relative * 1e6).toFixed(1)} ppm`;
    return '—';
  }
  if (category === 'waveform_generator') {
    return '—';
  }
  // Standard Resistors: relative ratio converted to ppm (1e6)
  if (c.mu_relative !== null && c.mu_relative !== undefined && c.mu_relative !== 0) {
    return `${(c.mu_relative * 1e6).toFixed(2)} ppm`;
  }
  if (c.uncertainty !== null && c.uncertainty !== undefined && c.uncertainty !== 0) {
    return `${(parseFloat(c.uncertainty) * 1e6).toFixed(2)} ppm`;
  }
  return '—';
}

// -----------------------------------------------------------------------------
// Router & View Mounting
// -----------------------------------------------------------------------------
const router = {
  async navigate(view, params = {}) {
    state.currentView = view;
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

    const root = document.getElementById('appRoot');
    const title = document.getElementById('currentViewTitle');
    const breadcrumb = document.getElementById('breadcrumbDetail');
    breadcrumb.style.display = 'none';

    if (view === 'dashboard') {
      document.getElementById('navDashboard')?.classList.add('active');
      title.textContent = 'Fleet Telemetry Overview';
      root.innerHTML = `<div style="text-align:center; padding:40px; color:var(--ink-muted);">Loading fleet status...</div>`;
      state.dashboardData = await api().get_dashboard();
      state.activeTheme = state.dashboardData.theme || 'dark';
      applyTheme(state.activeTheme);
      updateSidebarAlertBadge();
      renderDashboard();
    } 
    else if (view === 'alerts') {
      document.getElementById('navAlerts')?.classList.add('active');
      title.textContent = 'Alerts & Quality Reviews';
      root.innerHTML = `<div style="text-align:center; padding:40px; color:var(--ink-muted);">Loading quality alerts...</div>`;
      if (!state.dashboardData) state.dashboardData = await api().get_dashboard();
      renderAlertsView();
    }
    else if (view === 'asset_detail') {
      title.textContent = 'Standard Asset Detail';
      state.activeAssetId = params.asset_id;
      state.activeTestPointId = params.tp_id || null;
      root.innerHTML = `<div style="text-align:center; padding:40px; color:var(--ink-muted);">Loading asset telemetry...</div>`;
      state.activeAssetDetail = await api().get_asset_detail(state.activeAssetId, state.activeTestPointId);
      renderAssetDetail();
    }
    else if (view === 'htbasic') {
      document.getElementById('navHTBasic')?.classList.add('active');
      title.textContent = 'HTBasic 3458A Cal Factor Files';
      root.innerHTML = `<div style="text-align:center; padding:40px; color:var(--ink-muted);">Compiling pre-flight status...</div>`;
      state.htbasicContext = await api().get_htbasic_context();
      renderHTBasic();
    }
    else if (view === 'settings') {
      document.getElementById('navSettings')?.classList.add('active');
      title.textContent = 'Lab Setup & Database Synchronization';
      renderSettings();
    }
  }
};

function updateSidebarAlertBadge() {
  const badge = document.getElementById('sidebarAlertCount');
  if (!badge || !state.dashboardData) return;
  const count = state.dashboardData.out_count || 0;
  badge.textContent = count;
  badge.style.display = count > 0 ? 'inline-block' : 'none';
}

// -----------------------------------------------------------------------------
// 1. Dashboard View
// -----------------------------------------------------------------------------
function renderDashboard() {
  const d = state.dashboardData;
  const root = document.getElementById('appRoot');

  if (d.sync) {
    document.getElementById('syncStatusText').textContent = d.sync.last_sync ? `Synced: ${d.sync.last_sync.slice(11)}` : 'Not synced';
  }

  // Count reviewed out-of-trend standards
  let reviewedCount = 0;
  d.sets.forEach(s => {
    s.assets.forEach(a => {
      if (a.status === 'reviewed_out_of_trend') reviewedCount++;
    });
  });

  const activeFilterChips = [];
  if (state.filters.status !== 'all') activeFilterChips.push({ key: 'status', label: `Status: ${state.filters.status.replace(/_/g, ' ')}` });
  if (state.filters.category !== 'all') activeFilterChips.push({ key: 'category', label: `Category: ${state.filters.category.replace(/_/g, ' ')}` });
  if (state.filters.set !== 'all') activeFilterChips.push({ key: 'set', label: `Set: ${state.filters.set}` });
  if (state.filters.query) activeFilterChips.push({ key: 'query', label: `Search: "${escapeHtml(state.filters.query)}"` });

  root.innerHTML = `
    <!-- Top Action Banner if Out of Trend -->
    ${d.out_count > 0 ? `
      <div style="background:var(--warn-bg); border:1px solid var(--warn-border); border-radius:var(--radius-md); padding:10px 16px; margin-bottom:16px; display:flex; justify-content:space-between; align-items:center;">
        <div style="display:flex; align-items:center; gap:8px; color:var(--warn); font-weight:600;">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
          <span>Attention: ${d.out_count} active out-of-trend standard(s) require engineering review.</span>
        </div>
        <button class="btn" style="border-color:var(--warn); color:var(--warn);" onclick="filterByCard('out_of_trend')">Show Active Alerts</button>
      </div>
    ` : ''}

    <!-- Stat Grid -->
    <div class="stat-grid">
      <div class="stat-card ${state.filters.status === 'all' ? 'selected' : ''}" onclick="filterByCard('all')">
        <div class="label">Total Tracked</div>
        <div class="num">${d.total}</div>
      </div>
      <div class="stat-card ${state.filters.status === 'ok' ? 'selected' : ''}" onclick="filterByCard('ok')">
        <div class="label" style="color:var(--ok);">In Trend</div>
        <div class="num" style="color:var(--ok);">${d.ok_count}</div>
      </div>
      <div class="stat-card ${state.filters.status === 'out_of_trend' ? 'selected' : ''}" onclick="filterByCard('out_of_trend')">
        <div class="label" style="color:var(--warn);">Out of Trend</div>
        <div class="num" style="color:var(--warn);">${d.out_count}</div>
      </div>
      <div class="stat-card ${state.filters.status === 'reviewed_out_of_trend' ? 'selected' : ''}" onclick="filterByCard('reviewed_out_of_trend')">
        <div class="label" style="color:var(--reviewed);">Reviewed (OOT)</div>
        <div class="num" style="color:var(--reviewed);">${reviewedCount}</div>
      </div>
      <div class="stat-card ${state.filters.status === 'insufficient_data' ? 'selected' : ''}" onclick="filterByCard('insufficient_data')">
        <div class="label">Insufficient Data</div>
        <div class="num" style="color:var(--ink-muted);">${d.insufficient_count}</div>
      </div>
    </div>

    <!-- Category Strip & Filter Controls -->
    <div style="display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:12px; flex-wrap:wrap;">
      <div style="display:flex; gap:6px; background:var(--track); padding:3px; border-radius:var(--radius-sm); border:1px solid var(--line);">
        <button class="btn ${state.filters.category === 'all' ? 'btn-primary' : ''}" style="border:none;" onclick="filterByCategory('all')">All Standards (${d.total})</button>
        <button class="btn ${state.filters.category === 'standard_resistor' ? 'btn-primary' : ''}" style="border:none;" onclick="filterByCategory('standard_resistor')">Resistors (${d.sets.flatMap(s => s.assets).filter(a => a.category === 'standard_resistor').length})</button>
        <button class="btn ${state.filters.category === 'dcv_reference' ? 'btn-primary' : ''}" style="border:none;" onclick="filterByCategory('dcv_reference')">DCV 732A (${d.sets.flatMap(s => s.assets).filter(a => a.category === 'dcv_reference').length})</button>
        <button class="btn ${state.filters.category === 'ac_divider' ? 'btn-primary' : ''}" style="border:none;" onclick="filterByCategory('ac_divider')">AC Dividers (${d.sets.flatMap(s => s.assets).filter(a => a.category === 'ac_divider').length})</button>
        <button class="btn ${state.filters.category === 'waveform_generator' ? 'btn-primary' : ''}" style="border:none;" onclick="filterByCategory('waveform_generator')">33622A WFG (${d.sets.flatMap(s => s.assets).filter(a => a.category === 'waveform_generator').length})</button>
      </div>

      <div style="display:flex; align-items:center; gap:8px;">
        <input type="search" placeholder="Search serial, model, equipment ID..." style="width:240px;" value="${escapeHtml(state.filters.query)}" oninput="handleSearch(this.value)">
      </div>
    </div>

    <!-- Filter Breadcrumbs Bar (if active) -->
    ${activeFilterChips.length ? `
      <div class="filter-chips-bar">
        <span style="color:var(--ink-muted); font-size:11px; font-weight:700;">ACTIVE FILTERS:</span>
        ${activeFilterChips.map(c => `
          <span class="filter-chip-pill">
            ${escapeHtml(c.label)}
            <span class="filter-chip-remove" onclick="removeFilter('${c.key}')">&times;</span>
          </span>
        `).join('')}
        <button class="btn" style="padding:2px 8px; font-size:11px; margin-left:auto;" onclick="resetFilters()">Clear All</button>
      </div>
    ` : ''}

    <!-- Fleet Table -->
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Serial</th>
            <th>Model</th>
            <th>Equipment ID</th>
            <th class="right">Nominal / Range</th>
            <th style="text-align:center;">Set</th>
            <th>Category</th>
            <th class="right"># Cals</th>
            <th>Last Cal Date</th>
            <th class="right">Last Measured</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody id="fleetTableBody">
          ${renderFleetRows()}
        </tbody>
      </table>
    </div>
  `;
}

function renderFleetRows() {
  const d = state.dashboardData;
  let rowsHtml = '';

  d.sets.forEach(s => {
    s.assets.forEach(a => {
      const matchStatus = state.filters.status === 'all' || a.status === state.filters.status;
      const matchCat = state.filters.category === 'all' || (a.category || 'standard_resistor') === state.filters.category;
      const matchSet = state.filters.set === 'all' || s.set_id === state.filters.set;
      const searchText = `${a.serial} ${a.model || ''} ${a.asset_number || ''}`.toLowerCase();
      const matchQuery = !state.filters.query || searchText.includes(state.filters.query.toLowerCase());

      if (matchStatus && matchCat && matchSet && matchQuery) {
        let nomDisplay = `${a.nominal_ohms} Ω`;
        if (a.category === 'dcv_reference') nomDisplay = '10.0 V';
        else if (a.category === 'ac_divider') nomDisplay = (a.model && a.model.includes('10mV')) ? '100:1 Ratio' : '10:1 Ratio';
        else if (a.category === 'waveform_generator') nomDisplay = '15 Points (dB)';

        const measDisplay = formatMeasured(a.last_measured, a.nominal_ohms, a.category, a.unit);

        let badgeHtml = '<span class="badge badge-neutral"><span class="badge-dot"></span>Baseline</span>';
        if (a.status === 'ok') badgeHtml = '<span class="badge badge-ok"><span class="badge-dot"></span>In Trend</span>';
        else if (a.status === 'reviewed_out_of_trend') badgeHtml = '<span class="badge badge-reviewed"><span class="badge-dot"></span>Reviewed</span>';
        else if (a.status === 'out_of_trend') badgeHtml = '<span class="badge badge-warn"><span class="badge-dot"></span>Out of Trend</span>';

        let catDisplay = 'Standard Resistor';
        if (a.category === 'dcv_reference') catDisplay = 'DC Voltage Reference';
        else if (a.category === 'ac_divider') catDisplay = 'AC Voltage Divider';
        else if (a.category === 'waveform_generator') catDisplay = 'Waveform Generator';

        rowsHtml += `
          <tr onclick="router.navigate('asset_detail', { asset_id: ${a.id} })">
            <td class="mono" style="color:var(--primary-accent); font-weight:700;">${escapeHtml(a.serial)}</td>
            <td style="font-weight:600;">${escapeHtml(a.model || '—')}</td>
            <td class="mono" style="color:var(--ink-muted);">${escapeHtml(a.asset_number || '—')}</td>
            <td class="mono right">${nomDisplay}</td>
            <td style="text-align:center;"><span class="badge badge-neutral">${escapeHtml(s.set_id || '—')}</span></td>
            <td style="color:var(--ink-muted);">${catDisplay}</td>
            <td class="mono right">${a.num_calibrations}</td>
            <td class="mono">${escapeHtml(a.last_cal_date || '—')}</td>
            <td class="mono right" style="font-weight:600;">${measDisplay}</td>
            <td>${badgeHtml}</td>
          </tr>
        `;
      }
    });
  });

  return rowsHtml || `<tr><td colspan="10" style="text-align:center; padding:32px; color:var(--ink-muted);">No standards match active filters.</td></tr>`;
}

function filterByCard(status) {
  state.filters.status = status;
  renderDashboard();
}

function filterByCategory(cat) {
  state.filters.category = cat;
  renderDashboard();
}

function handleSearch(q) {
  state.filters.query = q.trim();
  document.getElementById('fleetTableBody').innerHTML = renderFleetRows();
}

function removeFilter(key) {
  if (key === 'status') state.filters.status = 'all';
  if (key === 'category') state.filters.category = 'all';
  if (key === 'set') state.filters.set = 'all';
  if (key === 'query') state.filters.query = '';
  renderDashboard();
}

function resetFilters() {
  state.filters = { status: 'all', category: 'all', set: 'all', query: '' };
  renderDashboard();
}

// -----------------------------------------------------------------------------
// 2. Alerts & Reviews View
// -----------------------------------------------------------------------------
function renderAlertsView() {
  const d = state.dashboardData;
  const root = document.getElementById('appRoot');

  const alerts = [];
  d.sets.forEach(s => {
    s.assets.forEach(a => {
      if (a.status === 'out_of_trend' || a.status === 'reviewed_out_of_trend') {
        alerts.push({ ...a, set_name: s.set_id });
      }
    });
  });

  root.innerHTML = `
    <div class="panel" style="margin-bottom:16px;">
      <div class="panel-header">
        <div class="panel-title">Quality Action Queue (${alerts.length} Standards)</div>
      </div>
      <p style="color:var(--ink-muted); font-size:12.5px; margin:0 0 14px 0;">
        Active out-of-trend anomalies require engineering review. Points with attached reviewer justifications appear as <strong>Reviewed (Out of Trend)</strong>.
      </p>

      <div class="table-container" style="box-shadow:none;">
        <table>
          <thead>
            <tr>
              <th>Serial</th>
              <th>Model</th>
              <th>Equipment ID</th>
              <th>Set</th>
              <th>Category</th>
              <th>Latest Reading</th>
              <th>Status</th>
              <th style="text-align:right;">Action</th>
            </tr>
          </thead>
          <tbody>
            ${alerts.length ? alerts.map(a => `
              <tr>
                <td class="mono" style="color:var(--primary-accent); font-weight:700;">${escapeHtml(a.serial)}</td>
                <td style="font-weight:600;">${escapeHtml(a.model || '—')}</td>
                <td class="mono">${escapeHtml(a.asset_number || '—')}</td>
                <td><span class="badge badge-neutral">${escapeHtml(a.set_name || '—')}</span></td>
                <td>${escapeHtml(a.category)}</td>
                <td class="mono">${formatMeasured(a.last_measured, a.nominal_ohms, a.category, a.unit)}</td>
                <td>
                  ${a.status === 'reviewed_out_of_trend' 
                    ? '<span class="badge badge-reviewed"><span class="badge-dot"></span>Reviewed</span>' 
                    : '<span class="badge badge-warn"><span class="badge-dot"></span>Out of Trend</span>'}
                </td>
                <td style="text-align:right;">
                  <button class="btn btn-primary" style="padding:2px 8px; font-size:11px;" onclick="router.navigate('asset_detail', { asset_id: ${a.id} })">
                    Open Asset
                  </button>
                </td>
              </tr>
            `).join('') : `
              <tr><td colspan="8" style="text-align:center; padding:32px; color:var(--ok);">✓ No out-of-trend anomalies active in the laboratory fleet.</td></tr>
            `}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// -----------------------------------------------------------------------------
// 3. Asset Detail: Restored Matrix & Calculation Traceability
// -----------------------------------------------------------------------------
function renderAssetDetail() {
  const d = state.activeAssetDetail;
  const root = document.getElementById('appRoot');
  const a = d.asset;
  const activeTp = d.active_test_point;
  const stability = d.stability;

  root.innerHTML = `
    <!-- Top Command Card -->
    <div class="panel" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
      <div>
        <div style="font-size:20px; font-weight:700; color:var(--ink);">${escapeHtml(a.model || a.serial)}</div>
        <div style="font-size:12px; color:var(--ink-muted); margin-top:2px;">
          Serial: <strong class="mono" style="color:var(--primary-accent); cursor:pointer;" onclick="app.copyToClipboard(this.textContent, 'Serial')">${escapeHtml(a.serial)}</strong> ·
          Equipment ID: <strong class="mono" style="cursor:pointer;" onclick="app.copyToClipboard(this.textContent, 'Equipment ID')">${escapeHtml(a.asset_number || '—')}</strong> ·
          Category: <strong>${escapeHtml(a.category)}</strong> ·
          Set: <strong>${escapeHtml(a.set_id || 'Unassigned')}</strong>
        </div>
      </div>
      <div style="display:flex; gap:8px;">
        <button class="btn btn-primary" onclick="openTraceDrawer()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
          Show Calculation Trace
        </button>
        <button class="btn" onclick="app.exportExcel(${a.id})">Export Excel</button>
        <button class="btn" onclick="router.navigate('dashboard')">Back to Fleet</button>
      </div>
    </div>

    <!-- 2-Column Telemetry: Left = Active Series Summary, Right = Dynamic Category Panel -->
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px; margin-bottom:16px;">
      
      <!-- Left Card: Active Test Series -->
      <div class="panel" style="margin-bottom:0;">
        <div class="panel-header">
          <div class="panel-title">Active Test Series Summary</div>
          <span class="badge badge-neutral">${escapeHtml(activeTp ? activeTp.point_name : (a.nominal_ohms + ' Ω'))}</span>
        </div>
        <div style="display:grid; grid-template-columns: auto 1fr; gap:8px 20px; font-size:12.5px;">
          <span style="color:var(--ink-muted);">Classification:</span>
          <span class="mono">${escapeHtml(activeTp ? activeTp.group_name : (a.source_sheet || 'Standard'))}</span>
          <span style="color:var(--ink-muted);">Baseline Fit Role:</span>
          <span><strong>${d.trend ? `${d.trend.n} historical points fitted; latest point held out` : 'Insufficient baseline points'}</strong></span>
          <span style="color:var(--ink-muted);">Calibrations:</span>
          <span><strong>${d.calibrations.length}</strong> total points recorded</span>
          <span style="color:var(--ink-muted);">Annual Drift Rate:</span>
          <span class="mono">${d.traceability ? d.traceability.annual_drift_rate : '—'}</span>
          <span style="color:var(--ink-muted);">Fit Residual (Syx):</span>
          <span class="mono">${d.trend ? d.trend.Syx.toExponential(3) : '—'}</span>
        </div>
      </div>

      <!-- Right Card: Dynamic Adaptation per Category -->
      ${renderDynamicRightCard(a, d, stability)}

    </div>

    <!-- Multi-Point Characterization Matrix (Full Table at a Glance) -->
    ${d.test_points && d.test_points.length > 1 ? `
      <div class="panel" style="margin-bottom:16px;">
        <div class="panel-header" style="margin-bottom:10px;">
          <div class="panel-title">
            Multi-Point Characterization Matrix (${d.test_points.length} Test Points)
          </div>
          <span style="font-size:11.5px; color:var(--ink-muted);">Click any row to switch active trend below</span>
        </div>
        <div class="table-container" style="box-shadow:none; margin-bottom:0;">
          <table class="matrix-table">
            <thead>
              <tr>
                <th>Test Point</th>
                <th>Classification</th>
                <th class="right">Latest Calibrated Value</th>
                <th class="right">Drift Since Prior Cal</th>
                <th>Latest Cal Date</th>
                <th>Trend Status</th>
                <th style="text-align:right;">Action</th>
              </tr>
            </thead>
            <tbody>
              ${d.test_points.map(tp => `
                <tr class="${tp.id === d.active_test_point_id ? 'is-active' : ''}"
                    style="cursor:pointer;"
                    onclick="switchTestPoint(${tp.id})">
                  <td style="font-weight:${tp.id === d.active_test_point_id ? '700; color:var(--primary-accent);' : '600;'}">
                    ${escapeHtml(tp.point_name)}
                  </td>
                  <td style="color:var(--ink-muted); font-size:12px;">${escapeHtml(tp.group_name || '—')}</td>
                  <td class="mono right" style="font-weight:600;">
                    ${formatMeasured(tp.latest_value, tp.nominal_value, a.category, tp.unit)}
                  </td>
                  <td class="mono right" style="color:var(--primary); font-weight:600;">
                    ${escapeHtml(tp.drift_display || '—')}
                  </td>
                  <td class="mono">${escapeHtml(tp.latest_date || '—')}</td>
                  <td>
                    ${tp.status === 'ok' ? '<span class="badge badge-ok"><span class="badge-dot"></span>In Trend</span>' : (tp.status === 'reviewed_out_of_trend' ? '<span class="badge badge-reviewed"><span class="badge-dot"></span>Reviewed</span>' : (tp.status === 'out_of_trend' ? '<span class="badge badge-warn"><span class="badge-dot"></span>Out of Trend</span>' : '<span class="badge badge-neutral"><span class="badge-dot"></span>Baseline</span>'))}
                  </td>
                  <td style="text-align:right;">
                    <button class="btn ${tp.id === d.active_test_point_id ? 'btn-primary' : ''}" style="padding:2px 8px; font-size:11px;">
                      ${tp.id === d.active_test_point_id ? 'Active' : 'View'}
                    </button>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    ` : ''}

    <!-- Trend Chart with Legends and Display Toggle -->
    <div class="panel" style="margin-bottom:16px;">
      <div class="panel-header" style="margin-bottom:10px;">
        <div class="panel-title">
          Trend Analysis: ${escapeHtml(activeTp ? activeTp.point_name : (a.model || a.serial))}
        </div>
        <div style="display:flex; gap:4px; background:var(--track); padding:2px; border-radius:var(--radius-sm); border:1px solid var(--line);">
          <button id="btnChartPrimary" class="btn ${state.chartMode === 'primary' ? 'btn-primary' : ''}" style="border:none; padding:3px 8px; font-size:11px;" onclick="setChartDisplayMode('primary')">
            Measured (${escapeHtml(a.unit)})
          </button>
          <button id="btnChartRelative" class="btn ${state.chartMode === 'relative' ? 'btn-primary' : ''}" style="border:none; padding:3px 8px; font-size:11px;" onclick="setChartDisplayMode('relative')">
            ${a.unit === 'dB' ? 'Deviation (dB)' : 'Relative Error (ppm)'}
          </button>
        </div>
      </div>

      <div style="height:320px; position:relative;">
        <canvas id="trendChartCanvas"></canvas>
      </div>

      <div style="margin-top:10px; font-size:11.5px; color:var(--ink-muted); display:flex; justify-content:space-between;">
        <span>The newest calibration is not included in the fitted regression. It is independently compared with the 95% prediction interval calculated from eligible historical baseline points.</span>
        <a href="javascript:void(0)" style="color:var(--primary-accent); font-weight:600;" onclick="openTraceDrawer()">Inspect Calculation Details →</a>
      </div>
    </div>

    <!-- Calibration History Table (With Notes and Correct Status Badges) -->
    <div class="panel-header">
      <div class="panel-title">Calibration History: ${escapeHtml(activeTp ? activeTp.point_name : a.model)}</div>
    </div>
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Fit Role</th>
            <th class="right">Measured Value</th>
            <th class="right">Uncertainty</th>
            <th class="right">Error / Deviation</th>
            <th class="right">Drift</th>
            <th class="right">95% Prediction Limits [Lower ↔ Upper]</th>
            <th>Status</th>
            <th style="text-align:center;">Note</th>
            <th style="text-align:right;">Action</th>
          </tr>
        </thead>
        <tbody>
          ${d.calibrations.slice().reverse().map(c => {
            let statusBadge = '<span class="badge badge-neutral"><span class="badge-dot"></span>Baseline</span>';
            if (c.excluded_from_regression) {
              statusBadge = '<span class="badge badge-neutral">Excluded</span>';
            } else if (c.in_active_epoch === false) {
              statusBadge = '<span class="badge badge-neutral"><span class="badge-dot"></span>Prior Epoch</span>';
            } else if (c.display_status === 'reviewed_out_of_trend') {
              statusBadge = '<span class="badge badge-reviewed"><span class="badge-dot"></span>Reviewed</span>';
            } else if (c.out_of_trend) {
              statusBadge = '<span class="badge badge-warn"><span class="badge-dot"></span>Out of Trend</span>';
            } else if (c.predicted !== null && c.predicted !== undefined) {
              statusBadge = '<span class="badge badge-ok"><span class="badge-dot"></span>In Trend</span>';
            }

            let roleDisplay = 'Included';
            if (c.fit_role === 'held_out') roleDisplay = '<strong style="color:var(--primary-accent);">Held Out</strong>';
            else if (c.fit_role === 'prior_epoch' || c.in_active_epoch === false) roleDisplay = '<span style="color:var(--ink-faint);">Prior Epoch</span>';
            else if (c.fit_role === 'excluded' || c.excluded_from_regression) roleDisplay = '<span style="color:var(--ink-faint);">Excluded</span>';

            const measStr = formatMeasured(c.measured_value, activeTp?.nominal_value || a.nominal_ohms, a.category, a.unit);
            const lowerStr = formatBound(c.lower, activeTp?.nominal_value || a.nominal_ohms, a.category, a.unit);
            const upperStr = formatBound(c.upper, activeTp?.nominal_value || a.nominal_ohms, a.category, a.unit);
            const uncertStr = formatUncertainty(c, a.category, activeTp?.nominal_value ?? a.nominal_ohms);

            return `
              <tr>
                <td class="mono" style="font-weight:600;">${escapeHtml(c.date)}</td>
                <td>${roleDisplay}</td>
                <td class="mono right" style="font-weight:700;">${measStr}</td>
                <td class="mono right" style="color:var(--ink-muted);">${uncertStr}</td>
                <td class="mono right">
                  ${c.error_ppm !== null && c.error_ppm !== undefined ? (c.error_ppm > 0 ? '+' : '') + c.error_ppm.toFixed(2) + (a.unit === 'dB' ? ' dB' : ' ppm') : '—'}
                </td>
                <td class="mono right">
                  ${c.drift_ppm !== null && c.drift_ppm !== undefined ? (c.drift_ppm > 0 ? '+' : '') + c.drift_ppm.toFixed(2) + (a.unit === 'dB' ? ' dB' : ' ppm') : '—'}
                </td>
                <td class="mono right">
                  ${c.lower !== null && c.lower !== undefined ? `
                    <span class="limit-chip">${lowerStr} <span class="limit-sep">↔</span> ${upperStr}</span>
                  ` : '—'}
                </td>
                <td>${statusBadge}</td>
                <td style="text-align:center;">
                  ${c.reviewer_comment || c.reviewer_attachment_path ? `
                    <button class="btn" style="padding:1px 6px; font-size:11px;" onclick="openStoredNote(${c.id})">Note</button>
                  ` : '<span style="color:var(--ink-faint);">—</span>'}
                </td>
                <td style="text-align:right;">
                  <button class="btn" style="padding:1px 7px; font-size:11px;" onclick="openEditCalModal(${c.id})">Edit</button>
                </td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    </div>
  `;

  renderChart(d);
  populateTraceDrawer(d);
}

// -----------------------------------------------------------------------------
// Dynamic Right Card Rendering
// -----------------------------------------------------------------------------
function renderDynamicRightCard(a, d, stability) {
  if (a.category === 'standard_resistor' || (!a.category && a.unit === 'Ω')) {
    if (stability && stability.allowance_ppm !== null && stability.allowance_ppm !== undefined) {
      const observed = stability.observed_drift_ppm;
      const allowance = stability.allowance_ppm;
      const consumedPct = Math.min(Math.round(Math.abs(observed) / allowance * 100), 999);
      const isExceeded = stability.exceeds;
      
      const ratio = observed / allowance;
      let pinPos = 50 + (ratio * 50);
      pinPos = Math.max(3, Math.min(97, pinPos));

      return `
        <div class="panel" style="margin-bottom:0; ${isExceeded ? 'border-color:var(--warn);' : ''}">
          <div class="panel-header">
            <div class="panel-title">Manufacturer Stability Check</div>
            <span class="badge ${isExceeded ? 'badge-warn' : 'badge-ok'}">
              <span class="badge-dot"></span>${isExceeded ? 'Exceeds Spec' : 'Within Spec'}
            </span>
          </div>
          <div style="font-size:12.5px;">
            <div style="color:var(--ink-muted); margin-bottom:4px;">Spec: <strong>${escapeHtml(stability.spec_description || 'Manufacturer Tolerance')}</strong></div>
            <div style="color:var(--ink-muted);">
              Observed drift across <strong>${stability.elapsed_days} days</strong>: 
              <strong class="mono" style="color:${isExceeded ? 'var(--warn)' : 'var(--ok)'};">
                ${observed > 0 ? '+' : ''}${observed.toFixed(2)} ppm
              </strong> 
              (allowance ±${allowance.toFixed(2)} ppm · <strong>${consumedPct}%</strong> consumed)
            </div>

            <div class="gauge-track-container">
              <div class="gauge-scale-labels">
                <span>-${allowance.toFixed(2)} ppm</span>
                <span>0 ppm</span>
                <span>+${allowance.toFixed(2)} ppm</span>
              </div>
              <div class="gauge-track-bar">
                <div class="gauge-compliance-window"></div>
                <div class="gauge-center-tick"></div>
                <div class="gauge-pointer-pin" style="left:${pinPos}%; background:${isExceeded ? 'var(--warn)' : 'var(--ok)'};" title="Observed: ${observed.toFixed(2)} ppm"></div>
              </div>
            </div>
          </div>
        </div>
      `;
    }
  }

  if (a.category === 'dcv_reference') {
    const latestCal = d.calibrations[d.calibrations.length - 1] || {};
    return `
      <div class="panel" style="margin-bottom:0;">
        <div class="panel-header">
          <div class="panel-title">Barometric Pressure &amp; Facility Epoch</div>
          <span class="badge badge-neutral">Altitude Shift Isolated</span>
        </div>
        <div style="font-size:12.5px;">
          <p style="margin:0 0 8px 0; color:var(--ink-muted); line-height:1.5;">
            <strong>Active Roseville Epoch:</strong> Calibrations since moving to Roseville on <code>2022-04-08</code> at sea level (~1013 hPa) are strictly isolated from Loveland (~845 hPa) to prevent barometric step shifts from corrupting the true Zener diode aging slope (+0.04 ppm/year).
          </p>
          <div style="padding:8px 12px; background:var(--panel-subtle); border-radius:var(--radius-sm); border:1px solid var(--line); display:flex; gap:16px;">
            <div>Facility: <strong>${latestCal.location || 'Roseville'}</strong></div>
            <div>Ambient Pressure: <strong class="mono">${latestCal.pressure_hpa ? Math.round(latestCal.pressure_hpa) + ' hPa' : '1013 hPa'}</strong></div>
          </div>
        </div>
      </div>
    `;
  }

  if (a.category === 'waveform_generator') {
    return `
      <div class="panel" style="margin-bottom:0;">
        <div class="panel-header">
          <div class="panel-title">Active Post-Adjustment Epoch</div>
          <span class="badge badge-neutral">Pre-Adj Quarantined</span>
        </div>
        <div style="font-size:12.5px;">
          <p style="margin:0 0 8px 0; color:var(--ink-muted); line-height:1.5;">
            <strong>Electronic Adjustment Quarantine:</strong> Calibrations prior to the latest adjustment on <code>2024-02-17</code> are isolated as Prior Epoch so electronic calibration steps do not distort the active 95% Prediction Interval.
          </p>
          <div style="padding:8px 12px; background:var(--panel-subtle); border-radius:var(--radius-sm); border:1px solid var(--line);">
            Active Post-Adjustment Drift Rate: <strong class="mono" style="color:var(--primary-accent);">${d.traceability ? d.traceability.annual_drift_rate : '-0.00310 dB/year'}</strong>
          </div>
        </div>
      </div>
    `;
  }

  if (a.category === 'ac_divider') {
    return `
      <div class="panel" style="margin-bottom:0;">
        <div class="panel-header">
          <div class="panel-title">Multi-Year Characterization Baseline</div>
          <span class="badge badge-ok"><span class="badge-dot"></span>Continuous Baseline</span>
        </div>
        <div style="font-size:12.5px;">
          <p style="margin:0 0 8px 0; color:var(--ink-muted); line-height:1.5;">
            <strong>11-Year Continuous Baseline:</strong> Ratio characterizations across all 6 test frequencies (1 kHz to 1 MHz) demonstrate high ratio stability with zero mechanical adjustments required over 11 years.
          </p>
          <div style="padding:8px 12px; background:var(--panel-subtle); border-radius:var(--radius-sm); border:1px solid var(--line);">
            Low-Frequency Stability (1 kHz – 100 kHz): <strong class="mono" style="color:var(--ok);">&lt; 26 ppm total drift</strong>
          </div>
        </div>
      </div>
    `;
  }

  return `<div class="panel" style="margin-bottom:0;"><div class="panel-title">Standard Telemetry</div><p style="color:var(--ink-muted); font-size:12px;">Active monitoring enabled.</p></div>`;
}

function escapeQuotes(str) {
  return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function switchTestPoint(tpId) {
  router.navigate('asset_detail', { asset_id: state.activeAssetId, tp_id: tpId });
}

function setChartDisplayMode(mode) {
  state.chartMode = mode;
  document.getElementById('btnChartPrimary')?.classList.toggle('btn-primary', mode === 'primary');
  document.getElementById('btnChartRelative')?.classList.toggle('btn-primary', mode === 'relative');
  renderChart(state.activeAssetDetail);
}

// -----------------------------------------------------------------------------
// Chart.js: Complete Legends & Diagnostics Tooltip
// -----------------------------------------------------------------------------
function renderChart(d) {
  const ctx = document.getElementById('trendChartCanvas');
  if (!ctx) return;

  if (state.chartInstance) {
    state.chartInstance.destroy();
  }

  const cals = d.calibrations;
  const isDark = state.activeTheme === 'dark';
  const gridColor = isDark ? '#162740' : '#edf2f7';
  const textColor = isDark ? '#94a3b8' : '#64748b';
  const assetUnit = d.asset.unit;
  const isPrimary = state.chartMode === 'primary';

  const inTrendPoints = [];
  const outOfTrendPoints = [];
  const reviewedPoints = [];
  const priorEpochPoints = [];
  const heldOutPoints = [];

  cals.forEach((c, idx) => {
    const pt = { x: c.accumulated_days, y: isPrimary ? c.measured_value : c.error_ppm, rawCal: c };
    if (c.excluded_from_regression || c.in_active_epoch === false) {
      priorEpochPoints.push(pt);
    } else if (idx === cals.length - 1 && c.in_active_epoch !== false) {
      heldOutPoints.push(pt);
    } else if (c.display_status === 'reviewed_out_of_trend') {
      reviewedPoints.push(pt);
    } else if (c.out_of_trend) {
      outOfTrendPoints.push(pt);
    } else {
      inTrendPoints.push(pt);
    }
  });

  const nominal = d.active_test_point?.nominal_value ?? d.asset.nominal_ohms;
  const relativeBound = value => value === null || value === undefined ? null :
    (assetUnit === 'dB' || !nominal ? value : (value - nominal) / nominal * 1e6);
  const upperData = cals.map(c => ({ x: c.accumulated_days, y: isPrimary ? c.upper : relativeBound(c.upper) }));
  const lowerData = cals.map(c => ({ x: c.accumulated_days, y: isPrimary ? c.lower : relativeBound(c.lower) }));
  const predData  = cals.map(c => ({ x: c.accumulated_days, y: isPrimary ? c.predicted : relativeBound(c.predicted) }));

  state.chartInstance = new CalibrationChart(ctx, {
    type: 'scatter',
    data: {
      datasets: [
        {
          label: '95% Upper Limit',
          data: upperData,
          showLine: true,
          borderColor: isDark ? '#38bdf8' : '#93c5fd',
          backgroundColor: isDark ? 'rgba(56, 189, 248, 0.12)' : 'rgba(219, 234, 254, 0.35)',
          fill: '+1',
          pointRadius: 0,
          borderWidth: 1.5,
          order: 6
        },
        {
          label: '95% Lower Limit',
          data: lowerData,
          showLine: true,
          borderColor: isDark ? '#38bdf8' : '#93c5fd',
          pointRadius: 0,
          borderWidth: 1.5,
          order: 6
        },
        {
          label: 'Linear Prediction',
          data: predData,
          showLine: true,
          borderColor: textColor,
          borderDash: [3, 4],
          pointRadius: 0,
          borderWidth: 1.2,
          order: 5
        },
        {
          label: 'Historical Fitted Reading',
          data: inTrendPoints,
          backgroundColor: '#10b981',
          pointStyle: 'circle',
          pointRadius: 5.5,
          order: 2
        },
        {
          label: 'Held-Out Reading (Tested)',
          data: heldOutPoints,
          backgroundColor: heldOutPoints.length && heldOutPoints[0].rawCal.out_of_trend ? '#f59e0b' : '#38bdf8',
          pointStyle: 'rectRot',
          pointRadius: 8,
          borderColor: '#ffffff',
          borderWidth: 2,
          order: 1
        },
        {
          label: 'Reviewed Out-of-Trend',
          data: reviewedPoints,
          backgroundColor: '#60a5fa',
          pointStyle: 'rectRot',
          pointRadius: 7,
          order: 2
        },
        {
          label: 'Prior Epoch / Excluded',
          data: priorEpochPoints,
          backgroundColor: '#64748b',
          pointStyle: 'triangle',
          pointRadius: 5.5,
          order: 3
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top',
          labels: {
            boxWidth: 10,
            usePointStyle: true,
            color: textColor,
            font: { family: "'IBM Plex Sans'", size: 11 }
          }
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              const pt = context.raw;
              const c = pt.rawCal || cals[context.dataIndex];
              const modeLabel = isPrimary ? ` ${assetUnit}` : (assetUnit === 'dB' ? ' dB' : ' ppm');
              const val = context.parsed.y;
              const lines = [
                `Date: ${escapeHtml(c.date)}`,
                `${context.dataset.label}: ${val !== null ? val.toFixed(assetUnit === 'V' ? 8 : (assetUnit === 'dB' ? 5 : 5)) + modeLabel : '—'}`
              ];
              if (c.pressure_hpa) {
                lines.push(`Pressure: ${Math.round(c.pressure_hpa)} hPa${c.location ? ` (${c.location})` : ''}`);
              }
              if (c.is_adjusted) {
                lines.push(`Adjustment: Instrument Adjusted (New Epoch)`);
              }
              if (c.in_active_epoch === false) {
                lines.push(`Epoch: Quarantined Prior Epoch`);
              }
              if (c.display_status === 'reviewed_out_of_trend') {
                lines.push(`Review: Metrologist Investigated & Documented`);
              }
              if (c.reviewer_comment) {
                lines.push(`Note: "${c.reviewer_comment}"`);
              }
              return lines;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { color: textColor },
          title: { display: true, text: 'Accumulated Days in Service', color: textColor, font: { size: 11 } }
        },
        y: {
          grid: { color: gridColor },
          ticks: { color: textColor },
          title: {
            display: true,
            text: isPrimary ? `Measured Value (${assetUnit})` : (assetUnit === 'dB' ? 'Deviation (dB)' : 'Relative Drift (ppm)'),
            color: textColor,
            font: { size: 11 }
          }
        }
      }
    }
  });
}

// -----------------------------------------------------------------------------
// Calculation Traceability Drawer
// -----------------------------------------------------------------------------
function openTraceDrawer() {
  document.getElementById('traceDrawer').classList.add('open');
}
function closeTraceDrawer() {
  document.getElementById('traceDrawer').classList.remove('open');
}

function populateTraceDrawer(d) {
  const content = document.getElementById('traceDrawerContent');
  const t = d.traceability;

  if (!t) {
    content.innerHTML = `<p style="color:var(--ink-muted);">Insufficient calibrations to calculate linear prediction intervals (minimum 4 points required in active epoch).</p>`;
    return;
  }

  const a = d.asset;
  const lowerBoundFormatted = formatBound(t.lower_bound, d.active_test_point?.nominal_value || a.nominal_ohms, a.category, a.unit);
  const upperBoundFormatted = formatBound(t.upper_bound, d.active_test_point?.nominal_value || a.nominal_ohms, a.category, a.unit);
  const actualReadingFormatted = formatMeasured(t.actual_reading, d.active_test_point?.nominal_value || a.nominal_ohms, a.category, a.unit);

  let stabilityBlockHtml = '';
  if (t.stability_calc) {
    const s = t.stability_calc;
    stabilityBlockHtml = `
      <div style="margin-top:20px; padding-top:14px; border-top:1px dashed var(--line);">
        <div style="font-weight:700; color:var(--ink); margin-bottom:4px;">Manufacturer Stability Derivation</div>
        <div style="font-size:11.5px; color:var(--ink-muted); margin-bottom:8px;">${escapeHtml(s.spec_description || 'Manufacturer Step Spec')}</div>
        <table class="trace-table">
          <tr>
            <td>Interval Evaluated<span class="math-param-help">Consecutive cal points</span></td>
            <td>${s.previous_date} → ${s.latest_date} (${s.elapsed_days} d)</td>
          </tr>
          <tr>
            <td>Allowed Drift Tolerance<span class="math-param-help">Interpolated spec allowance</span></td>
            <td>±${s.allowance_ppm.toFixed(2)} ppm</td>
          </tr>
          <tr>
            <td>Observed Drift<span class="math-param-help">Δppm = ppm_latest - ppm_prior</span></td>
            <td>${s.observed_drift_ppm > 0 ? '+' : ''}${s.observed_drift_ppm.toFixed(2)} ppm</td>
          </tr>
          <tr>
            <td>Tolerance Consumed<span class="math-param-help">|Observed| / Allowed × 100%</span></td>
            <td><strong>${s.consumed_percent.toFixed(1)}%</strong></td>
          </tr>
          <tr>
            <td>Compliance Verdict</td>
            <td>${s.exceeds ? '<span style="color:var(--warn); font-weight:700;">EXCEEDS SPEC</span>' : '<span style="color:var(--ok); font-weight:700;">WITHIN SPEC</span>'}</td>
          </tr>
        </table>
      </div>
    `;
  }

  content.innerHTML = `
    <div style="font-weight:700; color:var(--ink); margin-bottom:4px;">Hold-Out Anomaly Verification</div>
    <p style="color:var(--ink-muted); margin:0 0 12px 0;">
      Hold-out anomaly evaluation: calibration point dated <strong>${t.hold_out_date}</strong> was strictly excluded from the regression fit ($n = ${t.n}$) to prevent the latest reading from biasing its own limits.
    </p>

    <div style="font-weight:700; color:var(--ink); margin-bottom:4px;">Linear Regression Equation</div>
    <div class="math-block">${t.equation}</div>

    <table class="trace-table">
      <tr>
        <td>Baseline Sample Size (n)<span class="math-param-help">Historical points used in fit</span></td>
        <td>${t.n} points</td>
      </tr>
      <tr>
        <td>Degrees of Freedom (df = n - 2)<span class="math-param-help">Observations minus 2 fitted parameters</span></td>
        <td>${t.df}</td>
      </tr>
      <tr>
        <td>Critical t-Factor (t_crit)<span class="math-param-help">Two-tailed Student's t at 95% confidence</span></td>
        <td>${t.t_crit.toFixed(4)}</td>
      </tr>
      <tr>
        <td>Residual Std Dev (Syx)<span class="math-param-help">Standard scatter around drift slope</span></td>
        <td>${t.Syx.toExponential(4)}</td>
      </tr>
      <tr>
        <td>Annual Drift Rate<span class="math-param-help">Slope scaled to 365.25 days</span></td>
        <td>${t.annual_drift_rate}</td>
      </tr>
      <tr>
        <td>Historical Centroid (x̄)<span class="math-param-help">Mean accumulated days of baseline</span></td>
        <td>${t.xbar.toFixed(1)} days</td>
      </tr>
      <tr>
        <td>Leverage Factor<span class="math-param-help">(x₀ - x̄)² / SSx (distance penalty)</span></td>
        <td>${t.leverage.toFixed(4)}</td>
      </tr>
      <tr>
        <td>Computed 95% Prediction Intervals<span class="math-param-help">Expected range for hold-out date</span></td>
        <td>[ ${lowerBoundFormatted} ↔ ${upperBoundFormatted} ]</td>
      </tr>
      <tr>
        <td>Actual Reading Evaluated</td>
        <td><strong>${actualReadingFormatted}</strong></td>
      </tr>
      <tr>
        <td>Metrological Outcome</td>
        <td>${t.is_out_of_trend ? '<span style="color:var(--warn); font-weight:700;">OUT OF TREND</span>' : '<span style="color:var(--ok); font-weight:700;">PASSED IN-TREND</span>'}</td>
      </tr>
    </table>

    ${stabilityBlockHtml}
  `;
}

// -----------------------------------------------------------------------------
// 4. HTBasic Workbench: 33622A Pre-Flight Verification
// -----------------------------------------------------------------------------
function renderHTBasic() {
  const ctx = state.htbasicContext;
  const root = document.getElementById('appRoot');

  root.innerHTML = `
    <!-- Station Setup Toolbar -->
    <div class="panel" style="margin-bottom:16px;">
      <div class="panel-header">
        <div class="panel-title">Station Configuration</div>
      </div>
      <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:14px;">
        <div>
          <label style="font-size:11px; font-weight:700; color:var(--ink-muted);">Target Station</label>
          <select id="htStation" style="width:100%; margin-top:4px;" onchange="updateHTBasicConfig()">
            <option value="Set 1" ${ctx.set_name === 'Set 1' ? 'selected' : ''}>Station 1 (Set 1 → 286300.txt)</option>
            <option value="Set 2" ${ctx.set_name === 'Set 2' ? 'selected' : ''}>Station 2 (Set 2 → 286325.txt)</option>
          </select>
        </div>

        <div>
          <label style="font-size:11px; font-weight:700; color:var(--ink-muted);">0.1 Ω Reference Resistor</label>
          <select id="htResistor" style="width:100%; margin-top:4px;" onchange="updateHTBasicConfig()">
            ${Object.keys(ctx.zero_pt_one_options).map(pn => `
              <option value="${escapeHtml(pn)}" ${ctx.zero_pt_one_pn === pn ? 'selected' : ''}>${escapeHtml(ctx.zero_pt_one_options[pn])}</option>
            `).join('')}
          </select>
        </div>

        <div>
          <label style="font-size:11px; font-weight:700; color:var(--ink-muted);">33622A Waveform Generator</label>
          <select id="htWfg" style="width:100%; margin-top:4px;" onchange="updateHTBasicConfig()">
            ${Object.keys(ctx.wfg_options).map(sn => `
              <option value="${escapeHtml(sn)}" ${ctx.wfg_serial === sn ? 'selected' : ''}>${escapeHtml(ctx.wfg_options[sn].label)}</option>
            `).join('')}
          </select>
        </div>
      </div>

      <div style="margin-top:16px; display:flex; justify-content:flex-end;">
        <button class="btn btn-primary" onclick="app.downloadHTBasic()">
          Generate HTBasic Package
        </button>
      </div>
    </div>

    <!-- Section Tabs -->
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
      <div class="panel-title">Pre-Flight Factor Verification</div>
      <div style="display:flex; gap:6px;">
        <button class="btn ${state.preflightFilter === 'all' ? 'btn-primary' : ''}" style="font-size:11.5px;" onclick="setPreflightFilter('all')">All Standards (34 Points)</button>
        <button class="btn ${state.preflightFilter === 'resistor' ? 'btn-primary' : ''}" style="font-size:11.5px;" onclick="setPreflightFilter('resistor')">Resistors (11)</button>
        <button class="btn ${state.preflightFilter === 'divider' ? 'btn-primary' : ''}" style="font-size:11.5px;" onclick="setPreflightFilter('divider')">AC Dividers (12)</button>
        <button class="btn ${state.preflightFilter === 'wfg' ? 'btn-primary' : ''}" style="font-size:11.5px;" onclick="setPreflightFilter('wfg')">33622A Generator (11)</button>
      </div>
    </div>

    <!-- Table -->
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Target File</th>
            <th>Tag / Test Point</th>
            <th class="right">Nominal / Range</th>
            <th>Equipment ID</th>
            <th>Serial</th>
            <th class="right">Live Calibrated Value</th>
            <th>Cal Date</th>
          </tr>
        </thead>
        <tbody>
          <!-- 1. RESISTORS SECTION -->
          ${(state.preflightFilter === 'all' || state.preflightFilter === 'resistor') ? `
            <tr style="background:var(--track); font-weight:700;"><td colspan="7">📁 REFERENCE STANDARD RESISTORS (0.1 Ω – 1 GΩ)</td></tr>
            ${(() => {
              const d01 = ctx.zero_pt_one_details[ctx.zero_pt_one_pn] || {};
              return `
                <tr style="background:rgba(56, 189, 248, 0.08); font-weight:600;">
                  <td class="mono" style="color:var(--primary-accent); font-weight:700;">${ctx.set_name === 'Set 1' ? '286300.txt' : '286325.txt'}</td>
                  <td><span class="badge badge-reviewed">0.1 Ω Std</span></td>
                  <td class="mono right">0.1 Ω</td>
                  <td class="mono" style="color:var(--primary-accent); font-weight:700;">${escapeHtml(ctx.zero_pt_one_pn)}</td>
                  <td class="mono">${escapeHtml(d01.serial || '—')}</td>
                  <td class="mono right" style="color:var(--primary); font-weight:700;">${d01.last_measured ? d01.last_measured.toFixed(9) + ' Ω' : '<span style="color:var(--warn);">Missing</span>'}</td>
                  <td class="mono">${escapeHtml(d01.last_date || '—')}</td>
                </tr>
              `;
            })()}
            ${ctx.all_resistors.filter(r => r.set === ctx.set_name).map(r => `
              <tr>
                <td class="mono">${escapeHtml(r.file)}</td>
                <td>${escapeHtml(r.rx_tag)}</td>
                <td class="mono right">${escapeHtml(r.nominal)}</td>
                <td class="mono" style="color:var(--primary-accent); font-weight:700;">${escapeHtml(r.pn)}</td>
                <td class="mono">${escapeHtml(r.serial)}</td>
                <td class="mono right">${formatMeasured(r.measured_value, r.measured_value, 'standard_resistor', 'Ω')}</td>
                <td class="mono">${escapeHtml(r.cal_date)}</td>
              </tr>
            `).join('')}
          ` : ''}

          <!-- 2. AC DIVIDERS SECTION -->
          ${(state.preflightFilter === 'all' || state.preflightFilter === 'divider') ? `
            <tr style="background:var(--track); font-weight:700;"><td colspan="7">📁 AC VOLTAGE DIVIDERS (DIVMEANS.TXT — 10mV &amp; 100mV across 6 Frequencies)</td></tr>
            ${ctx.divider_test_points.filter(dp => dp.set === ctx.set_name).map(dp => `
              <tr>
                <td class="mono">${escapeHtml(dp.file)}</td>
                <td>${escapeHtml(dp.rx_tag)}</td>
                <td class="mono right">${escapeHtml(dp.nominal)}</td>
                <td class="mono" style="color:var(--primary-accent); font-weight:700;">${escapeHtml(dp.pn)}</td>
                <td class="mono">${escapeHtml(dp.serial)}</td>
                <td class="mono right">${dp.measured_value ? dp.measured_value.toFixed(5) : '<span style="color:var(--warn);">Missing</span>'}</td>
                <td class="mono">${escapeHtml(dp.cal_date)}</td>
              </tr>
            `).join('')}
          ` : ''}

          <!-- 3. 33622A WAVEFORM GENERATOR SECTION (11 cf Points) -->
          ${(state.preflightFilter === 'all' || state.preflightFilter === 'wfg') ? `
            <tr style="background:var(--track); font-weight:700;"><td colspan="7">📁 33622A WAVEFORM GENERATOR (${ctx.wfg_options[ctx.wfg_serial]?.file_id}_Extended.txt — 11 cf Data Points)</td></tr>
            ${(ctx.wfg_all_points[ctx.wfg_serial] || []).map(pt => `
              <tr>
                <td class="mono" style="color:var(--primary-accent);">${escapeHtml(pt.file)}</td>
                <td>${escapeHtml(pt.rx_tag)}</td>
                <td class="mono right">${escapeHtml(pt.nominal)}</td>
                <td class="mono" style="color:var(--primary-accent); font-weight:700;">${escapeHtml(pt.pn)}</td>
                <td class="mono">${escapeHtml(pt.serial)}</td>
                <td class="mono right" style="font-weight:700;">${pt.measured_value !== null ? (pt.measured_value > 0 ? '+' : '') + pt.measured_value.toFixed(5) + ' dB' : '<span style="color:var(--warn);">Missing</span>'}</td>
                <td class="mono">${escapeHtml(pt.cal_date)}</td>
              </tr>
            `).join('')}
          ` : ''}
        </tbody>
      </table>
    </div>
  `;
}

function setPreflightFilter(category) {
  state.preflightFilter = category;
  renderHTBasic();
}

async function updateHTBasicConfig() {
  const set_name = document.getElementById('htStation').value;
  const zero_pt_one_pn = document.getElementById('htResistor').value;
  const wfg_serial = document.getElementById('htWfg').value;

  state.htbasicContext = await api().get_htbasic_context(set_name, zero_pt_one_pn, wfg_serial);
  renderHTBasic();
}

// -----------------------------------------------------------------------------
// 5. Lab Setup & Database View
// -----------------------------------------------------------------------------
async function renderSettings() {
  const root = document.getElementById('appRoot');
  const s = await api().get_settings();

  root.innerHTML = `
    <div class="panel" style="max-width:680px; margin:0 auto;">
      <div class="panel-header">
        <div class="panel-title">Lab Network &amp; Environment Configuration</div>
      </div>

      <div style="margin-bottom:14px;">
        <label style="font-weight:700; font-size:12px; color:var(--ink-muted);">Local Working Database</label>
        <input type="text" readonly value="${escapeHtml(s.local_db_path)}" style="width:100%; margin-top:4px;" class="mono">
      </div>

      <div style="margin-bottom:14px;">
        <label style="font-weight:700; font-size:12px; color:var(--ink-muted);">Shared Lab Network Backup UNC Path</label>
        <input type="text" id="netDbPathInput" value="${escapeHtml(s.network_db_path)}" style="width:100%; margin-top:4px;" class="mono">
        <div style="font-size:11px; color:var(--ink-faint); margin-top:3px;">
          Backups create separate timestamped folders beside this path. They include the database and available certificates and attachments; they do not merge workstation changes.
        </div>
      </div>

      <div style="margin-bottom:20px;">
        <label style="font-weight:700; font-size:12px; color:var(--ink-muted);">Visual Theme Mode</label>
        <select id="themeSelector" style="width:100%; margin-top:4px;" onchange="app.setTheme(this.value)">
          <option value="dark" ${s.theme === 'dark' ? 'selected' : ''}>Obsidian Dark (Bench Low-Light Mode)</option>
          <option value="light" ${s.theme === 'light' ? 'selected' : ''}>Titanium Light (Standard Light Mode)</option>
        </select>
      </div>

      <div style="display:flex; justify-content:space-between; align-items:center; padding-top:14px; border-top:1px solid var(--line);">
        <button class="btn btn-primary" onclick="app.syncNow()">Back Up to Network</button>
        <button class="btn" onclick="saveSettingsForm()">Save Configuration</button>
      </div>
    </div>
  `;
}

async function saveSettingsForm() {
  const netPath = document.getElementById('netDbPathInput').value.trim();
  const theme = document.getElementById('themeSelector').value;
  await api().save_settings({ network_db_path: netPath, theme: theme });
  app.showToast('Configuration saved successfully.', 'success');
}

// -----------------------------------------------------------------------------
// App Actions, Modals & Toast System
// -----------------------------------------------------------------------------
const app = {
  showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = String(message);
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(8px)';
      setTimeout(() => toast.remove(), 250);
    }, 3500);
  },

  async copyToClipboard(text, label) {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      this.showToast(`${label} copied to clipboard: ${text}`, 'success');
    } catch {
      this.showToast(`Could not copy ${label}`, 'warning');
    }
  },

  async syncNow() {
    const pulse = document.getElementById('syncStatusPulse');
    const text = document.getElementById('syncStatusText');
    if (pulse) pulse.className = 'sync-pulse syncing';
    if (text) text.textContent = 'Backing up...';

    const res = await api().sync_database();
    if (res.ok) {
      if (pulse) pulse.className = 'sync-pulse';
      if (text) text.textContent = `Synced: ${res.time.slice(11)}`;
      this.showToast(res.missing_documents?.length ? `Backup completed; ${res.missing_documents.length} missing document(s) are listed in its manifest.` : 'Database and documents backed up successfully.', res.missing_documents?.length ? 'warning' : 'success');
    } else {
      if (pulse) pulse.className = 'sync-pulse error';
      if (text) text.textContent = 'Backup Failed';
      this.showToast(`Network backup failed: ${res.error}`, 'error');
    }
  },

  async downloadHTBasic() {
    const set_name = document.getElementById('htStation').value;
    const zero_pt_one_pn = document.getElementById('htResistor').value;
    const wfg_serial = document.getElementById('htWfg').value;
    
    const res = await api().generate_htbasic(set_name, zero_pt_one_pn, wfg_serial);
    if (res.ok) {
      this.showToast(`HTBasic package generated: ${res.path.split(/[\\\\/]/).pop()}`, 'success');
    } else if (res.problems) {
      this.showToast(`Pre-flight check failed: ${res.problems.length} missing reading(s).`, 'error');
    }
  },

async importCert() {
    const res = await api().import_certificate();
    if (res.ok) {
      if (Array.isArray(res.test_points)) {
        renderMultiPointImport(res);
        return;
      }
      window.pendingScalarImport = res;
      const card = document.getElementById('genericModalCard');
      card.innerHTML = `
        <div class="panel-header">
          <div class="panel-title">Ingest Calibration Certificate</div>
          <button class="btn" style="padding:2px 7px;" onclick="closeGenericModal()">&times;</button>
        </div>
        <p style="color:var(--ink-muted); margin:0 0 12px 0;">Verify extracted certificate values before committing to database:</p>
        <table class="trace-table" style="margin-bottom:16px;">
          <tr><td>Serial Number</td><td><strong class="mono">${escapeHtml(res.serial)}</strong></td></tr>
          <tr><td>Calibration Date</td><td><strong class="mono">${escapeHtml(res.cal_date)}</strong></td></tr>
          <tr><td>Measured Value</td><td><strong class="mono" style="color:var(--primary-accent);">${res.measured_value}</strong></td></tr>
          <tr><td>Relative Uncertainty</td><td><span class="mono">${res.mu_relative ? (res.mu_relative * 1e6).toFixed(2) + ' ppm' : '—'}</span></td></tr>
          <tr><td>Matched Standard</td><td>${res.asset ? escapeHtml(res.asset.model + ' (' + res.asset.asset_number + ')') : '<span style="color:var(--warn);">Unregistered Serial</span>'}</td></tr>
        </table>
        ${res.warnings && res.warnings.length ? `
          <div style="background:var(--warn-bg); border:1px solid var(--warn-border); border-radius:4px; padding:8px 10px; margin-bottom:14px; font-size:11.5px; color:var(--warn);">
            ${res.warnings.map(w => `<div>⚠ ${escapeHtml(w)}</div>`).join('')}
          </div>
        ` : ''}
        <div style="display:flex; justify-content:flex-end; gap:8px;">
          <button class="btn" onclick="closeGenericModal()">Cancel</button>
          <label><input type="checkbox" id="scalarVerified"> I verified the values and warnings against the PDF.</label>
          <button class="btn btn-primary" ${!res.asset ? 'disabled' : ''} onclick="commitImport(window.pendingScalarImport)">Commit to Database</button>
        </div>
      `;
      document.getElementById('genericModal').classList.add('open');
    }
    else if (!res.cancelled) {
      this.showToast(
        res.error || 'Certificate import failed. Check the application log.',
        'error'
      );
    }
  },

  openReportDialog() {
    const card = document.getElementById('genericModalCard');
    card.innerHTML = `
      <div class="panel-header">
        <div class="panel-title">Export Calibration Audit Report</div>
        <button class="btn" style="padding:2px 7px;" onclick="closeGenericModal()">&times;</button>
      </div>
      <p style="color:var(--ink-muted); margin:0 0 14px 0;">Select standard scope for instant PDF audit generation:</p>
      
      <div style="margin-bottom:16px;">
        <label style="font-weight:700; font-size:12px; color:var(--ink-muted); display:block; margin-bottom:6px;">Report Scope</label>
        <select id="reportScopeSelect" style="width:100%;">
          <option value="all">Full Metrology Master (All 34 Standards)</option>
          <option value="Set 1">Station 1 Kit (Set 1 Standards)</option>
          <option value="Set 2">Station 2 Kit (Set 2 Standards)</option>
          ${state.activeAssetId ? `<option value="current">Current Asset Only (${escapeHtml(state.activeAssetDetail?.asset?.model || 'Asset')})</option>` : ''}
        </select>
      </div>

      <div style="display:flex; justify-content:flex-end; gap:8px;">
        <button class="btn" onclick="closeGenericModal()">Cancel</button>
        <button class="btn btn-primary" onclick="generateReportByScope()">Save PDF Report</button>
      </div>
    `;
    document.getElementById('genericModal').classList.add('open');
  },

  async exportExcel(assetId) {
    const res = await api().export_excel(assetId);
    if (res.ok) this.showToast(`Excel workbook exported successfully.`, 'success');
  },

  toggleTheme() {
    const nextTheme = state.activeTheme === 'dark' ? 'light' : 'dark';
    this.setTheme(nextTheme);
  },

  async setTheme(theme) {
    state.activeTheme = theme;
    applyTheme(theme);
    await api().save_settings({ theme: theme });
  }
};

function applyTheme(theme) {
  document.body.className = `desktop-app-body theme-${theme}`;
  const label = document.getElementById('themeToggleLabel');
  if (label) label.textContent = `Theme: ${theme === 'dark' ? 'Dark' : 'Light'}`;
}

async function commitImport(res) {
  if (!res || !document.getElementById('scalarVerified')?.checked) {
    app.showToast('Verify the values and warnings against the certificate first.', 'warning');
    return;
  }
  const result = await api().commit_imported_certificate({
    asset_id: res.asset.id,
    cal_date: res.cal_date,
    measured_value: res.measured_value,
    mu_relative: res.mu_relative,
    cert_number: res.cert_number,
    pdf_path: res.pdf_path
  });
  closeGenericModal();
  if (result.ok) {
    app.showToast('Calibration recorded successfully.', 'success');
    router.navigate('asset_detail', { asset_id: res.asset.id });
  } else {
    app.showToast(
      result.error || 'Calibration could not be saved.',
      result.duplicate ? 'warning' : 'error'
    );
  }
} // <-- Make sure this closing brace exists


async function commitMultiPointImport() {
  const res = window.pendingMultiPointImport;

  if (!res || !Array.isArray(res.test_points) || !res.test_points.length) {
    app.showToast('No multi-point certificate is awaiting verification.', 'error');
    return;
  }

  const needsUncertainty = ['ac_divider', 'dcv_reference'].includes(res.asset.category);
  const readings = [];

  for (let i = 0; i < res.test_points.length; i++) {
    const point = res.test_points[i];
    const valueText = document.getElementById(`mp-value-${i}`)?.value;
    const uncertaintyText = needsUncertainty
      ? document.getElementById(`mp-uncertainty-${i}`)?.value
      : null;
    const verified = document.getElementById(`mp-verified-${i}`)?.checked;

    if (!verified) {
      app.showToast(`Please verify test point: ${point.name || point.point_name}`, 'warning');
      return;
    }

    if (valueText === '' || !Number.isFinite(Number(valueText))) {
      app.showToast(`Enter a valid measured value for ${point.name || point.point_name}.`, 'error');
      return;
    }

    const reading = {
      test_point_id: point.id,
      measured_value: Number(valueText),
      uncertainty: null
    };

    if (needsUncertainty) {
      if (
        uncertaintyText === '' ||
        !Number.isFinite(Number(uncertaintyText)) ||
        Number(uncertaintyText) < 0
      ) {
        app.showToast(`Enter a valid non-negative uncertainty for ${point.name || point.point_name}.`, 'error');
        return;
      }
      reading.uncertainty = Number(uncertaintyText);
    }

    readings.push(reading);
  }

  const result = await api().commit_imported_certificate({
    asset_id: res.asset.id,
    cal_date: res.cal_date,
    cert_number: res.cert_number,
    pdf_path: res.pdf_path,
    readings
  });

  if (result.ok) {
    window.pendingMultiPointImport = null;
    closeGenericModal();
    app.showToast(
      `Calibration recorded successfully (${result.point_count} test points).`,
      'success'
    );
    router.navigate('asset_detail', { asset_id: res.asset.id });
  } else {
    app.showToast(
      result.error || 'Calibration could not be saved.',
      result.duplicate ? 'warning' : 'error'
    );
  }
}


async function generateReportByScope() {
  const scope = document.getElementById('reportScopeSelect').value;
  closeGenericModal();

  let assetIds = null;
  if (scope === 'current') {
    assetIds = [state.activeAssetId];
  } else if (scope.startsWith('Set')) {
    const d = state.dashboardData || await api().get_dashboard();
    const group = d.sets.find(s => s.set_id === scope);
    if (group) assetIds = group.assets.map(a => a.id);
  }

  const res = await api().save_report(assetIds);
  if (res.ok) app.showToast('Audit PDF report generated successfully.', 'success');
}


function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  })[ch]);
}

function renderMultiPointImport(res) {
  const card = document.getElementById('genericModalCard');
  const points = res.test_points || [];
  const category = res.asset.category;
  const needsUncertainty = ['ac_divider', 'dcv_reference'].includes(category);
  const canSave = points.length > 0;

  window.pendingMultiPointImport = res;

  card.innerHTML = `
    <div class="panel-header">
      <div class="panel-title">Verify Multi-Point Certificate</div>
      <button class="btn" onclick="closeGenericModal()">&times;</button>
    </div>

    <p style="color:var(--ink-muted)">
      Standard: <strong>${escapeHtml(res.asset.model)}</strong>
      (${escapeHtml(res.serial)})<br>
      Calibration date: <strong>${escapeHtml(res.cal_date)}</strong><br>
      Certificate: <strong>${escapeHtml(res.cert_number || 'Not detected')}</strong>
    </p>

    <p style="color:var(--warn)">
      Review every reading against the certificate. Tick each verification
      box only after checking that point. OCR results are suggestions, not
      authoritative values.
    </p>

    ${res.warnings?.length ? `
      <div style="margin-bottom:12px;color:var(--warn)">
        ${res.warnings.map(w => `<div>⚠ ${escapeHtml(w)}</div>`).join('')}
      </div>
    ` : ''}

    <div style="overflow-x:auto;max-height:420px;overflow-y:auto">
      <table class="trace-table" style="width:100%">
        <thead>
          <tr>
            <th>Test Point</th>
            <th>Measured Value (${escapeHtml(points[0]?.unit || '')})</th>
            ${needsUncertainty ? `<th>Uncertainty (${escapeHtml(res.uncertainty_unit || '')})</th>` : ''}
            <th>Verified</th>
          </tr>
        </thead>
        <tbody>
          ${points.map((p, i) => `
            <tr>
              <td>
                <strong>${escapeHtml(p.name || p.point_name)}</strong>
                <div style="color:var(--ink-muted);font-size:11px">
                  ${escapeHtml(p.group_name || '')}
                </div>
                ${p.extraction_status !== 'extracted'
                  ? '<div style="color:var(--warn);font-size:11px">Manual entry required</div>'
                  : '<div style="font-size:11px">OCR extracted — verify</div>'}
              </td>
              <td>
                <input
                  id="mp-value-${i}"
                  type="number"
                  step="any"
                  value="${p.measured_value ?? ''}"
                  style="width:150px"
                  aria-label="Measured value for ${escapeHtml(p.name || p.point_name)}"
                >
              </td>
              ${needsUncertainty ? `
                <td>
                  <input
                    id="mp-uncertainty-${i}"
                    type="number"
                    min="0"
                    step="any"
                    value="${p.uncertainty ?? ''}"
                    style="width:110px"
                    aria-label="Uncertainty for ${escapeHtml(p.name || p.point_name)}"
                  >
                </td>
              ` : ''}
              <td>
                <input id="mp-verified-${i}" type="checkbox"
                  aria-label="Verify ${escapeHtml(p.name || p.point_name)}">
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>

    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px">
      <button class="btn" onclick="closeGenericModal()">Cancel</button>
      <button class="btn btn-primary"
        ${canSave ? '' : 'disabled'}
        onclick="commitMultiPointImport()">
        Verify and Commit
      </button>
    </div>
  `;

  document.getElementById('genericModal').classList.add('open');
}

function openStoredNote(calId) {
  const cal = state.activeAssetDetail?.calibrations.find(item => item.id === calId);
  if (cal) openNoteModal(cal.date, cal.reviewer_comment, cal.reviewer_attachment_path, calId);
}

function openNoteModal(date, comment, attachPath, calId) {
  const card = document.getElementById('genericModalCard');
  card.innerHTML = `
    <div class="panel-header">
      <div class="panel-title">Reviewer Quality Note — ${escapeHtml(date)}</div>
      <button class="btn" style="padding:2px 7px;" onclick="closeGenericModal()">&times;</button>
    </div>
    <p style="font-size:13.5px; color:var(--ink); line-height:1.6; white-space:pre-wrap; margin:0 0 16px 0;">${escapeHtml(comment || 'No note text entered.')}</p>
    ${attachPath ? `
      <div style="padding-top:12px; border-top:1px dashed var(--line); margin-bottom:14px;">
        <span style="font-size:12px; color:var(--ink-muted);">Attached File: <strong>${escapeHtml(attachPath.split(/[\\\\/]/).pop())}</strong></span>
      </div>
    ` : ''}
    <div style="display:flex; justify-content:flex-end;">
      <button class="btn btn-primary" onclick="closeGenericModal()">Close</button>
    </div>
  `;
  document.getElementById('genericModal').classList.add('open');
}

function openEditCalModal(calId) {
  api().get_calibration_for_edit(calId).then(cal => {
    if (!cal) return;
    const card = document.getElementById('genericModalCard');
    card.replaceChildren();
    const title = document.createElement('h3');
    title.textContent = 'Edit Calibration Event';
    card.appendChild(title);
    const form = document.createElement('form');
    card.appendChild(form);
    const fields = {};
    const addInput = (parent, key, label, type, value, required = false) => {
      const wrapper = document.createElement('label');
      wrapper.style.cssText = 'display:block;margin:10px 0;font-size:12px';
      const caption = document.createElement('span');
      caption.textContent = label;
      wrapper.appendChild(caption);
      const input = document.createElement('input');
      input.type = type;
      if (type === 'checkbox') input.checked = Boolean(value);
      else input.value = value ?? '';
      if (type === 'number') input.step = 'any';
      input.required = required;
      input.style.cssText = type === 'checkbox' ? 'margin-left:10px' : 'display:block;width:100%';
      wrapper.appendChild(input);
      parent.appendChild(wrapper);
      return input;
    };
    fields.cal_date = addInput(form, 'date', 'Calibration date', 'date', cal.cal_date, true);
    fields.cert_number = addInput(form, 'certificate', 'Certificate number', 'text', cal.cert_number);
    const points = cal.test_point_readings || [];
    if (!points.length) {
      fields.measured_value = addInput(form, 'measured', 'Measured reading', 'number', cal.measured_value, true);
      fields.mu_relative = addInput(form, 'mu', 'Relative uncertainty (ratio)', 'number', cal.mu_relative, true);
      fields.mu_relative.min = '0';
    }
    const pointInputs = points.map(point => {
      const group = document.createElement('fieldset');
      const legend = document.createElement('legend');
      legend.textContent = point.point_name;
      group.appendChild(legend);
      form.appendChild(group);
      const value = addInput(group, 'value', `Measured value (${point.unit})`, 'number', point.measured_value, true);
      let uncertainty = null;
      if (point.uncertainty !== null && point.uncertainty !== undefined) {
        uncertainty = addInput(group, 'uncertainty', point.unit === 'V' ? 'Uncertainty (nV)' : 'Uncertainty (ppm)', 'number', point.uncertainty, true);
        uncertainty.min = '0';
      }
      const excluded = addInput(group, 'excluded', 'Exclude this point from regression', 'checkbox', point.excluded_from_regression);
      return {point, value, uncertainty, excluded};
    });
    fields.pressure_hpa = addInput(form, 'pressure', 'Pressure (hPa)', 'number', cal.pressure_hpa);
    fields.location = addInput(form, 'location', 'Location', 'text', cal.location);
    fields.is_adjusted = addInput(form, 'adjusted', 'Instrument adjusted (starts a new trend epoch)', 'checkbox', cal.is_adjusted);
    fields.excluded_from_regression = addInput(form, 'exclude', 'Exclude this entire event from regression', 'checkbox', cal.excluded_from_regression);
    const caption = document.createElement('label');
    caption.textContent = 'Reviewer quality note';
    const comment = document.createElement('textarea');
    comment.value = cal.reviewer_comment || '';
    comment.style.cssText = 'width:100%;height:70px';
    caption.appendChild(comment);
    form.appendChild(caption);
    const cancel = document.createElement('button');
    cancel.type = 'button'; cancel.className = 'btn'; cancel.textContent = 'Cancel';
    cancel.addEventListener('click', () => closeGenericModal());
    const save = document.createElement('button');
    save.type = 'submit'; save.className = 'btn btn-primary'; save.textContent = 'Save changes';
    form.append(cancel, save);
    form.addEventListener('submit', async event => {
      event.preventDefault();
      save.disabled = true;
      const data = {id: cal.id, reviewer_comment: comment.value};
      Object.entries(fields).forEach(([name, input]) => {
        data[name] = input.type === 'checkbox' ? input.checked : input.value;
      });
      data.test_point_readings = pointInputs.map(({point, value, uncertainty, excluded}) => ({
        tp_id: point.tp_id, measured_value: value.value,
        uncertainty: uncertainty ? uncertainty.value : null,
        excluded_from_regression: excluded.checked
      }));
      try {
        const result = await api().save_calibration_edit(data);
        if (!result.ok) {
          app.showToast(result.error || 'Calibration could not be saved.', 'error');
          return;
        }
        closeGenericModal();
        app.showToast('Calibration record updated successfully.', 'success');
        router.navigate('asset_detail', {asset_id: state.activeAssetId, tp_id: state.activeTestPointId});
      } catch (error) {
        app.showToast(`Calibration could not be saved: ${error.message}`, 'error');
      } finally {
        save.disabled = false;
      }
    });
    document.getElementById('genericModal').classList.add('open');
  }).catch(error => app.showToast(`Could not open calibration: ${error.message}`, 'error'));
}

function closeGenericModal() {
  document.getElementById('genericModal').classList.remove('open');
}



// Global Startup
function startApp() {
  router.navigate('dashboard');
}

if (window.pywebview) {
  startApp();
} else {
  window.addEventListener('pywebviewready', startApp);
}