import '../styles/main.css';
import { toast } from '../utils/toast.js';

/* ═══════════════════════════════════════════════════
   Mission Builder — Timeline Scheduler
   Drag checkpoints onto 30-min time slots
═══════════════════════════════════════════════════ */

const $ = id => document.getElementById(id);
const $$ = s => document.querySelectorAll(s);

const MB = {
  routes: [],
  selectedRoute: null,
  checkpoints: [],        // From selected route
  placedCheckpoints: [],  // { cp, slotIndex, time }
  strategy: 'Flexible',
  date: '',
  startTime: '08:00',
  slotInterval: 30, // minutes
  slotsPerDay: 32,    // 08:00 to 24:00 in 30min slots
  dragSource: null,
};

/* ── API helper ── */
const api = async (url, opts = {}) => {
  if (typeof window.apiFetch === 'function') return window.apiFetch(url, opts);
  const token = JSON.parse(localStorage.getItem('gt_user') || '{}').token;
  const headers = { 'Content-Type': 'application/json', ...(token ? { 'Authorization': 'Bearer ' + token } : {}), ...(opts.headers || {}) };
  return fetch(url, { credentials: 'same-origin', ...opts, headers });
};

/* ── Load routes ── */
async function mbLoadRoutes() {
  try {
    const res = await api('/api/routes/');
    if (res.ok) {
      const d = await res.json();
      MB.routes = (Array.isArray(d) ? d : (d.results || [])).filter(r => !r.is_archived);
    }
  } catch (e) {
    toast('Failed to load routes', true);
  }
}

/* ── Select route ── */
async function mbSelectRoute(id) {
  const route = MB.routes.find(r => r.id === id);
  if (!route) return;

  MB.selectedRoute = route;
  MB.placedCheckpoints = [];
  MB.date = new Date().toISOString().split('T')[0];
  $('mbDate').value = MB.date;
  $('mbStartTime').value = MB.startTime;
  $('mbRouteName').textContent = route.name;

  // Load checkpoints for this route
  try {
    const res = await api(`/api/routes/${id}/`);
    if (res.ok) {
      const d = await res.json();
      MB.checkpoints = d.checkpoints || [];
    }
  } catch (e) {
    MB.checkpoints = [];
  }

  $('mbCpCount').textContent = MB.checkpoints.length;
  mbRenderPool();
  mbRenderTimeline();
  mbUpdateBrief();
}

/* ── Render checkpoint pool ── */
function mbRenderPool() {
  const pool = $('mbCheckpointPool');
  if (!pool) return;
  if (!MB.checkpoints.length) {
    pool.innerHTML = '<div class="rs-empty" style="padding:20px;"><i class="fas fa-check"></i><br/>No checkpoints on this route</div>';
    return;
  }
  pool.innerHTML = MB.checkpoints.map((cp, i) => {
    const type = cp.checkpoint_type || 'nfc';
    const icon = type === 'gps' ? 'fa-map-pin' : type === 'peer' ? 'fa-user-shield' : type === 'custom' ? 'fa-pen' : 'fa-wifi';
    const isPlaced = MB.placedCheckpoints.some(p => p.cp.id === cp.id || p.cp.name === cp.name);
    return `<div class="mb-pool-item${isPlaced ? ' placed' : ''}" draggable="true" data-cp-idx="${i}" data-type="${type}">
      <i class="fas ${icon}" style="margin-right:6px;font-size:0.65rem;"></i>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${cp.name || 'Checkpoint ' + (i + 1)}</span>
      <span style="font-size:0.5rem;color:var(--r-mute);text-transform:uppercase;">${type}</span>
    </div>`;
  }).join('');

  // Attach drag handlers
  pool.querySelectorAll('.mb-pool-item').forEach(el => {
    el.addEventListener('dragstart', (e) => {
      if (el.classList.contains('placed')) { e.preventDefault(); return; }
      MB.dragSource = { type: 'pool', cpIdx: parseInt(el.dataset.cpIdx) };
      el.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'copy';
    });
    el.addEventListener('dragend', () => {
      el.classList.remove('dragging');
      MB.dragSource = null;
    });
  });
}

/* ── Render timeline grid ── */
function mbRenderTimeline() {
  const labels = $('mbTimeLabels');
  const slots = $('mbTimeSlots');
  if (!labels || !slots) return;

  labels.innerHTML = '';
  slots.innerHTML = '';

  const [startH, startM] = MB.startTime.split(':').map(Number);
  const totalSlots = MB.slotsPerDay;

  for (let i = 0; i < totalSlots; i++) {
    const mins = startH * 60 + startM + i * MB.slotInterval;
    const h = Math.floor(mins / 60) % 24;
    const m = mins % 60;
    const timeStr = String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');

    // Label
    const label = document.createElement('div');
    label.className = 'mb-time-label';
    label.textContent = timeStr;
    labels.appendChild(label);

    // Slot
    const slot = document.createElement('div');
    slot.className = 'mb-time-slot';
    slot.dataset.slotIdx = i;
    slot.dataset.time = timeStr;
    slot.addEventListener('dragover', (e) => {
      e.preventDefault();
      slot.classList.add('drag-over');
    });
    slot.addEventListener('dragleave', () => slot.classList.remove('drag-over'));
    slot.addEventListener('drop', (e) => {
      e.preventDefault();
      slot.classList.remove('drag-over');
      mbOnDrop(i, timeStr);
    });
    slots.appendChild(slot);
  }

  // Render placed checkpoints
  MB.placedCheckpoints.forEach(p => {
    mbRenderPlacedCp(p);
  });

  mbUpdateSummary();
}

/* ── Render a placed checkpoint on the timeline ── */
function mbRenderPlacedCp(p) {
  const slots = $('mbTimeSlots');
  if (!slots) return;
  const slot = slots.children[p.slotIdx];
  if (!slot) return;

  const type = p.cp.checkpoint_type || 'nfc';
  const icon = type === 'gps' ? 'fa-map-pin' : type === 'peer' ? 'fa-user-shield' : type === 'custom' ? 'fa-pen' : 'fa-wifi';
  const el = document.createElement('div');
  el.className = `mb-placed-cp ${type}`;
  el.style.top = '2px';
  el.style.bottom = '2px';
  el.draggable = true;
  el.innerHTML = `<i class="fas ${icon}" style="font-size:0.5rem;"></i>
    <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${p.cp.name || 'CP'}</span>
    <span class="cp-time">${p.time}</span>
    <button class="cp-remove" onclick="mbRemovePlaced(${p.slotIdx})"><i class="fas fa-times"></i></button>`;

  el.addEventListener('dragstart', (e) => {
    MB.dragSource = { type: 'placed', slotIdx: p.slotIdx };
    e.dataTransfer.effectAllowed = 'move';
  });
  slot.appendChild(el);
}

/* ── Handle drop ── */
function mbOnDrop(slotIdx, timeStr) {
  if (!MB.dragSource) return;

  if (MB.dragSource.type === 'pool') {
    const cp = MB.checkpoints[MB.dragSource.cpIdx];
    if (!cp) return;
    // Remove from previous slot if already placed
    MB.placedCheckpoints = MB.placedCheckpoints.filter(p => p.cp.id !== cp.id && p.cp.name !== cp.name);
    MB.placedCheckpoints.push({ cp, slotIdx, time: timeStr });
  } else if (MB.dragSource.type === 'placed') {
    const placed = MB.placedCheckpoints.find(p => p.slotIdx === MB.dragSource.slotIdx);
    if (placed) {
      MB.placedCheckpoints = MB.placedCheckpoints.filter(p => p.slotIdx !== MB.dragSource.slotIdx);
      placed.slotIdx = slotIdx;
      placed.time = timeStr;
      MB.placedCheckpoints.push(placed);
    }
  }

  // Sort by slot index
  MB.placedCheckpoints.sort((a, b) => a.slotIdx - b.slotIdx);

  // If sequential, auto-adjust subsequent checkpoints
  if (MB.strategy === 'Sequential') {
    mbEnforceSequence();
  }

  mbRenderPool();
  mbRenderTimeline();
  mbUpdateBrief();
}

/* ── Enforce sequential ordering ── */
function mbEnforceSequence() {
  // In sequential mode, each checkpoint must be after the previous
  for (let i = 1; i < MB.placedCheckpoints.length; i++) {
    if (MB.placedCheckpoints[i].slotIdx <= MB.placedCheckpoints[i - 1].slotIdx) {
      MB.placedCheckpoints[i].slotIdx = MB.placedCheckpoints[i - 1].slotIdx + 1;
      const [startH, startM] = MB.startTime.split(':').map(Number);
      const mins = startH * 60 + startM + MB.placedCheckpoints[i].slotIdx * MB.slotInterval;
      const h = Math.floor(mins / 60) % 24;
      const m = mins % 60;
      MB.placedCheckpoints[i].time = String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
    }
  }
}

/* ── Remove placed checkpoint ── */
function mbRemovePlaced(slotIdx) {
  MB.placedCheckpoints = MB.placedCheckpoints.filter(p => p.slotIdx !== slotIdx);
  mbRenderPool();
  mbRenderTimeline();
  mbUpdateBrief();
}

/* ── Strategy ── */
function mbSetStrategy(strategy, btn) {
  MB.strategy = strategy;
  $$('.mb-strategy-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  $('mbSumStrat').textContent = strategy;

  if (strategy === 'Sequential') {
    mbEnforceSequence();
    mbRenderTimeline();
  }
}

/* ── Date/Time changes ── */
function mbOnDateChange() {
  MB.date = $('mbDate').value;
  mbUpdateSummary();
}

function mbOnStartChange() {
  MB.startTime = $('mbStartTime').value;
  // Recalculate all placed checkpoint times
  MB.placedCheckpoints.forEach(p => {
    const [startH, startM] = MB.startTime.split(':').map(Number);
    const mins = startH * 60 + startM + p.slotIdx * MB.slotInterval;
    const h = Math.floor(mins / 60) % 24;
    const m = mins % 60;
    p.time = String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
  });
  mbRenderTimeline();
  mbUpdateBrief();
}

/* ── Update brief ── */
function mbUpdateBrief() {
  const content = $('mbBriefContent');
  if (!content) return;
  if (!MB.selectedRoute) {
    content.innerHTML = '<div class="rs-empty"><i class="fas fa-satellite-dish"></i><br/>Select a route to begin</div>';
    return;
  }
  content.innerHTML = `
    <div class="rs-block" style="background:linear-gradient(135deg, rgba(211,47,47,0.05), rgba(20,20,32,0.96) 50%);">
      <div style="font-size:0.85rem;font-weight:900;color:#fff;">${MB.selectedRoute.name}</div>
      <div style="font-size:0.65rem;color:var(--r-mute);margin-top:4px;">${MB.checkpoints.length} checkpoints available</div>
    </div>
    <div class="rs-block" style="margin-top:8px;">
      <div style="font-size:0.65rem;font-weight:800;color:var(--r-mute);text-transform:uppercase;margin-bottom:6px;">Scheduled</div>
      ${MB.placedCheckpoints.length ? MB.placedCheckpoints.map(p => `
        <div style="display:flex;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.03);">
          <span style="font-size:0.55rem;color:var(--r-teal);font-family:monospace;width:40px;">${p.time}</span>
          <span style="font-size:0.65rem;color:var(--r-text);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${p.cp.name}</span>
          <span style="font-size:0.5rem;color:var(--r-mute);text-transform:uppercase;">${p.cp.checkpoint_type}</span>
        </div>
      `).join('') : '<div style="font-size:0.65rem;color:var(--r-mute);">Drag checkpoints to timeline</div>'}
    </div>`;
}

/* ── Update summary ── */
function mbUpdateSummary() {
  $('mbSumDate').textContent = MB.date || '—';
  $('mbSumStart').textContent = MB.startTime || '—';
  const [startH, startM] = MB.startTime.split(':').map(Number);
  const endMins = startH * 60 + startM + MB.slotsPerDay * MB.slotInterval;
  const endH = Math.floor(endMins / 60) % 24;
  const endM = endMins % 60;
  $('mbSumEnd').textContent = String(endH).padStart(2, '0') + ':' + String(endM).padStart(2, '0');
  $('mbSumCp').textContent = MB.placedCheckpoints.length + '/' + MB.checkpoints.length;
}

/* ── Deploy ── */
async function mbDeploy() {
  if (!MB.selectedRoute) { toast('Select a route first', true); return; }
  if (!MB.date) { toast('Set a date', true); return; }
  if (!MB.placedCheckpoints.length) { toast('Place at least one checkpoint', true); return; }

  try {
    // Build checkpoint payload with planned_time from timeline
    const checkpoints = MB.placedCheckpoints.map((p, i) => ({
      id: p.cp.id,
      name: p.cp.name,
      checkpoint_type: p.cp.checkpoint_type,
      nfc_tag: p.cp.nfc_tag,
      lat: p.cp.lat,
      lng: p.cp.lng,
      planned_time: p.time,
      time_tolerance: p.cp.time_tolerance || 15,
      dwell_time: p.cp.dwell_time || 0,
      radius: p.cp.radius || 50,
      order: i,
      auditor_id: p.cp.auditor_id,
      target_id: p.cp.target_id,
    }));

    // Update route with scheduled checkpoints
    const saveRes = await api(`/api/routes/${MB.selectedRoute.id}/`, {
      method: 'PATCH',
      body: JSON.stringify({
        scheduled_date: MB.date,
        scheduled_start_time: MB.startTime,
        logic_type: MB.strategy,
        checkpoints: checkpoints,
      }),
    });

    if (!saveRes.ok) {
      toast('Failed to save schedule', true);
      return;
    }

    // Deploy
    const deployRes = await api(`/api/routes/${MB.selectedRoute.id}/deploy/`, {
      method: 'POST',
      body: JSON.stringify({
        scheduled_date: MB.date,
        scheduled_start_time: MB.startTime,
      }),
    });

    if (deployRes.ok) {
      toast('Mission deployed — ' + MB.placedCheckpoints.length + ' checkpoints scheduled');
      mbReset();
    } else {
      let detail = '';
      try { const d = await deployRes.json(); detail = d?.detail ? ' — ' + d.detail : ''; } catch (_) {}
      toast('Deploy failed' + detail, true);
    }
  } catch (e) {
    toast('Deploy request failed', true);
  }
}

/* ── Reset ── */
function mbReset() {
  MB.selectedRoute = null;
  MB.checkpoints = [];
  MB.placedCheckpoints = [];
  $('mbRouteName').textContent = '—';
  $('mbCpCount').textContent = '0';
  $('mbCheckpointPool').innerHTML = '<div class="rs-empty" style="padding:20px;"><i class="fas fa-map-pin"></i><br/>Select a route first</div>';
  mbRenderTimeline();
  mbUpdateBrief();
  mbUpdateSummary();
}

/* ── Filter routes in left panel ── */
function mbFilterRoutes(q) {
  const term = (q || '').toLowerCase();
  $$('#mbRouteList .rs-r-card').forEach(el => {
    const name = (el.textContent || '').toLowerCase();
    el.style.display = name.includes(term) ? '' : 'none';
  });
}

/* ── Filter checkpoint pool ── */
function mbFilterPool(q) {
  const term = (q || '').toLowerCase();
  $$('#mbCheckpointPool .mb-pool-item').forEach(el => {
    const name = (el.textContent || '').toLowerCase();
    el.style.display = name.includes(term) ? '' : 'none';
  });
}

/* ── Quick deploy (skip timeline) ── */
async function mbQuickDeploy(routeId) {
  const now = new Date();
  const date = now.toISOString().split('T')[0];
  const time = String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');
  try {
    const res = await api(`/api/routes/${routeId}/deploy/`, {
      method: 'POST',
      body: JSON.stringify({ scheduled_date: date, scheduled_start_time: time }),
    });
    if (res.ok) toast('Quick deployed for today at ' + time);
    else toast('Quick deploy failed', true);
  } catch (e) { toast('Deploy failed', true); }
}

/* ── Route list onclick (from route list partial) ── */
function mbOnRouteClick(id) { mbSelectRoute(id); }

/* ── Boot ── */
async function mbBoot() {
  await mbLoadRoutes();
  // Render route list in left panel if it exists
  const list = $('mbRouteList');
  if (list && MB.routes.length) {
    list.innerHTML = MB.routes.map(r => `
      <div class="rs-r-card" data-id="${r.id}" onclick="mbOnRouteClick(${r.id})">
        <div class="rs-r-card-top">
          <div class="rs-r-name">${r.name || 'Unnamed'}</div>
        </div>
        <div class="rs-r-meta">${r.logic_type || 'Flex'} · ${r.checkpoint_count || 0} CPs</div>
      </div>
    `).join('');
  }
  mbRenderTimeline();
  mbUpdateSummary();
}

// Exports
window.mbSelectRoute = mbSelectRoute;
window.mbOnRouteClick = mbOnRouteClick;
window.mbSetStrategy = mbSetStrategy;
window.mbDeploy = mbDeploy;
window.mbReset = mbReset;
window.mbFilterRoutes = mbFilterRoutes;
window.mbFilterPool = mbFilterPool;
window.mbQuickDeploy = mbQuickDeploy;
window.mbOnDateChange = mbOnDateChange;
window.mbBoot = mbBoot;

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mbBoot);
} else {
  mbBoot();
}
