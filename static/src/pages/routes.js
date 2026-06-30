import '../styles/main.css';
/* ═══════════════════════════════════════════════════
   STATE
═══════════════════════════════════════════════════ */
let allRoutes    = [];
let allPersonnel = [];
let allAssets    = [];
let allDevices   = [];
let selId        = null;
let logic        = 'Flexible';

/* ── htmx helper: refresh route list ─────────────── */
function refreshRouteList() {
    if (window.htmx) {
        htmx.ajax('GET', '/api/routes-list-partial/', {
            target: '#bpRouteList', swap: 'innerHTML'
        });
    }
}
let assignedGuardIds = [];
let bpDirty      = false;
let wizStrategy  = null;
let auditTargetCount = 0;

const $  = id => document.getElementById(id);
const $$ = s  => document.querySelectorAll(s);

/* ═══════════════════════════════════════════════════
   API
═══════════════════════════════════════════════════ */
const api = async (url, opts = {}) => {
    if (typeof window.apiFetch === 'function') return window.apiFetch(url, opts);
    var token = JSON.parse(localStorage.getItem('gt_user') || '{}').token;
    var headers = { 'Content-Type': 'application/json', ...(token ? { 'Authorization': 'Bearer ' + token } : {}), ...(opts.headers || {}) };
    return fetch(url, { credentials: 'same-origin', ...opts, headers: headers });
};

/* ═══════════════════════════════════════════════════
   TOAST
═══════════════════════════════════════════════════ */
function toast(msg, isErr) {
    const el = document.createElement('div');
    el.className = 'rs-toast';
    el.innerHTML = `<span class="td${isErr ? ' tde' : ''}"></span>${msg}`;
    $('bpToasts').appendChild(el);
    setTimeout(() => el.remove(), 2800);
}

function bpAutoGrow(el) { el.style.height = 'auto'; el.style.height = Math.max(60, el.scrollHeight) + 'px'; }
window.bpSetDirty = function() { bpDirty = true; };

/* ═══════════════════════════════════════════════════
   OVERLAY — htmx-driven wizard navigation
═══════════════════════════════════════════════════ */

window.showOverlay = function(stepId = 'wizStep1') {
    $('bpOverlay').classList.remove('rs-hidden');
    $('rsSidebar').classList.add('rs-hidden');
    $('rsLibPanel')?.classList.add('rs-hidden');
    var cs = $('qdConfirmStrip'); if (cs && stepId !== 'wizStepQuick') cs.style.display = 'none';
    // Load step content via htmx
    if (window.htmx) {
        const stepMap = { wizStepQuick: 'quick', wizStepAudit: 'audit', wizStepQuickDeploy: 'quickdeploy', wizStepEditConfirm: 'editconfirm' };
        const stepParam = stepMap[stepId] || stepId.replace('wizStep', '');
        const strategy = wizStrategy || '';
        htmx.ajax('GET', '/api/routes-wizard-partial/?step=' + stepParam + (strategy ? '&strategy=' + strategy : ''), {
            target: '#bpOverlayContent', swap: 'innerHTML'
        });
    }
};

window.hideOverlay = function() { 
    $('bpOverlay').classList.add('rs-hidden'); 
    $('rsSidebar').classList.remove('rs-hidden');
    $('rsLibPanel')?.classList.remove('rs-hidden');
    var cs = $('qdConfirmStrip'); if (cs) cs.style.display = 'none';
};

window.bpShowBuilder = function() {
    showOverlay('wizStep1');
};

/* ═══════════════════════════════════════════════════
   WIZARD NAV — htmx-driven step loading
═══════════════════════════════════════════════════ */
window.wizGo = function(step, strategyOrKey) {
    if (step === 'quick') {
        wizStrategy = 'Quick';
        bpSetLogic('Flexible');
        showOverlay('wizStepQuick');
        return;
    } else if (step === 'audit') {
        wizStrategy = 'Audit';
        bpSetLogic('Audit');
        showOverlay('wizStepAudit');
        return;
    }
    wizStrategy = strategyOrKey;
    bpSetLogic(strategyOrKey);
    hideOverlay();
};

window.wizBack = step => showOverlay('wizStep' + step);

/* ═══════════════════════════════════════════════════
   LOAD DATA
═══════════════════════════════════════════════════ */
async function bpLoad() {
    try {
        const [rRes, pRes, aRes, dRes] = await Promise.all([
            api('/api/routes/'),
            api('/api/profiles/'),
            api('/api/map-objects/'),
            api('/api/devices/')
        ]);
        if (rRes.ok) { const d = await rRes.json(); allRoutes    = Array.isArray(d) ? d : (d.results || []); }
        if (pRes.ok) { const d = await pRes.json(); allPersonnel = Array.isArray(d) ? d : (d.results || []); }
        if (aRes.ok) { const d = await aRes.json(); allAssets    = Array.isArray(d) ? d : (d.results || []); }
        if (dRes.ok) { const d = await dRes.json(); allDevices   = Array.isArray(d) ? d : (d.results || []); }
    } catch (e) {}
    refreshRouteList();
}

function getPersonById(id) {
    if (!id) return null;
    return (allPersonnel || []).find(p => String(p.id) === String(id)) || null;
}

function getPersonByCallsign(q) {
    const lq = q.toLowerCase();
    return (allPersonnel || []).find(p =>
        (p.username || '').toLowerCase() === lq ||
        (p.callsign || '').toLowerCase() === lq
    ) || null;
}

/* ═══════════════════════════════════════════════════
   CALLSIGN TAG INPUT (shared across all tag fields)
═══════════════════════════════════════════════════ */
function populateTagSuggest(inputId, tagsContainerId) {
    // Wire up a generic tag input
    const inp  = $(inputId);
    const tags = $(tagsContainerId);
    if (!inp || !tags) return;

    const suggestId = inputId.replace('Input', 'Suggest');
    const suggest = $(suggestId);

    inp.oninput = () => {
        const val = inp.value.trim().toLowerCase();
        if (!val || !suggest) { suggest?.classList.add('rs-hidden'); return; }
        
        const pM = allPersonnel.filter(p => 
            (p.username || '').toLowerCase().includes(val) || 
            (p.callsign || '').toLowerCase().includes(val)
        ).slice(0, 5);

        const dM = allDevices.filter(d => 
            (d.device_id || '').toLowerCase().includes(val) || 
            (d.device_name || '').toLowerCase().includes(val)
        ).slice(0, 5);

        if (!pM.length && !dM.length) { suggest.classList.add('rs-hidden'); return; }

        let html = dM.map(d => `
            <div class="rs-suggest-item" onclick="bpPickTagForWrap('${inputId}','${tagsContainerId}','${d.id}','${d.device_id}','device')">
                <span><i class="fas fa-mobile-screen" style="color:var(--r-teal)"></i> ${d.device_id}</span>
                <span style="opacity:.5;font-size:.6rem;text-transform:uppercase;">${d.device_name}</span>
            </div>`).join('');
            
        html += pM.map(p => `
            <div class="rs-suggest-item" onclick="bpPickTagForWrap('${inputId}','${tagsContainerId}','${p.id}','${p.callsign || p.username}','person')">
                <span><i class="fas fa-user-shield"></i> ${p.callsign || p.username}</span>
                <span style="opacity:.5;font-size:.6rem;text-transform:uppercase;">${p.role || 'Personnel'}</span>
            </div>`).join('');

        suggest.innerHTML = html;
        suggest.classList.remove('rs-hidden');
    };

    inp.onkeydown = (e) => {
        if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            const val = inp.value.trim();
            if (!val) return;
            // Check for guard by callsign first
            const guardMatches = allPersonnel.filter(p => (p.username || '').toLowerCase() === val.toLowerCase() || (p.callsign || '').toLowerCase() === val.toLowerCase());
            // Check for device by device_id or device_name
            const deviceMatches = allDevices.filter(d => (d.device_id || '').toLowerCase() === val.toLowerCase() || (d.device_name || '').toLowerCase() === val.toLowerCase());
            const p = guardMatches.length ? guardMatches[0] : getPersonByCallsign(val);
            const d = deviceMatches.length ? deviceMatches[0] : null;
            // Add as device if found, otherwise add as guard
            if (d) {
                addPersonTag(tagsContainerId, d.id, d.device_id || d.device_name, 'device');
            } else {
                addPersonTag(tagsContainerId, p ? p.id : null, p ? (p.callsign || p.username) : val);
            }
            inp.value = '';
            suggest?.classList.add('rs-hidden');
        }
    };

    inp.onblur = () => {
        setTimeout(() => suggest?.classList.add('rs-hidden'), 250);
    };
}

window.bpPickTagForWrap = function(inputId, tagsContainerId, id, label, type) {
    const inp = $(inputId);
    addPersonTag(tagsContainerId, id, label, type);
    if (inp) inp.value = '';
    $(inputId.replace('Input', 'Suggest'))?.classList.add('rs-hidden');
    if (inputId === 'bpGuardInput') bpSetDirty();
};

window.sweepTargetLookup = function(el) { bpTagInput(el); };

function addPersonTag(containerId, id, label, type = 'person') {
    const container = $(containerId);
    if (!container) return;
    // Avoid duplicate
    if (id && Array.from(container.querySelectorAll('.rs-person-tag')).some(t => t.dataset.pid === String(id))) return;
    const span = document.createElement('span');
    span.className = 'rs-person-tag';
    span.dataset.pid   = id || '';
    span.dataset.label = label;
    span.dataset.type  = type;
    if(type === 'device') { span.style.background = 'rgba(0,196,154,0.15)'; span.style.color = 'var(--r-teal)'; span.style.borderColor = 'rgba(0,196,154,0.3)'; }
    
    const icon = type === 'device' ? 'fa-mobile-screen' : 'fa-user-shield';
    span.innerHTML = `<i class="fas ${icon}" style="font-size:.55rem;"></i>${label}<button type="button" onclick="this.parentElement.remove();bpUpdatePreview();bpSetDirty();" title="Remove"><i class="fas fa-times"></i></button>`;
    container.appendChild(span);
    if (id && containerId === 'bpGuardTags') {
        if (!assignedGuardIds.includes(Number(id))) assignedGuardIds.push(Number(id));
    }
    bpUpdatePreview();
}

function getTaggedIds(containerId) {
    return Array.from($(containerId)?.querySelectorAll('.rs-person-tag') || [])
        .map(t => t.dataset.pid).filter(Boolean).map(Number);
}

function getTaggedLabels(containerId) {
    return Array.from($(containerId)?.querySelectorAll('.rs-person-tag') || [])
        .map(t => t.dataset.label).filter(Boolean);
}

function clearTags(containerId) {
    Array.from($(containerId)?.querySelectorAll('.rs-person-tag') || []).forEach(t => t.remove());
}

/* ═══════════════════════════════════════════════════
   LIBRARY LIST — rendered via htmx (/api/routes-list-partial/)
═══════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════
   SELECT / LOAD ROUTE
═══════════════════════════════════════════════════ */
window.bpSelectRoute = async function (id) {
    if (selId !== id && bpDirty && !confirm('Discard unsaved changes?')) return;
    selId = id; bpDirty = false; refreshRouteList();
    try {
        const res = await api(`/api/routes/${id}/`);
        if (!res.ok) return;
        const r = await res.json();
        hideOverlay();
        $('bpEdTitle').textContent          = 'Edit Blueprint';
        $('bpRouteName').value              = r.name || '';
        $('bpDate').value                   = r.scheduled_date || '';
        $('bpMissionBrief').value           = r.description || r.readout_text || '';
        CalendarComponent.render();
        $('bpAnnounceToggle').checked       = r.send_announcement !== false;
        $('bpLeadTime').value               = r.start_alert_lead_time || 15;
        $('bpRepeatLabel').textContent      = $('bpLeadTime').value;
        bpUpdateAlertTime();
        $('bpIsDaily').checked              = r.is_daily || false;
        $('bpStartTime').value              = r.scheduled_start_time || '';
        $('bpSendAlert').checked            = r.send_start_alert !== false;
        const shiftVal = (r.shift || r.duty_cycle || '').toLowerCase();
        $('bpShiftDay').checked             = shiftVal === 'day';
        $('bpShiftNight').checked           = shiftVal === 'night';
        $('bpShiftAny').checked             = shiftVal !== 'day' && shiftVal !== 'night';
        if (typeof bpHandleShift === 'function') bpHandleShift();
        assignedGuardIds = r.assigned_guards || [];
        clearTags('bpGuardTags');
        assignedGuardIds.forEach(gid => {
            const g = getPersonById(gid);
            if (g) addPersonTag('bpGuardTags', gid, g.username);
        });
        bpSetLogic(r.logic_type || 'Flexible');
        bpClearCps();
        (r.checkpoints || []).forEach(cp => bpAddCp(cp));
        setDispatch(true);
        bpUpdatePreview();
        var reviewBtn = $('bpReviewBtn');
        if (reviewBtn) reviewBtn.classList.remove('rs-hidden');
    } catch (e) {}
};

/* ═══════════════════════════════════════════════════
   QUICK DEPLOY (from route list)
═══════════════════════════════════════════════════ */
window.mgQuickDeploy = async function(routeId) {
    if (bpDirty && !confirm('Discard unsaved changes?')) return;
    try {
        const res = await api('/api/routes/' + routeId + '/');
        if (!res.ok) return;
        const r = await res.json();
        selId = routeId; bpDirty = false; refreshRouteList();
        $('bpEdTitle').textContent = 'Edit Blueprint';
        $('bpRouteName').value = r.name || '';
        $('bpDate').value = r.scheduled_date || '';
        $('bpMissionBrief').value = r.description || r.readout_text || '';
        $('bpAnnounceToggle').checked = r.send_announcement !== false;
        $('bpLeadTime').value = r.start_alert_lead_time || 15;
        $('bpRepeatLabel').textContent = $('bpLeadTime').value;
        bpUpdateAlertTime();
        $('bpIsDaily').checked = r.is_daily || false;
        $('bpStartTime').value = r.scheduled_start_time || '';
        $('bpSendAlert').checked = r.send_start_alert !== false;
        const shiftVal = (r.shift || r.duty_cycle || '').toLowerCase();
        $('bpShiftDay').checked = shiftVal === 'day';
        $('bpShiftNight').checked = shiftVal === 'night';
        $('bpShiftAny').checked = shiftVal !== 'day' && shiftVal !== 'night';
        bpHandleShift();
        assignedGuardIds = r.assigned_guards || [];
        clearTags('bpGuardTags');
        assignedGuardIds.forEach(gid => {
            const g = getPersonById(gid);
            if (g) addPersonTag('bpGuardTags', gid, g.username);
        });
        bpSetLogic(r.logic_type || 'Flexible');
        bpClearCps();
        (r.checkpoints || []).forEach(cp => bpAddCp(cp));
        setDispatch(true);
        bpUpdatePreview();
        wizStrategy = 'Quick';
        // Open quick deploy wizard via htmx
        showOverlay('wizStepQuick');
        // Populate quick deploy fields
        $('qName').value = r.name || '';
        $('qTime').value = r.scheduled_start_time || '';
        $('qAlert').checked = r.send_start_alert !== false;
        $('qAnnounceToggle').checked = r.send_announcement !== false;
        $('qLead').value = r.start_alert_lead_time || 15;
        $('qAnnouncementText').value = r.description || r.readout_text || '';
        var sv = (r.shift || r.duty_cycle || '').toLowerCase();
        $('qShiftDay').checked = sv === 'day';
        $('qShiftNight').checked = sv === 'night';
        $('qShiftAny').checked = sv !== 'day' && sv !== 'night';
        clearTags('qGuardTags');
        (r.assigned_guards || []).forEach(function(gid) {
            var g = getPersonById(gid);
            if (g) addPersonTag('qGuardTags', gid, g.username);
        });
        $('qPointsList').innerHTML = '';
        (r.checkpoints || []).forEach(function(cp) { qAddPoint(cp.checkpoint_type || cp.type || 'nfc'); });
        var pointCards = $('qPointsList').querySelectorAll('.q-point-card');
        (r.checkpoints || []).forEach(function(cp, i) {
            if (!pointCards[i]) return;
            var nameInp = pointCards[i].querySelector('.q-name');
            if (nameInp) nameInp.value = cp.name || '';
            var tagInp = pointCards[i].querySelector('.q-tag');
            if (tagInp && cp.nfc_tag) tagInp.value = cp.nfc_tag;
            var latInp = pointCards[i].querySelector('.q-lat');
            if (latInp && cp.lat) latInp.value = cp.lat;
            var lngInp = pointCards[i].querySelector('.q-lng');
            if (lngInp && cp.lng) lngInp.value = cp.lng;
            var timeChip = pointCards[i].querySelector('.q-time');
            if (timeChip && cp.planned_time) { timeChip.value = cp.planned_time; timeChip.closest('.rs-cp-setting').classList.add('on'); }
            var tolInp = pointCards[i].querySelector('.q-gap');
            if (tolInp) tolInp.value = cp.time_tolerance ?? 15;
            var dwellInp = pointCards[i].querySelector('.q-dwell');
            if (dwellInp) dwellInp.value = cp.dwell_time ?? 0;
            var radInp = pointCards[i].querySelector('.q-radius');
            if (radInp) radInp.value = cp.radius ?? 50;
        });
        regSliderSyncAll();
        qdShowInlineConfirm();
    } catch (e) { toast('Failed to load route', true); }
};

/* ═══════════════════════════════════════════════════
   CREATE / CLOSE
═══════════════════════════════════════════════════ */
window.bpCreateNew = function () {
    if (bpDirty && !confirm('Discard unsaved changes?')) return;
    selId = null; bpDirty = false; assignedGuardIds = [];
    
    const today = new Date().toISOString().split('T')[0];
    if ($('bpDate')) $('bpDate').value = today;
    if ($('wiz2Date')) $('wiz2Date').value = today;
    if ($('auditDate')) $('auditDate').value = today;
    CalendarComponent.render();

    $('bpEdTitle').textContent = 'New Blueprint';
    $('bpLeadTime').value = 15;
    $('bpRepeatLabel').textContent = '15';
    bpUpdateAlertTime();
    $('bpIsDaily').checked = false; $('bpAnnounceToggle').checked = true;
    $('bpMissionBrief').value = '';
    wizStrategy = null;
    clearTags('bpGuardTags');
    bpClearCps(); bpSetLogic('Flexible'); setDispatch(false); 
    hideOverlay(); refreshRouteList();
    var reviewBtn = $('bpReviewBtn'); if (reviewBtn) reviewBtn.classList.add('rs-hidden');
};

window.bpCloseEditor = function () {
    if (bpDirty && !confirm('Discard unsaved changes?')) return;
    selId = null; bpDirty = false;
    hideOverlay(); $('bpEdTitle').textContent = 'Routes Dispatch';
    bpClearCps(); setDispatch(false); refreshRouteList();
};

function setDispatch(show) {
    $('bpDeployBtn')?.classList.toggle('rs-hidden', !show);
    $('bpDeployFooter')?.classList.toggle('rs-hidden', !show);
}

window.bpGoDispatch = () => window.location.href = '/dispatch/';

/* ═══════════════════════════════════════════════════
   SHIFT
══════════════════════════════════════════════════ */
window.bpHandleShift = function () {
    bpValidateShiftTime();
};

window.bpValidateShiftTime = function() {
    const timeInp = $('bpStartTime');
    if (!timeInp || !timeInp.value) return;
    
    const [h, m] = timeInp.value.split(':').map(Number);
    const shift = $('bpShiftDay')?.checked ? 'Day' : ($('bpShiftNight')?.checked ? 'Night' : 'Any');
    
    let isInvalid = false;
    let defaultTime = "";

    if (shift === 'Day') {
        // Day shift: 06:00 - 18:00
        if (h < 6 || h >= 18) { isInvalid = true; defaultTime = "08:00"; }
    } else if (shift === 'Night') {
        // Night shift: 18:00 - 06:00
        if (h >= 6 && h < 18) { isInvalid = true; defaultTime = "20:00"; }
    }
    
    if (isInvalid) {
        timeInp.value = defaultTime;
        timeInp.style.borderColor = 'var(--r-crim)';
        toast(`Time restricted to ${shift} hours`, true);
        setTimeout(() => { if(timeInp) timeInp.style.borderColor = ''; }, 2000);
    }
};

/* ═══════════════════════════════════════════════════
   LOGIC CHIPS
═══════════════════════════════════════════════════ */
/* NOTE: bpHandleShift is defined above (with shift-time validation).
   The earlier no-op duplicate that shadowed it has been removed so
   bpValidateShiftTime() actually runs when Day/Night is selected. */

/* ═══════════════════════════════════════════════════
   LOGIC CHIPS
═══════════════════════════════════════════════════ */
const LOGIC_CLS = { Flexible:'active-flex', Sequential:'active-seq', Scheduled:'active-sched', Audit:'active-audit', Custom:'active-custom' };

window.bpSetLogic = function (l) {
    logic = l;
    bpUpdateLogicUI();
    bpRefreshCps();
    bpUpdatePreview();
};

function bpUpdateLogicUI() {
    $$('.rs-logic-chip').forEach(c => c.classList.remove('active-flex','active-seq','active-sched','active-audit','active-custom'));
    $('bpChip-' + logic)?.classList.add(LOGIC_CLS[logic] || 'active-flex');

    const desc = $('rsLogicDesc');
    const textMap = {
        Flexible: "Checkpoints can be hit in any order. No time constraints. Best for general roaming.",
        Sequential: "Checkpoints must be scanned in the exact order listed. Path enforcement active.",
        Scheduled: "Checkpoints must be hit in order AND within specific time windows. Strict enforcement.",
        Audit: "Supervisors verify guards at their posts. Scans recorded against guard profiles.",
        Custom: "Manual enforcement rules. Configure sequence and time overrides below."
    };
    if (desc) desc.textContent = textMap[logic] || "Operational strategy active.";

    const peerBlock = $('bpPeerSweepBlock');
    if (peerBlock) {
        peerBlock.classList.toggle('rs-hidden', logic !== 'Audit');
    }
}

function isOrderEnforced() {
    return ['Sequential', 'Scheduled', 'Audit', 'Custom'].includes(logic);
}
function isTimeEnforced() {
    return ['Scheduled', 'Audit'].includes(logic);
}

/* ═══════════════════════════════════════════════════
   CHECKPOINTS (editor)
═══════════════════════════════════════════════════ */
function getCpData() {
    return Array.from($('bpCpList').querySelectorAll('.rs-cp-row')).map(r => ({
        name:           r.querySelector('.bp-cp-name')?.value || '',
        checkpoint_type: r.dataset.cpType || 'nfc',
        nfc_tag:        r.querySelector('.bp-cp-tag')?.value  || '',
        auditor_id:     r.querySelector('.bp-cp-auditor')?.value || '',
        target_id:      r.querySelector('.bp-cp-target')?.value || '',
        lat:            r.querySelector('.bp-cp-lat')?.value  || '',
        lng:            r.querySelector('.bp-cp-lng')?.value  || '',
        planned_time:   r.querySelector('.bp-cp-time')?.value || null,
        time_tolerance: parseInt(r.querySelector('.bp-cp-tol')?.value, 10) ?? 15,
        dwell_time:     parseInt(r.querySelector('.bp-cp-dwell')?.value, 10) ?? 0,
        radius:         parseInt(r.querySelector('.bp-cp-rad')?.value, 10) ?? 50,
        type:           r.dataset.cpType || 'nfc',
    }));
}

window.bpRefreshCps = function () {
    const data = getCpData();
    $('bpCpList').innerHTML = '';
    data.forEach(d => bpAddCp(d));
};

window.bpAddCp = async function (data = {}) {
    const list     = $('bpCpList');
    const idx      = list.children.length;
    const cpType   = data.checkpoint_type || data.type || 'nfc';
    const isGps    = cpType === 'gps' || (!data.nfc_tag && (data.lat || data.lng));
    const isPeer   = cpType === 'peer';
    const isCustom = cpType === 'custom';
    const finalType = isCustom ? 'custom' : (isPeer ? 'peer' : isGps ? 'gps' : 'nfc');

    // Fetch server-rendered checkpoint row
    try {
        const res = await fetch('/api/routes-checkpoint-form-partial/?type=' + finalType + '&order=' + idx);
        if (!res.ok) throw new Error('Failed to load checkpoint row');
        const html = await res.text();
        const div = document.createElement('div');
        div.innerHTML = html;
        const row = div.firstElementChild;

        // Set type and drag behavior
        row.dataset.cpType = finalType;
        row.addEventListener('dragstart', () => row.classList.add('dragging'));
        row.addEventListener('dragend',   () => { row.classList.remove('dragging'); bpRenumber(); });

        // Populate data
        if (data.name) row.querySelector('.bp-cp-name').value = data.name;
        if (data.nfc_tag) row.querySelector('.bp-cp-tag').value = data.nfc_tag;
        if (data.lat) row.querySelector('.bp-cp-lat').value = data.lat;
        if (data.lng) row.querySelector('.bp-cp-lng').value = data.lng;
        if (data.auditor_id) row.querySelector('.bp-cp-auditor').value = data.auditor_id;
        if (data.target_id) row.querySelector('.bp-cp-target').value = data.target_id;
        if (data.planned_time) row.querySelector('.bp-cp-time').value = data.planned_time;
        if (data.next_announcement_text) row.querySelector('.bp-cp-next-announce').value = data.next_announcement_text;
        if (data.fetch_location_on_scan) row.querySelector('.bp-cp-fetch-location').checked = true;

        // Set sliders
        const rad = data.radius || 50;
        const dwell = data.dwell_time || 0;
        const tol = data.time_tolerance ?? 15;
        const radSlider = row.querySelector('.bp-cp-rad');
        const dwellSlider = row.querySelector('.bp-cp-dwell');
        const tolSlider = row.querySelector('.bp-cp-tol');
        if (radSlider) radSlider.value = rad;
        if (dwellSlider) dwellSlider.value = dwell;
        if (tolSlider) tolSlider.value = tol;

        // Sync slider displays
        row.querySelectorAll('.rs-enf-slider').forEach(s => regSliderSync(s));

        // Wire dragover on list
        list.ondragover = e => {
            e.preventDefault();
            const drag = list.querySelector('.dragging');
            if (!drag) return;
            const sibs = [...list.querySelectorAll('.rs-cp-row:not(.dragging)')];
            const after = sibs.find(s => e.clientY < s.getBoundingClientRect().top + s.offsetHeight / 2);
            list.insertBefore(drag, after || null);
        };

        $('bpCpEmpty')?.classList.add('rs-hidden');
        list.appendChild(row);
        bpRenumber();
        bpDirty = true;
        bpUpdatePreview();
    } catch (e) {
        console.error('bpAddCp failed:', e);
        toast('Failed to add checkpoint', true);
    }
};

/* Legacy sync version for non-async callers (fallback) */
window.bpAddCpSync = function (data = {}) {
    const list     = $('bpCpList');
    const idx      = list.children.length;
    const cpType   = data.checkpoint_type || data.type || 'nfc';
    const isGps    = cpType === 'gps' || (!data.nfc_tag && (data.lat || data.lng));
    const isPeer   = cpType === 'peer';
    const isCustom = cpType === 'custom';

    const div = document.createElement('div');
    div.className = 'rs-cp-row';
    div.draggable = true;
    div.dataset.cpType = isCustom ? 'custom' : (isPeer ? 'peer' : isGps ? 'gps' : 'nfc');

    div.addEventListener('dragstart', () => div.classList.add('dragging'));
    div.addEventListener('dragend',   () => { div.classList.remove('dragging'); bpRenumber(); });

    const typeIcon = isCustom ? 'fa-pen' : (isPeer ? 'fa-user-shield' : isGps ? 'fa-map-pin' : 'fa-wifi');
    const typeCol  = isCustom ? 'var(--r-teal)' : (isPeer ? 'var(--r-violet)' : isGps ? 'var(--r-indigo)' : 'var(--r-crim)');
    const showOrder = isOrderEnforced();

    const rad  = data.radius || 50;
    const dwell = data.dwell_time || 0;
    const tol  = data.time_tolerance ?? 15;

    div.innerHTML = `
        <div class="rs-cp-grip" title="Drag to reorder"><i class="fas fa-grip-vertical"></i></div>
        <div class="rs-cp-badge">
            ${showOrder ? `<div class="rs-cp-num">${idx + 1}</div>` : ''}
            <div class="rs-cp-type-icon"><i class="fas ${typeIcon}" style="color:${typeCol}"></i></div>
        </div>
        <div style="flex:1; display:flex; flex-direction:column; gap:3px; min-width:0;">
            ${isPeer ? `
                <div style="display:flex; gap:4px;">
                    <div style="position:relative; flex:1;">
                        <input id="cp-auditor-${idx}" class="rs-fi rs-fi-sm bp-cp-auditor" style="font-size:0.62rem; padding:2px 6px;" placeholder="Auditor" value="${data.auditor_id || ''}"
                            oninput="bpTagInput(this);bpUpdatePreview()"
                            onkeydown="if(event.key==='Enter'){ const s=this.parentElement.querySelector('.rs-suggest-item'); if(s) s.click(); else this.blur(); }"
                            onblur="setTimeout(()=>this.parentElement.querySelector('.rs-suggest-list')?.classList.add('rs-hidden'),200)">
                        <div class="rs-suggest-list rs-hidden" style="top:24px;"></div>
                        <i class="fas fa-check-double rs-verified ${data.auditor_id ? '' : 'rs-hidden'}"></i>
                        <button type="button" class="rs-tag-clear ${data.auditor_id ? '' : 'rs-hidden'}" onclick="bpClearTagField(this)" title="Clear field"><i class="fas fa-times"></i></button>
                    </div>
                    <div style="opacity:0.15;display:flex;align-items:center;"><i class="fas fa-arrow-right-arrow-left" style="font-size:0.45rem;"></i></div>
                    <div style="position:relative; flex:1;">
                        <input id="cp-target-${idx}" class="rs-fi rs-fi-sm bp-cp-target" style="font-size:0.62rem; padding:2px 6px;" placeholder="Target" value="${data.target_id || data.nfc_tag || ''}"
                            oninput="bpTagInput(this);bpUpdatePreview()"
                            onkeydown="if(event.key==='Enter'){ const s=this.parentElement.querySelector('.rs-suggest-item'); if(s) s.click(); else this.blur(); }"
                            onblur="setTimeout(()=>this.parentElement.querySelector('.rs-suggest-list')?.classList.add('rs-hidden'),200)">
                        <div class="rs-suggest-list rs-hidden" style="top:24px;"></div>
                        <i class="fas fa-check-double rs-verified ${(data.target_id || data.nfc_tag) ? '' : 'rs-hidden'}"></i>
                        <button type="button" class="rs-tag-clear ${(data.target_id || data.nfc_tag) ? '' : 'rs-hidden'}" onclick="bpClearTagField(this)" title="Clear field"><i class="fas fa-times"></i></button>
                    </div>
                </div>
            ` : `
                <div style="display:flex; align-items:center; gap:3px; min-width:0;">
                    <div class="bp-cp-name-wrap" style="position:relative; min-width:80px; flex:1;">
                        <input id="cp-name-${idx}" class="rs-fi rs-fi-sm bp-cp-name" style="font-size:0.82rem; padding:2px 6px;" placeholder="Point name" value="${data.name || ''}"
                            oninput="bpNameInput(this);bpUpdatePreview()"
                            onblur="setTimeout(()=>this.parentElement.querySelector('.rs-suggest-list')?.classList.add('rs-hidden'),200)">
                        <div class="rs-suggest-list rs-hidden" style="top:24px;"></div>
                        <i class="fas fa-check-double rs-verified rs-hidden"></i>
                    </div>
                    ${isGps || isCustom ? `
                        <input id="cp-lat-${idx}" type="number" step="any" class="rs-fi rs-fi-sm bp-cp-lat" style="width:48px; font-size:0.55rem; padding:2px 3px;" placeholder="Lat" value="${data.lat || ''}" oninput="bpUpdatePreview()">
                        <input id="cp-lng-${idx}" type="number" step="any" class="rs-fi rs-fi-sm bp-cp-lng" style="width:48px; font-size:0.55rem; padding:2px 3px;" placeholder="Lng" value="${data.lng || ''}" oninput="bpUpdatePreview()">
                    ` : `
                        <div class="bp-cp-tag-wrap" style="position:relative; width:90px;">
                            <input id="cp-tag-${idx}" class="rs-fi rs-fi-sm bp-cp-tag" style="font-size:0.55rem; padding:2px 5px 2px 3px; letter-spacing:.2px; font-family:monospace;" placeholder="NFC ID" value="${data.nfc_tag || ''}"
                                oninput="bpTagInput(this);bpUpdatePreview()"
                                onkeydown="if(event.key==='Enter'){ const s=this.parentElement.querySelector('.rs-suggest-item'); if(s) s.click(); else this.blur(); }"
                                onblur="setTimeout(()=>this.parentElement.querySelector('.rs-suggest-list')?.classList.add('rs-hidden'),200)">
                            <div class="rs-suggest-list rs-hidden" style="top:24px;"></div>
                            <i class="fas fa-check-double rs-verified ${data.nfc_tag ? '' : 'rs-hidden'}"></i>
                            <button type="button" class="rs-tag-clear ${data.nfc_tag ? '' : 'rs-hidden'}" onclick="bpClearTagField(this)" title="Clear value"><i class="fas fa-times"></i></button>
                        </div>
                        <label class="rs-cp-fetch-gps" data-fetched="${data.lat ? 'true' : 'false'}" title="Capture GPS on first tag scan">
                            <input type="checkbox" class="bp-cp-fetch-location" ${data.fetch_location_on_scan ? 'checked' : ''} onchange="bpToggleFetchGps(this)">
                            <i class="fas fa-satellite"></i> GPS
                        </label>
                        <span class="rs-cp-fetch-status" style="display:${data.lat ? 'inline-flex' : 'none'};font-size:0.4rem;color:var(--r-teal);gap:2px;align-items:center;"><i class="fas fa-check-circle"></i> ${data.lat ? parseFloat(data.lat).toFixed(4)+', '+parseFloat(data.lng).toFixed(4) : ''}</span>
                        <input type="hidden" class="bp-cp-lat" value="${data.lat || ''}">
                        <input type="hidden" class="bp-cp-lng" value="${data.lng || ''}">
                    `}
                </div>
            `}
            <div class="rs-cp-summary">
                <span class="rs-cp-summary-pill rad"><i class="fas fa-bullseye"></i> ${rad}<small>m</small></span>
                <span class="rs-cp-summary-pill dwell"><i class="fas fa-person-walking"></i> ${dwell}<small>min</small></span>
                <span class="rs-cp-summary-pill tol"><i class="fas fa-hourglass-start"></i> ${tol}<small>min</small></span>
            </div>
            <div class="rs-cp-sticky-settings" style="display:flex;gap:3px;margin:2px 0;">
                <div class="rs-cp-setting ${data.planned_time ? 'on' : ''}" onclick="rsToggleProp(event,this)" for="cp-time-${idx}">
                    <i class="fas fa-alarm-clock"></i>
                    <input type="time" id="cp-time-${idx}" class="si bp-cp-time" value="${data.planned_time || ''}" onchange="bpValidateCpTime(this)">
                    <span class="sl">time</span>
                </div>
                <div class="rs-cp-setting rs-cp-tts-set ${data.next_announcement_text ? 'on' : ''}" onclick="rsToggleProp(event,this)" for="cp-next-announce-${idx}">
                    <i class="fas fa-bullhorn"></i>
                    <input type="text" id="cp-next-announce-${idx}" class="si bp-cp-next-announce" value="${data.next_announcement_text || ''}" placeholder="Next TTS…">
                    <span class="sl">tts</span>
                </div>
            </div>
            <div class="rs-cp-config" style="overflow:hidden;max-height:0;transition:max-height .25s ease;">
                <div class="rs-enf-row">
                    <div class="rs-enf-card">
                        <div class="rs-enf-head">
                            <div class="rs-enf-icon" style="background:rgba(211,47,47,0.12);color:#d32f2f;"><i class="fas fa-bullseye"></i></div>
                            <div class="rs-enf-info"><div class="rs-enf-lbl">Radius</div><div class="rs-enf-desc">Perimeter</div></div>
                            <div class="rs-enf-val cp-rad-val">${rad}<small>m</small></div>
                        </div>
                        <div class="rs-enf-body">
                            <input type="range" class="rs-enf-slider bp-cp-rad" min="0" max="500" value="${rad}" step="5" oninput="regSliderSync(this)">
                            <div class="rs-enf-presets"><div class="rs-enf-preset" data-v="0">Off</div><div class="rs-enf-preset" data-v="25">25</div><div class="rs-enf-preset" data-v="50">50</div><div class="rs-enf-preset" data-v="100">100</div><div class="rs-enf-preset" data-v="250">250</div></div>
                        </div>
                    </div>
                    <div class="rs-enf-card">
                        <div class="rs-enf-head">
                            <div class="rs-enf-icon" style="background:rgba(239,159,39,0.12);color:#EF9F27;"><i class="fas fa-person-walking"></i></div>
                            <div class="rs-enf-info"><div class="rs-enf-lbl">Dwell</div><div class="rs-enf-desc">Minimum stay</div></div>
                            <div class="rs-enf-val cp-dwell-val">${dwell}<small>min</small></div>
                        </div>
                        <div class="rs-enf-body">
                            <input type="range" class="rs-enf-slider bp-cp-dwell" min="0" max="60" value="${dwell}" step="1" oninput="regSliderSync(this)">
                            <div class="rs-enf-presets"><div class="rs-enf-preset" data-v="0">Off</div><div class="rs-enf-preset" data-v="5">5</div><div class="rs-enf-preset" data-v="10">10</div><div class="rs-enf-preset" data-v="30">30</div><div class="rs-enf-preset" data-v="60">60</div></div>
                        </div>
                    </div>
                    <div class="rs-enf-card">
                        <div class="rs-enf-head">
                            <div class="rs-enf-icon" style="background:rgba(108,142,239,0.12);color:#6C8EEF;"><i class="fas fa-hourglass-start"></i></div>
                            <div class="rs-enf-info"><div class="rs-enf-lbl">Tolerance</div><div class="rs-enf-desc">Grace window</div></div>
                            <div class="rs-enf-val cp-tol-val">${tol}<small>min</small></div>
                        </div>
                        <div class="rs-enf-body">
                            <input type="range" class="rs-enf-slider bp-cp-tol" min="0" max="60" value="${tol}" step="1" oninput="regSliderSync(this)">
                            <div class="rs-enf-presets"><div class="rs-enf-preset" data-v="0">Off</div><div class="rs-enf-preset" data-v="5">5</div><div class="rs-enf-preset" data-v="15">15</div><div class="rs-enf-preset" data-v="30">30</div><div class="rs-enf-preset" data-v="60">60</div></div>
                        </div>
                    </div>
                </div>
            </div>
            <div id="cp-time-warn-${idx}" class="rs-hidden" style="font-size:0.45rem;color:var(--r-amber);display:flex;align-items:center;gap:3px;padding:1px 4px;"><i class="fas fa-triangle-exclamation"></i> <span></span></div>
        </div>
        <div class="rs-cp-actions" style="align-items:stretch;">
            <button type="button" class="rs-cp-settings-toggle" title="Settings" onclick="bpToggleCpConfig(this)" style="border:none;background:none;color:var(--r-mute);cursor:pointer;padding:2px 4px;border-radius:4px;font-size:0.6rem;transition:color .15s;" onmouseenter="this.style.color='var(--r-teal)'" onmouseleave="this.style.color='var(--r-mute)'"><i class="fas fa-sliders"></i></button>
            <button type="button" class="rs-cp-del" title="Remove checkpoint" onclick="this.closest('.rs-cp-row').remove();bpRenumber();bpSetDirty();"><i class="fas fa-times"></i></button>
            ${isPeer ? '' : `<button type="button" class="rs-cp-save" title="Save to library" onclick="bpLibrarySaveRow(this.closest('.rs-cp-row'))"><i class="fas fa-floppy-disk"></i></button>`}
        </div>
    `;

    list.ondragover = e => {
        e.preventDefault();
        const drag = list.querySelector('.dragging');
        if (!drag) return;
        const sibs = [...list.querySelectorAll('.rs-cp-row:not(.dragging)')];
        const after = sibs.find(s => e.clientY < s.getBoundingClientRect().top + s.offsetHeight / 2);
        list.insertBefore(drag, after || null);
    };

    // Initialize sliders
    div.querySelectorAll('.rs-enf-slider').forEach(s => regSliderSync(s));

    $('bpCpEmpty')?.classList.add('rs-hidden');
    list.appendChild(div);
    bpRenumber();
    bpDirty = true;
    bpUpdatePreview();
};

window.bpClearCps  = () => {
    $('bpCpList').innerHTML = '';
    $('bpCpEmpty')?.classList.remove('rs-hidden');
    bpUpdatePreview();
};
window.bpRenumber  = () => { $$('.rs-cp-num').forEach((el, i) => el.textContent = i + 1); bpUpdatePreview(); };

/* ── Toggle checkpoint config panel ── */
window.bpToggleCpConfig = function(btn) {
    const row = btn.closest('.rs-cp-row');
    const cfg = row.querySelector('.rs-cp-config');
    const sum = row.querySelector('.rs-cp-summary');
    if (!cfg) return;
    const isOpen = cfg.style.maxHeight !== '0px' && cfg.style.maxHeight !== '';
    if (isOpen) {
        cfg.style.maxHeight = '0px';
        if (sum) sum.style.display = '';
        btn.innerHTML = '<i class="fas fa-sliders"></i>';
        btn.title = 'Settings';
    } else {
        cfg.style.maxHeight = cfg.scrollHeight + 40 + 'px';
        if (sum) sum.style.display = 'none';
        btn.innerHTML = '<i class="fas fa-chevron-up"></i>';
        btn.title = 'Collapse';
    }
};

/* ── Fetch GPS on NFC scan ── */
window.bpToggleFetchGps = async function(cb) {
    const label = cb.closest('.rs-cp-fetch-gps');
    const row = cb.closest('.rs-cp-row');
    if (!cb.checked) {
        label.dataset.fetched = 'false';
        const status = row.querySelector('.rs-cp-fetch-status');
        if (status) { status.style.display = 'none'; }
        return;
    }
    if (label.dataset.fetched === 'true') return;
    if (!navigator.geolocation) { toast('Geolocation not available', true); cb.checked = false; return; }
    try {
        const pos = await new Promise((res, rej) => navigator.geolocation.getCurrentPosition(res, rej, { timeout: 10000 }));
        const lat = pos.coords.latitude.toFixed(6);
        const lng = pos.coords.longitude.toFixed(6);
        const latInp = row.querySelector('.bp-cp-lat');
        const lngInp = row.querySelector('.bp-cp-lng');
        if (latInp) latInp.value = lat;
        if (lngInp) lngInp.value = lng;
        label.dataset.fetched = 'true';
        const status = row.querySelector('.rs-cp-fetch-status');
        if (status) { status.style.display = 'inline-flex'; status.textContent = lat + ', ' + lng; }
        toast('GPS captured: ' + lat + ', ' + lng);
    } catch (e) {
        toast('GPS fetch failed: ' + e.message, true);
        cb.checked = false;
    }
};

/* ── Validate checkpoint time vs blueprint time ── */
window.bpValidateCpTime = function(inp) {
    const warn = inp.closest('.rs-cp-row')?.querySelector('[id^="cp-time-warn-"]');
    if (!inp.value || !warn) { if (warn) warn.classList.add('rs-hidden'); return; }
    const bpTime = $('bpStartTime')?.value;
    if (!bpTime) { warn.classList.add('rs-hidden'); return; }
    const cpMin = inp.value.split(':').reduce((a,b) => +a*60+ +b, 0);
    const bpMin = bpTime.split(':').reduce((a,b) => +a*60+ +b, 0);
    if (cpMin < bpMin) {
        warn.querySelector('span').textContent = `Before blueprint start (${bpTime})`;
        warn.classList.remove('rs-hidden');
    } else {
        warn.classList.add('rs-hidden');
    }
};

/* ── Sync enf-slider display ── */
window.regSliderSync = function(slider) {
    const val = parseInt(slider.value) || 0;
    const card = slider.closest('.rs-enf-card');
    if (!card) return;
    const valEl = card.querySelector('.rs-enf-val');
    if (valEl) {
        const unit = valEl.classList.contains('cp-tol-val') || valEl.classList.contains('cp-dwell-val') ? 'min' : 'm';
        valEl.innerHTML = val + '<small>' + unit + '</small>';
        valEl.style.color = val > 0 ? '#fff' : 'rgba(255,255,255,0.12)';
    }
    card.querySelectorAll('.rs-enf-preset').forEach(p => {
        p.classList.toggle('active', parseInt(p.dataset.v) === val);
    });
    card.style.borderColor = val > 0 ? 'rgba(255,255,255,0.12)' : 'var(--border)';
    const row = slider.closest('.rs-cp-row');
    if (row) {
        const cls = slider.classList.contains('bp-cp-rad') ? 'rad' : slider.classList.contains('bp-cp-dwell') ? 'dwell' : 'tol';
        const pill = row.querySelector('.rs-cp-summary-pill.' + cls);
        if (pill) {
            const unit = cls === 'rad' ? 'm' : 'min';
            pill.innerHTML = '<i class="fas ' + (cls==='rad'?'fa-bullseye':cls==='dwell'?'fa-person-walking':'fa-hourglass-start') + '"></i> ' + val + '<small>' + unit + '</small>';
        }
    }
    bpUpdatePreview();
};

window.regSliderSyncAll = function() {
    document.querySelectorAll('.rs-enf-slider').forEach(function(s) { regSliderSync(s); });
};

// Delegate enf-preset clicks
document.addEventListener('click', function(e) {
    const preset = e.target.closest('.rs-enf-preset');
    if (!preset) return;
    const card = preset.closest('.rs-enf-card');
    if (!card) return;
    const slider = card.querySelector('.rs-enf-slider');
    if (!slider) return;
    slider.value = parseInt(preset.dataset.v) || 0;
    regSliderSync(slider);
});

window.rsToggleProp = function (e, chip) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    const was = chip.classList.contains('on');
    chip.classList.toggle('on');
    chip.querySelectorAll('.su').forEach(u => u.classList.toggle('rs-hidden', was));
    bpUpdatePreview(); bpSetDirty();
};

/* ═══════════════════════════════════════════════════
   NAME LOOKUP (autocomplete per row)
═══════════════════════════════════════════════════ */
window.bpNameInput = function (el) {
    const val = el.value.trim().toLowerCase();
    const row = el.closest('.rs-cp-row') || el.closest('.q-point-card');
    if (!row) return;
    const suggest = row.querySelector('.rs-suggest-list');
    const verify  = row.querySelector('.rs-verified');
    if (!val) { suggest?.classList.add('rs-hidden'); verify?.classList.add('rs-hidden'); return; }

    const aM = allAssets.filter(a  => (a.name || '').toLowerCase().includes(val)).slice(0, 5);
    const pM = allPersonnel.filter(p => ((p.username || '') + (p.callsign || '')).toLowerCase().includes(val)).slice(0, 4);

    if (!aM.length && !pM.length) { suggest?.classList.add('rs-hidden'); return; }

    let html = aM.map(a => `
        <div class="rs-suggest-item" onclick="bpPickAssetForRow('${a.id}','asset',this)">
            <span><i class="fas ${a.type === 'geofence' ? 'fa-draw-polygon' : 'fa-location-dot'}"></i> ${a.name}</span>
            <span style="opacity:.5;font-size:.6rem;text-transform:uppercase;">${a.type}</span>
        </div>`).join('');
    html += pM.map(p => `
        <div class="rs-suggest-item" onclick="bpPickAssetForRow('${p.id}','person',this)">
            <span><i class="fas fa-user-shield"></i> ${p.username}</span>
            <span style="opacity:.5;font-size:.6rem;text-transform:uppercase;">officer</span>
        </div>`).join('');

    if (suggest) { suggest.innerHTML = html; suggest.classList.remove('rs-hidden'); }
    const exact = allAssets.some(a => (a.name || '').toLowerCase() === val) || allPersonnel.some(p => (p.username || '').toLowerCase() === val);
    verify?.classList.toggle('rs-hidden', !exact);
};

window.bpPickAssetForRow = function (id, type, itemEl) {
    const row = itemEl.closest('.rs-cp-row') || itemEl.closest('.q-point-card');
    if (!row) return;
    const nameInp = row.querySelector('.bp-cp-name') || row.querySelector('.q-name');
    const tagInp  = row.querySelector('.bp-cp-tag')  || row.querySelector('.q-tag');
    const latInp  = row.querySelector('.bp-cp-lat')  || row.querySelector('.q-lat');
    const lngInp  = row.querySelector('.bp-cp-lng')  || row.querySelector('.q-lng');
    const radInp  = row.querySelector('.bp-cp-rad')  || row.querySelector('.q-radius');

    const activateChip = inp => { const ch = inp?.closest('.rs-cp-setting'); if (ch) ch.classList.add('on'); };

    if (type === 'asset') {
        const a = allAssets.find(x => String(x.id) === String(id));
        if (!a) return;
        if (nameInp) nameInp.value = a.name || '';
        if (tagInp && a.nfc_tag) tagInp.value = a.nfc_tag;
        if (latInp && lngInp && Array.isArray(a.geometry) && a.geometry.length === 2) {
            latInp.value = a.geometry[0]; lngInp.value = a.geometry[1];
        }
        if (radInp && a.radius) { radInp.value = a.radius; activateChip(radInp); }
    } else {
        const p = allPersonnel.find(x => String(x.id) === String(id));
        if (!p) return;
        if (nameInp) nameInp.value = p.username;
        if (tagInp)  tagInp.value  = p.callsign || '';
    }
    row.querySelector('.rs-suggest-list')?.classList.add('rs-hidden');
    row.querySelector('.rs-verified')?.classList.remove('rs-hidden');
    bpUpdatePreview(); bpSetDirty();
};

window.bpTagInput = function (el) {
    const val = el.value.trim().toLowerCase();
    const container = el.parentElement;
    const suggest = container.querySelector('.rs-suggest-list');
    const verify  = container.querySelector('.rs-verified');
    const clear   = container.querySelector('.rs-tag-clear');
    
    if (!val) { suggest?.classList.add('rs-hidden'); verify?.classList.add('rs-hidden'); clear?.classList.add('rs-hidden'); return; }
    clear?.classList.remove('rs-hidden');

    // Immediate Auto-Resolve Check
    const exactMatch = allAssets.find(a => (a.nfc_tag || '').toLowerCase() === val);
    if (exactMatch) {
        const row = el.closest('.rs-cp-row') || el.closest('.q-point-card');
        if (row) {
            const nameInp = row.querySelector('.bp-cp-name') || row.querySelector('.q-name');
            if (nameInp && !nameInp.value.trim()) {
                nameInp.value = exactMatch.name;
                toast(`Resolved point name: ${exactMatch.name}`);
            }
            // For Peer Audit mode, if tag matches a target, label it as "Peer Verification"
            if (row.dataset.cpType === 'peer' && !exactMatch.name) el.value = exactMatch.callsign || el.value;
        }
        if(verify) verify.classList.remove('rs-hidden');
    }

    const pM = allPersonnel.filter(p => ((p.callsign || '') + (p.username || '')).toLowerCase().includes(val)).slice(0, 5);
    const aM = allAssets.filter(a => (a.nfc_tag || '').toLowerCase().includes(val)).slice(0, 5);

    if (!pM.length && !aM.length) { suggest?.classList.add('rs-hidden'); return; }

    let html = pM.map(p => `<div class="rs-suggest-item" onclick="bpPickTagForRow('${p.callsign || p.username}', this)"><span><i class="fas fa-user-shield"></i> ${p.callsign || p.username}</span><span style="opacity:.5;font-size:.6rem;text-transform:uppercase;">CALLSIGN</span></div>`).join('');
    html += aM.map(a => `<div class="rs-suggest-item" onclick="bpPickTagForRow('${a.nfc_tag}', this, '${a.name}')"><span><i class="fas fa-wifi"></i> ${a.nfc_tag} <small style="opacity:0.6; margin-left:4px;">(${a.name})</small></span><span style="opacity:.5;font-size:.6rem;text-transform:uppercase;">POI</span></div>`).join('');

    if (suggest) { suggest.innerHTML = html; suggest.classList.remove('rs-hidden'); }
    const exact = allPersonnel.some(p => (p.callsign || p.username).toLowerCase() === val) || allAssets.some(a => (a.nfc_tag || '').toLowerCase() === val);
    verify?.classList.toggle('rs-hidden', !exact);
};

window.bpPickTagForRow = function (tag, itemEl, nameHint) {
    const container = itemEl.parentElement.parentElement;
    const inp = container.querySelector('input');
    if (inp) inp.value = tag;

    const row = itemEl.closest('.rs-cp-row') || itemEl.closest('.q-point-card');
    if (row && nameHint) {
        const nameInp = row.querySelector('.bp-cp-name') || row.querySelector('.q-name');
        if (nameInp && !nameInp.value.trim()) {
            nameInp.value = nameHint;
        }
    }

    container.querySelector('.rs-suggest-list')?.classList.add('rs-hidden');
    container.querySelector('.rs-verified')?.classList.remove('rs-hidden');
    container.querySelector('.rs-tag-clear')?.classList.remove('rs-hidden');
    bpUpdatePreview(); bpSetDirty();
};

window.bpClearTagField = function (btn) {
    const container = btn.parentElement;
    const inp = container.querySelector('input');
    if (inp) inp.value = '';
    btn.classList.add('rs-hidden');
    container.querySelector('.rs-verified')?.classList.add('rs-hidden');
    bpUpdatePreview(); bpSetDirty();
};

/* Global asset search (above cp list) */
window.bpAssetInput = function (val) {
    const list = $('bpAssetSuggest');
    if (!val) { list.classList.add('rs-hidden'); return; }
    const m = allAssets.filter(a => (a.name || '').toLowerCase().includes(val.toLowerCase()));
    if (!m.length) { list.classList.add('rs-hidden'); return; }
    list.innerHTML = m.map(a => `
        <div class="rs-suggest-item" onclick="bpPickAsset(${a.id})">
            <span><i class="fas ${a.type === 'geofence' ? 'fa-draw-polygon' : 'fa-location-dot'}"></i> ${a.name}</span>
            <span style="opacity:.5;font-size:.6rem;text-transform:uppercase;">${a.type}</span>
        </div>`).join('');
    list.classList.remove('rs-hidden');
};

window.bpPickAsset = function (id) {
    const a = allAssets.find(x => x.id === id);
    if (!a) return;
    const isPoint = Array.isArray(a.geometry) && a.geometry.length === 2;
    bpAddCp({ name: a.name, lat: isPoint ? a.geometry[0] : null, lng: isPoint ? a.geometry[1] : null, radius: a.radius || 50, type: isPoint ? 'gps' : 'nfc' });
    $('bpAssetSearch').value = '';
    $('bpAssetSuggest').classList.add('rs-hidden');
};

/* Save to library */
window.bpLibrarySaveRow = async function (rowEl) {
    const name = rowEl.querySelector('.bp-cp-name')?.value;
    const tag  = rowEl.querySelector('.bp-cp-tag')?.value;
    const lat  = rowEl.querySelector('.bp-cp-lat')?.value;
    const lng  = rowEl.querySelector('.bp-cp-lng')?.value;
    const rad  = rowEl.querySelector('.bp-cp-rad')?.value || 50;
    if (!name) { toast('Name required to save to library', true); return; }
    try {
        const res = await api('/api/map-objects/', { method: 'POST', body: JSON.stringify({
            name, type: 'poi', nfc_tag: tag,
            geometry: (lat && lng) ? [parseFloat(lat), parseFloat(lng)] : null,
            radius: parseInt(rad, 10), assigned_personnel: []
        })});
        if (res.ok) { const s = await res.json(); allAssets.push(s); rowEl.querySelector('.rs-verified')?.classList.remove('rs-hidden'); toast(`${name} saved to library`); }
        else toast('Library save failed', true);
    } catch (e) { toast('Network error', true); }
};

/* ═══════════════════════════════════════════════════
   REMOVE / UNTAG
═══════════════════════════════════════════════════ */
window.bpUntagGuard = function (id) {
    assignedGuardIds = assignedGuardIds.filter(x => x !== id);
    Array.from($('bpGuardTags')?.querySelectorAll('.rs-person-tag') || [])
        .filter(t => String(t.dataset.pid) === String(id)).forEach(t => t.remove());
    bpUpdatePreview();
};

window.bpRemoveCpAt = function (idx) {
    const rows = $('bpCpList').querySelectorAll('.rs-cp-row');
    if (rows[idx]) { rows[idx].remove(); bpRenumber(); bpUpdatePreview(); }
};

/* ═══════════════════════════════════════════════════
   WIZARD STEP 2 — Standard
═══════════════════════════════════════════════════ */
function wiz2BuildCps() {
    const labels  = getTaggedLabels('wiz2GuardTags');
    const repeat  = Math.max(1, parseInt($('wiz2Repeat').value || '3', 10));
    const start   = $('wiz2StartTime').value;
    const interval = parseInt($('wiz2Interval')?.value || '15', 10);
    const dwell   = parseInt($('wiz2Stay')?.value || '0', 10);

    bpClearCps();
    bpSetLogic(wizStrategy);

    for (let i = 0; i < repeat; i++) {
        let pt = null;
        if (wizStrategy === 'Scheduled' && start) {
            const [h, m] = start.split(':').map(Number);
            const tot = (h * 60) + m + (i * interval);
            pt = `${String(Math.floor(tot / 60) % 24).padStart(2,'0')}:${String(tot % 60).padStart(2,'0')}`;
        }
        bpAddCp({
            name:       `${wizStrategy} Point ${i + 1}${labels.length ? ' [' + labels.join(', ') + ']' : ''}`,
            nfc_tag:    '',
            planned_time: pt,
            dwell_time: dwell,
        });
    }
}

function wiz2SyncFields() {
    const name = $('wiz2Name').value.trim();
    if (!name) { toast('Blueprint name required', true); return false; }
    $('bpRouteName').value    = name;
    $('bpDate').value         = $('wiz2Date')?.value || '';
    $('bpStartTime').value    = $('wiz2StartTime').value;
    $('bpLeadTime').value     = 15;
    bpUpdateAlertTime();
    $('bpSendAlert').checked  = $('wiz2Alert').checked;
    $('bpIsDaily').checked    = false;
    $('bpMissionBrief').value = ""; 
    if ($('wiz2ShiftDay').checked)   { $('bpShiftDay').checked = true; }
    else if ($('wiz2ShiftNight').checked) { $('bpShiftNight').checked = true; }
    else { $('bpShiftAny').checked = true; }
    // Copy guard tags
    clearTags('bpGuardTags'); assignedGuardIds = [];
    Array.from($('wiz2GuardTags')?.querySelectorAll('.rs-person-tag') || []).forEach(t => {
        addPersonTag('bpGuardTags', t.dataset.pid, t.dataset.label, t.dataset.type);
    });

    return true;
}

window.wiz2Apply = function () {
    if (!wiz2SyncFields()) return;
    wiz2BuildCps();
    hideOverlay(); setDispatch(false);
    $('bpEdTitle').textContent = 'New Blueprint';
    bpUpdatePreview();
    toast(`${wizStrategy} blueprint ready — save when done.`);
};

window.wiz2SaveDeploy = function () {
    if (!wiz2SyncFields()) return;
    wiz2BuildCps();
    rsDeployOpen();
};

/* ═══════════════════════════════════════════════════
   QUICK DEPLOY
═══════════════════════════════════════════════════ */
window.qAddPoint = function (type) {
    const list = $('qPointsList');
    $('qPointsEmpty')?.remove();
    const idx = list.querySelectorAll('.q-point-card').length;
    const icons = { nfc: 'fa-wifi', gps: 'fa-map-pin', peer: 'fa-user-shield', custom: 'fa-pen' };
    const cols  = { nfc: 'var(--r-crim)', gps: 'var(--r-indigo)', peer: 'var(--r-violet)', custom: 'var(--r-teal)' };
    const names = { nfc: 'NFC', gps: 'GPS', peer: 'Peer', custom: 'Custom' };

    const div = document.createElement('div');
    div.className = 'rs-cp-row q-point-card';
    div.dataset.type = type;
    div.style.marginBottom = '4px';

    div.innerHTML = `
        <div class="rs-cp-grip" title="Drag to reorder"><i class="fas fa-grip-vertical"></i></div>
        <div class="rs-cp-badge">
            <div class="rs-cp-type-icon"><i class="fas ${icons[type]}" style="color:${cols[type]}"></i></div>
        </div>
        <div style="flex:1;display:flex;flex-direction:column;gap:3px;">
            <div class="rs-cp-top-row">
                ${type === 'gps' || type === 'custom' ? `
                    <div style="position:relative; flex:1;">
                        <input class="rs-fi rs-fi-sm q-name" style="width:100%; font-size:0.62rem; padding:3px 6px;" placeholder="Point name" oninput="bpNameInput(this)">
                        <div class="rs-suggest-list rs-hidden" style="top:26px;left:0;right:0;"></div>
                    </div>
                    <div style="display:flex; gap:2px; align-items:center;">
                        <span style="font-size:0.42rem; color:var(--r-mute); font-weight:700;">LAT</span>
                        <input class="rs-fi rs-fi-sm q-lat" style="width:48px; font-size:0.6rem; padding:3px 4px;" placeholder="0.00">
                    </div>
                    <div style="display:flex; gap:2px; align-items:center;">
                        <span style="font-size:0.42rem; color:var(--r-mute); font-weight:700;">LNG</span>
                        <input class="rs-fi rs-fi-sm q-lng" style="width:48px; font-size:0.6rem; padding:3px 4px;" placeholder="0.00">
                    </div>
                ` : `
                    <div style="position:relative; flex:1;">
                        <input class="rs-fi rs-fi-sm q-name" style="width:100%; font-size:0.62rem; padding:3px 6px;" placeholder="Point name" oninput="bpNameInput(this)">
                        <div class="rs-suggest-list rs-hidden" style="top:26px;left:0;right:0;"></div>
                    </div>
                    <input class="rs-fi rs-fi-sm q-tag" style="width:95px; font-size:0.6rem; padding:3px 6px; font-family:monospace;" placeholder="NFC ID">
                `}
            </div>
            <div class="rs-enf-row" style="max-width:100%;">
                <div class="rs-enf-card" style="min-width:70px;">
                    <div class="rs-enf-head" style="padding:3px 5px;">
                        <div class="rs-enf-icon" style="width:18px;height:18px;border-radius:4px;background:rgba(108,142,239,0.12);color:#6C8EEF;font-size:0.42rem;"><i class="fas fa-hourglass-start"></i></div>
                        <div class="rs-enf-info"><div class="rs-enf-lbl" style="font-size:0.42rem;">Gap</div></div>
                        <div class="rs-enf-val cp-tol-val" style="font-size:0.65rem;">15<small>min</small></div>
                    </div>
                    <div class="rs-enf-body" style="padding:0 5px 3px;">
                        <input type="range" class="rs-enf-slider q-gap" min="0" max="60" value="15" step="1" oninput="regSliderSync(this)">
                        <div class="rs-enf-presets"><div class="rs-enf-preset" data-v="0">Off</div><div class="rs-enf-preset" data-v="5">5</div><div class="rs-enf-preset" data-v="15">15</div><div class="rs-enf-preset" data-v="30">30</div><div class="rs-enf-preset" data-v="60">60</div></div>
                    </div>
                </div>
                <div class="rs-enf-card" style="min-width:60px;">
                    <div class="rs-enf-head" style="padding:3px 5px;">
                        <div class="rs-enf-icon" style="width:18px;height:18px;border-radius:4px;background:rgba(239,159,39,0.12);color:#EF9F27;font-size:0.42rem;"><i class="fas fa-person-walking"></i></div>
                        <div class="rs-enf-info"><div class="rs-enf-lbl" style="font-size:0.42rem;">Dwell</div></div>
                        <div class="rs-enf-val cp-dwell-val" style="font-size:0.65rem;">5<small>min</small></div>
                    </div>
                    <div class="rs-enf-body" style="padding:0 5px 3px;">
                        <input type="range" class="rs-enf-slider q-dwell" min="0" max="60" value="5" step="1" oninput="regSliderSync(this)">
                        <div class="rs-enf-presets"><div class="rs-enf-preset" data-v="0">Off</div><div class="rs-enf-preset" data-v="5">5</div><div class="rs-enf-preset" data-v="10">10</div><div class="rs-enf-preset" data-v="30">30</div><div class="rs-enf-preset" data-v="60">60</div></div>
                    </div>
                </div>
                <div class="rs-enf-card" style="min-width:60px;">
                    <div class="rs-enf-head" style="padding:3px 5px;">
                        <div class="rs-enf-icon" style="width:18px;height:18px;border-radius:4px;background:rgba(211,47,47,0.12);color:#d32f2f;font-size:0.42rem;"><i class="fas fa-bullseye"></i></div>
                        <div class="rs-enf-info"><div class="rs-enf-lbl" style="font-size:0.42rem;">Radius</div></div>
                        <div class="rs-enf-val cp-rad-val" style="font-size:0.65rem;">50<small>m</small></div>
                    </div>
                    <div class="rs-enf-body" style="padding:0 5px 3px;">
                        <input type="range" class="rs-enf-slider q-radius" min="0" max="500" value="50" step="5" oninput="regSliderSync(this)">
                        <div class="rs-enf-presets"><div class="rs-enf-preset" data-v="0">Off</div><div class="rs-enf-preset" data-v="25">25</div><div class="rs-enf-preset" data-v="50">50</div><div class="rs-enf-preset" data-v="100">100</div><div class="rs-enf-preset" data-v="250">250</div></div>
                    </div>
                </div>
            </div>
            <div class="rs-cp-settings" style="margin-top:2px;">
                <div class="rs-cp-setting" onclick="rsToggleProp(event,this)">
                    <i class="fas fa-alarm-clock"></i><input type="time" class="si q-time"><span class="sl">time</span>
                </div>
            </div>
        </div>
        <div class="rs-cp-actions">
            <button type="button" class="rs-cp-del" onclick="this.closest('.q-point-card').remove();if(!$('qPointsList').querySelectorAll('.q-point-card').length)qResetList();">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `;
    list.appendChild(div);
};

window.qResetList = function () {
    const list = $('qPointsList');
    if (!list.querySelector('#qPointsEmpty')) {
        const el = document.createElement('div');
        el.id = 'qPointsEmpty';
        el.style.cssText = 'display:flex;flex-direction:column;align-items:center;justify-content:center;padding:18px 0;color:rgba(255,255,255,0.1);font-size:0.7rem;font-weight:700;';
        el.innerHTML = '<i class="fas fa-layer-group" style="font-size:1.2rem;margin-bottom:5px;"></i>Empty — add points above';
        list.appendChild(el);
    }
};

window.qHandleShift = function() {
    var val = document.querySelector('input[name="qShift"]:checked')?.value || '';
    $('bpShiftDay').checked = val === 'Day';
    $('bpShiftNight').checked = val === 'Night';
    $('bpShiftAny').checked = val !== 'Day' && val !== 'Night';
    if (typeof bpHandleShift === 'function') bpHandleShift();
};

function qSyncFields() {
    const name = ($('qName').value || '').trim();
    if (!name) { toast('Blueprint name required', true); return false; }
    $('bpRouteName').value        = name;
    $('bpMissionBrief').value     = $('qAnnouncementText').value;
    $('bpAnnounceToggle').checked = $('qAnnounceToggle').checked;
    $('bpSendAlert').checked      = $('qAlert')?.checked || false;
    $('bpStartTime').value        = $('qTime').value;
    $('bpLeadTime').value         = $('qLead').value || 15;
    $('bpIsDaily').checked        = false;
    const today = new Date().toISOString().split('T')[0];
    if ($('bpDate')) $('bpDate').value = today;
    clearTags('bpGuardTags'); assignedGuardIds = [];
    Array.from($('qGuardTags')?.querySelectorAll('.rs-person-tag') || []).forEach(t => {
        addPersonTag('bpGuardTags', t.dataset.pid, t.dataset.label, t.dataset.type);
    });

    return true;
}

function qBuildCps() {
    const points = Array.from($('qPointsList').querySelectorAll('.q-point-card'));
    if (!points.length) { toast('Add at least one point', true); return false; }
    bpClearCps(); bpSetLogic('Flexible');
    points.forEach(p => {
        bpAddCp({
            name:           p.querySelector('.q-name')?.value || '',
            nfc_tag:        p.querySelector('.q-tag')?.value  || '',
            lat:            p.querySelector('.q-lat')?.value  || '',
            lng:            p.querySelector('.q-lng')?.value  || '',
            planned_time:   p.querySelector('.q-time')?.value || null,
            time_tolerance: parseInt(p.querySelector('.q-gap')?.value, 10) ?? 15,
            dwell_time:     parseInt(p.querySelector('.q-dwell')?.value, 10) ?? 0,
            radius:         parseInt(p.querySelector('.q-radius')?.value, 10) ?? 50,
            type: p.dataset.type === 'gps' ? 'gps' : p.dataset.type === 'peer' ? 'peer' : 'nfc',
        });
    });
    return true;
}

window.qApply = function () {
    if (!qSyncFields()) return;
    if (!qBuildCps()) return;
    hideOverlay(); $('bpEdTitle').textContent = 'New Blueprint'; setDispatch(false);
    bpUpdatePreview(); toast('Quick blueprint ready — save when done.');
};

window.qSaveDeploy = function () {
    if (!qSyncFields()) return;
    if (!qBuildCps()) return;
    bpUpdatePreview();
    qdShowInlineConfirm();
};

window.qdShowInlineConfirm = function() {
    var cps = getCpData();
    var name = ($('bpRouteName').value || '').trim() || 'UNNAMED_MISSION';
    var time = $('bpStartTime').value || '—';
    var shift = $('bpShiftDay')?.checked ? 'Day' : $('bpShiftNight')?.checked ? 'Night' : 'Any';
    var tags = Array.from($('bpGuardTags')?.querySelectorAll('.rs-person-tag') || []);
    var guardCount = tags.filter(function(t){ return t.dataset.type !== 'device'; }).length;

    $('qdConfirmSummary').textContent = name + '  ·  ' + shift + '  ·  ' + time + '  ·  ' + guardCount + ' guard' + (guardCount !== 1 ? 's' : '') + '  ·  ' + cps.length + ' CP';

    $('qdConfirmCps').innerHTML = cps.length
        ? cps.map(function(cp, i) {
            var icon = cp.type==='gps'?'fa-map-pin':cp.type==='peer'?'fa-user-shield':'fa-wifi';
            var col = cp.type==='gps'?'var(--r-indigo)':cp.type==='peer'?'var(--r-violet)':'var(--r-crim)';
            var cpname = cp.type === 'peer' ? (cp.auditor_id||'??')+' \u2192 '+(cp.target_id||'??') : (cp.name || 'Point '+(i+1));
            var timeHtml = cp.planned_time ? '<span style="color:var(--r-crim2);font-weight:700;font-family:monospace;font-size:0.5rem;"><i class="far fa-clock" style="font-size:0.38rem;"></i> '+cp.planned_time+'</span>' : '';
            return '<div style="display:flex;align-items:center;gap:4px;padding:3px 8px;border-radius:5px;background:rgba(0,0,0,0.12);border:1px solid rgba(255,255,255,0.03);font-size:0.52rem;">' +
                '<span style="color:var(--r-mute);width:10px;font-weight:900;font-size:0.42rem;font-family:monospace;">'+(i+1)+'</span>' +
                '<i class="fas '+icon+'" style="font-size:0.45rem;opacity:0.5;color:'+col+';width:9px;"></i>' +
                '<span style="flex:1;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+cpname+'</span>' +
                timeHtml +
                '</div>';
        }).join('')
        : '<div style="padding:8px;text-align:center;color:rgba(255,255,255,0.15);font-size:0.6rem;">No checkpoints</div>';

    $('qdInlineVerify').checked = false;
    qdInlineUpdateBtn();
    $('qdConfirmStrip').style.display = 'block';
    $('qdConfirmStrip').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
};

window.qdDismissConfirm = function() {
    $('qdConfirmStrip').style.display = 'none';
};

window.qdInlineUpdateBtn = function() {
    var ok = $('qdInlineVerify').checked;
    var btn = $('qdInlineDeployBtn');
    if (btn) { btn.disabled = !ok; btn.style.opacity = ok ? '1' : '.4'; btn.style.cursor = ok ? 'pointer' : 'not-allowed'; }
};

window.qdInlineExecute = async function() {
    if ($('qdInlineDeployBtn').disabled) return;
    $('qdInlineDeployBtn').disabled = true;
    $('qdInlineDeployBtn').style.opacity = '.6';
    $('qdInlineDeployBtn').innerHTML = '<i class="fas fa-spinner fa-spin"></i> DEPLOYING…';
    await bpConfirmExecute();
    qdDismissConfirm();
};

window.bpPopulateQuickDeploy = function(cps) {
    cps = cps || getCpData();
    var name = ($('bpRouteName').value || '').trim() || 'UNNAMED_MISSION';
    var strat = logic;
    var date = $('bpDate').value || '';
    var time = $('bpStartTime').value || '';
    var sendAlert = !!$('bpSendAlert').checked;
    var sendAnnounce = !!$('bpAnnounceToggle').checked;
    var leadTime = parseInt($('bpLeadTime').value, 10) || 15;

    $('qdBpName').textContent = name;
    $('qdBpStrat').textContent = strat.toUpperCase();
    var clrMap = {FLEXIBLE:'var(--r-teal)',SEQUENTIAL:'var(--r-amber)',SCHEDULED:'var(--r-crim)',AUDIT:'var(--r-crim)',CUSTOM:'var(--r-indigo)'};
    $('qdBpStrat').style.color = clrMap[strat.toUpperCase()] || 'var(--r-teal)';
    $('qdBpStrat').style.background = (clrMap[strat.toUpperCase()] || 'var(--r-teal)').replace(')','').replace('rgb','rgba').replace(/[^,]+$/, '0.12)');
    if ($('qdDate')) $('qdDate').value = date;
    if ($('qdTime')) $('qdTime').value = time;
    $('qdSendAlert').checked = sendAlert;
    $('qdSendAnnounce').checked = sendAnnounce;
    $('qdLeadTime').value = leadTime;

    // Sync shift
    $('qdShift').textContent = $('bpShiftDay')?.checked ? 'Day' : $('bpShiftNight')?.checked ? 'Night' : 'Any';

    // Guard tags
    var tags = Array.from($('bpGuardTags')?.querySelectorAll('.rs-person-tag') || []);
    $('qdGuardTags').innerHTML = tags.map(function(t) {
        var col = t.dataset.type === 'device' ? 'var(--r-teal)' : 'var(--r-crim)';
        return '<span style="padding:1px 6px;font-size:0.5rem;border-radius:4px;font-weight:700;color:'+col+';border:1px solid '+col+'40;background:'+col+'08;">'+t.dataset.label+'</span>';
    }).join('');

    // Checkpoints with time inline
    $('qdCpCount').textContent = cps.length ? '('+cps.length+')' : '(0)';
    $('qdCpList').innerHTML = cps.length
        ? cps.map(function(cp, i) {
            var icon = cp.type==='gps'?'fa-map-pin':cp.type==='peer'?'fa-user-shield':'fa-wifi';
            var col = cp.type==='gps'?'var(--r-indigo)':cp.type==='peer'?'var(--r-violet)':'var(--r-crim)';
            var cpname = cp.type === 'peer' ? (cp.auditor_id||'??')+' \u2192 '+(cp.target_id||'??') : (cp.name || 'Point '+(i+1));
            var timeHtml = cp.planned_time ? '<span style="color:var(--r-crim2);font-weight:700;font-family:monospace;"><i class="far fa-clock" style="font-size:0.4rem;"></i> '+cp.planned_time+'</span>' : '<span style="color:rgba(255,255,255,0.15);font-family:monospace;">\u2014:\u2014</span>';
            return '<div style="display:flex;align-items:center;gap:4px;padding:3px 8px;border-radius:5px;background:rgba(0,0,0,0.15);border:1px solid rgba(255,255,255,0.04);margin-bottom:1px;font-size:0.52rem;">' +
                '<span style="color:var(--r-mute);width:12px;font-weight:900;font-size:0.45rem;font-family:monospace;">'+(i+1)+'</span>' +
                '<i class="fas '+icon+'" style="font-size:0.5rem;opacity:0.45;color:'+col+';width:10px;"></i>' +
                '<span style="flex:1;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+cpname+'</span>' +
                timeHtml +
                '</div>';
        }).join('')
        : '<div style="padding:16px;text-align:center;color:rgba(255,255,255,0.2);font-size:0.7rem;">No checkpoints defined</div>';

    $('qdVerify').checked = false;
    qdUpdateBtn();
};

/* ═══════════════════════════════════════════════════
   PEER AUDIT
═══════════════════════════════════════════════════ */
window.auditAddTarget = function () {
    const container = $('auditTargets');
    const idx = auditTargetCount++;
    const guards = (allPersonnel || []).filter(p => (!p.role || p.role === 'guard' || p.role === 'supervisor'));
    const opts = guards.map(p => `<option value="${p.id}">${p.username} (${p.callsign || 'N/A'})</option>`).join('');

    const div = document.createElement('div');
    div.className = 'rs-cp-row'; div.draggable = true; div.style.cursor = 'grab';
    div.addEventListener('dragstart', () => div.classList.add('dragging'));
    div.addEventListener('dragend',   () => {
        div.classList.remove('dragging');
        container.querySelectorAll('.rs-cp-row').forEach((r, i) => {
            const n = r.querySelector('.rs-cp-num'); if (n) n.textContent = i + 1;
        });
    });
    container.ondragover = e => {
        e.preventDefault();
        const drag = container.querySelector('.dragging');
        if (!drag) return;
        const sibs = [...container.querySelectorAll('.rs-cp-row:not(.dragging)')];
        const after = sibs.find(s => e.clientY < s.getBoundingClientRect().top + s.offsetHeight / 2);
        container.insertBefore(drag, after || null);
    };
    div.innerHTML = `
        <div class="rs-cp-grip" title="Drag to reorder"><i class="fas fa-grip-vertical"></i></div>
        <div class="rs-cp-badge"><div class="rs-cp-num">${container.children.length + 1}</div></div>
        <div style="flex:1; display:flex; align-items:center; gap:4px;">
            <select id="audit-target-guard-${idx}" class="rs-fi rs-fi-sm audit-target-guard" style="height:24px; font-size:0.65rem; padding:0 6px; flex:1;">${opts || '<option value="">No guards</option>'}</select>
            <input id="audit-target-time-${idx}" type="time" class="rs-fi rs-fi-sm audit-target-time" style="width:80px; font-size:0.62rem; padding:2px 5px;">
        </div>
        <div class="rs-cp-actions">
            <button type="button" class="rs-cp-del" onclick="this.closest('.rs-cp-row').remove()"><i class="fas fa-times"></i></button>
        </div>
    `;
    container.appendChild(div);
};

function auditBuildCps() {
    const auditorLabels = getTaggedLabels('auditAuditorTags');
    const auditorIds    = getTaggedIds('auditAuditorTags');
    if (!auditorLabels.length) { toast('Select an auditor', true); return false; }

    const rows = Array.from($('auditTargets').querySelectorAll('.rs-cp-row'));
    if (!rows.length) { toast('Add at least one target guard', true); return false; }

    const start    = $('auditStartTime').value;
    const interval = parseInt($('auditInterval').value || '15', 10);
    const dwell    = parseInt($('auditStay')?.value || '5', 10);
    const enforceSeq = $('auditEnforceSeq').checked;

    bpClearCps(); bpSetLogic('Audit');
    if (enforceSeq) $('bpEnforceOrder').checked = true;

    const involvedIds = new Set(auditorIds.map(Number));

    rows.forEach((row, i) => {
        const sel    = row.querySelector('.audit-target-guard');
        const timeEl = row.querySelector('.audit-target-time');
        const target = getPersonById(sel?.value);
        if (!target) return;
        involvedIds.add(Number(target.id));

        let pt = timeEl?.value || null;
        if (!pt && start) {
            const [h, m] = start.split(':').map(Number);
            const tot = (h * 60) + m + (i * interval);
            pt = `${String(Math.floor(tot / 60) % 24).padStart(2,'0')}:${String(tot % 60).padStart(2,'0')}`;
        }
        bpAddCp({
            name:           `Audit: ${target.username} [by ${auditorLabels.join(', ')}]`,
            nfc_tag:        target.callsign || '',
            planned_time:   pt,
            time_tolerance: 15,
            dwell_time:     dwell,
            type:           'nfc',
        });
    });

    assignedGuardIds = Array.from(involvedIds);
    return true;
}

function auditSyncFields() {
    const name = ($('auditName').value || '').trim();
    if (!name) { toast('Blueprint name required', true); return false; }
    $('bpRouteName').value  = name;
    $('bpDate').value       = $('auditDate').value;
    $('bpStartTime').value  = $('auditStartTime').value;
    $('bpSendAlert').checked = $('auditAlert').checked;
    $('bpIsDaily').checked  = false;
    return true;
}

window.auditApply = function () {
    if (!auditSyncFields()) return;
    if (!auditBuildCps()) return;
    hideOverlay(); $('bpEdTitle').textContent = 'New Blueprint'; setDispatch(false);
    bpUpdatePreview(); toast('Peer Audit blueprint ready — review & save.');
};

window.auditSaveDeploy = function () {
    if (!auditSyncFields()) return;
    if (!auditBuildCps()) return;
    rsDeployOpen();
};

/* ═══════════════════════════════════════════════════
   DEPLOYMENT CONFIRMATION
═══════════════════════════════════════════════════ */
function bpValidatePastDueBlocking() {
    const errors = [];

    const now = new Date();

    const dateStr = $('bpDate')?.value;

    const startTimeStr = $('bpStartTime')?.value;
    const leadMin = parseInt($('bpLeadTime')?.value, 10);
    const sendStartAlert = $('bpSendAlert')?.checked;
    const isDaily = !!$('bpIsDaily')?.checked;

    const isQuick = wizStrategy === 'Quick';

    // Quick deploy treats date as today (UI locks date)
    const todayStr = new Date().toISOString().split('T')[0];
    const execDateStr = isQuick ? todayStr : (dateStr || todayStr);

    if (!execDateStr) return { ok: errors.length === 0, errors };

    // Parse execution date + start time
    if (execDateStr && startTimeStr) {
        const [y, m, d] = execDateStr.split('-').map(Number);
        const [hh, mm] = startTimeStr.split(':').map(Number);
        const startDt = new Date(y, m - 1, d, hh, mm, 0, 0);

        // Daily missions repeat; only block non-daily if launch time has passed today
        if (!isDaily && execDateStr === todayStr && now > startDt) {
            errors.push('Launch time is past due for today. Choose a future time.');
        }

        // Alert window = launchStart - leadTime minutes; skip for daily missions
        if (!isDaily && execDateStr === todayStr && sendStartAlert && !isNaN(leadMin)) {
            const alertStartDt = new Date(startDt.getTime() - leadMin * 60 * 1000);
            if (now > alertStartDt) {
                errors.push('Start alert time is past due for today. Increase the lead time or pick a future launch time.');
            }
        }
    }

    // Checkpoints: only validate planned_time for time-enforced missions (Scheduled/Audit)
    const cps = Array.from($('bpCpList').querySelectorAll('.rs-cp-row'));
    if (execDateStr === todayStr && isTimeEnforced()) {
        const [y, m, d] = execDateStr.split('-').map(Number);
        const cpRows = cps;
        cpRows.forEach((r, idx) => {
            const plannedTime = r.querySelector('.bp-cp-time')?.value;
            if (!plannedTime) return;
            if (!plannedTime.includes(':')) return;
            const [hh, mm] = plannedTime.split(':').map(Number);
            const plannedDt = new Date(y, m - 1, d, hh, mm, 0, 0);
            if (now > plannedDt) {
                errors.push(`Checkpoint ${idx + 1} planned time is past due. Update its time or choose another date.`);
            }
        });
    }

    return { ok: errors.length === 0, errors, isDaily };
}

/* duplicate bpValidatePastDueBlocking removed (kept the earlier version) */

/* ═══════════════════════════════════════════════════
   QUICK DEPLOY OVERLAY
═══════════════════════════════════════════════════ */
window.qdUpdateBtn = function() {
    var ok = $('qdVerify').checked;
    var btn = $('qdDeployBtn');
    if (btn) { btn.disabled = !ok; btn.style.opacity = ok ? '1' : '.4'; btn.style.cursor = ok ? 'pointer' : 'not-allowed'; }
};

window.qdExecute = async function() {
    if ($('qdDeployBtn').disabled) return;
    // Sync overlay fields to editor
    if ($('qdDate').value) $('bpDate').value = $('qdDate').value;
    if ($('qdTime').value) $('bpStartTime').value = $('qdTime').value;
    $('bpSendAlert').checked = $('qdSendAlert').checked;
    $('bpAnnounceToggle').checked = $('qdSendAnnounce').checked;
    $('bpLeadTime').value = $('qdLeadTime').value;
    // Call existing deploy and save
    await bpConfirmExecute();
};

/* ═══════════════════════════════════════════════════
   EDIT CONFIRMATION OVERLAY
═══════════════════════════════════════════════════ */
window.editUpdateBtn = function() {
    var ok = $('editVerify').checked;
    var btn = $('editSaveBtn');
    if (btn) { btn.disabled = !ok; btn.style.opacity = ok ? '1' : '.4'; btn.style.cursor = ok ? 'pointer' : 'not-allowed'; }
};

window.editExecute = async function() {
    if ($('editSaveBtn').disabled) return;
    await bpSaveRoute(false);
    toast('Blueprint updated');
    hideOverlay();
    await bpLoad();
};

window.showEditConfirm = function() {
    showOverlay('wizStepEditConfirm');
    var diff = $('editDiffContent');
    if (!diff) return;
    if (!selId) { diff.innerHTML = '<div style="padding:12px;text-align:center;color:var(--r-teal);"><i class="fas fa-plus-circle"></i> New blueprint — no previous version to compare.</div>'; return; }
    var cps = getCpData();
    var html = '<div style="display:flex;flex-direction:column;gap:8px;">';
    html += '<div class="rs-conf-row"><span class="rs-conf-key">Name</span><span class="rs-conf-val">' + (($('bpRouteName').value||'').trim() || '—') + '</span></div>';
    html += '<div class="rs-conf-row"><span class="rs-conf-key">Strategy</span><span class="rs-conf-val">' + logic + '</span></div>';
    html += '<div class="rs-conf-row"><span class="rs-conf-key">Date</span><span class="rs-conf-val">' + (($('bpDate').value||'—')) + '</span></div>';
    html += '<div class="rs-conf-row"><span class="rs-conf-key">Start Time</span><span class="rs-conf-val">' + (($('bpStartTime').value||'—')) + '</span></div>';
    html += '<div class="rs-conf-row"><span class="rs-conf-key">Checkpoints</span><span class="rs-conf-val">' + cps.length + ' defined</span></div>';
    if (cps.length) {
        html += '<div style="font-size:0.58rem;font-weight:900;color:var(--r-mute);text-transform:uppercase;letter-spacing:0.5px;margin-top:4px;">Checkpoint Times</div>';
        cps.forEach(function(cp, i) {
            var t = cp.planned_time || '<span style="color:rgba(255,255,255,0.15);">—:—</span>';
            html += '<div style="display:flex;align-items:center;gap:6px;padding:3px 8px;border-radius:4px;background:rgba(0,0,0,0.1);font-size:0.6rem;">' +
                '<span style="color:var(--r-mute);width:14px;font-weight:700;font-family:monospace;">' + (i+1) + '</span>' +
                '<span style="flex:1;color:#fff;">' + (cp.name || 'Point '+(i+1)) + '</span>' +
                '<span style="font-family:monospace;color:var(--r-crim2);font-weight:700;">' + t + '</span>' +
                '</div>';
        });
    }
    html += '</div>';
    diff.innerHTML = html;
    $('editVerify').checked = false;
    editUpdateBtn();
};

window.bpConfirmExecute = async function () {
    const name = ($('bpRouteName')?.value || '').trim();
    if (!name) { toast('Mission name required', true); return; }

    bpUpdatePreview(); bpSetDirty();

    let saved;
    try {
        saved = await bpSaveRoute(true);
    } catch (e) {
        toast('Save threw an exception', true);
        return;
    }
    if (!saved || !saved.id) {
        toast('Save failed: blueprint not created/updated', true);
        return;
    }

    const hasAnyTag = Array.from($('bpGuardTags')?.querySelectorAll('.rs-person-tag') || []).length > 0;

    let deployOk = false;
    try {
        if (hasAnyTag) {
            const res = await api('/api/routes/' + saved.id + '/deploy/', { method: 'POST' });
            if (res.ok) {
                deployOk = true;
                toast('Mission force deployed successfully');
            } else {
                let detail = '';
                try { const d = await res.json(); detail = d?.detail ? ' — ' + d.detail : ''; } catch (_) {}
                toast('Tactical launch failed' + detail, true);
            }
        } else {
            toast('Mission saved in Uncrewed Mode');
            deployOk = true;
        }
    } catch (e) {
        toast('Deploy request failed (network/server error)', true);
    }
    try { await bpLoad(); } catch (_) {}
    if (deployOk) {
        toast('Mission deployed — view live tracking in Dispatch Console');
        rsDeployCancel();
        hideOverlay();
    }
};

/* ═══════════════════════════════════════════════════
   SIDEBAR DEPLOY PANEL
═══════════════════════════════════════════════════ */
window.rsDeployOpen = async function() {
    // Must have a saved route to show deploy preview
    if (!selId) {
        toast('Save the blueprint first', true);
        return;
    }
    $('rsDeployPanel').style.display = 'flex';
    var mp = $('rsManifestPanel'); if (mp) mp.style.display = 'none';
    // Fetch server-rendered deploy preview
    try {
        if (window.htmx) {
            htmx.ajax('GET', '/api/routes-deploy-preview-partial/' + selId + '/', {
                target: '#rsDeployPanel', swap: 'innerHTML'
            });
        }
    } catch (e) {
        console.error('Deploy preview load failed:', e);
    }
};

window.rsDeployCancel = function() {
    $('rsDeployPanel').style.display = 'none';
    var mp = $('rsManifestPanel'); if (mp) mp.style.display = 'flex';
};

window.rsDeployUpdateBtn = function() {
    var ok = $('rsVerify').checked;
    var btn = $('rsDeployBtn');
    if (btn) { btn.disabled = !ok; btn.style.opacity = ok ? '1' : '.4'; }
};

window.rsDeployExecute = async function() {
    if ($('rsDeployBtn').disabled) return;
    // Sync deploy panel edits back to editor fields
    if ($('rsDeployDate').value) $('bpDate').value = $('rsDeployDate').value;
    if ($('rsDeployTime').value) $('bpStartTime').value = $('rsDeployTime').value;
    // Call the existing confirmation execute
    await bpConfirmExecute();
};

/* ═══════════════════════════════════════════════════
   PREVIEW & MANIFEST
═══════════════════════════════════════════════════ */
window.bpUpdatePreview = function () {
    const bar = $('bpPreviewBar');
    if (!bar) return;

    const cps = getCpData();
    const eo  = isOrderEnforced(), et = isTimeEnforced();
    const hasNfc = cps.some(c => c.nfc_tag);
    const hasGps = cps.some(c => c.lat && c.lng);

    const score = 20 + (eo ? 30 : 0) + (et ? 40 : 0);
    const [lvLabel, lvCls] = score > 80 ? ['Critical','rs-b-crim'] : score > 50 ? ['Strict','rs-b-amb'] : ['Standard','rs-b-std'];

    bar.innerHTML = `
        <span class="rs-badge rs-b-crim" style="text-transform:uppercase; margin-right:4px;">${logic}</span>
        <span class="rs-badge ${eo ? 'rs-b-on' : 'rs-b-off'}"><i class="fas fa-list-ol" style="margin-right:3px;font-size:.55rem;"></i>Seq: ${eo ? 'on' : 'off'}</span>
        <span class="rs-badge ${et ? 'rs-b-on' : 'rs-b-off'}"><i class="fas fa-clock" style="margin-right:3px;font-size:.55rem;"></i>Time: ${et ? 'on' : 'off'}</span>
        <span class="rs-badge ${(hasNfc || hasGps) ? 'rs-b-on' : 'rs-b-off'}">${hasNfc ? '✓ NFC' : hasGps ? '✓ GPS' : '✗ No tags'}</span>
        <span class="rs-badge ${lvCls}" style="margin-left:auto;">${lvLabel}</span>
    `;
    const sb = $('summaryStatusBar'); if (sb) sb.innerHTML = bar.innerHTML;

    /* Date handling for Quick Deploy — Lock to today visually */
    const dateInp = $('bpDate');
    const dateLock = $('bpDateQuickLock');
    if (wizStrategy === 'Quick') {
        const today = new Date().toISOString().split('T')[0];
        if (dateInp) { dateInp.value = today; dateInp.style.visibility = 'hidden'; }
        dateLock?.classList.remove('rs-hidden');
    } else {
        if (dateInp) dateInp.style.visibility = 'visible';
        dateLock?.classList.add('rs-hidden');
    }

    /* Personnel manifest */
    const pm = $('summaryPersonnel');
    if (pm) {
        const tags = Array.from($('bpGuardTags')?.querySelectorAll('.rs-person-tag') || []);
        const personnelTags = tags.filter(t => t.dataset.type === 'person');
        const deviceTags = tags.filter(t => t.dataset.type === 'device');

        if (!personnelTags.length && !deviceTags.length) {
            pm.innerHTML = `
                <div style="background:rgba(245,166,35,0.05); border:1px solid rgba(245,166,35,0.1); border-radius:8px; padding:10px;">
                    <div style="font-size:0.6rem; color:var(--r-amber); font-weight:900; text-transform:uppercase; margin-bottom:4px;"><i class="fas fa-microchip"></i> UNCREWED MODE</div>
                    <div style="font-size:0.68rem; color:rgba(255,255,255,0.4); line-height:1.3;">No specific personnel assigned. Mission tracking is bound to hardware unit login codes.</div>
                </div>
            `;
        } else {
            let html = '';
            if (personnelTags.length > 0) {
                html += personnelTags.map(t => {
                    const icon = 'fa-user-shield';
                    const col = 'var(--r-crim)';
                    const isAuditor = logic === 'Audit' && personnelTags.indexOf(t) === 0; // First personnel tag is auditor in Audit mode
                    const label = isAuditor ? `<span style="color:var(--r-violet); font-size:0.5rem; margin-right:4px;">AUDITOR</span> ${t.dataset.label}` : t.dataset.label;
                    return `<div class="rs-manifest-item" style="background:rgba(255,255,255,0.02); border-radius:8px;">
                        <span style="display:flex;align-items:center;gap:6px; font-weight:700;"><i class="fas ${icon}" style="color:${col}; font-size:0.6rem;"></i>${label}</span>
                        <button type="button" class="rs-manifest-remove" onclick="this.parentElement.remove();bpUpdatePreview();"><i class="fas fa-times"></i></button>
                    </div>`;
                }).join('');
            }
            if (deviceTags.length > 0) {
                html += deviceTags.map(t => {
                    const icon = 'fa-mobile-screen';
                    const col = 'var(--r-teal)';
                    return `<div class="rs-manifest-item" style="background:rgba(255,255,255,0.02); border-radius:8px;">
                        <span style="display:flex;align-items:center;gap:6px; font-weight:700;"><i class="fas ${icon}" style="color:${col}; font-size:0.6rem;"></i>${t.dataset.label}</span>
                        <button type="button" class="rs-manifest-remove" onclick="this.parentElement.remove();bpUpdatePreview();"><i class="fas fa-times"></i></button>
                    </div>`;
                }).join('');
            }
            pm.innerHTML = html;
        }
    }

    /* Sequence manifest */
    const cm = $('summaryCps');
    if (cm) {
        if (!cps.length) {
            cm.innerHTML = '<div style="font-size:.7rem;color:var(--r-mute);padding:4px;">Empty</div>';
        } else {
            const typeIcon = { gps:'fa-map-pin', peer:'fa-user-shield', nfc:'fa-wifi' };
            const typeCol  = { gps:'var(--r-indigo)', peer:'var(--r-violet)', nfc:'var(--r-crim)' };
            cm.innerHTML = cps.map((cp, i) => `
                <div class="rs-manifest-item" style="flex-direction:row; padding:6px 10px; gap:8px;">
                    <i class="fas ${typeIcon[cp.type]||'fa-wifi'}" style="color:${typeCol[cp.type]||'var(--r-crim)'}; width:14px; font-size:0.7rem; opacity:0.7;"></i>
                    <div style="flex:1; min-width:0;">
                        <div style="font-weight:800; font-size:0.7rem; display:flex; justify-content:space-between; align-items:center;">
                            <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                                ${cp.type === 'peer' ? `${cp.auditor_id||'??'} ⇢ ${cp.target_id||'??'}` : (cp.name || 'Point '+(i+1))}
                            </span>
                            <button type="button" class="rs-manifest-remove" onclick="bpRemoveCpAt(${i})"><i class="fas fa-trash-can" style="font-size:.6rem;"></i></button>
                        </div>
                        <div style="display:flex; gap:6px; font-size:.55rem; color:var(--r-mute); margin-top:1px;">
                            ${cp.planned_time ? `<span><i class="fas fa-clock"></i> ${cp.planned_time}</span>` : ''}
                            ${cp.dwell_time > 0 ? `<span><i class="fas fa-stopwatch"></i> ${cp.dwell_time}m</span>` : ''}
                            ${cp.nfc_tag ? `<span style="font-family:monospace;">[${cp.nfc_tag.slice(-6)}]</span>` : ''}
                        </div>
                    </div>
                </div>`).join('');
        }
    }
};

/* ═══════════════════════════════════════════════════
   ALERT TIME COMPUTATION
═══════════════════════════════════════════════════ */
window.bpUpdateAlertTime = function () {
    const row = $('bpAlertTimeRow');
    const txt = $('bpAlertTimeText');
    if (!row || !txt) return;
    const alertOn = $('bpSendAlert')?.checked;
    const timeVal = $('bpStartTime')?.value;
    const lead    = parseInt($('bpLeadTime')?.value, 10) || 0;
    if (!alertOn) {
        txt.innerHTML = '<i class="fas fa-bell-slash" style="font-size:0.35rem;color:var(--r-mute);opacity:0.3;"></i> <span style="color:rgba(255,255,255,0.25);">Off</span>';
        return;
    }
    if (!timeVal || lead <= 0) {
        txt.innerHTML = '<i class="fas fa-bell" style="font-size:0.35rem;color:var(--r-amber);opacity:0.6;"></i> <span style="color:var(--r-amber);opacity:0.65;">' + (timeVal ? 'Lead &gt; 0' : 'Set time') + '</span>';
        return;
    }
    const [h, m] = timeVal.split(':').map(Number);
    const totalMin = h * 60 + m;
    const alertMin = ((totalMin - lead) % 1440 + 1440) % 1440;
    const ah = String(Math.floor(alertMin / 60)).padStart(2, '0');
    const am = String(alertMin % 60).padStart(2, '0');
    const dateVal = $('bpDate')?.value;
    const datePart = dateVal ? new Date(dateVal + 'T' + timeVal).toLocaleDateString('en-US', { month:'short', day:'numeric' }) + ' ' : '';
    txt.innerHTML = '<i class="fas fa-bell" style="font-size:0.35rem;color:var(--r-crim);"></i> <span style="color:var(--r-crim2);font-weight:900;">' + datePart + ah + ':' + am + '</span> <span style="color:var(--r-mute);font-size:0.38rem;">(' + lead + ' ahead)</span>';
};

/* ═══════════════════════════════════════════════════
   SAVE
═══════════════════════════════════════════════════ */
window.bpSaveRoute = async function (skipUI = false) {
    const name = ($('bpRouteName').value || '').trim();
    if (!name) { toast('Blueprint name required', true); return null; }

    let orgId = null;
    if (typeof userData !== 'undefined' && userData.organization_id)
        orgId = Array.isArray(userData.organization_id) ? userData.organization_id[0] : userData.organization_id;

    // Separate assigned guards and devices from the tags
    const allSelectedTags = Array.from($('bpGuardTags')?.querySelectorAll('.rs-person-tag') || []);

    const selectedGuardIds = allSelectedTags
        .filter(t => t.dataset.type === 'person')
        .map(t => Number(t.dataset.pid))
        .filter(id => !isNaN(id) && id > 0);

    const selectedDeviceIds = allSelectedTags
        .filter(t => t.dataset.type === 'device')
        .map(t => Number(t.dataset.pid))
        .filter(id => !isNaN(id) && id > 0);

    // Client-side validation for guards
    const validAssignedGuards = selectedGuardIds.filter(id => allPersonnel.some(p => p.id === id));
    if (selectedGuardIds.length !== validAssignedGuards.length) {
        const invalidGuardLabels = allSelectedTags
            .filter(t => t.dataset.type === 'person' && !allPersonnel.some(p => String(p.id) === t.dataset.pid))
            .map(t => t.dataset.label);
        toast(`Invalid personnel selected: ${invalidGuardLabels.join(', ')}. Please review assigned personnel.`, true);
        return null;
    }

    // Client-side validation for devices
    const validAssignedDevices = selectedDeviceIds.filter(id => allDevices.some(d => d.id === id));
    if (selectedDeviceIds.length !== validAssignedDevices.length) {
        const invalidDeviceLabels = allSelectedTags
            .filter(t => t.dataset.type === 'device' && !allDevices.some(d => String(d.id) === t.dataset.pid))
            .map(t => t.dataset.label);
        toast(`Invalid devices selected: ${invalidDeviceLabels.join(', ')}. Please review assigned devices.`, true);
        return null;
    }

    // Checkpoints processing remains the same
    const checkpoints = Array.from($('bpCpList').querySelectorAll('.rs-cp-row')).map((r, i) => {
        const latVal = r.querySelector('.bp-cp-lat')?.value?.trim();
        const lngVal = r.querySelector('.bp-cp-lng')?.value?.trim();
        const timeVal = r.querySelector('.bp-cp-time')?.value;

        // Safely parse integers to avoid sending null/NaN to non-nullable backend fields
        const parseSafeInt = (selector, fallback) => {
            const val = r.querySelector(selector)?.value;
            const parsed = parseInt(val, 10);
            return isNaN(parsed) ? fallback : parsed;
        };

        const cpNfc   = (r.querySelector('.bp-cp-tag')?.value || r.querySelector('.bp-cp-target')?.value || '').trim() || null;
        const cpLat   = (latVal && !isNaN(parseFloat(latVal))) ? parseFloat(latVal) : null;
        const cpLng   = (lngVal && !isNaN(parseFloat(lngVal))) ? parseFloat(lngVal) : null;
        const cpAud   = r.querySelector('.bp-cp-auditor')?.value?.trim() || null;
        const cpTgt   = r.querySelector('.bp-cp-target')?.value?.trim() || null;
        const cpType  = r.dataset.cpType || 'nfc';
        const cpFetchLoc = r.querySelector('.bp-cp-fetch-location')?.checked || false;
        // For NFC rows, read lat/lng from hidden fields if set
        const nfcLat = r.querySelector('.bp-cp-lat')?.value;
        const nfcLng = r.querySelector('.bp-cp-lng')?.value;
        return {
            name:           (r.querySelector('.bp-cp-name')?.value || cpTgt || 'Checkpoint '+(i+1)).trim(),
            checkpoint_type: cpType,
            nfc_tag:        cpType === 'nfc' ? cpNfc : null,
            auditor_id:     cpType === 'peer' ? cpAud : null,
            target_id:      cpType === 'peer' ? cpTgt : null,
            lat:            cpType !== 'nfc' ? cpLat : (nfcLat ? parseFloat(nfcLat) : null),
            lng:            cpType !== 'nfc' ? cpLng : (nfcLng ? parseFloat(nfcLng) : null),
            planned_time:   timeVal || null,
            time_tolerance: parseSafeInt('.bp-cp-tol', 15),
            dwell_time:     parseSafeInt('.bp-cp-dwell', 0),
            radius:         parseSafeInt('.bp-cp-rad', 50),
            fetch_location_on_scan: cpFetchLoc,
            order:          i,
        };
    }).filter(cp => cp.nfc_tag || (cp.lat !== null && cp.lng !== null) || (cp.auditor_id && cp.target_id) || cp.checkpoint_type === 'custom');

    // Validate no duplicate planned_times within this route
    const times = checkpoints.map(cp => cp.planned_time).filter(Boolean);
    if (new Set(times).size !== times.length) {
        toast('Duplicate planned times detected. Two or more checkpoints share the same time.', true);
        return null;
    }

    const payload = {
        name,
        description:          $('bpMissionBrief').value,
        scheduled_date:       $('bpDate').value || null,
        organization:         orgId,
        logic_type:           logic,
        enforce_order:        isOrderEnforced(),
        enforce_time:         isTimeEnforced(),
        is_audit:             logic === 'Audit',
        is_geofence:          false,
        scheduled_start_time: $('bpStartTime').value || null,
        send_announcement:    $('bpAnnounceToggle').checked,
        readout_text:         $('bpMissionBrief').value,
        send_start_alert:     $('bpSendAlert').checked,
        is_daily:             $('bpIsDaily').checked,
        start_alert_lead_time: parseInt($('bpLeadTime').value, 10) || 15,
        checkpoints,
        assigned_guards: validAssignedGuards, // Send validated guard IDs
        assigned_devices: validAssignedDevices, // Send validated device IDs
    };

    try {
        const method = selId ? 'PUT' : 'POST';
        const url    = selId ? `/api/routes/${selId}/` : '/api/routes/';
        const res    = await api(url, { method, body: JSON.stringify(payload) });
        if (!res.ok) { toast('Save failed', true); return null; }
        const d = await res.json();
        toast('Blueprint saved');
        bpDirty = false;
        if (!selId) {
            selId = d.id; $('bpEdTitle').textContent = 'Edit Blueprint'; setDispatch(true);
        } else if (!skipUI) {
            bpCloseEditor();
        }
        await bpLoad();
        return d;
    } catch (e) { toast('Save failed', true); return null; }
};

/* ═══════════════════════════════════════════════════
   DELETE
═══════════════════════════════════════════════════ */
window.bpDeleteRoute = async function (e, id) {
    e.stopPropagation();
    if (!confirm('Decommission this blueprint?')) return;
    try {
        const res = await api(`/api/routes/${id}/`, { method: 'DELETE' });
        if (res.ok) { toast('Deleted'); allRoutes = allRoutes.filter(r => r.id !== id); if (selId === id) bpCloseEditor(); else refreshRouteList(); }
    } catch (e) {}
};

/* ═══════════════════════════════════════════════════
   KEYBOARD
═══════════════════════════════════════════════════ */
document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        if ($('bpOverlay').classList.contains('hidden')) bpSaveRoute();
    }
});

document.addEventListener('click', e => {
    if (!e.target.closest('#bpAssetSearch') && !e.target.closest('#bpAssetSuggest'))
        $('bpAssetSuggest')?.classList.add('rs-hidden');
});

/* ═══════════════════════════════════════════════════
   BOOT
═══════════════════════════════════════════════════ */
function bpBoot() {
    bpLoad().then(function() {
        showOverlay('wizStep1');
    });
    // Wire callsign inputs
    populateTagSuggest('qGuardInput', 'qGuardTags');
    populateTagSuggest('wiz2GuardInput', 'wiz2GuardTags');
    populateTagSuggest('bpGuardInput', 'bpGuardTags');
    populateTagSuggest('auditAuditorInput', 'auditAuditorTags');
    populateTagSuggest('sweepTargetInput', 'sweepTargetTags');
    bpUpdatePreview();
    CalendarComponent.init({
        onDayClick: function(dateStr) {
            $('bpDate').value = dateStr;
            bpSetDirty();
            CalendarComponent.setDate(new Date(dateStr + 'T12:00:00'));
        },
        onDeployClick: rsDeployOpen
    });
    // Init TTS repeat label
    const lt = $('bpLeadTime');
    if (lt) { const rl=$('bpRepeatLabel'); if(rl) rl.textContent=lt.value; }
    bpUpdateAlertTime();

    // Wire start time for validation
    $('bpStartTime')?.addEventListener('change', bpValidateShiftTime);
}

// Initial page load
document.addEventListener('DOMContentLoaded', bpBoot);

// htmx SPA navigation — show overlay when routes page is swapped into main content
document.addEventListener('htmx:afterSettle', function(evt) {
    var target = evt.detail && evt.detail.target;
    if (target && target.id === 'spa-content' && $('bpOverlay')) {
        bpBoot();
    }
});

// After any htmx swap inside the overlay, re-wire tag suggestion inputs
document.addEventListener('htmx:afterSwap', function(evt) {
    var target = evt.detail && evt.detail.target;
    if (target && target.id === 'bpOverlayContent') {
        // Re-initialize tag inputs for the loaded wizard step
        if ($('wiz2GuardInput')) populateTagSuggest('wiz2GuardInput', 'wiz2GuardTags');
        if ($('qGuardInput')) populateTagSuggest('qGuardInput', 'qGuardTags');
        if ($('auditAuditorInput')) populateTagSuggest('auditAuditorInput', 'auditAuditorTags');
    }
});
