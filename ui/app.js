/**
 * app.js - UI controller communicating with Python through window.pywebview.api
 */

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

  async refresh() {
    try {
      this.data = await window.pywebview.api.get_dashboard();
      this.updateSyncStatus();
      render();
    } catch (e) {
      console.error("Failed to load dashboard:", e);
      document.getElementById('appRoot').innerHTML = `
        <div style="padding:40px; text-align:center; color:#b45309;">
          Failed to load dashboard data. Right click and choose Inspect to view error console.
        </div>
      `;
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

  async generateBatchReport() {
    const res = await window.pywebview.api.save_report();
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

function renderDashboard(data) {
  const allAssets = (data.sets || []).flatMap(s => s.assets || []);
  const filtered = allAssets.filter(a => {
    if (app.activeSet !== 'all' && a.set_id !== app.activeSet) return false;
    if (app.activeFilter !== 'all' && (a.category || 'standard_resistor') !== app.activeFilter) return false;
    return true;
  });

  return `
    <div style="padding: 24px;">
      <!-- KPI Cards -->
      <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px;">
        <div class="panel" style="margin:0; padding:16px;">
          <div style="font-size:11px; font-weight:700; color:var(--ink-muted);">TOTAL STANDARDS</div>
          <div class="mono" style="font-size:28px; font-weight:700; color:var(--primary); margin-top:4px;">${data.total || 0}</div>
        </div>
        <div class="panel" style="margin:0; padding:16px;">
          <div style="font-size:11px; font-weight:700; color:var(--ink-muted);">WITHIN TREND</div>
          <div class="mono" style="font-size:28px; font-weight:700; color:var(--ok); margin-top:4px;">${data.ok_count || 0}</div>
        </div>
        <div class="panel" style="margin:0; padding:16px;">
          <div style="font-size:11px; font-weight:700; color:var(--ink-muted);">OUT OF TREND (UNREVIEWED)</div>
          <div class="mono" style="font-size:28px; font-weight:700; color:var(--warn); margin-top:4px;">${data.out_count || 0}</div>
        </div>
        <div class="panel" style="margin:0; padding:16px;">
          <div style="font-size:11px; font-weight:700; color:var(--ink-muted);">INSUFFICIENT HISTORY</div>
          <div class="mono" style="font-size:28px; font-weight:700; color:var(--neutral-status); margin-top:4px;">${data.insufficient_count || 0}</div>
        </div>
      </div>

      <!-- Category Filter Strip -->
      <div style="display:flex; gap:6px; margin-bottom:14px;">
        ${['all', 'standard_resistor', 'dcv_reference', 'ac_divider', 'waveform_generator'].map(cat => `
          <button class="btn ${app.activeFilter === cat ? 'btn-primary' : ''}" 
                  onclick="app.activeFilter='${cat}'; render();">
            ${cat === 'all' ? 'All Standards' : cat === 'standard_resistor' ? 'Resistors' : cat === 'dcv_reference' ? 'DC Voltage' : cat === 'ac_divider' ? 'AC Dividers' : 'Waveform Gen'}
          </button>
        `).join('')}
      </div>

      <!-- Master Fleet Table -->
      <div class="table-container">
        <table>
          <thead>
            <tr>
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
              <tr><td colspan="10" style="text-align:center; padding:32px; color:var(--ink-faint);">No standards match this filter.</td></tr>
            ` : filtered.map(a => `
              <tr onclick="router.navigate('asset', { id: ${a.id} })">
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
    </div>
  `;
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

async function loadAssetDetail(id, tpId) {
  const root = document.getElementById('appRoot');
  const d = await window.pywebview.api.get_asset_detail(id, tpId);
  root.innerHTML = `
    <div style="padding: 24px;">
      <button class="btn" onclick="router.navigate('dashboard')" style="margin-bottom:14px;">← Back to Dashboard</button>
      <div class="panel">
        <h2 style="margin:0 0 4px 0; color:var(--primary); font-size:20px;">${d.asset.model || d.asset.serial}</h2>
        <div style="font-size:12px; color:var(--ink-muted);">
          Serial: <strong>${d.asset.serial}</strong> · Trace ID: <strong>${d.asset.asset_number || '—'}</strong> · Set: <strong>${d.asset.set_id || '—'}</strong>
        </div>
      </div>
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>Cal Date</th>
              <th class="right">Measured Value</th>
              <th class="right">Error</th>
              <th class="right">Drift</th>
              <th class="right">95% Limits</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${(d.calibrations || []).slice().reverse().map(c => `
              <tr>
                <td class="mono"><strong>${c.date}</strong></td>
                <td class="num-cell right" style="font-weight:700;">${Number(c.measured_value).toFixed(5)} ${d.asset.unit}</td>
                <td class="num-cell right">${c.error_ppm !== undefined ? Number(c.error_ppm).toFixed(2) + ' ppm' : '—'}</td>
                <td class="num-cell right">${c.drift_ppm !== undefined && c.drift_ppm !== null ? Number(c.drift_ppm).toFixed(2) + ' ppm' : '—'}</td>
                <td class="num-cell right font-mono">[ ${c.lower ? Number(c.lower).toFixed(5) : '—'} ↔ ${c.upper ? Number(c.upper).toFixed(5) : '—'} ]</td>
                <td><span class="badge ${c.display_status === 'ok' ? 'badge-ok' : 'badge-warn'}">${c.display_status === 'ok' ? 'In Trend' : 'Out of Trend'}</span></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

async function loadHTBasic() {
  const root = document.getElementById('appRoot');
  const d = await window.pywebview.api.get_htbasic_context();
  root.innerHTML = `
    <div style="padding: 24px;">
      <button class="btn" onclick="router.navigate('dashboard')" style="margin-bottom:14px;">← Back to Dashboard</button>
      <div class="panel">
        <h2 style="margin:0 0 6px 0; color:var(--primary);">HTBasic 3458A Cal Factor Files Generator</h2>
        <p style="font-size:13px; color:var(--ink-muted); margin:0;">Target Station 1 & 2 file packaging with pre-flight standards verification.</p>
      </div>
      <button class="btn btn-primary" onclick="generateHTBasicFiles()" style="padding:10px 20px;">
        Compile &amp; Download HTBasic Package (.zip)
      </button>
    </div>
  `;
}

async function generateHTBasicFiles() {
  const res = await window.pywebview.api.generate_htbasic('Set 1', 'PN010034', 'SG53800187');
  if (res.ok) alert(`HTBasic package compiled and saved to:\n${res.path}`);
}

// Robust Dual-Check Initializer (Never hangs)
window.addEventListener('pywebviewready', () => app.refresh());
if (window.pywebview && window.pywebview.api) {
  app.refresh();
}