/**
 * app.js - Complete Studio Application Controller for pywebview
 * Built-in zero-dependency Metrology Canvas Charting Engine with Interactive Hover
 */

let activeAssetDetail = null;
let currentChartMode = 'primary';
let hoveredPoint = null;

const router = {
  current: 'dashboard',
  params: {},
  navigate(view, params = {}) {
    this.current = view;
    this.params = params;
    render();
  }
};

const app = {
  data: null,
  activeFilter: 'all',
  activeSet: 'all',
  searchQuery: '',
  selectedIds: [],

  async init() {
    window.addEventListener('pywebviewready', () => this.refresh());
    if (window.pywebview && window.pywebview.api) this.refresh();
    setInterval(() => this.updateSyncStatus(), 30000);
  },

  async refresh() {
    try {
      this.data = await window.pywebview.api.get_dashboard();
      this.updateSyncStatus();
      render();
    } catch (e) {
      console.error(e);
    }
  },

  async updateSyncStatus() {
    try {
      const status = await window.pywebview.api.get_sync_status();
      const txt = document.getElementById('syncStatusText');
      if (txt) {
        txt.textContent = status.last_sync ? `Synced: ${status.last_sync.slice(11, 16)}` : 'Network Ready';
      }
    } catch (e) {}
  },

  async syncNow() {
    const res = await window.pywebview.api.sync_database();
    if (res.ok) {
      alert(`Database backed up successfully to:\n${res.target}`);
      this.updateSyncStatus();
    } else {
      alert(`Sync failed: ${res.error}`);
    }
  },

  async importCert() {
    const res = await window.pywebview.api.import_certificate();
    if (res.ok) {
      alert(`Certificate parsed successfully!\nSerial: ${res.serial}\nDate: ${res.cal_date}\nValue: ${res.measured_value}`);
      this.refresh();
    } else if (!res.cancelled) {
      alert(`Import error: ${res.error}`);
    }
  },

  async generateBatchReport() {
    const ids = this.selectedIds.length > 0 ? this.selectedIds : null;
    const res = await window.pywebview.api.save_report(ids);
    if (res.ok) alert(`PDF Report generated:\n${res.path}`);
  }
};

function render() {
  const root = document.getElementById('appRoot');
  const title = document.getElementById('currentViewTitle');
  if (!app.data) return;

  if (router.current === 'dashboard') {
    title.textContent = 'Fleet Overview';
    root.innerHTML = renderDashboard(app.data);
  } else if (router.current === 'asset') {
    title.textContent = 'Asset Telemetry';
    loadAssetDetail(router.params.id, router.params.tp);
  } else if (router.current === 'htbasic') {
    title.textContent = 'Cal. Factor Files';
    loadHTBasic();
  }
}

// -----------------------------------------------------------------------------
// 1. DASHBOARD VIEW
// -----------------------------------------------------------------------------
function renderDashboard(data) {
  const allAssets = (data.sets || []).flatMap(s => s.assets || []);
  const filtered = allAssets.filter(a => {
    if (app.activeSet !== 'all' && a.set_id !== app.activeSet) return false;
    if (app.activeFilter !== 'all' && (a.category || 'standard_resistor') !== app.activeFilter) return false;
    if (app.searchQuery) {
      const q = app.searchQuery.toLowerCase();
      const text = `${a.serial} ${a.model || ''} ${a.asset_number || ''}`.toLowerCase();
      if (!text.includes(q)) return false;
    }
    return true;
  });

  return `
    <div style="max-width: 1480px; margin: 0 auto;">
      <!-- KPI Metric Cards -->
      <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px;">
        <div class="panel" style="margin:0; padding:16px; border-top:3px solid var(--primary);">
          <div style="font-size:11px; font-weight:700; color:var(--ink-muted);">TOTAL STANDARDS TRACKED</div>
          <div class="mono" style="font-size:30px; font-weight:700; color:var(--primary); margin-top:4px;">${data.total || 0}</div>
        </div>
        <div class="panel" style="margin:0; padding:16px; border-top:3px solid var(--ok);">
          <div style="font-size:11px; font-weight:700; color:var(--ink-muted);">WITHIN TREND</div>
          <div class="mono" style="font-size:30px; font-weight:700; color:var(--ok); margin-top:4px;">${data.ok_count || 0}</div>
        </div>
        <div class="panel" style="margin:0; padding:16px; border-top:3px solid var(--warn);">
          <div style="font-size:11px; font-weight:700; color:var(--ink-muted);">OUT OF TREND (UNREVIEWED)</div>
          <div class="mono" style="font-size:30px; font-weight:700; color:var(--warn); margin-top:4px;">${data.out_count || 0}</div>
        </div>
        <div class="panel" style="margin:0; padding:16px; border-top:3px solid #94a3b8;">
          <div style="font-size:11px; font-weight:700; color:var(--ink-muted);">INSUFFICIENT HISTORY</div>
          <div class="mono" style="font-size:30px; font-weight:700; color:var(--neutral-status); margin-top:4px;">${data.insufficient_count || 0}</div>
        </div>
      </div>

      <!-- Category Filter Strip -->
      <div style="background:var(--track); padding:4px; border-radius:var(--radius-md); display:flex; gap:4px; margin-bottom:16px; border:1px solid var(--line);">
        ${[
          { id: 'all', label: 'All Standards', count: data.total },
          { id: 'standard_resistor', label: 'Resistors', count: 23 },
          { id: 'dcv_reference', label: 'DC Voltage Reference', count: 3 },
          { id: 'ac_divider', label: 'AC Dividers', count: 4 },
          { id: 'waveform_generator', label: 'Waveform Generators', count: 3 }
        ].map(cat => `
          <button class="btn ${app.activeFilter === cat.id ? 'btn-primary' : ''}" 
                  style="flex:1; border:none; ${app.activeFilter === cat.id ? '' : 'background:transparent; box-shadow:none;'}"
                  onclick="app.activeFilter='${cat.id}'; render();">
            ${cat.label} <span style="font-family:monospace; font-size:11px; opacity:0.8; margin-left:4px;">(${cat.count})</span>
          </button>
        `).join('')}
      </div>

      <!-- Secondary Toolbar -->
      <div style="background:#fff; padding:10px 16px; border-radius:var(--radius-md); border:1px solid var(--line); display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
        <div style="display:flex; align-items:center; gap:6px;">
          <span style="font-size:12px; font-weight:600; color:var(--ink-muted); margin-right:4px;">Set Filter:</span>
          ${['all', 'Set 1', 'Set 2', 'Set 3'].map(sName => `
            <button class="btn ${app.activeSet === sName ? 'btn-primary' : ''}" 
                    style="border-radius:999px; padding:2px 10px; font-size:11.5px;"
                    onclick="app.activeSet='${sName}'; render();">
              ${sName === 'all' ? 'All Sets' : sName}
            </button>
          `).join('')}
        </div>
        <input type="text" placeholder="Search serial, model, trace ID..." value="${app.searchQuery}"
               oninput="app.searchQuery=this.value; render();"
               style="padding:6px 12px; border-radius:6px; border:1px solid var(--line); font-size:12px; width:260px;">
      </div>

      <!-- Master Fleet Table -->
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th style="width:34px;"><input type="checkbox" onchange="toggleSelectAll(this)"></th>
              <th>Serial</th>
              <th>Model</th>
              <th>Equipment ID</th>
              <th class="right">Nominal / Function</th>
              <th>Set</th>
              <th>Category</th>
              <th class="right"># Cals</th>
              <th>Last Cal</th>
              <th class="right">Last Measured</th>
              <th>Trend Status</th>
            </tr>
          </thead>
          <tbody>
            ${filtered.length === 0 ? `
              <tr><td colspan="11" style="text-align:center; padding:32px; color:var(--ink-faint);">No standards match active criteria.</td></tr>
            ` : filtered.map(a => `
              <tr onclick="router.navigate('asset', { id: ${a.id} })">
                <td onclick="event.stopPropagation()">
                  <input type="checkbox" ${app.selectedIds.includes(a.id) ? 'checked' : ''} onchange="toggleSelectOne(${a.id})">
                </td>
                <td class="mono" style="font-weight:700; color:var(--primary-accent);">${a.serial}</td>
                <td><strong>${a.model || '—'}</strong></td>
                <td class="mono" style="color:var(--ink-muted);">${a.asset_number || '—'}</td>
                <td class="num-cell right">${formatNominal(a)}</td>
                <td><span class="badge badge-neutral">${a.set_id || '—'}</span></td>
                <td style="color:var(--ink-muted); font-size:12px;">${formatCat(a.category)}</td>
                <td class="num-cell right">${a.num_calibrations || 0}</td>
                <td class="num-cell">${a.last_cal_date || '—'}</td>
                <td class="num-cell right" style="font-weight:700;">${formatVal(a)}</td>
                <td>
                  <span class="badge ${a.status === 'ok' ? 'badge-ok' : (a.status === 'reviewed_out_of_trend' ? 'badge-reviewed' : 'badge-warn')}">
                    <span class="badge-dot"></span>
                    ${a.status === 'ok' ? 'In Trend' : (a.status === 'reviewed_out_of_trend' ? 'Reviewed' : 'Out of Trend')}
                  </span>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>

      <!-- Floating Batch Drawer -->
      <div class="floating-drawer ${app.selectedIds.length > 0 ? 'visible' : ''}">
        <span style="font-size:12.5px; font-weight:500;">
          <strong class="mono">${app.selectedIds.length}</strong> standards selected
        </span>
        <button class="btn btn-primary" onclick="app.generateBatchReport()" style="padding:4px 14px; font-size:12px;">Generate PDF Report</button>
        <button class="btn" onclick="app.selectedIds=[]; render();" style="background:transparent; color:#fff; border-color:rgba(255,255,255,0.3); padding:4px 10px; font-size:12px;">Clear</button>
      </div>
    </div>
  `;
}

function toggleSelectAll(cb) {
  if (cb.checked && app.data) {
    const all = (app.data.sets || []).flatMap(s => s.assets || []);
    app.selectedIds = all.map(a => a.id);
  } else {
    app.selectedIds = [];
  }
  render();
}

function toggleSelectOne(id) {
  if (app.selectedIds.includes(id)) {
    app.selectedIds = app.selectedIds.filter(i => i !== id);
  } else {
    app.selectedIds.push(id);
  }
  render();
}

function formatNominal(a) {
  if (a.category === 'dcv_reference') return '10.0 V';
  if (a.category === 'ac_divider') return (a.model && a.model.includes('10mV')) ? '100:1 Ratio' : '10:1 Ratio';
  if (a.category === 'waveform_generator') return '15 Points (dB)';
  const n = parseFloat(a.nominal_ohms) || 0;
  return n >= 1e6 ? `${n/1e6} MΩ` : n >= 1e3 ? `${n/1e3} kΩ` : `${n} Ω`;
}

function formatCat(c) {
  if (c === 'dcv_reference') return 'DC Voltage Ref';
  if (c === 'ac_divider') return 'AC Voltage Divider';
  if (c === 'waveform_generator') return 'Waveform Gen';
  return 'Standard Resistor';
}

function formatVal(a) {
  if (a.last_measured === null || a.last_measured === undefined) return '—';
  const val = Number(a.last_measured);
  if (isNaN(val)) return String(a.last_measured);
  if (a.category === 'dcv_reference') return val.toFixed(8) + ' V';
  if (a.category === 'ac_divider') return val.toFixed(5);
  if (a.category === 'waveform_generator') return (val > 0 ? '+' : '') + val.toFixed(4) + ' dB';
  return val.toFixed(7) + ' Ω';
}

// -----------------------------------------------------------------------------
// 2. ASSET DETAIL & INTERACTIVE CANVAS CHART WITH HOVER & CROSSHAIR
// -----------------------------------------------------------------------------
async function loadAssetDetail(id, tpId) {
  const root = document.getElementById('appRoot');
  const d = await window.pywebview.api.get_asset_detail(id, tpId);
  activeAssetDetail = d;
  hoveredPoint = null;

  root.innerHTML = `
    <div style="max-width: 1480px; margin: 0 auto;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
        <button class="btn" onclick="router.navigate('dashboard')">← Return to Dashboard</button>
        <button class="btn" onclick="exportCurrentExcel(${d.asset.id})">Export Excel</button>
      </div>

      <!-- Hero Banner -->
      <div class="panel" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
        <div>
          <h2 style="margin:0 0 4px 0; color:var(--primary); font-size:20px;">${d.asset.model || d.asset.serial}</h2>
          <div style="font-size:12px; color:var(--ink-muted); display:flex; gap:10px;">
            <span>Equipment ID: <strong>${d.asset.asset_number || '—'}</strong></span>
            <span>·</span>
            <span>Serial: <strong class="mono" style="background:#f1f5f9; padding:1px 6px; border-radius:4px;">${d.asset.serial}</strong></span>
            <span>·</span>
            <span>Category: <strong>${formatCat(d.asset.category)}</strong></span>
            <span>·</span>
            <span>Set: <strong>${d.asset.set_id || '—'}</strong></span>
          </div>
        </div>
      </div>

      <!-- Multi-Point Matrix -->
      ${d.test_points && d.test_points.length > 1 ? `
        <div class="panel" style="margin-bottom:16px;">
          <div class="panel-header">
            <h3 class="panel-title">Characterized Test Points Matrix (${d.test_points.length} Series)</h3>
            <span style="font-size:11.5px; color:var(--ink-muted);">Click any row to switch active curve below</span>
          </div>
          <div class="table-container" style="box-shadow:none; margin:0;">
            <table>
              <thead>
                <tr>
                  <th>Test Point</th>
                  <th>Classification</th>
                  <th class="right">Latest Value</th>
                  <th class="right">Drift</th>
                  <th>Latest Cal Date</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                ${d.test_points.map(tp => `
                  <tr style="cursor:pointer; ${tp.id === d.active_test_point_id ? 'background:#eff6ff; font-weight:600;' : ''}"
                      onclick="router.navigate('asset', { id: ${d.asset.id}, tp: ${tp.id} })">
                    <td style="color:var(--primary-accent);">${tp.point_name}</td>
                    <td style="color:var(--ink-muted);">${tp.group_name}</td>
                    <td class="num-cell right">${tp.latest_value !== null ? Number(tp.latest_value).toFixed(5) + ' ' + tp.unit : '—'}</td>
                    <td class="num-cell right">${tp.drift !== null ? (tp.drift > 0 ? '+' : '') + Number(tp.drift).toFixed(4) : '—'}</td>
                    <td class="num-cell">${tp.latest_date || '—'}</td>
                    <td><span class="badge ${tp.status === 'ok' ? 'badge-ok' : (tp.status === 'reviewed_out_of_trend' ? 'badge-reviewed' : 'badge-warn')}">${tp.status === 'ok' ? 'In Trend' : (tp.status === 'reviewed_out_of_trend' ? 'Reviewed' : 'Out of Trend')}</span></td>
                    <td>
                      <button class="btn ${tp.id === d.active_test_point_id ? 'btn-primary' : ''}" style="padding:1px 8px; font-size:11px;">
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

      <!-- 2-Column Info & Specs -->
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px; margin-bottom:16px;">
        <div class="panel" style="margin:0;">
          <div class="panel-header"><h3 class="panel-title">Active Characterization Series</h3></div>
          <div style="display:grid; grid-template-columns: auto 1fr; gap:6px 16px; font-size:12px;">
            <span style="color:var(--ink-muted);">Series:</span><strong>${d.active_test_point ? d.active_test_point.point_name : d.asset.nominal_ohms + ' Ω'}</strong>
            <span style="color:var(--ink-muted);">Records:</span><strong>${d.calibrations.length} calibrations</strong>
            ${d.trend ? `
              <span style="color:var(--ink-muted);">Regression Fit:</span><span>n = ${d.trend.n} (excludes newest calibration)</span>
              <span style="color:var(--ink-muted);">Annual Drift Rate:</span><strong class="mono" style="color:var(--primary-accent);">${(d.trend.slope * 365.25).toExponential(3)} ${d.asset.unit}/yr</strong>
              <span style="color:var(--ink-muted);">Residual Error (Syx):</span><span class="mono">${d.trend.Syx.toExponential(3)}</span>
            ` : ''}
          </div>
        </div>

        <div class="panel" style="margin:0;">
          <div class="panel-header"><h3 class="panel-title">Stability &amp; Environmental Telemetry</h3></div>
          ${d.stability ? `
            <div style="font-size:12px;">
              <div>Spec: <strong>${d.stability.spec_description}</strong></div>
              <div style="margin-top:4px;">Observed drift across ${d.stability.elapsed_days} days: <strong>${d.stability.observed_drift_ppm.toFixed(2)} ppm</strong> (Limit: ±${d.stability.allowance_ppm.toFixed(2)} ppm)</div>
              <div style="margin-top:12px;">
                <div style="display:flex; justify-content:space-between; font-size:10px; font-family:monospace; font-weight:700; color:var(--ink-faint); margin-bottom:2px;">
                  <span>-${d.stability.allowance_ppm.toFixed(2)} ppm</span>
                  <span>0 ppm</span>
                  <span>+${d.stability.allowance_ppm.toFixed(2)} ppm</span>
                </div>
                <div style="height:10px; background:#e2e8f0; border:1px solid #cbd5e1; border-radius:999px; position:relative;">
                  <div style="position:absolute; left:50%; top:0; bottom:0; width:2px; background:#475569; transform:translateX(-50%);"></div>
                  <div style="position:absolute; left:0; right:0; top:0; bottom:0; background:rgba(5, 150, 105, 0.15); border-radius:999px;"></div>
                  <div style="position:absolute; left:${Math.min(98, Math.max(2, 50 + (d.stability.observed_drift_ppm / d.stability.allowance_ppm) * 50))}%; top:50%; width:12px; height:12px; border-radius:50%; transform:translate(-50%, -50%); background:${d.stability.exceeds ? '#d97706' : '#059669'}; border:2px solid #ffffff;"></div>
                </div>
              </div>
            </div>
          ` : (d.asset.category === 'dcv_reference' ? `
            <div style="font-size:12px;">
              <p style="margin:0 0 6px 0; color:var(--ink-muted);">Fluke 732A/C altitude sensitivity (~ -2.5 to -3 nV/hPa). Active Roseville epoch isolated from Loveland step shifts.</p>
              ${d.calibrations.length > 0 && d.calibrations[d.calibrations.length - 1].pressure_hpa ? `
                <div style="padding:6px 10px; background:var(--panel-subtle); border-radius:6px; border:1px solid var(--line); font-family:monospace;">
                  Ambient: <strong>${d.calibrations[d.calibrations.length - 1].pressure_hpa} hPa</strong> · Facility: <strong>${d.calibrations[d.calibrations.length - 1].location || 'Roseville'}</strong>
                </div>
              ` : ''}
            </div>
          ` : `
            <div style="font-size:12px; color:var(--ink-muted); padding:8px 0;">
              Continuous multi-year regression active across all historical observations.
            </div>
          `)}
        </div>
      </div>

      <!-- Trend Canvas with 95% Shading & Interactive Hover Crosshair -->
      <div class="panel" style="margin-bottom:16px;">
        <div class="panel-header">
          <h3 class="panel-title">Regression Trend &amp; 95% Prediction Interval: ${d.active_test_point ? d.active_test_point.point_name : d.asset.model}</h3>
          <div style="display:flex; gap:4px; background:var(--track); padding:2px; border-radius:6px;">
            <button class="btn ${currentChartMode === 'primary' ? 'btn-primary' : ''}" style="padding:2px 10px; font-size:11.5px;" onclick="switchChartMode('primary')">Measured (${d.asset.unit})</button>
            <button class="btn ${currentChartMode === 'relative' ? 'btn-primary' : ''}" style="padding:2px 10px; font-size:11.5px;" onclick="switchChartMode('relative')">${d.asset.unit === 'dB' ? 'Deviation (dB)' : 'Relative Error (ppm)'}</button>
          </div>
        </div>
        <div style="position:relative; width:100%; height:320px;">
          <canvas id="desktopTrendCanvas" style="width:100%; height:100%; cursor:crosshair;"></canvas>
          <!-- Floating Dark Telemetry Tooltip -->
          <div id="canvasHoverTooltip" style="display:none; position:absolute; pointer-events:none; z-index:20; background:#0a192f; color:#fff; padding:10px 14px; border-radius:8px; border:1px solid #334155; box-shadow:0 10px 25px rgba(0,0,0,0.3); font-size:11.5px; min-width:190px;"></div>
        </div>
      </div>

      <!-- Calibration History Table (Zero Overflow) -->
      <div class="panel-header" style="margin-bottom:8px;"><h3 class="panel-title">Calibration History: ${d.active_test_point ? d.active_test_point.point_name : 'Readings'}</h3></div>
      <div class="table-container" style="max-height:460px; overflow-y:auto;">
        <table>
          <thead style="position:sticky; top:0; z-index:10; background:#f8fafc;">
            <tr>
              <th>Cal Date</th>
              <th class="right">Measured Value</th>
              <th class="right">Uncertainty</th>
              <th class="right">Error</th>
              <th class="right">Drift</th>
              <th class="right">95% Acceptance Limits</th>
              ${d.asset.category === 'dcv_reference' ? '<th>Facility</th><th class="right">Pressure</th>' : ''}
              <th>Status</th>
              <th style="text-align:center;">Note</th>
              <th style="text-align:right;">Action</th>
            </tr>
          </thead>
          <tbody>
            ${(d.calibrations || []).slice().reverse().map(c => `
              <tr style="${c.display_status === 'out_of_trend' ? 'background:rgba(254,243,199,0.4);' : (c.display_status === 'reviewed_out_of_trend' ? 'background:rgba(239,246,255,0.45);' : '')}">
                <td class="mono font-bold">${c.date} ${c.is_adjusted ? '<span class="badge badge-warn" style="font-size:9px;">Adj</span>' : ''}</td>
                <td class="num-cell right font-bold">${Number(c.measured_value).toFixed(d.asset.unit === 'V' ? 8 : (d.asset.unit === 'dB' ? 5 : 5))} ${d.asset.unit}</td>
                <td class="num-cell right">${d.asset.category === 'dcv_reference' ? (c.mu_relative * 10 * 1e9).toFixed(1) + ' nV' : (d.asset.category === 'ac_divider' ? Number(c.mu_relative).toFixed(1) + ' ppm' : '—')}</td>
                <td class="num-cell right">${c.error_ppm !== undefined ? (c.error_ppm > 0 ? '+' : '') + Number(c.error_ppm).toFixed(2) + ' ppm' : '—'}</td>
                <td class="num-cell right">${c.drift_ppm !== undefined && c.drift_ppm !== null ? (c.drift_ppm > 0 ? '+' : '') + Number(c.drift_ppm).toFixed(2) + ' ppm' : '—'}</td>
                <td class="num-cell right">
                  ${c.lower !== null && c.upper !== null && c.lower !== undefined && c.upper !== undefined ? `
                    <span class="limit-chip">${Number(c.lower).toFixed(d.asset.unit === 'V' ? 8 : 5)} <span class="limit-sep">↔</span> ${Number(c.upper).toFixed(d.asset.unit === 'V' ? 8 : 5)}</span>
                  ` : '—'}
                </td>
                ${d.asset.category === 'dcv_reference' ? `<td>${c.location || '—'}</td><td class="num-cell right">${c.pressure_hpa ? Math.round(c.pressure_hpa) + ' hPa' : '—'}</td>` : ''}
                <td>
                  <span class="badge ${c.display_status === 'ok' ? 'badge-ok' : (c.display_status === 'reviewed_out_of_trend' ? 'badge-reviewed' : 'badge-warn')}">
                    <span class="badge-dot"></span>
                    ${c.display_status === 'ok' ? 'In Trend' : (c.display_status === 'reviewed_out_of_trend' ? 'Reviewed' : 'Out of Trend')}
                  </span>
                </td>
                <td style="text-align:center;">
                  ${c.reviewer_comment || c.reviewer_attachment_path ? `
                    <button class="btn" style="padding:1px 6px; font-size:11px;" onclick="openNoteModal('${c.date}', '${(c.reviewer_comment || '').replace(/'/g, "\\'")}', '${c.reviewer_attachment_path || ''}', ${c.id})">Note</button>
                  ` : '—'}
                </td>
                <td style="text-align:right;">
                  <button class="btn" style="padding:1px 7px; font-size:11px;" onclick="openEditCalibrationModal(${c.id})">Edit</button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;

// Wait for DOM reflow so canvas has full width and height
  requestAnimationFrame(() => {
    setTimeout(() => {
      setupInteractiveCanvas(d, currentChartMode);
    }, 50);
  });
}

// -----------------------------------------------------------------------------
// STANDALONE 100% OFFLINE INTERACTIVE CANVAS CHART WITH HOVER & CROSSHAIR
// -----------------------------------------------------------------------------
function setupInteractiveCanvas(d, mode) {
  const canvas = document.getElementById('desktopTrendCanvas');
  const tooltip = document.getElementById('canvasHoverTooltip');
  if (!canvas) return;

  function renderChart() {
    const ctx = canvas.getContext('2d');
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * window.devicePixelRatio;
    canvas.height = rect.height * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    const w = rect.width;
    const h = rect.height;
    const padding = { top: 20, right: 30, bottom: 35, left: 75 };

    const isPrimary = (mode === 'primary');
    const cals = d.calibrations || [];
    if (cals.length === 0) return;

    const points = cals.map(c => ({
      x: c.accumulated_days,
      y: isPrimary ? c.measured_value : c.error_ppm,
      pred: isPrimary ? c.predicted : (c.predicted ? c.error_ppm : null),
      lower: isPrimary ? c.lower : null,
      upper: isPrimary ? c.upper : null,
      status: c.display_status,
      adj: c.is_adjusted,
      raw: c
    }));

    const allX = points.map(p => p.x);
    const allY = points.flatMap(p => [p.y, p.pred, p.lower, p.upper]).filter(v => v !== null && v !== undefined && !isNaN(v));

    const minX = Math.min(...allX, 0);
    const maxX = Math.max(...allX, 100);
    let minY = Math.min(...allY);
    let maxY = Math.max(...allY);

    const yRange = (maxY - minY) || 0.0001;
    minY -= yRange * 0.08;
    maxY += yRange * 0.08;

    const toScreenX = (x) => padding.left + ((x - minX) / ((maxX - minX) || 1)) * (w - padding.left - padding.right);
    const toScreenY = (y) => h - padding.bottom - ((y - minY) / ((maxY - minY) || 1)) * (h - padding.top - padding.bottom);

    ctx.clearRect(0, 0, w, h);

    // Draw Gridlines
    ctx.strokeStyle = '#f1f5f9';
    ctx.lineWidth = 1;
    const gridRows = 5;
    ctx.fillStyle = '#64748b';
    ctx.font = '10px "IBM Plex Mono", monospace';
    ctx.textAlign = 'right';

    for (let i = 0; i <= gridRows; i++) {
      const yVal = minY + (i / gridRows) * (maxY - minY);
      const sy = toScreenY(yVal);
      ctx.beginPath();
      ctx.moveTo(padding.left, sy);
      ctx.lineTo(w - padding.right, sy);
      ctx.stroke();

      const label = isPrimary ? yVal.toFixed(d.asset.unit === 'V' ? 7 : (d.asset.unit === 'dB' ? 4 : 5)) : yVal.toFixed(2);
      ctx.fillText(label, padding.left - 8, sy + 3);
    }

    // Shaded 95% Prediction Interval Band
    const validLimits = points.filter(p => p.lower !== null && p.upper !== null);
    if (validLimits.length > 1) {
      ctx.fillStyle = 'rgba(59, 130, 246, 0.12)';
      ctx.beginPath();
      validLimits.forEach((p, i) => {
        const sx = toScreenX(p.x);
        const sy = toScreenY(p.upper);
        if (i === 0) ctx.moveTo(sx, sy);
        else ctx.lineTo(sx, sy);
      });
      for (let i = validLimits.length - 1; i >= 0; i--) {
        ctx.lineTo(toScreenX(validLimits[i].x), toScreenY(validLimits[i].lower));
      }
      ctx.closePath();
      ctx.fill();

      // Lines
      ctx.strokeStyle = '#93c5fd';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      validLimits.forEach((p, i) => {
        const sx = toScreenX(p.x);
        const sy = toScreenY(p.upper);
        if (i === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
      });
      ctx.stroke();

      ctx.beginPath();
      validLimits.forEach((p, i) => {
        const sx = toScreenX(p.x);
        const sy = toScreenY(p.lower);
        if (i === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
      });
      ctx.stroke();

      // Dashed Prediction Line
      ctx.strokeStyle = '#64748b';
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      validLimits.forEach((p, i) => {
        const sx = toScreenX(p.x);
        const sy = toScreenY(p.pred);
        if (i === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
      });
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Baseline
    ctx.strokeStyle = '#cbd5e1';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(padding.left, h - padding.bottom);
    ctx.lineTo(w - padding.right, h - padding.bottom);
    ctx.stroke();

    // X Axis Labels
    ctx.fillStyle = '#64748b';
    ctx.textAlign = 'center';
    const xSteps = 5;
    for (let i = 0; i <= xSteps; i++) {
      const xVal = minX + (i / xSteps) * (maxX - minX);
      const sx = toScreenX(xVal);
      ctx.fillText(`${Math.round(xVal)} d`, sx, h - padding.bottom + 15);
    }

    // Crosshair Line on Hover
    if (hoveredPoint) {
      const hx = toScreenX(hoveredPoint.x);
      ctx.strokeStyle = 'rgba(37, 99, 235, 0.4)';
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(hx, padding.top);
      ctx.lineTo(hx, h - padding.bottom);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Measured Scatter Points
    points.forEach(p => {
      if (p.y === null || isNaN(p.y)) return;
      const sx = toScreenX(p.x);
      const sy = toScreenY(p.y);

      let color = '#0a192f';
      if (p.status === 'reviewed_out_of_trend') color = '#1d4ed8';
      else if (p.status === 'out_of_trend') color = '#d97706';

      ctx.fillStyle = color;
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2;

      const isHovered = (hoveredPoint && hoveredPoint.raw.id === p.raw.id);

      if (p.adj) {
        ctx.save();
        ctx.translate(sx, sy);
        ctx.rotate(Math.PI / 4);
        ctx.fillRect(-4.5, -4.5, 9, 9);
        ctx.strokeRect(-4.5, -4.5, 9, 9);
        ctx.restore();
      } else {
        ctx.beginPath();
        ctx.arc(sx, sy, isHovered ? 7.5 : 5.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }

      if (isHovered) {
        ctx.strokeStyle = 'rgba(37, 99, 235, 0.5)';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(sx, sy, 10, 0, Math.PI * 2);
        ctx.stroke();
      }
    });

    return { points, toScreenX, toScreenY, padding, w, h };
  }

  const chartMeta = renderChart();

  // ATTACH INTERACTIVE MOUSEMOVE & HOVER ENGINE
  canvas.onmousemove = function (e) {
    if (!chartMeta) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    let closest = null;
    let minDist = 20;

    chartMeta.points.forEach(p => {
      const px = chartMeta.toScreenX(p.x);
      const py = chartMeta.toScreenY(p.y);
      const dist = Math.hypot(mx - px, my - py);
      if (dist < minDist) {
        minDist = dist;
        closest = p;
      }
    });

    if (closest !== hoveredPoint) {
      hoveredPoint = closest;
      renderChart();
    }

    if (hoveredPoint && tooltip) {
      const c = hoveredPoint.raw;
      const unit = d.asset.unit || '';
      tooltip.style.display = 'block';
      tooltip.style.left = `${Math.min(mx + 15, chartMeta.w - 220)}px`;
      tooltip.style.top = `${Math.max(my - 70, 10)}px`;
      tooltip.innerHTML = `
        <div style="font-weight:700; color:#cbd5e1; border-bottom:1px solid #334155; padding-bottom:4px; margin-bottom:6px;">
          ${c.date} (Day ${c.accumulated_days})
        </div>
        <div style="display:flex; justify-content:space-between; gap:12px;">
          <span style="color:#94a3b8;">Measured:</span>
          <strong class="mono" style="color:#fff;">${Number(c.measured_value).toFixed(unit === 'V' ? 8 : 5)} ${unit}</strong>
        </div>
        ${c.predicted ? `
          <div style="display:flex; justify-content:space-between; gap:12px; color:#cbd5e1;">
            <span style="color:#94a3b8;">Predicted:</span>
            <span class="mono">${Number(c.predicted).toFixed(unit === 'V' ? 8 : 5)}</span>
          </div>
        ` : ''}
        ${c.lower && c.upper ? `
          <div style="color:#93c5fd; font-size:10.5px; margin-top:3px; font-family:monospace;">
            Limits: [${Number(c.lower).toFixed(unit === 'V' ? 7 : 5)} ↔ ${Number(c.upper).toFixed(unit === 'V' ? 7 : 5)}]
          </div>
        ` : ''}
        ${c.pressure_hpa ? `
          <div style="color:#94a3b8; font-size:10.5px; margin-top:4px; border-top:1px dashed #334155; padding-top:4px;">
            Pressure: ${c.pressure_hpa} hPa ${c.location ? `(${c.location})` : ''}
          </div>
        ` : ''}
        ${c.display_status === 'reviewed_out_of_trend' ? `
          <div style="color:#60a5fa; font-weight:700; font-size:10.5px; margin-top:3px;">✓ Reviewed by Metrologist</div>
        ` : ''}
      `;
    } else if (tooltip) {
      tooltip.style.display = 'none';
    }
  };

  canvas.onmouseleave = function () {
    hoveredPoint = null;
    if (tooltip) tooltip.style.display = 'none';
    renderChart();
  };
}

function switchChartMode(mode) {
  currentChartMode = mode;
  if (activeAssetDetail) {
    loadAssetDetail(activeAssetDetail.asset.id, activeAssetDetail.active_test_point_id);
  }
}

async function exportCurrentExcel(id) {
  const res = await window.pywebview.api.export_excel(id);
  if (res.ok) alert(`Excel export saved:\n${res.path}`);
}

// -----------------------------------------------------------------------------
// 3. EDIT CALIBRATION MODAL HANDLER
// -----------------------------------------------------------------------------
async function openEditCalibrationModal(calId) {
  const cal = await window.pywebview.api.get_calibration_for_edit(calId);
  if (!cal) return;

  document.getElementById('editCalId').value = cal.id;
  document.getElementById('editCalDate').value = cal.cal_date;
  document.getElementById('editCalMeas').value = cal.measured_value;
  document.getElementById('editCalComment').value = cal.reviewer_comment || '';
  document.getElementById('editCalAdj').checked = Boolean(cal.is_adjusted);
  document.getElementById('editCalExcl').checked = Boolean(cal.excluded_from_regression);

  const isDcv = Boolean(cal.location || cal.pressure_hpa);
  document.getElementById('editDcvContainer').style.display = isDcv ? 'grid' : 'none';
  if (isDcv) {
    document.getElementById('editCalLoc').value = cal.location || '';
    document.getElementById('editCalPress').value = cal.pressure_hpa || '';
  }

  const tpCont = document.getElementById('editTestPointsContainer');
  const tpGrid = document.getElementById('editTestPointsGrid');
  if (cal.test_point_readings && cal.test_point_readings.length > 1) {
    tpCont.style.display = 'block';
    tpGrid.innerHTML = cal.test_point_readings.map(tpr => `
      <div>
        <label style="font-size:11px; font-weight:700; color:var(--ink-muted);">${tpr.point_name}</label>
        <input type="number" step="any" class="tp-edit-input" data-tp-id="${tpr.tp_id}" value="${tpr.measured_value}" style="width:100%; margin-top:2px;">
      </div>
    `).join('');
  } else {
    tpCont.style.display = 'none';
    tpGrid.innerHTML = '';
  }

  document.getElementById('editCalModal').classList.add('open');
}

function closeEditModal(e) {
  if (!e || e.target === document.getElementById('editCalModal')) {
    document.getElementById('editCalModal').classList.remove('open');
  }
}

async function saveCalibrationModal(e) {
  e.preventDefault();
  const form = document.getElementById('editCalForm');
  const calId = document.getElementById('editCalId').value;

  const tpInputs = Array.from(document.querySelectorAll('.tp-edit-input'));
  const tpReadings = tpInputs.map(inp => ({
    tp_id: inp.dataset.tpId,
    measured_value: inp.value
  }));

  const payload = {
    id: calId,
    cal_date: document.getElementById('editCalDate').value,
    measured_value: document.getElementById('editCalMeas').value,
    reviewer_comment: document.getElementById('editCalComment').value,
    is_adjusted: document.getElementById('editCalAdj').checked,
    excluded_from_regression: document.getElementById('editCalExcl').checked,
    location: document.getElementById('editCalLoc')?.value || '',
    pressure_hpa: document.getElementById('editCalPress')?.value || '',
    test_point_readings: tpReadings
  };

  const res = await window.pywebview.api.save_calibration_edit(payload);
  if (res.ok) {
    closeEditModal();
    if (activeAssetDetail) {
      loadAssetDetail(activeAssetDetail.asset.id, activeAssetDetail.active_test_point_id);
    }
  } else {
    alert(`Failed to save: ${res.error}`);
  }
}

function openNoteModal(date, comment, attachPath, calId) {
  document.getElementById('noteModalTitle').textContent = 'Reviewer Note — ' + date;
  document.getElementById('noteModalContent').textContent = comment || 'No note text entered.';
  const attachDiv = document.getElementById('noteModalAttachment');
  const attachLink = document.getElementById('noteModalAttachLink');
  if (attachPath) {
    attachDiv.style.display = 'block';
    attachLink.href = `/calibrations/${calId}/attachment`;
  } else {
    attachDiv.style.display = 'none';
  }
  document.getElementById('noteModal').classList.add('open');
}

function closeNoteModal(e) {
  if (!e || e.target === document.getElementById('noteModal')) {
    document.getElementById('noteModal').classList.remove('open');
  }
}

// -----------------------------------------------------------------------------
// 4. HTBASIC CAL FACTOR STUDIO (ALL 34 TEST POINTS COMPLETE)
// -----------------------------------------------------------------------------
let selectedSet = 'Set 1';
let selected01Ohm = 'PN010034';
let selectedWfg = 'SG53800187';
let activePreflightCategory = 'all';

async function loadHTBasic() {
  const root = document.getElementById('appRoot');
  const d = await window.pywebview.api.get_htbasic_context(selectedSet, selected01Ohm, selectedWfg);

  root.innerHTML = `
    <div style="max-width: 1360px; margin: 0 auto;">
      <button class="btn" onclick="router.navigate('dashboard')" style="margin-bottom:14px;">← Back to Dashboard</button>
      <div class="panel" style="margin-bottom:16px;">
        <h2 style="margin:0 0 4px 0; color:var(--primary); font-size:20px;">Generate HTBasic 3458A Calibration Factor Files</h2>
        <p style="font-size:12.5px; color:var(--ink-muted); margin:0;">Station 1 &amp; Station 2 automated file compilation with pre-flight standards verification.</p>
      </div>

      <!-- STEP 1: Station Selector Cards -->
      <label style="font-weight:700; font-size:12.5px; color:var(--primary); margin-bottom:6px; display:block;">Step 1: Select Target Test Station &amp; Station File</label>
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:14px; margin-bottom:16px;">
        <div class="panel ${selectedSet === 'Set 1' ? 'selected' : ''}" style="margin:0; cursor:pointer; border:2px solid ${selectedSet === 'Set 1' ? 'var(--primary)' : 'var(--line)'}; ${selectedSet === 'Set 1' ? 'background:#fcfdfe;' : ''}" onclick="setStation('Set 1')">
          <div style="font-weight:700; font-size:14.5px; color:var(--primary); margin-bottom:3px;">Station 1 (Set 1)</div>
          <div style="font-size:12px; color:var(--ink-muted);">Compiles target station file <strong>286300.txt</strong>, Set 1 standard resistors (1 Ω – 1 GΩ), Set 1 AC Dividers into <strong>DIVMEANS.TXT</strong>, and selected 33622A factor file.</div>
        </div>
        <div class="panel ${selectedSet === 'Set 2' ? 'selected' : ''}" style="margin:0; cursor:pointer; border:2px solid ${selectedSet === 'Set 2' ? 'var(--primary)' : 'var(--line)'}; ${selectedSet === 'Set 2' ? 'background:#fcfdfe;' : ''}" onclick="setStation('Set 2')">
          <div style="font-weight:700; font-size:14.5px; color:var(--primary); margin-bottom:3px;">Station 2 (Set 2)</div>
          <div style="font-size:12px; color:var(--ink-muted);">Compiles target station file <strong>286325.txt</strong>, Set 2 standard resistors (1 Ω – 1 GΩ), Set 2 AC Dividers into <strong>DIVMEANS.TXT</strong>, and selected 33622A factor file.</div>
        </div>
      </div>

      <!-- STEP 2: 0.1 Ohm Reference Resistor Selector -->
      <label style="font-weight:700; font-size:12.5px; color:var(--primary); margin-bottom:6px; display:block;">Step 2: Select 0.1 Ω Station Reference Standard</label>
      <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:12px; margin-bottom:16px;">
        ${['PN010034', 'EQ358990', 'PN010069'].map(pn => {
          const resD = d.zero_pt_one_details[pn] || {};
          return `
            <div class="panel" style="margin:0; cursor:pointer; border:2px solid ${selected01Ohm === pn ? 'var(--primary-accent)' : 'var(--line)'}; ${selected01Ohm === pn ? 'background:#eff6ff;' : ''}" onclick="set01Ohm('${pn}')">
              <div style="font-weight:700; font-size:13.5px; color:var(--primary);">${pn}</div>
              <div style="font-size:11.5px; color:var(--ink-muted); margin-bottom:6px;">Serial: <strong>${resD.serial || '—'}</strong> · ${resD.set_id || '—'}</div>
              <div style="font-size:11.5px; border-top:1px dashed var(--line); padding-top:4px;">
                <div style="color:var(--ink-faint);">Live Value: <strong class="mono" style="color:var(--primary);">${resD.last_measured ? Number(resD.last_measured).toFixed(8) + ' Ω' : 'Missing'}</strong></div>
                <div style="font-size:10.5px; color:var(--ink-faint);">Cal Date: ${resD.last_date || '—'}</div>
              </div>
            </div>
          `;
        }).join('')}
      </div>

      <!-- STEP 3: 33622A Waveform Generator Selector (Title is Equipment ID) -->
      <label style="font-weight:700; font-size:12.5px; color:var(--primary); margin-bottom:6px; display:block;">Step 3: Select 33622A Waveform Generator Standard</label>
      <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:12px; margin-bottom:16px;">
        ${Object.entries(d.wfg_options).map(([sn, item]) => {
          const wD = d.wfg_details[sn] || {};
          return `
            <div class="panel" style="margin:0; cursor:pointer; border:2px solid ${selectedWfg === sn ? 'var(--primary-accent)' : 'var(--line)'}; ${selectedWfg === sn ? 'background:#eff6ff;' : ''}" onclick="setWfg('${sn}')">
              <div style="font-weight:700; font-size:13.5px; color:var(--primary);">${wD.trace_id || item.pn}</div>
              <div style="font-size:11.5px; color:var(--ink-muted); margin-bottom:4px;">Serial: <strong>${sn}</strong> · ${wD.set_id || item.default_set}</div>
              <div style="font-size:11.5px; border-top:1px dashed var(--line); padding-top:4px;">
                <div>Target: <strong>${item.file_id}_Extended.txt</strong></div>
                <div style="font-size:10.5px; color:var(--ink-faint); margin-top:2px;">Cal Date: ${wD.last_date || '—'}</div>
              </div>
            </div>
          `;
        }).join('')}
      </div>

      <!-- Package Manifest Checklist (7 Files) -->
      <div style="background:var(--track); padding:12px 18px; border-radius:var(--radius-md); border:1px solid var(--line); margin-bottom:16px;">
        <div style="font-size:11px; font-weight:700; text-transform:uppercase; color:var(--ink-muted); margin-bottom:8px;">Package Manifest (7 Production Files Compiled into .zip)</div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:6px; font-size:11.5px;">
          <div>✓ <strong>RESNOM.txt</strong> (Nominal standards: 1Ω, 10M, 100M, 1G)</div>
          <div>✓ <strong>RESVALUE.TXT</strong> (Transfer standards: 10Ω – 10kΩ)</div>
          <div>✓ <strong>HIGHRES.txt</strong> (100kΩ standards)</div>
          <div>✓ <strong>ONEMEG.txt</strong> (1MΩ standards)</div>
          <div>✓ <strong>${selectedSet === 'Set 1' ? '286300.txt' : '286325.txt'}</strong> (0.1 Ω station factor)</div>
          <div>✓ <strong>DIVMEANS.TXT</strong> (AC Dividers: 10mV &amp; 100mV across 6 freqs)</div>
          <div style="grid-column: span 2;">✓ <strong>${d.wfg_options[selectedWfg]?.file_id}_Extended.txt</strong> (33622A 11 cf Data points)</div>
        </div>
      </div>

      <!-- STEP 4: PRE-FLIGHT VERIFICATION TABLE (ALL 34 TEST POINTS) -->
      <div class="panel-header" style="margin-bottom:8px;">
        <h3 class="panel-title">Pre-Flight Standards Verification (All 34 Test Points for ${selectedSet})</h3>
      </div>

      <!-- Category Filter Pills -->
      <div style="display:flex; gap:6px; margin-bottom:12px;">
        ${[
          { id: 'all', label: 'All Standards (34 Points)' },
          { id: 'resistor', label: 'Resistors (11)' },
          { id: 'divider', label: 'AC Dividers (12)' },
          { id: 'wfg', label: '33622A Generator (11)' }
        ].map(cat => `
          <button class="btn ${activePreflightCategory === cat.id ? 'btn-primary' : ''}" 
                  style="border-radius:999px; font-size:11px; padding:2px 10px;"
                  onclick="activePreflightCategory='${cat.id}'; loadHTBasic();">
            ${cat.label}
          </button>
        `).join('')}
      </div>

      <div class="table-container" style="max-height:460px; overflow-y:auto; margin-bottom:16px;">
        <table>
          <thead style="position:sticky; top:0; z-index:10; background:#f8fafc;">
            <tr>
              <th>Target File</th>
              <th>Rx# / Test Point</th>
              <th class="right">Nominal / Function</th>
              <th>Equipment ID</th>
              <th>Serial</th>
              <th class="right">Live Calibrated Value</th>
              <th>Cal Date</th>
            </tr>
          </thead>
          <tbody>
            <!-- SECTION 1: RESISTORS (0.1 Ohm to 1 GOhm) -->
            ${(activePreflightCategory === 'all' || activePreflightCategory === 'resistor') ? `
              <tr style="background:#eff6ff; font-weight:700;">
                <td colspan="7" style="color:var(--primary); font-size:11px;">📁 REFERENCE STANDARD RESISTORS (0.1 Ω – 1 GΩ)</td>
              </tr>
              <!-- 0.1 Ohm Row -->
              <tr style="background:#eff6ff; font-weight:600;">
                <td class="mono font-bold">${selectedSet === 'Set 1' ? '286300.txt' : '286325.txt'}</td>
                <td>0.1 Ω Std</td>
                <td class="num-cell right">0.1 Ω</td>
                <td class="mono font-bold" style="color:var(--primary);">${selected01Ohm}</td>
                <td class="mono">${d.zero_pt_one_details[selected01Ohm]?.serial || '—'}</td>
                <td class="num-cell right" style="color:var(--primary); font-weight:700;">${d.zero_pt_one_details[selected01Ohm]?.last_measured ? Number(d.zero_pt_one_details[selected01Ohm].last_measured).toFixed(8) + ' Ω' : '<span style="color:var(--warn)">Missing</span>'}</td>
                <td class="num-cell">${d.zero_pt_one_details[selected01Ohm]?.last_date || '—'}</td>
              </tr>
              <!-- 1 Ohm to 1 GOhm -->
              ${d.all_resistors.filter(r => r.set === selectedSet).map(r => `
                <tr>
                  <td class="mono font-bold">${r.file}</td>
                  <td>${r.rx_tag}</td>
                  <td class="num-cell right">${r.nominal}</td>
                  <td class="mono" style="color:var(--primary-accent); font-weight:600;">${r.pn}</td>
                  <td class="mono">${r.serial}</td>
                  <td class="num-cell right" style="font-weight:700;">${r.measured_value ? Number(r.measured_value).toFixed(8) + ' Ω' : '<span style="color:var(--warn)">Missing</span>'}</td>
                  <td class="num-cell">${r.cal_date}</td>
                </tr>
              `).join('')}
            ` : ''}

            <!-- SECTION 2: AC VOLTAGE DIVIDERS (12 Frequency Points) -->
            ${(activePreflightCategory === 'all' || activePreflightCategory === 'divider') ? `
              <tr style="background:#f1f5f9; font-weight:700;">
                <td colspan="7" style="color:var(--primary); font-size:11px;">📁 AC VOLTAGE DIVIDERS (DIVMEANS.TXT — 10mV &amp; 100mV across 6 Frequencies)</td>
              </tr>
              ${d.divider_test_points.filter(dp => dp.set === selectedSet).map(dp => `
                <tr>
                  <td class="mono font-bold">${dp.file}</td>
                  <td>${dp.rx_tag}</td>
                  <td class="num-cell right">${dp.nominal}</td>
                  <td class="mono" style="color:var(--primary-accent); font-weight:600;">${dp.pn}</td>
                  <td class="mono">${dp.serial}</td>
                  <td class="num-cell right" style="font-weight:700;">${dp.measured_value ? Number(dp.measured_value).toFixed(5) : '<span style="color:var(--warn)">Missing</span>'}</td>
                  <td class="num-cell">${dp.cal_date}</td>
                </tr>
              `).join('')}
            ` : ''}

            <!-- SECTION 3: 33622A WAVEFORM GENERATOR (11 cf Points) -->
            ${(activePreflightCategory === 'all' || activePreflightCategory === 'wfg') ? `
              <tr style="background:#f1f5f9; font-weight:700;">
                <td colspan="7" style="color:var(--primary); font-size:11px;">📁 33622A WAVEFORM GENERATOR (${d.wfg_options[selectedWfg]?.file_id}_Extended.txt — 11 cf Data Points)</td>
              </tr>
              ${(d.wfg_all_points[selectedWfg] || []).map(pt => `
                <tr>
                  <td class="mono font-bold">${pt.file}</td>
                  <td><span class="rx-tag-chip" style="background:#e0e7ff; color:#3730a3;">${pt.rx_tag}</span></td>
                  <td class="num-cell right">${pt.nominal}</td>
                  <td class="mono" style="color:var(--primary-accent); font-weight:600;">${pt.pn}</td>
                  <td class="mono">${pt.serial}</td>
                  <td class="num-cell right" style="font-weight:700;">${pt.measured_value !== null ? (pt.measured_value > 0 ? '+' : '') + Number(pt.measured_value).toFixed(5) + ' dB' : '<span style="color:var(--warn)">Missing</span>'}</td>
                  <td class="num-cell">${pt.cal_date}</td>
                </tr>
              `).join('')}
            ` : ''}
          </tbody>
        </table>
      </div>

      <button class="btn btn-primary" onclick="generateHTBasicFiles()" style="padding:10px 24px; font-size:13.5px;">
        Compile &amp; Download HTBasic Package (.zip)
      </button>
    </div>
  `;
}

function setStation(s) { selectedSet = s; loadHTBasic(); }
function set01Ohm(pn) { selected01Ohm = pn; loadHTBasic(); }
function setWfg(sn) { selectedWfg = sn; loadHTBasic(); }

async function generateHTBasicFiles() {
  const res = await window.pywebview.api.generate_htbasic(selectedSet, selected01Ohm, selectedWfg);
  if (res.ok) {
    alert(`HTBasic package compiled and saved successfully to:\n${res.path}`);
  } else if (res.problems) {
    alert(`Cannot generate package — missing calibration data:\n` + res.problems.map(p => `${p.nominal} (${p.asset_number}): ${p.issue}`).join('\n'));
  }
}

app.init();