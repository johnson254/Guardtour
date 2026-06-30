import '../styles/main.css';
import { toast } from '../utils/toast.js';

/* ═══════════════════════════════════════════════════
   Mission Builder — standalone page
   Dark ops console aesthetic (matches routes/dispatch)
═══════════════════════════════════════════════════ */

const $ = id => document.getElementById(id);
const $$ = s  => document.querySelectorAll(s);

const MB = {
  routes: [],
  selectedRouteId: null,
  windowDate: null,
  windowTime: null,
  checkpointTimeMode: null,
  checkpointTime: null,
};

/* ── API helper ── */
const api = async (url, opts = {}) => {
  if (typeof window.apiFetch === 'function') return window.apiFetch(url, opts);
  var token = JSON.parse(localStorage.getItem('gt_user') || '{}').token;
  var headers = { 'Content-Type': 'application/json', ...(token ? { 'Authorization': 'Bearer ' + token } : {}), ...(opts.headers || {}) };
  return fetch(url, { credentials: 'same-origin', ...opts, headers });
};

/* ── Load routes ── */
async function mbLoadRoutes() {
  try {
    const res = await api('/api/routes/');
    if (res.ok) {
      const d = await res.json();
      MB.routes = Array.isArray(d) ? d : (d.results || []);
    }
    mbRenderRouteList();
  } catch (e) {
    toast('Failed to load routes', true);
  }
}

/* ── Render route list ── */
function mbRenderRouteList() {
  const box = $('mbRouteList');
  if (!box) return;
  if (!MB.routes.length) {
    box.innerHTML = '<div class="rs-empty"><i class="fas fa-map"></i>No blueprints available</div>';
    return;
  }
  box.innerHTML = MB.routes.map(r => `
    <div class="rs-r-card${MB.selectedRouteId === r.id ? ' active' : ''}" data-id="${r.id}" data-name="${(r.name || '').replace(/"/g, '&quot;')}" onclick="window.mbSelectRoute(${r.id})">
      <div class="rs-r-card-top">
        <div class="rs-r-name">${r.name || 'Unnamed'}</div>
        <div style="display:flex;gap:5px;">
          <button type="button" class="rs-r-del" style="color:var(--r-teal); opacity:0.6;" onclick="event.stopPropagation();window.mbQuickDeploy(${r.id})" title="Quick Deploy"><i class="fas fa-bolt"></i></button>
        </div>
      </div>
      <div class="rs-r-meta">${r.logic_type || 'Flex'} route · ${r.checkpoint_count || 0} checkpoints${r.is_daily ? ' · ↻ Daily' : ''}</div>
    </div>
  `).join('');
}

/* ── Select route ── */
function mbSelectRoute(id) {
  MB.selectedRouteId = id;
  MB.windowDate = null;
  MB.windowTime = null;
  MB.checkpointTimeMode = null;
  MB.checkpointTime = null;
  mbRenderRouteList();
  mbUpdateBrief();
  mbUpdateSummary();
  $('mbCheckpointTime').value = '';
  $$('[data-ct]').forEach(el => el.classList.remove('active'));
}

/* ── Set checkpoint time ── */
function mbSetCheckpointTime(mode, btn) {
  MB.checkpointTimeMode = mode;
  let t = '';
  const d = new Date();
  if (mode === 'now') t = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  else if (mode === '+15') { d.setMinutes(d.getMinutes() + 15); t = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); }
  else if (mode === '+30') { d.setMinutes(d.getMinutes() + 30); t = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); }
  else if (mode === '+60') { d.setMinutes(d.getMinutes() + 60); t = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); }
  else if (mode === 'eos') t = '18:00';
  MB.checkpointTime = t;
  $('mbCheckpointTime').value = t;
  $$('[data-ct]').forEach(el => el.classList.remove('active'));
  if (btn) btn.classList.add('active');
  mbUpdateSummary();
}

/* ── Apply window ── */
function mbApplyWindow() {
  const dt = window.CalendarTimePicker ? window.CalendarTimePicker.getDateTime() : null;
  if (!dt) { toast('Choose a date and time first', true); return; }
  MB.windowDate = dt.date;
  MB.windowTime = dt.time;
  mbUpdateSummary();
  mbUpdateBrief();
}

/* ── Update summary ── */
function mbUpdateSummary() {
  const dEl = $('mbSummaryDate');
  const tEl = $('mbSummaryTime');
  const cEl = $('mbSummaryCp');
  if (dEl) dEl.textContent = MB.windowDate || '—';
  if (tEl) tEl.textContent = MB.windowTime || '—';
  if (cEl) cEl.textContent = MB.checkpointTime ? (MB.checkpointTime + (MB.checkpointTimeMode ? ' (' + MB.checkpointTimeMode + ')' : '')) : '—';
}

/* ── Update brief ── */
function mbUpdateBrief() {
  const brief = $('mbBrief');
  const badge = $('mbBadge');
  const foot = $('mbFoot');
  if (!brief) return;
  const route = (MB.routes || []).find(r => r.id === MB.selectedRouteId);
  if (!route) {
    brief.innerHTML = '<div class="rs-empty"><i class="fas fa-satellite-dish"></i><br/>Select a blueprint and time window</div>';
    if (badge) badge.textContent = '';
    if (foot) foot.style.display = 'none';
    return;
  }
  if (badge) badge.textContent = route.logic_type || 'Route';
  brief.innerHTML = `
    <div class="rs-block" style="background:linear-gradient(135deg, rgba(211,47,47,0.05), rgba(20,20,32,0.96) 50%);">
      <div style="font-size:0.9rem; font-weight:900; color:#fff;">${route.name || 'Unnamed'}</div>
      <div style="font-size:0.68rem; color:var(--r-mute); margin-top:6px; font-weight:600;">${route.checkpoint_count || 0} checkpoints${route.is_daily ? ' · Daily recurrence' : ''}</div>
      <div class="rs-summary-row" style="margin-top:12px;">
        <div class="rs-summary-pill">Window: <strong>${MB.windowDate || '—'} ${MB.windowTime || '—'}</strong></div>
        <div class="rs-summary-pill">CP Time: <strong>${MB.checkpointTime || '—'}</strong></div>
      </div>
    </div>
    <div class="rs-block" style="background:linear-gradient(135deg, rgba(0,196,154,0.04), rgba(20,20,32,0.96) 50%);">
      <div style="font-size:0.72rem; font-weight:900; color:var(--r-mute); text-transform:uppercase; letter-spacing:0.5px;">Operational Notes</div>
      <div style="font-size:0.78rem; color:rgba(255,255,255,0.85); margin-top:8px; line-height:1.5;">Assign this window in dispatch once validated. All parameters are ready for deployment.</div>
    </div>`;
  if (foot) foot.style.display = 'flex';
}

/* ── Deploy (connects to real backend) ── */
async function mbDeploy() {
  if (!MB.selectedRouteId) { toast('Select a blueprint first', true); return; }
  if (!MB.windowDate || !MB.windowTime) { toast('Set a mission window', true); return; }

  try {
    // First save the route with the scheduled date/time
    const route = MB.routes.find(r => r.id === MB.selectedRouteId);
    if (!route) return;

    // Update route with mission window
    const saveRes = await api(`/api/routes/${MB.selectedRouteId}/`, {
      method: 'PATCH',
      body: JSON.stringify({
        scheduled_date: MB.windowDate,
        scheduled_start_time: MB.windowTime,
      }),
    });

    if (!saveRes.ok) {
      toast('Failed to update route schedule', true);
      return;
    }

    // Deploy the route
    const deployRes = await api(`/api/routes/${MB.selectedRouteId}/deploy/`, {
      method: 'POST',
      body: JSON.stringify({
        scheduled_date: MB.windowDate,
        scheduled_start_time: MB.windowTime,
      }),
    });

    if (deployRes.ok) {
      toast('Mission deployed successfully');
      // Reset
      MB.selectedRouteId = null;
      MB.windowDate = null;
      MB.windowTime = null;
      MB.checkpointTime = null;
      mbRenderRouteList();
      mbUpdateBrief();
      mbUpdateSummary();
    } else {
      let detail = '';
      try { const d = await deployRes.json(); detail = d?.detail ? ' — ' + d.detail : ''; } catch (_) {}
      toast('Deploy failed' + detail, true);
    }
  } catch (e) {
    toast('Deploy request failed', true);
  }
}

/* ── Quick deploy (skip window selection) ── */
async function mbQuickDeploy(routeId) {
  const now = new Date();
  const date = now.toISOString().split('T')[0];
  const time = String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');

  try {
    const deployRes = await api(`/api/routes/${routeId}/deploy/`, {
      method: 'POST',
      body: JSON.stringify({ scheduled_date: date, scheduled_start_time: time }),
    });
    if (deployRes.ok) {
      toast('Quick deployed for today at ' + time);
    } else {
      toast('Quick deploy failed', true);
    }
  } catch (e) {
    toast('Deploy failed', true);
  }
}

/* ── Reset ── */
function mbReset() {
  MB.selectedRouteId = null;
  MB.windowDate = null;
  MB.windowTime = null;
  MB.checkpointTimeMode = null;
  MB.checkpointTime = null;
  mbRenderRouteList();
  mbUpdateSummary();
  mbUpdateBrief();
  $('mbCheckpointTime').value = '';
  $$('[data-ct]').forEach(el => el.classList.remove('active'));
}

/* ── Filter routes ── */
function mbFilterRoutes(q) {
  const term = (q || '').toLowerCase();
  $$('.mb-route-card, .rs-r-card').forEach(card => {
    const name = (card.dataset.name || '').toLowerCase();
    card.style.display = name.includes(term) ? '' : 'none';
  });
}

/* ── Boot ── */
function mbBoot() {
  mbLoadRoutes();
  // Init calendar if available
  if (window.CalendarTimePicker && CalendarTimePicker.init) {
    CalendarTimePicker.init({
      onDayClick: function(dateStr) {
        const dt = window.CalendarTimePicker ? window.CalendarTimePicker.getDateTime() : null;
        if (dt) {
          MB.windowDate = dt.date;
          MB.windowTime = dt.time;
          mbUpdateSummary();
          mbUpdateBrief();
        }
      }
    });
  }
}

// Export to global scope for onclick handlers
window.mbSelectRoute = mbSelectRoute;
window.mbSetCheckpointTime = mbSetCheckpointTime;
window.mbApplyWindow = mbApplyWindow;
window.mbDeploy = mbDeploy;
window.mbQuickDeploy = mbQuickDeploy;
window.mbReset = mbReset;
window.mbFilterRoutes = mbFilterRoutes;
window.mbBoot = mbBoot;

// Auto-boot when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mbBoot);
} else {
  mbBoot();
}
