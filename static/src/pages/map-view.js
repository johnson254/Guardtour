import '../styles/main.css';
import { $ as dom$ } from '../utils/dom.js';
import { toast } from '../utils/toast.js';
import { api } from '../utils/api.js';

const $ = dom$;

/* ── Alias for backward-compat inside this module ── */
const byId = (id) => $(id);
const bySel = (sel) => Array.from(document.querySelectorAll(sel));
const escHtml = (s) => {
  if (s == null) return '';
  const div = document.createElement('div');
  div.textContent = String(s);
  return div.innerHTML;
};

/* ── State ── */
let map, currentDrawHandler, currentDrawLayer, currentDrawType;
const markers = {}, pathLayers = {}, historyLayers = {}, blueprintLayers = {}, objectLayers = {}, deviceMarkers = {};
const visibleBlueprints = new Set(), historyVisible = { all: false }, deviceVisible = { markers: true, trails: false };
let allPersonnel = [], allRoutes = [], allAssignments = [], allMapObjects = [], lastScans = [], allDevices = [];
const TRAIL_COLORS = ['#E24B4A','#5DCAA5','#EF9F27','#6C8EEF','#CF72E0','#F06292'], guardColors = {};

/* ── Map init ── */
function initMap() {
  map = L.map('tmMap', { zoomControl: false, attributionControl: false }).setView([0, 0], 2);
  L.control.zoom({ position: 'topright' }).addTo(map);
  setTimeout(() => map.invalidateSize(), 200);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://carto.com/attributions">CARTO</a>, &copy; <a href="https://openstreetmap.org/copyright">OSM</a>',
    maxZoom: 19
  }).addTo(map);
  L.control.attribution({ position: 'bottomleft' }).addTo(map);
  map.on(L.Draw.Event.CREATED, e => {
    currentDrawLayer = e.layer;
    map.addLayer(currentDrawLayer);
    tmTab('objects', bySel('.tm-tab')[1]);
    byId('tmDrawForm')?.classList.add('open');
    const titles = { poi: 'New POI', geofence: 'New Geofence', patrol: 'New Patrol Point', circle: 'New Circle Geofence' };
    byId('tmDrawFormTitle').textContent = titles[currentDrawType] || 'New Object';
    if (currentDrawType === 'poi' || currentDrawType === 'patrol') {
      var ll = currentDrawLayer.getLatLng();
      if (byId('tmObjLat')) byId('tmObjLat').value = ll.lat.toFixed(6);
      if (byId('tmObjLng')) byId('tmObjLng').value = ll.lng.toFixed(6);
    } else if (currentDrawType === 'circle') {
      var ll2 = currentDrawLayer.getLatLng();
      if (byId('tmObjLat')) byId('tmObjLat').value = ll2.lat.toFixed(6);
      if (byId('tmObjLng')) byId('tmObjLng').value = ll2.lng.toFixed(6);
      if (byId('tmObjRadius')) { byId('tmObjRadius').value = Math.round(currentDrawLayer.getRadius()); tmEnfSlider(byId('tmObjRadius'), 'tmRadVal', 'm'); }
    }
    if (currentDrawType === 'geofence') {
      var coords = currentDrawLayer.getLatLngs();
      if (coords && coords[0] && coords[0][0]) {
        var first = coords[0][0];
        if (byId('tmObjLat')) byId('tmObjLat').value = first.lat.toFixed(6);
        if (byId('tmObjLng')) byId('tmObjLng').value = first.lng.toFixed(6);
      }
    }
  });
}

/* Mobile sidebar toggle */
window.tmToggleSidebar = function () {
  const sidebar = document.querySelector('.tm-sidebar');
  const toggle = byId('tmSidebarToggle');
  if (!sidebar) return;
  sidebar.classList.toggle('open');
  const isOpen = sidebar.classList.contains('open');
  if (toggle) toggle.innerHTML = isOpen ? '<i class="fas fa-chevron-down"></i> <span id=tmSidebarLabel>Close</span>' : '<i class="fas fa-chevron-up"></i> <span id=tmSidebarLabel>Open</span>';
  setTimeout(() => { if (map) map.invalidateSize(); }, 350);
};

/* Tab switching */
window.tmTab = function (id, el) {
  bySel('.tm-panel').forEach(p => p.classList.remove('active'));
  bySel('.tm-tab').forEach(t => t.classList.remove('active'));
  byId('tmPanel' + id.charAt(0).toUpperCase() + id.slice(1)).classList.add('active');
  if (el) el.classList.add('active');
  if (id === 'assets') tmLoadSavedCheckpoints();
};

/* Draw tools */
window.tmStartDraw = function (type) {
  if (currentDrawHandler) currentDrawHandler.disable();
  tmCancelDraw(false);
  currentDrawType = type;
  ['tmObjRadius','tmObjDwell','tmObjTol'].forEach((id, i) => {
    if (byId(id)) { byId(id).value = [50,0,15][i]; tmEnfSlider(byId(id), ['tmRadVal','tmDwellVal','tmTolVal'][i], ['m','min','min'][i]); }
  });
  if (byId('tmObjLat')) byId('tmObjLat').value = '';
  if (byId('tmObjLng')) byId('tmObjLng').value = '';
  if (byId('tmObjEntryMsg')) byId('tmObjEntryMsg').value = '';
  if (byId('tmObjExitMsg')) byId('tmObjExitMsg').value = '';
  if (byId('tmObjIntrusion')) { byId('tmObjIntrusion').checked = false; tmToggleLabel(byId('tmObjIntrusion'),'tmIntrusionLabel'); }
  var geoRules = byId('tmGeoRules');
  if (geoRules) geoRules.style.display = (type === 'geofence' || type === 'circle') ? 'flex' : 'none';
  var isFence = type === 'geofence' || type === 'circle';
  if (byId('tmPersonnelWrap')) byId('tmPersonnelWrap').style.display = isFence ? 'none' : '';
  if (byId('tmPickBtn')) byId('tmPickBtn').style.display = isFence ? 'none' : '';
  bySel('.tm-map-btn').forEach(b => b.classList.remove('active'));
  const btnMap = { patrol: 'tmBtnPatrol', geofence: 'tmBtnGeo', circle: 'tmBtnCircle', poi: 'tmBtnPoi' };
  if (btnMap[type]) byId(btnMap[type]).classList.add('active');
  if (type === 'patrol' || type === 'poi') currentDrawHandler = new L.Draw.Marker(map);
  else if (type === 'circle') currentDrawHandler = new L.Draw.Circle(map, { shapeOptions: { color: '#EF9F27', fillOpacity: 0.15, weight: 2 }});
  else currentDrawHandler = new L.Draw.Polygon(map, { shapeOptions: { color: type === 'geofence' ? '#5DCAA5' : '#E24B4A', fillOpacity: 0.08, weight: 2 }});
  currentDrawHandler.enable();
  toast('Click on the map to place');
};

/* Slider helpers */
window.tmEnfSlider = function(slider, valId, unit) {
  var valEl = byId(valId);
  if (!valEl) return;
  var v = parseInt(slider.value) || 0;
  valEl.innerHTML = v + '<small>' + unit + '</small>';
  var card = slider.closest('.enf-card');
  if (card) card.querySelectorAll('.enf-preset').forEach(function(p) { p.classList.toggle('active', parseInt(p.textContent.trim()) === v); });
};
window.tmSetPreset = function(sliderId, valId, val, unit) {
  var slider = byId(sliderId);
  if (!slider) return;
  slider.value = val;
  tmEnfSlider(slider, valId, unit);
};
window.tmToggleLabel = function(cb, labelId) {
  var lbl = byId(labelId);
  if (lbl) lbl.style.color = cb.checked ? '#5DCAA5' : 'rgba(255,255,255,0.4)';
};

/* Cancel draw */
window.tmCancelDraw = function (removeLayer = true) {
  if (currentDrawHandler) { currentDrawHandler.disable(); currentDrawHandler = null; }
  if (removeLayer && currentDrawLayer) { map.removeLayer(currentDrawLayer); currentDrawLayer = null; }
  if (window._tmPickMarker) { map.removeLayer(window._tmPickMarker); window._tmPickMarker = null; }
  byId('tmDrawForm').classList.remove('open');
  byId('tmObjName').value = '';
  ['tmObjRadius','tmObjDwell','tmObjTol'].forEach(id => {
    if (byId(id)) { byId(id).value = [50,0,15][['tmObjRadius','tmObjDwell','tmObjTol'].indexOf(id)]; tmEnfSlider(byId(id), id==='tmObjRadius'?'tmRadVal':id==='tmObjDwell'?'tmDwellVal':'tmTolVal', id!=='tmObjRadius'?'min':'m'); }
  });
  if (byId('tmObjLat')) byId('tmObjLat').value = '';
  if (byId('tmObjLng')) byId('tmObjLng').value = '';
  if (byId('tmObjEntryMsg')) byId('tmObjEntryMsg').value = '';
  if (byId('tmObjExitMsg')) byId('tmObjExitMsg').value = '';
  if (byId('tmObjIntrusion')) { byId('tmObjIntrusion').checked = false; tmToggleLabel(byId('tmObjIntrusion'),'tmIntrusionLabel'); }
  if (byId('tmGeoRules')) byId('tmGeoRules').style.display = 'none';
  if (byId('tmPersonnelWrap')) byId('tmPersonnelWrap').style.display = '';
  if (byId('tmPickBtn')) byId('tmPickBtn').style.display = '';
  if (window._tmPickHandler) { map.off('click', window._tmPickHandler); window._tmPickHandler = null; }
  bySel('.tm-map-btn').forEach(b => b.classList.remove('active'));
  bySel('.tm-tool-btn').forEach(b => b.classList.remove('active'));
};

/* Save object */
window.tmSaveObject = async function () {
  const name = byId('tmObjName').value.trim();
  if (!name) { toast('Name required', true); return; }
  if (!currentDrawLayer) { toast('Place object on map first', true); return; }
  const personnel = Array.from(byId('tmObjPersonnel').selectedOptions).map(o => o.value);
  const type = currentDrawType;
  let geometry = [], radius = null;
  if (type === 'patrol' || type === 'poi') {
    const ll = currentDrawLayer.getLatLng();
    geometry = [ll.lat, ll.lng];
    radius = parseInt(byId('tmObjRadius')?.value) || 50;
  } else if (type === 'circle') {
    const ll = currentDrawLayer.getLatLng();
    geometry = [ll.lat, ll.lng];
    radius = Math.round(currentDrawLayer.getRadius());
  } else {
    geometry = currentDrawLayer.getLatLngs()[0].map(p => [p.lat, p.lng]);
  }
  var latOverride = byId('tmObjLat')?.value, lngOverride = byId('tmObjLng')?.value;
  if (latOverride && lngOverride && (type === 'poi' || type === 'patrol')) geometry = [parseFloat(latOverride), parseFloat(lngOverride)];
  try {
    const res = await apiWrapper('/api/map-objects/', {
      method: 'POST',
      body: JSON.stringify({
        name, type: type === 'geofence' ? 'geofence' : 'poi', geometry, radius,
        assigned_personnel: personnel,
        entry_msg: byId('tmObjEntryMsg')?.value?.trim() || null,
        exit_msg: byId('tmObjExitMsg')?.value?.trim() || null,
        intrusion_alarm: byId('tmObjIntrusion')?.checked || false
      })
    });
    if (res.ok) { toast('Object saved'); tmCancelDraw(false); await loadAll(); }
    else { toast('Save failed', true); }
  } catch (e) { toast('Error saving', true); }
};

/* Load all data */
async function loadAll() {
  try {
    const [statsRes, routesRes, personRes, assignRes, devicesRes] = await Promise.all([
      apiWrapper('/api/org-stats/'), apiWrapper('/api/routes/'),
      apiWrapper('/api/profiles/'), apiWrapper('/api/shifts/'), apiWrapper('/api/devices/')
    ]);
    if (statsRes.ok) {
      const data = await statsRes.json();
      allMapObjects = data.map_objects || [];
      lastScans = data.recent_scans || [];
      renderMapObjects(allMapObjects);
      renderFeed();
      renderGuardMarkers(data.scans_history_today || []);
      (data.blueprints || []).forEach(bp => { if (visibleBlueprints.has(bp.id)) renderBlueprint(bp); });
    }
    if (routesRes.ok) {
      const d = await routesRes.json();
      allRoutes = Array.isArray(d) ? d : (d.results || []);
      renderRoutesList();
    }
    if (personRes.ok) {
      const d = await personRes.json();
      allPersonnel = Array.isArray(d) ? d : (d.results || []);
      populateGuardDropdowns();
    }
    if (assignRes.ok) {
      const d = await assignRes.json();
      allAssignments = Array.isArray(d) ? d : (d.results || []);
      renderLiveDeployments();
    }
    if (devicesRes.ok) {
      const d = await devicesRes.json();
      allDevices = Array.isArray(d) ? d : (d.results || []);
      renderDeviceMarkers();
      renderDeviceList();
    }
  } catch (e) { console.error('Map load error:', e); }
}

/* Bootstrap */
(async function boot() {
  while (typeof L === 'undefined') await new Promise(r => setTimeout(r, 50));
  initMap();
  byId('tmHistoryDate').value = new Date().toISOString().split('T')[0];
  loadAll().then(() => {
    var allLayers = [];
    Object.values(objectLayers).forEach(l => allLayers.push(l));
    Object.values(deviceMarkers).forEach(m => allLayers.push(m));
    if (allLayers.length) {
      var group = L.featureGroup(allLayers);
      if (group.getBounds().isValid()) map.flyToBounds(group.getBounds().pad(0.2), { duration: 0.5 });
    }
  });
  setInterval(loadAll, 15000);
  console.log('Map view initialized');
})();

/* expose map-page globals expected by inline handlers */
window.tmToggleSidebar = window.tmToggleSidebar;
window.tmTab = tmTab;
window.tmStartDraw = tmStartDraw;
window.tmEnfSlider = tmEnfSlider;
window.tmT = tmTab;
window.tmCancelDraw = tmCancelDraw;
window.tmSetPreset = tmSetPreset;
window.tmToggleLabel = tmToggleLabel;
window.tmSaveObject = tmSaveObject;

/* missing map-page controllers stubbed to avoid template ReferenceErrors */
window.tmToggleHistory = () => {
  historyVisible.all = !historyVisible.all;
  Object.values(historyLayers).forEach(layer => {
    if (historyVisible.all) map.addLayer(layer); else map.removeLayer(layer);
  });
  byId('tmBtnHistory')?.classList.toggle('active', historyVisible.all);
};

window.tmToggleDevices = () => {
  deviceVisible.trails = !deviceVisible.trails;
  Object.values(pathLayers).forEach(layer => {
    if (deviceVisible.trails) map.addLayer(layer); else map.removeLayer(layer);
  });
  byId('tmBtnDevices')?.classList.toggle('active', deviceVisible.trails);
};

window.tmLoadGuardHistory = async () => {
  const guardId = byId('tmHistoryGuard')?.value;
  const date = byId('tmHistoryDate')?.value;
  if (!guardId || !date) { toast('Select guard and date', true); return; }
  toast('History loading...');
  try {
    const res = await apiWrapper('/api/scans/', { params: new URLSearchParams({ guard_supervisor: guardId, date }) });
    if (!res.ok) throw new Error('Failed');
    const data = await res.json();
    renderHistoryList(data);
  } catch (e) {
    toast('Failed to load history', true);
  }
};

window.tmSaveCheckpoints = async () => {
  const staged = Array.from(document.querySelectorAll('.tm-staged-item'))
    .map(el => ({
      route: el.dataset.routeId ? Number(el.dataset.routeId) : null,
      nfc_tag: el.dataset.nfc || '',
      checkpoint_type: el.dataset.type || 'nfc',
      lat: el.dataset.lat ? Number(el.dataset.lat) : null,
      lng: el.dataset.lng ? Number(el.dataset.lng) : null,
      planned_time: el.dataset.planned || null,
      order: el.dataset.order ? Number(el.dataset.order) : 0,
      radius: el.dataset.radius ? Number(el.dataset.radius) : 50,
      dwell_time: el.dataset.dwell ? Number(el.dataset.dwell) : 0,
      time_tolerance: el.dataset.tol ? Number(el.dataset.tol) : 15,
      next_announcement_text: el.dataset.entry || '',
    }));
  if (!staged.length) { toast('No checkpoints staged', true); return; }
  try {
    const res = await apiWrapper('/api/checkpoints/bulk/', { method: 'POST', body: JSON.stringify(staged) });
    if (!res.ok) throw new Error('Failed');
    document.querySelectorAll('.tm-staged-item').forEach(el => el.remove());
    toast('Checkpoints saved');
    await loadAll();
  } catch (e) {
    toast('Save failed', true);
  }
};

window.tmClearStaged = () => {
  document.querySelectorAll('.tm-staged-item').forEach(el => el.remove());
};

window.tmQuickAdd = (type) => {
  const item = document.createElement('div');
  item.className = 'tm-item tm-staged-item';
  item.dataset.type = type;
  item.dataset.nfc = '';
  item.dataset.lat = '';
  item.dataset.lng = '';
  item.dataset.planned = '';
  item.dataset.order = '0';
  item.dataset.radius = '50';
  item.dataset.dwell = '0';
  item.dataset.tol = '15';
  item.dataset.entry = '';
  item.dataset.exit = '';
  item.dataset.intrusion = '0';
  item.innerHTML = `<div class="tm-item-head"><div class="tm-item-name">New ${type}</div><div class="tm-item-sub">Not placed</div></div>`;
  byId('tmCpRegistry').prepend(item);
  toast('Staged ' + type);
};

window.tmFitObjects = () => {
  const layers = Object.values(objectLayers).filter(Boolean);
  if (!layers.length) return;
  const group = L.featureGroup(layers);
  if (group.getBounds().isValid()) map.flyToBounds(group.getBounds().pad(0.2), { duration: 0.5 });
};

window.tmToggleBlueprint = function(routeId) {
  const route = allRoutes.find(r => String(r.id) === String(routeId));
  if (!route) return;
  renderBlueprint(route);
};

window.tmSelectRoute = function(routeId) {
  window.tmSelectedRouteId = routeId;
  renderRoutesList();
  focusRoute(routeId);
};

window.tmPickOnMap = () => {
  if (window._tmPickHandler) map.off('click', window._tmPickHandler);
  window._tmPickMarker = L.marker([0,0], { opacity: 0 }).addTo(map);
  window._tmPickHandler = (e) => {
    const { lat, lng } = e.latlng;
    if (byId('tmObjLat')) byId('tmObjLat').value = lat.toFixed(6);
    if (byId('tmObjLng')) byId('tmObjLng').value = lng.toFixed(6);
    if (window._tmPickMarker) {
      window._tmPickMarker.setLatLng(e.latlng).setOpacity(1);
    }
    map.off('click', window._tmPickHandler);
    window._tmPickHandler = null;
  };
  map.on('click', window._tmPickHandler);
  toast('Click map to set location');
};

/* minimal render stubs so loadAll does not crash during refactor */
function renderMapObjects(objects = []) {
  const container = byId('tmObjectsList');
  if (!container) return;
  Object.values(objectLayers).forEach(l => map.removeLayer(l));
  Object.keys(objectLayers).forEach(k => delete objectLayers[k]);

  container.innerHTML = objects.length
    ? objects.map(o => {
        const key = o.id || o.name;
        let layer = null;
        if (o.type === 'poi' || o.type === 'patrol') {
          layer = L.circleMarker([o.lat, o.lng], { radius: 6, color: '#d32f2f', fillColor: '#d32f2f', fillOpacity: 0.8 });
          layer.bindPopup(`<b>${escHtml(o.name)}</b>`);
        } else if (o.type === 'circle') {
          layer = L.circle([o.lat, o.lng], { radius: o.radius || 50, color: '#6C8EEF', fillColor: '#6C8EEF', fillOpacity: 0.15 });
          layer.bindPopup(`<b>${escHtml(o.name)}</b><br>Radius: ${o.radius || 50}m`);
        } else if (o.type === 'geofence') {
          const coords = o.geometry?.coordinates?.[0];
          if (coords && coords.length) {
            layer = L.polygon(coords.map(c => [c[1], c[0]]), { color: '#2dd4bf', fillColor: '#2dd4bf', fillOpacity: 0.15 });
            layer.bindPopup(`<b>${escHtml(o.name)}</b>`);
          }
        }
        if (layer) {
          objectLayers[key] = layer;
          layer.addTo(map);
        }
        return `<div class="tm-item"><div class="tm-item-head"><div class="tm-item-name">${escHtml(o.name || 'Object')}</div></div><div class="tm-item-sub">${escHtml(o.type || '')}</div></div>`;
      }).join('')
    : '<div class="tm-empty"><i class="fas fa-layer-group"></i>No objects yet</div>';
}

function renderFeed() {
  const container = byId('tmFeed');
  if (!container) return;
  if (lastScans && lastScans.length) {
    container.innerHTML = lastScans.slice(0, 20).map(s => `<div class="tm-feed-item"><div class="tm-feed-guard">${escHtml(s.guard || 'Guard')}</div><div class="tm-feed-cp">${escHtml(s.checkpoint || 'Point')}</div><div class="tm-feed-time">${escHtml(s.timestamp || '')}</div></div>`).join('');
  } else {
    container.innerHTML = '<div class="tm-empty"><i class="fas fa-signal"></i>No recent scans</div>';
  }
}

function renderBlueprint(bp) {
  if (!bp || !bp.id) return;
  const key = 'bp-' + bp.id;
  if (blueprintLayers[key]) { map.removeLayer(blueprintLayers[key]); delete blueprintLayers[key]; return; }
  const checkpoints = bp.checkpoints || bp.waypoints || [];
  if (!checkpoints.length) return;
  const latlngs = checkpoints.filter(c => c.lat && c.lng).map(c => [c.lat, c.lng]);
  if (!latlngs.length) return;
  const layer = L.polyline(latlngs, { color: '#d32f2f', weight: 3, opacity: 0.8, dashArray: '8, 12' });
  layer.bindPopup(`<b>${escHtml(bp.name || 'Blueprint')}</b><br>${checkpoints.length} checkpoints`);
  layer.addTo(map);
  blueprintLayers[key] = layer;
  if (!visibleBlueprints.has(bp.id)) visibleBlueprints.add(bp.id);
  map.flyToBounds(layer.getBounds().pad(0.2), { duration: 0.5 });
}

function renderGuardMarkers(scans = []) {
  const seen = new Set();
  scans.forEach((s) => {
    if (!s.lat || !s.lng || seen.has(s.guard_id || s.id)) return;
    seen.add(s.guard_id || s.id);
    const color = guardColors[s.guard_id || s.id] || (guardColors[s.guard_id || s.id] = TRAIL_COLORS[Object.keys(guardColors).length % TRAIL_COLORS.length]);
    const m = L.circleMarker([s.lat, s.lng], { radius: 6, color, fillColor: color, fillOpacity: 0.9, weight: 2 });
    m.bindPopup(`<b>${escHtml(s.guard || 'Guard')}</b><br>${escHtml(s.checkpoint || 'Scan')}`);
    m.addTo(map);
  });
}

function renderRoutesList() {
  const container = byId('tmRoutesList');
  if (!container) return;

  const fmtDuration = (s) => {
    if (!s && s !== 0) return '';
    const m = Math.round((s || 0) / 60);
    if (m < 60) return m + ' min';
    return Math.floor(m / 60) + 'h ' + (m % 60) + 'm';
  };

  const fmtDist = (m) => {
    if (!m && m !== 0) return '';
    if (m < 1000) return Math.round(m) + ' m';
    return (m / 1000).toFixed(1) + ' km';
  };

  // Sort by dummy preview so selected route floats to top.
  const sorted = allRoutes
    .map((r, i) => ({ r, i }))
    .sort((a, b) => {
      const aSel = a.r.id === window.tmSelectedRouteId ? -1 : 0;
      const bSel = b.r.id === window.tmSelectedRouteId ? -1 : 0;
      return aSel - bSel || 0;
    });

  container.innerHTML = allRoutes.length
    ? sorted
        .map(({ r }) => {
          const active = window.tmSelectedRouteId === r.id;
          const fast = r.is_fastest ? '<span style="width:auto;border-radius:999px;padding:3px 7px;margin-left:8px;background:rgba(90,222,170,0.12);border:1px solid rgba(90,222,170,0.25);color:#5DCAA5;font-size:0.62rem;font-weight:900;white-space:nowrap;">Fastest</span>' : '';
          const surf =
            r.duration || r.distance
              ? `<span class="tm-pill-meta"><span class="tm-guard-pill"><span class="tm-guard-trail"><svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" fill="rgba(255,255,255,0.25)"/></svg></span><span>${escHtml(fmtDuration(r.duration))}${r.distance ? ' · ' + escHtml(fmtDist(r.distance)) : ''}</span></span></span>${fast}`
              : fast;
          return `
            <button type="button"
                class="tm-item tm-route-pill${active ? ' active' : ''}"
                onclick="window.tmSelectRoute('${r.id}')"
                style="text-align:left;border-radius:10px;">
                <div style="display:flex;flex-direction:column">
                    <div class="tm-item-name" style="font-weight:900;">${escHtml(r.name || 'Route')}</div>
                    <div class="tm-item-sub">${escHtml(r.organization || '')}</div>
                </div>
                ${surf}
            </button>`;
        })
        .join('')
    : '<div class="tm-empty"><i class="fas fa-route"></i>No routes</div>';
}

function populateGuardDropdowns() {
  const sel = byId('tmHistoryGuard');
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = '<option value="">— All active guards —</option>' + allPersonnel.map(g => `<option value="${g.id}">${escHtml(g.username || g.user?.username || 'Guard')}</option>`).join('');
}

function renderLiveDeployments() {
  const container = byId('tmLiveDeployments');
  if (!container) return;
  container.innerHTML = allAssignments.length
    ? allAssignments.slice(0, 20).map(a => `<div class="tm-item"><div class="tm-item-head"><div class="tm-item-name">${escHtml(a.route?.name || 'Assignment')}</div></div><div class="tm-item-sub">${escHtml(a.guard_supervisor?.guard?.user?.username || 'Guard')}</div></div>`).join('')
    : '<div class="tm-empty"><i class="fas fa-satellite-dish"></i>No active deployments</div>';
}

function renderDeviceMarkers() {
  const container = byId('tmDeviceList');
  if (!container) return;
  container.innerHTML = allDevices.length
    ? allDevices.slice(0, 20).map(d => `<div class="tm-item"><div class="tm-item-head"><div class="tm-item-name">${escHtml(d.device_id || 'Device')}</div></div><div class="tm-item-sub">${escHtml(d.user?.username || d.guard?.user?.username || 'Unassigned')}</div></div>`).join('')
    : '<div class="tm-empty"><i class="fas fa-microchip"></i>No devices</div>';
}

function renderDeviceList() {
  renderDeviceMarkers();
}

function renderHistoryList(scans = []) {
  const container = byId('tmHistoryList');
  if (!container) return;
  container.innerHTML = scans.length
    ? scans.slice(0, 30).map(s => `<div class="tm-feed-item"><div class="tm-feed-guard">${escHtml(s.guard || 'Guard')}</div><div class="tm-feed-cp">${escHtml(s.checkpoint || 'Scan')}</div><div class="tm-feed-time">${escHtml(s.timestamp || '')}</div></div>`).join('')
    : '<div class="tm-empty"><i class="fas fa-route"></i>No trail data</div>';
}
