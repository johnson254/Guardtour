import '../styles/main.css';
/* ── State ──────────────────────────────────────── */
let allGuards    = [];
let allDevices   = [];
let allCallsigns = [];
let allAssets    = [];
let allRoutes    = [];
let allDeploys   = [];
let allLog       = [];
let guardFilter  = 'all';
let deviceFilter = 'all';
let assetFilter  = 'all';
let logFilter    = 'all';
let calDate      = new Date();
let selCalDay    = null;
let currentModal = null;
let editId       = null;
let currentTab   = 'staff';
const $  = id => document.getElementById(id);
const $$ = s  => document.querySelectorAll(s);

/* ── API ────────────────────────────────────────── */
const api = async (url, opts = {}) => {
    // Check for the global helper at call-time to avoid load-order issues
    if (typeof window.apiFetch === 'function') return window.apiFetch(url, opts);
    
    // Fallback: Ensure we still send the token if apiFetch isn't ready
    const token = JSON.parse(localStorage.getItem('gt_user') || '{}').token;
    const headers = { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}), ...(opts.headers || {}) };
    return fetch(url, { credentials: 'same-origin', ...opts, headers });
};

/* ── Toast ──────────────────────────────────────── */
function toast(msg,isErr){
    const el=document.createElement('div');
    el.className='mg-toast';
    el.innerHTML=`<span class="td${isErr?' tde':''}"></span>${msg}`;
    $('mgToasts').appendChild(el);
    setTimeout(()=>el.remove(),2700);
}

/* ── Tab switch ─────────────────────────────────── */
/* ── Search clear utilities ────────────────────────── */
window.mgSearchShowClear = function(inp) {
    var btn = inp.nextElementSibling;
    if (btn) btn.classList.toggle('visible', inp.value.length > 0);
};
window.mgClearSearch = function(inpId, btnId) {
    var inp = $(inpId);
    var btn = $(btnId);
    if (inp) { inp.value = ''; inp.focus(); inp.dispatchEvent(new Event('input')); }
    if (btn) btn.classList.remove('visible');
};

window.mgTab = function(id, el){
     /* Legacy — kept for backward compat but tabs now use htmx.
        This just updates currentTab for the refresh interval guard. */
     currentTab = id;
};


/* ══════════════════════════════════════════════════
   PERSONNEL
══════════════════════════════════════════════════ */
async function mgLoadGuards(){
    try{
        const res=await api('/api/profiles/');
        if(res.ok){ const d=await res.json(); allGuards=Array.isArray(d)?d:(d.results||[]); }
    }catch(e){}
    mgRenderGuardStats();
    mgRenderGuards();
    return allGuards;
}

function mgRenderGuardStats(){
    const total=allGuards.length;
    const guards=allGuards.filter(g=>g.role==='guard'||!g.role).length;
    const supers=allGuards.filter(g=>g.role==='supervisor').length;
    const day=allGuards.filter(g=>g.shift==='Day').length;
    const night=allGuards.filter(g=>g.shift==='Night').length;
    $('personnelStats').innerHTML=`
        <div class="mg-stat"><div class="mg-stat-val">${total}</div><div class="mg-stat-lbl">Total</div></div>
        <div class="mg-stat"><div class="mg-stat-val red">${guards}</div><div class="mg-stat-lbl">Guards</div></div>
        <div class="mg-stat"><div class="mg-stat-val amber">${supers}</div><div class="mg-stat-lbl">Supervisors</div></div>
        <div class="mg-stat"><div class="mg-stat-val" style="color:#FFD54F">${day}</div><div class="mg-stat-lbl">Day</div></div>
        <div class="mg-stat"><div class="mg-stat-val blue">${night}</div><div class="mg-stat-lbl">Night</div></div>
    `;
    $('tcStaff').textContent=total;
}

window.mgGuardFilter=function(f,el){
    guardFilter=f;
    $$('#mgPanelStaff .mg-filter-chip').forEach(c=>c.classList.remove('active'));
    el.classList.add('active');
    mgRenderGuards();
};

window.mgFilterGuards=function(){ mgRenderGuards(); };

function mgRenderGuards(){
    const q=($('guardSearch')?.value||'').toLowerCase();
    let list=allGuards;
    if(guardFilter==='guard') list=list.filter(g=>g.role==='guard'||!g.role);
    else if(guardFilter==='supervisor') list=list.filter(g=>g.role==='supervisor');
    else if(guardFilter==='Day') list=list.filter(g=>g.shift==='Day');
    else if(guardFilter==='Night') list=list.filter(g=>g.shift==='Night');
    if(q) list=list.filter(g=>(g.username+g.first_name+g.last_name+g.callsign).toLowerCase().includes(q));

    const container=$('guardList');
    if(!list.length){container.innerHTML='<div class="mg-empty"><i class="fas fa-user-slash"></i>No personnel found</div>';return;}

    // Build deployment lookup: guard_id -> active deployment
    var deployByGuard = {};
    if (typeof allDeploys !== 'undefined' && Array.isArray(allDeploys)) {
        allDeploys.forEach(function(s) {
            if (s.guard_supervisor && !s.is_completed) {
                if (!deployByGuard[s.guard_supervisor]) deployByGuard[s.guard_supervisor] = [];
                deployByGuard[s.guard_supervisor].push(s);
            }
        });
    }

    const shiftColor={Day:'#FFD54F',Night:'#7986cb',Flex:'rgba(255,255,255,.5)'};
    const roleClass={guard:'mg-b-guard',supervisor:'mg-b-super'};

    container.innerHTML=list.map((g,i)=>{
        const name = [g.first_name, g.last_name].filter(Boolean).join(' ') || g.username || 'Unnamed Officer';
        const shift=g.shift||'Day';
        const role=g.role||'guard';
        const avatarColor=shift==='Day'?'rgba(255,213,79,.15)':'rgba(63,81,181,.2)';
        const avatarIcon=shift==='Day'?'fa-sun':'fa-moon';

        // Determine duty status from deployments
        var deploys = deployByGuard[g.id] || [];
        var activeDeploy = deploys.find(function(s) { return s.is_active; });
        var upcomingDeploy = deploys.find(function(s) { return !s.is_active; });
        var status = 'available';
        var statusLabel = 'Available';
        var statusColor = 'rgba(255,255,255,0.25)';
        if (activeDeploy) { status = 'mission'; statusLabel = 'On Mission'; statusColor = '#5DCAA5'; }
        else if (upcomingDeploy) { status = 'queued'; statusLabel = 'Queued'; statusColor = '#EF9F27'; }

        var currentRoute = '';
        if (activeDeploy) currentRoute = activeDeploy.route_name || '';
        else if (upcomingDeploy) currentRoute = upcomingDeploy.route_name || '';

        var lastSeen = g.last_seen || g.online_at || '';
        var lastSeenStr = lastSeen ? new Date(lastSeen).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : '';
        var isOnline = g.is_online || false;

                return `
        <div class="mg-card mg-card-duty mg-duty-${status}" data-guard-id="${g.id}" style="--i:${i};">
            <div class="mg-card-avatar" style="background:${avatarColor}; position:relative;">
                <i class="fas ${avatarIcon}" style="color:${shiftColor[shift]||'#fff'}"></i>
                ${status === 'mission' ? '<span class="mg-duty-pulse"></span>' : ''}
            </div>
            <div class="mg-card-info">
                <div class="mg-card-name">${name}</div>
                <div class="mg-card-sub" style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                    <span><i class="fas fa-id-badge" style="opacity:.5"></i> ${g.callsign||'No Callsign'}</span>
                    <span class="mg-duty-status mg-ds-${status}" style="display:inline-flex;align-items:center;gap:3px;">
                        <span class="mg-ds-dot" style="background:${statusColor};"></span>${statusLabel}
                    </span>
                    ${isOnline ? '<span style="color:#5DCAA5;font-size:0.55rem;"><i class="fas fa-circle" style="font-size:0.35rem;"></i> Online</span>' : ''}
                </div>
                ${currentRoute ? '<div class="mg-card-sub" style="margin-top:2px;font-size:0.6rem;color:var(--primary-light);"><i class="fas fa-route" style="opacity:.5;margin-right:3px;"></i>' + currentRoute + '</div>' : ''}
                <div class="mg-card-tags">
                    ${g.callsign ? `<span class="mg-badge mg-b-active" style="letter-spacing:0.5px;">${g.callsign}</span>` : ''}
                    <span class="mg-badge ${roleClass[role]||'mg-b-guard'}">${role}</span>
                    <span class="mg-badge ${shift==='Day'?'mg-b-day':shift==='Night'?'mg-b-night':'mg-b-flex'}">${shift}</span>
                </div>
            </div>
            <div class="mg-card-actions" style="flex-direction:column;gap:4px;">
                ${activeDeploy ? '<button type="button" class="mg-btn mg-btn-xs mg-btn-success" onclick="event.stopPropagation();window.location.href=\'/dispatch/\'" title="View Mission"><i class="fas fa-eye"></i></button>' : '<button type="button" class="mg-btn mg-btn-xs mg-btn-primary" onclick="event.stopPropagation();mgOpenModal(\'blueprint-shift\',null,' + g.id + ')" title="Assign to Mission"><i class="fas fa-plus"></i></button>'}
                <button type="button" class="mg-btn mg-btn-xs ${isOnline?'mg-btn-success':'mg-btn'}" onclick="event.stopPropagation();mgToggleGuardStatus(${g.id},${!isOnline})" title="${isOnline?'Go Offline':'Mark Online'}"><i class="fas ${isOnline?'fa-power-off':'fa-plug'}"></i></button>
                <button type="button" class="mg-btn mg-btn-xs" onclick="event.stopPropagation();mgEditGuard(${g.id})" title="Edit"><i class="fas fa-pen"></i></button>
                <button type="button" class="mg-btn mg-btn-xs mg-btn-danger" onclick="event.stopPropagation();mgDelete('profiles',${g.id},'personnel')" title="Remove"><i class="fas fa-trash-alt"></i></button>
            </div>
        </div>`;
    }).join('');
}

window.mgEditGuard=function(id){
    const g=allGuards.find(x=>x.id===id);
    if(!g) return;
    editId=id;
    mgOpenModal('guard',g);
};

window.mgToggleGuardStatus=async function(id,online){
    try{
        const res=await api('/api/profiles/'+id+'/',{method:'PATCH',body:JSON.stringify({is_online:online})});
        if(res.ok){ const g=allGuards.find(x=>x.id===id); if(g) g.is_online=online; mgRenderGuards(); }
    }catch(e){}
};

/* ══════════════════════════════════════════════════
   CALLSIGNS
══════════════════════════════════════════════════ */
async function mgLoadCallsigns(){
    // Legacy: kept for backwards compatibility.
    try{
        const res = await api('/api/callsigns/');
        if(res.ok){ const d = await res.json(); allCallsigns = Array.isArray(d) ? d : (d.results || []); }
    }catch(e){}
    mgRenderCallsignStats();
    mgRenderCallsigns();
}

/* ══════════════════════════════════════════════════
   BLUEPRINT-AWARE CALLSIGNS
══════════════════════════════════════════════════ */
async function mgLoadBlueprintAwareCallsigns(){ await mgRefreshBlueprintShift(); }

window.mgRefreshBlueprintShift = async function(){
    try {
        const res = await api('/api/shifts/');
        if(!res.ok) return;
        const data = await res.json();
        const shifts = Array.isArray(data) ? data : (data.results || []);
        allDeploys = shifts;
        mgRenderBlueprintActiveDeployments(shifts);
        if(window.CalendarComponent) CalendarComponent.render();
        
        // Update panel stats
        const activeCount = shifts.filter(s => s.is_active).length;
        const queuedCount = shifts.filter(s => !s.is_active && !s.is_completed).length;
        const todaysDeploys = shifts.filter(s => (s.scheduled_date || s.assigned_at || '').split('T')[0] === new Date().toISOString().split('T')[0]);
        const onDutyGuards = new Set(shifts.filter(s => s.is_active).map(s => s.guard_supervisor).filter(Boolean)).size;
        const nonCompleted = shifts.filter(s => !s.is_completed);
        
        $('tcStaff').textContent = activeCount;
        
        $('callsignStats').innerHTML = `
            <div class="mg-stat"><div class="mg-stat-val green">${activeCount}</div><div class="mg-stat-lbl">On Mission</div></div>
            <div class="mg-stat"><div class="mg-stat-val amber">${queuedCount}</div><div class="mg-stat-lbl">Queued</div></div>
            <div class="mg-stat"><div class="mg-stat-val blue">${onDutyGuards}</div><div class="mg-stat-lbl">Active Personnel</div></div>
            <div class="mg-stat"><div class="mg-stat-val" style="color:#fff">${todaysDeploys.length}</div><div class="mg-stat-lbl">Today's Ops</div></div>
            <div class="mg-stat"><div class="mg-stat-val" style="color:rgba(255,255,255,0.4)">${shifts.length}</div><div class="mg-stat-lbl">Total Deployments</div></div>
        `;
        
        // Re-render guard list with updated duty status
        mgRenderGuards();
        // Re-render shift pairs
        mgRenderShiftPairs();
    } catch(e) { console.error(e); }
};

/* ── Shift Pair Renderer ──────────────────────────────── */
function mgRenderShiftPairs(){
    const el = $('shiftPairsList');
    if (!el) return;
    
    // Group non-completed shifts by device ID
    const pairs = {};
    const relevant = allDeploys.filter(s => !s.is_completed);
    
    relevant.forEach(s => {
        const devId = s.device || 'unbound';
        if (!pairs[devId]) pairs[devId] = { device_id: devId, device_name: s.device_name || 'Unbound', guards: [] };
        if (s.guard_supervisor) {
            const guard = allGuards.find(g => g.id === s.guard_supervisor);
            if (guard && !pairs[devId].guards.find(g => g.id === guard.id)) {
                pairs[devId].guards.push({
                    id: guard.id,
                    name: guard.first_name + ' ' + guard.last_name,
                    callsign: guard.callsign || '',
                    shift: s.shift_type || guard.shift || 'Flex',
                    role: guard.role || 'guard',
                    is_online: guard.is_online || false,
                    is_active: s.is_active || false
                });
            }
        }
    });
    
    // Also add unassigned guards (no device) as standalone
    const assignedGuardIds = new Set();
    Object.values(pairs).forEach(p => p.guards.forEach(g => assignedGuardIds.add(g.id)));
    
    const pairArr = Object.values(pairs);
    if (!pairArr.length) {
        el.innerHTML = '<div class="mg-empty" style="padding:14px;font-size:0.58rem;"><i class="fas fa-plug"></i>No shift pairs configured</div>';
        return;
    }
    
    el.innerHTML = '<div class="mg-pair-list">' + pairArr.map((p, pi) => {
        const guards = p.guards;
        const activeCount = guards.filter(g => g.is_active).length;
        const totalGuards = guards.length;
        
        let statusClass = 'mg-pair-st-idle';
        let statusLabel = 'Idle';
        if (activeCount >= 2) { statusClass = 'mg-pair-st-active'; statusLabel = 'Both Active'; }
        else if (activeCount === 1) { statusClass = 'mg-pair-st-partial'; statusLabel = 'Partial'; }
        else if (totalGuards > 0) { statusClass = 'mg-pair-st-idle'; statusLabel = 'Standby'; }
        
        const SHIFT_COLORS = { Day: '#FFD54F', Night: '#7986cb', Flex: '#EF9F27' };
        const ROLE_COLORS = { guard: 'rgba(211,47,47,0.15)', supervisor: 'rgba(239,159,39,0.15)' };
        const ROLE_ICONS = { guard: 'fa-user-shield', supervisor: 'fa-star' };
        
        const renderGuard = (g, idx) => `
            <div class="mg-pair-guard ${g ? '' : 'empty'}" ${g ? '' : 'onclick="mgOpenModal(\'blueprint-shift\')"'} title="${g ? g.callsign : 'Assign guard'}">
                ${g ? `
                <div class="mg-pair-av" style="background:${ROLE_COLORS[g.role]||'rgba(211,47,47,0.15)'}; position:relative;">
                    <i class="fas ${ROLE_ICONS[g.role]||'fa-user-shield'}" style="color:${SHIFT_COLORS[g.shift]||'#fff'};font-size:0.55rem;"></i>
                    ${g.is_online ? '<span style="position:absolute;bottom:-1px;right:-1px;width:6px;height:6px;border-radius:50%;background:#5DCAA5;border:1.5px solid #0D0D14;"></span>' : ''}
                </div>
                <div class="mg-pair-g-info">
                    <div class="mg-pair-g-name">${g.name}</div>
                    <div class="mg-pair-g-meta">
                        <span class="mp-g-shift"><span style="color:${SHIFT_COLORS[g.shift]||'#fff'}">●</span> ${g.shift}</span>
                        ${g.callsign ? ' <span style="opacity:0.4;">|</span> ' + g.callsign : ''}
                    </div>
                </div>
                ${g.is_active ? '<span style="width:6px;height:6px;border-radius:50%;background:#5DCAA5;flex-shrink:0;box-shadow:0 0 6px rgba(93,202,165,0.4);"></span>' : ''}
                ` : `<span style="opacity:0.5;font-size:0.55rem;font-weight:700;">Empty slot</span>`}
            </div>
        `;
        
        const guard1 = guards[0] || null;
        const guard2 = guards[1] || null;
        
        return `
        <div class="mg-pair-card">
            <div class="mg-pair-head">
                <div class="mg-pair-callsign"><i class="fas fa-link"></i> ${p.device_name}</div>
                <span class="mg-pair-status ${statusClass}">${statusLabel}</span>
            </div>
            <div class="mg-pair-body">
                ${renderGuard(guard1, 0)}
                <div class="mg-pair-connect">
                    <div class="line"></div>
                    <i class="fas fa-arrows-left-right"></i>
                    <div class="line"></div>
                </div>
                ${renderGuard(guard2, 1)}
            </div>
            <div class="mg-pair-foot">
                <div class="mg-pair-device">
                    <i class="fas fa-microchip"></i> ${p.device_name}
                    ${guards.length > 0 ? '<span style="opacity:0.4;">·</span> ' + guards.length + ' guard' + (guards.length > 1 ? 's' : '') : ''}
                </div>
                <div class="mg-pair-actions">
                    <button type="button" class="mg-btn mg-btn-xs" onclick="mgOpenModal('blueprint-shift')" title="Assign guard"><i class="fas fa-user-plus"></i></button>
                    <button type="button" class="mg-btn mg-btn-xs mg-btn-danger" onclick="mgUnpairDevice(${p.device_id})" title="Release all"><i class="fas fa-link-slash"></i></button>
                </div>
            </div>
        </div>`;
    }).join('') + '</div>';
}

/* ── Unpair device (release all guards) ── */
window.mgUnpairDevice = async function(deviceId){
    if (!deviceId || deviceId === 'unbound') return;
    if (!confirm('Release all guards from this device?')) return;
    try {
        // End all active shifts for this device
        const deps = allDeploys.filter(s => s.device === deviceId && !s.is_completed);
        for (const s of deps) {
            await api('/api/shifts/' + s.id + '/', { method: 'PATCH', body: JSON.stringify({ is_active: false, is_completed: true }) });
        }
        toast('Device released');
        mgRefreshBlueprintShift();
    } catch(e) { toast('Failed to release', true); }
};

/* ── Inline Pair Form ─────────────────────────────── */
window.mgTogglePairForm = function(){
    var form = $('mgPairForm');
    var btn = $('mgPairToggleBtn');
    if (!form) return;
    var isOpen = form.style.display !== 'none' && !form.classList.contains('mg-form-collapsed');
    if (isOpen) {
        form.classList.remove('mg-form-slide');
        form.classList.add('mg-form-collapsed');
        if (btn) btn.innerHTML = '<i class="fas fa-plus"></i> Create Pair';
        return;
    }
    // Populate dropdowns with current data
    var devOpts = (allDevices||[]).map(function(d){
        return '<option value="'+d.id+'">'+d.device_name+' ('+(d.callsign||'No callsign')+')</option>';
    }).join('');
    $('mSpDevice').innerHTML = '<option value="">— Select device —</option>' + devOpts;

    var guardOpts = (allGuards||[]).map(function(g){
        var label = [g.first_name, g.last_name].filter(Boolean).join(' ') || g.username || 'Unnamed';
        return '<option value="'+g.id+'">'+label+' ('+(g.callsign||'N/A')+')</option>';
    }).join('');
    $('mSpGuard1').innerHTML = '<option value="">— Guard —</option>' + guardOpts;
    $('mSpGuard2').innerHTML = '<option value="">— Guard —</option>' + guardOpts;

    form.style.display = '';
    form.classList.remove('mg-form-collapsed');
    form.classList.add('mg-form-slide');
    if (btn) btn.innerHTML = '<i class="fas fa-times"></i> Cancel';
};

window.mgSubmitPairForm = async function(){
    var deviceId = $('mSpDevice').value;
    var g1 = $('mSpGuard1').value;
    var s1 = $('mSpShift1').value;
    var g2 = $('mSpGuard2').value;
    var s2 = $('mSpShift2').value;
    var start = $('mSpStart').value;
    var end = $('mSpEnd').value;

    if(!deviceId){ toast('Select a device', true); return; }
    if(!g1 && !g2){ toast('Select at least one guard', true); return; }

    var calls = [];
    if(g1) calls.push(api('/api/assign-guard-to-blueprint-shift/',{method:'POST',body:JSON.stringify({
        guard_id: parseInt(g1), device_id: parseInt(deviceId),
        shift_type: s1, scheduled_start: start, scheduled_end: end
    })}));
    if(g2) calls.push(api('/api/assign-guard-to-blueprint-shift/',{method:'POST',body:JSON.stringify({
        guard_id: parseInt(g2), device_id: parseInt(deviceId),
        shift_type: s2, scheduled_start: start, scheduled_end: end
    })}));

    var results = await Promise.all(calls);
    var ok = results.every(function(r){ return r.ok; });
    if(!ok){
        var errs = await Promise.all(results.filter(function(r){ return !r.ok; }).map(function(r){ return r.json().catch(function(){ return {}; }); }));
        toast('Pair creation failed: '+(errs[0]?.detail||'error').slice(0,80), true);
        return;
    }
    toast('Shift pair created — ' + (g1&&g2?'2 guards':'1 guard') + ' linked to device');
    mgTogglePairForm(); // close form
    mgRefreshBlueprintShift();
};

window.mgRenderBlueprintActiveDeployments = function(shifts){
    const el=$('callsignList');
    const relevant = shifts.filter(s => !s.is_completed);
    if(!relevant.length){
        el.innerHTML='<div class="mg-tl-empty"><i class="fas fa-satellite-dish"></i>No active or upcoming deployments</div>';
        return;
    }

    const active = relevant.filter(s => s.is_active);
    const upcoming = relevant.filter(s => !s.is_active);

    const renderRow=(s, type)=>{
        const guard=s.guard_supervisor_name || '';
        const device=s.device_name || '';
        const route = s.route_name || 'Standby';
        const isDeviceOnly = !s.guard_supervisor_name && !s.operator_name && !s.guard_callsign;
        const who = isDeviceOnly ? (device || 'HW Unit') : (s.operator_name || guard || 'Unassigned');
        const whoIcon = isDeviceOnly ? 'fa-microchip' : 'fa-user-shield';
        const timeStr = s.scheduled_date ? s.scheduled_date.substring(11,16) : '';
        const dateStr = s.scheduled_date ? s.scheduled_date.substring(0,10) : '';
        var elapsedStr = '';
        if (s.is_active && s.assigned_at) {
            var diff = Date.now() - new Date(s.assigned_at).getTime();
            var mins = Math.floor(diff / 60000);
            elapsedStr = mins < 60 ? mins + 'm ago' : Math.floor(mins/60) + 'h ' + (mins%60) + 'm';
        }
        const dotIcon = type === 'live' ? 'fa-play' : 'fa-clock';
        return '<div class="mg-tl-row" onclick="window.location.href=\'/dispatch/\'"' + (s.guard_supervisor ? ' data-guard-id="' + s.guard_supervisor + '"' : '') + '>' +
            '<div class="mg-tl-dot ' + type + '"><i class="fas ' + dotIcon + '"></i></div>' +
            '<div class="mg-tl-body">' +
            '<div class="mg-tl-title"><i class="fas ' + whoIcon + '" style="margin-right:4px;opacity:0.5;"></i>' + who + '</div>' +
            '<div class="mg-tl-meta">' +
            (route ? '<span><i class="fas fa-route"></i>' + route + '</span>' : '') +
            (device && !isDeviceOnly ? '<span><i class="fas fa-microchip"></i>' + device + '</span>' : '') +
            (timeStr ? '<span><i class="far fa-clock"></i>' + dateStr + ' ' + timeStr + '</span>' : '') +
            (elapsedStr ? '<span><i class="fas fa-hourglass-half"></i>' + elapsedStr + '</span>' : '') +
            '</div></div>' +
            '<div class="mg-tl-actions">' +
            (s.is_active ?
                '<button type="button" class="mg-btn mg-btn-xs mg-btn-danger" onclick="event.stopPropagation();mgEndShift(' + s.id + ')" title="End Mission"><i class="fas fa-stop"></i></button>' :
                '<button type="button" class="mg-btn mg-btn-xs mg-btn-primary" onclick="event.stopPropagation();mgActivateUpcoming(' + s.id + ')" title="Deploy Now"><i class="fas fa-play"></i></button>'
            ) +
            '<button type="button" class="mg-btn mg-btn-xs" onclick="event.stopPropagation();mgEditAssignmentCallsign(' + s.id + ')" title="Configure"><i class="fas fa-sliders"></i></button>' +
            '</div></div>';
    };

    el.innerHTML = '<div class="mg-timeline">' +
        (active.length ? '<div class="mg-tl-section"><div class="mg-tl-section-hdr"><i class="fas fa-satellite-dish" style="color:var(--r-teal);font-size:0.45rem;"></i> Live (' + active.length + ')</div>' + active.map(function(s) { return renderRow(s, 'live'); }).join('') + '</div>' : '') +
        (upcoming.length ? '<div class="mg-tl-section"><div class="mg-tl-section-hdr"><i class="fas fa-hourglass-start" style="color:var(--r-mute);font-size:0.45rem;"></i> Queued (' + upcoming.length + ')</div>' + upcoming.map(function(s) { return renderRow(s, 'queued'); }).join('') + '</div>' : '') +
        '</div>';
}


function mgRenderCallsignStats(){
    const total = allCallsigns.length;
    const assigned = allCallsigns.filter(c => c.current_guard).length;
    const day = allCallsigns.filter(c => c.active_shift === 'Day').length;
    const night = allCallsigns.filter(c => c.active_shift === 'Night').length;
    
    $('callsignStats').innerHTML = `
        <div class="mg-stat"><div class="mg-stat-val">${total}</div><div class="mg-stat-lbl">Hardware Units</div></div>
        <div class="mg-stat"><div class="mg-stat-val green">${assigned}</div><div class="mg-stat-lbl">Personnel on Shift</div></div>
        <div class="mg-stat"><div class="mg-stat-val amber">${day}</div><div class="mg-stat-lbl">Day Deployment</div></div>
        <div class="mg-stat"><div class="mg-stat-val blue">${night}</div><div class="mg-stat-lbl">Night Deployment</div></div>
    `;
    $('tcStaff').textContent = total;
}

function mgRenderCallsigns(){
    const container = $('callsignList');
    if(!allCallsigns.length){ container.innerHTML='<div class="mg-empty"><i class="fas fa-clock-rotate-left"></i>No shift assignments found</div>'; return; }

    container.innerHTML = `
        <table style="width: 100%; border-collapse: separate; border-spacing: 0 8px; margin-top: -8px;">
            <thead>
                <tr>
                    <th style="padding-left:18px;">Callsign</th>
                    <th>Tactical Device</th>
                    <th>Officer</th>
                    <th>Duty Shift</th>
                    <th>Mission Status</th>
                    <th style="text-align:right; padding-right:18px;">Registry Actions</th>
                </tr>
            </thead>
            <tbody>
                ${allCallsigns.map(cs => {
                    const shiftBadge = cs.active_shift 
                        ? `<span class="mg-badge ${cs.active_shift==='Day'?'mg-b-day':'mg-b-night'}">${cs.active_shift} Shift</span>`
                        : '<span class="mg-badge mg-b-off">Unassigned</span>';
                    
                    const guardBadge = `<span class="mg-badge ${cs.current_guard ? 'mg-b-active' : 'mg-b-off'}" style="font-size:0.75rem; padding:4px 10px;">
                        <i class="fas fa-user-shield" style="margin-right:6px;"></i>${cs.guard_name}
                    </span>`;

                    const missionStatus = cs.current_guard 
                        ? `<div style="font-size:0.78rem; color:var(--primary-light); font-weight:700;"><i class="fas fa-route" style="margin-right:5px; opacity:0.5;"></i>${cs.active_mission}</div>`
                        : '<div style="font-size:0.7rem; color:rgba(255,255,255,0.2);">Available for Duty</div>';

                    const lastSeenStr = cs.last_seen 
                        ? new Date(cs.last_seen).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})
                        : 'Offline';

                    return `
                    <tr>
                        <td style="font-weight:900; color:var(--primary-light); padding-left:18px; font-size:1.05rem;">${cs.callsign}</td>
                        <td>
                            <div style="font-weight:700; color:#fff; display:flex; align-items:center;">
                                <span class="status-led ${cs.is_online?'active':'inactive'}" style="margin-right:8px;"></span>
                                ${cs.device_name || 'Unit'}
                            </div>
                            <div style="font-size:0.65rem; color:rgba(255,255,255,0.4);"><i class="fas fa-clock" style="margin-right:4px;"></i>Last: ${lastSeenStr}</div>
                        </td>
                        <td>${guardBadge}</td>
                        <td>${shiftBadge}</td>
                        <td>${missionStatus}</td>
                        <td style="text-align:right; padding-right:18px;">
                            <button type="button" class="mg-btn mg-btn-sm mg-btn-primary" onclick="mgEditCallsign(${cs.id})" title="Modify Assignment">
                                <i class="fas fa-user-gear"></i> Manage
                            </button>
                        </td>
                    </tr>`;
                }).join('')}
            </tbody>
        </table>`;
}

window.mgEditCallsign = function(id){
    const cs = allCallsigns.find(x => x.id === id);
    if(!cs) return;
    editId = id;
    mgOpenModal('callsign', cs);
};

/* ══════════════════════════════════════════════════
   SHIFT CALENDAR
══════════════════════════════════════════════════ */
function mgRenderCal(){
    var titleEl=$('mgCalTitle'), grid=$('mgCalGrid');
    if(!grid) return; // calendar moved to CalendarComponent
    const MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
    if(titleEl) titleEl.textContent=`${MONTHS[calDate.getMonth()]} ${calDate.getFullYear()}`;
    const today=new Date();

    const dayGuards=allGuards.filter(g=>g.shift==='Day'||g.shift==='Flex');
    const nightGuards=allGuards.filter(g=>g.shift==='Night'||g.shift==='Flex');

    grid.innerHTML=['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
        .map(d=>`<div class="mg-cal-dow">${d}</div>`).join('');

    const firstDay=new Date(calDate.getFullYear(),calDate.getMonth(),1).getDay();
    const daysInMonth=new Date(calDate.getFullYear(),calDate.getMonth()+1,0).getDate();

    for(let i=0;i<firstDay;i++) grid.innerHTML+=`<div class="mg-cal-cell" style="opacity:0;pointer-events:none;"></div>`;

    for(let d=1;d<=daysInMonth;d++){
        const isToday=today.getDate()===d&&today.getMonth()===calDate.getMonth()&&today.getFullYear()===calDate.getFullYear();
        const isSel=selCalDay===d;
        
        // Visual indicators for deployments on this day
        const dateStr = `${calDate.getFullYear()}-${String(calDate.getMonth() + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
        const dayShifts = allDeploys.filter(s => (s.scheduled_date || s.assigned_at || '').split('T')[0] === dateStr);
        
        let indicators = '';
        if(dayShifts.length > 0) {
            const hasActive = dayShifts.some(s => s.is_active);
            const hasUpcoming = dayShifts.some(s => !s.is_active && !s.is_completed);
            if(hasActive) indicators += `<span class="mg-cal-dot" style="background:#5DCAA5;" title="Active Personnel"></span>`;
            if(hasUpcoming) indicators += `<span class="mg-cal-dot" style="background:#EF9F27;" title="Upcoming Mission"></span>`;
        }

        grid.innerHTML+=`
            <div class="mg-cal-cell${isToday?' today':''}${isSel?' selected':''}" onclick="mgDayClick(${d})">
                <div style="display:flex; justify-content:space-between; align-items:start;">
                    <div class="mg-cal-dn${isToday?' today-num':''}">${d}</div>
                    <div style="display:flex;">${indicators}</div>
                </div>
                <div class="mg-cal-slot day" style="font-size:0.5rem;"><i class="fas fa-sun"></i>${dayGuards.length}</div>
                <div class="mg-cal-slot night" style="font-size:0.5rem;"><i class="fas fa-moon"></i>${nightGuards.length}</div>
            </div>`;
    }
}

window.mgCalMonth=function(dir){
    if(window.CalendarComponent){
        var d = new Date();
        d.setMonth(d.getMonth()+dir);
        CalendarComponent.setDate(d);
    }
};
window.mgCalToday=function(){
    calDate=new Date(); selCalDay=null;
    if(window.CalendarComponent) CalendarComponent.setDate(new Date());
    mgRenderCal();
};

window.mgDayClick=function(day){
    selCalDay=day;
    mgRenderCal();
    mgShowDayDetail(day);
};

function mgShowDayDetail(day){
    const MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
    const label=`${day} ${MONTHS[calDate.getMonth()]} ${calDate.getFullYear()}`;
    const dateStr = `${calDate.getFullYear()}-${String(calDate.getMonth() + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const dayG=allGuards.filter(g=>g.shift==='Day');
    const nightG=allGuards.filter(g=>g.shift==='Night');
    const flexG=allGuards.filter(g=>g.shift==='Flex');

    // Deployments on this day
    var dayDeploys = [];
    if (typeof allDeploys !== 'undefined' && Array.isArray(allDeploys)) {
        dayDeploys = allDeploys.filter(function(s) { return (s.scheduled_date || s.assigned_at || '').split('T')[0] === dateStr; });
    }

    const renderGuardRow=g=>{
        const name=(g.first_name&&g.last_name)?`${g.first_name} ${g.last_name}`:(g.username||'?');
        // Find if this guard has a deployment on this day
        var gDeploy = null;
        if (typeof allDeploys !== 'undefined') {
            gDeploy = allDeploys.find(function(s) { return String(s.guard_supervisor) === String(g.id) && (s.scheduled_date || s.assigned_at || '').split('T')[0] === dateStr; });
        }
        var statusColor = 'rgba(255,255,255,0.08)';
        var statusIcon = '';
        if (gDeploy && gDeploy.is_active) { statusColor = '#5DCAA5'; statusIcon = '<span class="mg-cal-dot" style="background:#5DCAA5;width:6px;height:6px;margin-right:4px;"></span>'; }
        else if (gDeploy && !gDeploy.is_completed) { statusColor = '#EF9F27'; statusIcon = '<span class="mg-cal-dot" style="background:#EF9F27;width:6px;height:6px;margin-right:4px;"></span>'; }
        var routeInfo = gDeploy ? gDeploy.route_name || '' : '';
        return '<div style="padding:5px 0;border-bottom:1px solid var(--border);font-size:.72rem;display:flex;align-items:center;gap:6px;">' +
            '<span style="width:6px;height:6px;border-radius:50%;background:' + statusColor + ';flex-shrink:0;"></span>' +
            '<i class="fas fa-user-shield" style="opacity:.4;width:12px;font-size:0.6rem;"></i> ' + name +
            '<span class="mg-badge mg-b-idle" style="margin-left:auto;font-size:.55rem;">' + (g.callsign||'\u2014') + '</span>' +
            (routeInfo ? '<span style="font-size:0.55rem;color:var(--primary-light);max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"><i class="fas fa-route" style="opacity:.5;"></i> ' + routeInfo + '</span>' : '') +
        '</div>';
    };

    // Render deployment entries for the day
    var deployHtml = '';
    if (dayDeploys.length) {
        deployHtml = '<div style="margin-top:12px;">' +
            '<span class="mg-lbl" style="font-size:0.55rem;margin-bottom:6px;"><i class="fas fa-tasks" style="margin-right:4px;"></i> Scheduled Operations (' + dayDeploys.length + ')</span>' +
            dayDeploys.map(function(s) {
                var who = s.guard_supervisor_name || s.operator_name || (s.device_name || 'HW Unit');
                var st = s.is_active ? 'Live' : (s.is_completed ? 'Done' : 'Queued');
                var stCls = s.is_active ? 'mg-b-online' : (s.is_completed ? 'mg-b-idle' : 'mg-b-off');
                var route = s.route_name || 'Standby';
                var timeStr = s.scheduled_date ? s.scheduled_date.substring(11,16) : '';
                return '<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.03);font-size:0.65rem;">' +
                    '<span style="width:5px;height:5px;border-radius:50%;background:' + (s.is_active ? '#5DCAA5' : 'rgba(255,255,255,0.15)') + ';flex-shrink:0;"></span>' +
                    '<span style="font-weight:700;color:#fff;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + who + '</span>' +
                    '<span style="color:rgba(255,255,255,0.3);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"><i class="fas fa-route" style="opacity:.5;margin-right:3px;"></i>' + route + '</span>' +
                    (timeStr ? '<span style="color:rgba(255,255,255,0.2);white-space:nowrap;"><i class="far fa-clock"></i> ' + timeStr + '</span>' : '') +
                    '<span class="mg-badge ' + stCls + '" style="font-size:0.45rem;padding:1px 6px;">' + st + '</span>' +
                '</div>';
            }).join('') +
        '</div>';
    }

    $('mgDayDetail').innerHTML=`
        <div class="mg-day-detail">
            <div style="font-size:.78rem;font-weight:900;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between;">
                <span><i class="fas fa-calendar-day" style="color:var(--primary-light);margin-right:6px;"></i>${label}</span>
                <span style="font-size:0.55rem;font-weight:700;color:rgba(255,255,255,0.25);">${dayDeploys.length} ops · ${dayG.length+nightG.length+flexG.length} personnel</span>
            </div>
            <div class="mg-g2">
                <div>
                    <span class="mg-lbl" style="color:#FFD54F;font-size:0.55rem;margin-bottom:4px;"><i class="fas fa-sun"></i> Day (${dayG.length})</span>
                    ${dayG.length?dayG.map(renderGuardRow).join(''):'<div style="font-size:.65rem;color:rgba(255,255,255,.25);padding:4px 0;">None assigned</div>'}
                </div>
                <div>
                    <span class="mg-lbl" style="color:#7986cb;font-size:0.55rem;margin-bottom:4px;"><i class="fas fa-moon"></i> Night (${nightG.length})</span>
                    ${nightG.length?nightG.map(renderGuardRow).join(''):'<div style="font-size:.65rem;color:rgba(255,255,255,.25);padding:4px 0;">None assigned</div>'}
                </div>
            </div>
            ${flexG.length ? '<div style="margin-top:6px;"><span class="mg-lbl" style="color:rgba(255,255,255,0.3);font-size:0.5rem;">Flex</span><div style="display:flex;gap:4px;flex-wrap:wrap;">' + flexG.map(function(g) { return '<span style="font-size:0.6rem;padding:2px 8px;background:rgba(255,255,255,0.04);border-radius:6px;color:rgba(255,255,255,0.4);">' + (g.first_name||g.username) + '</span>'; }).join('') + '</div></div>' : ''}
            ${deployHtml}
            <div style="margin-top:10px;display:flex;gap:6px;">
                <button type="button" class="mg-btn mg-btn-sm mg-btn-primary" onclick="window.location.href='/dispatch/'">
                    <i class="fas fa-rocket"></i> Dispatch
                </button>
                <button type="button" class="mg-btn mg-btn-sm" onclick="mgOpenModal('blueprint-shift')">
                    <i class="fas fa-plus"></i> New Assignment
                </button>
            </div>
        </div>`;
}

/* ══════════════════════════════════════════════════
   DEVICES
══════════════════════════════════════════════════ */
async function mgLoadDevices(){
    try{
        // Tab now loads both devices and map-objects (checkpoints)
        const [res, cpRes] = await Promise.all([api('/api/devices/'), api('/api/map-objects/')]);
        if(res.ok){ const d=await res.json(); allDevices=Array.isArray(d)?d:(d.results||[]); }
        if(cpRes.ok){ const d=await cpRes.json(); allAssets=Array.isArray(d)?d:(d.results||[]); }
    }catch(e){}
    mgRenderDeviceStats();
    mgRenderDevices();
}

function mgRenderDeviceStats(){
    const total=allDevices.length;
    const online=allDevices.filter(d=>d.is_online).length;
    const assigned=allDevices.filter(d=>d.assigned_callsign).length;
    const batLow=allDevices.filter(d=>d.battery_pct!==null&&d.battery_pct!==undefined&&parseInt(d.battery_pct)<=20).length;
    const ttsPending=allDevices.filter(d=>d.tts_acked===false && d.tts_pending).length;
    const onMission=allDevices.filter(d=>d.current_mission && d.current_mission.route_name).length;
    const nfcPending=allDevices.filter(d=>d.nfc_fetch_requested).length;
    $('deviceStats').innerHTML=`
        <div class="mg-stat"><div class="mg-stat-val">${total}</div><div class="mg-stat-lbl">Devices</div></div>
        <div class="mg-stat"><div class="mg-stat-val green">${online}</div><div class="mg-stat-lbl">Online</div></div>
        <div class="mg-stat"><div class="mg-stat-val blue">${onMission}</div><div class="mg-stat-lbl">On Mission</div></div>
        <div class="mg-stat"><div class="mg-stat-val ${ttsPending ? 'amber' : ''}">${ttsPending}</div><div class="mg-stat-lbl">TTS Pending</div></div>
        <div class="mg-stat"><div class="mg-stat-val ${nfcPending ? 'amber' : ''}">${nfcPending}</div><div class="mg-stat-lbl">NFC Fetch</div></div>
        <div class="mg-stat"><div class="mg-stat-val red">${total - online}</div><div class="mg-stat-lbl">Offline</div></div>
    `;
    var tcFleet = $('tcFleet');
    if (tcFleet) tcFleet.textContent = String(total + (allAssets||[]).length);
    var deviceCountBadge = $('deviceCountBadge');
    if (deviceCountBadge) deviceCountBadge.textContent = String(total);
}

window.mgDeviceFilter=function(f,el){
    deviceFilter=f;
    $$('#mgPanelFleet .mg-filter-chip').forEach(c=>c.classList.remove('active'));
    if(el) el.classList.add('active');
    mgRenderDevices();
};
window.mgFilterDevices=function(){ mgRenderDevices(); };

let _deviceSearchTimer = null;
window.mgFilterDevicesDebounced = function() {
    clearTimeout(_deviceSearchTimer);
    _deviceSearchTimer = setTimeout(function(){ mgRenderDevices(); }, 200);
};

function mgRenderDevices(){
    const q=($('deviceSearch')?.value||'').toLowerCase();
    let list = allDevices.slice();
    if(deviceFilter==='online') list=list.filter(d=>d.is_online);
    if(deviceFilter==='mission') list=list.filter(d=>d.current_mission && d.current_mission.route_name);
    if(deviceFilter==='available') list=list.filter(d=>!d.current_mission || !d.current_mission.route_name);
    if(deviceFilter==='nfc') list=list.filter(d=>d.nfc_fetch_requested);
    if(q) list=list.filter(d=>(d.device_name||d.device_id||'').toLowerCase().includes(q));

    const container=$('deviceList');
    if(!list.length){
        if (q || deviceFilter !== 'all') {
            container.innerHTML='<div class="mg-empty"><i class="fas fa-search"></i>No devices match your filter</div>';
        } else {
            container.innerHTML='<div class="mg-empty"><i class="fas fa-microchip" style="font-size:1.8rem;"></i>No devices registered yet<div style="font-size:0.6rem;color:rgba(255,255,255,0.15);margin-top:6px;">Register your first device to get started</div></div>';
        }
        return;
    }

    container.innerHTML=list.map((d,i)=>{
        var lastSeen = d.last_seen || d.last_ping || '';
        var lastSeenStr = '';
        if (lastSeen) {
            var diff = Math.floor((new Date() - new Date(lastSeen)) / 1000);
            if (diff < 60) lastSeenStr = 'just now';
            else if (diff < 3600) lastSeenStr = Math.floor(diff/60) + 'm ago';
            else if (diff < 86400) lastSeenStr = Math.floor(diff/3600) + 'h ago';
            else lastSeenStr = Math.floor(diff/86400) + 'd ago';
        }
        var batPct = d.battery_pct != null ? parseInt(d.battery_pct) : null;
        var batColor = batPct != null ? (batPct > 50 ? '#5DCAA5' : batPct > 20 ? '#EF9F27' : '#FF6659') : '';
        var batIcon = batPct != null ? (batPct > 50 ? 'fa-battery-three-quarters' : batPct > 20 ? 'fa-battery-quarter' : 'fa-battery-empty') : '';
        var callsign = d.assigned_callsign || d.callsign || '';
        var accentColor = d.is_online ? '#5DCAA5' : 'rgba(255,255,255,0.15)';
        var mission = d.current_mission || null;
        var hasMission = mission && mission.route_name;
        return `<div class="mg-card mg-card-device${d.nfc_fetch_requested ? ' staged' : ''}" data-device-id="${d.id}" style="cursor:pointer;--i:${i};--card-accent:${hasMission ? '#6C8EEF' : accentColor};">
            <div class="mg-card-topline" style="background:${hasMission ? '#6C8EEF' : accentColor};"></div>
            <div class="mg-card-avatar" style="background:${d.is_online?'rgba(29,158,117,.12)':'rgba(255,255,255,.03)'};position:relative;width:42px;height:42px;border-radius:14px;">
                <i class="fas fa-mobile-screen" style="color:${d.is_online?'#5DCAA5':'rgba(255,255,255,.25)'};font-size:0.95rem;"></i>
                ${d.is_online ? '<span class="mg-card-live-dot" style="position:absolute;bottom:-1px;right:-1px;width:10px;height:10px;border-radius:50%;background:#5DCAA5;border:2px solid #14141c;box-shadow:0 0 6px rgba(93,202,165,0.4);"></span>' : ''}
            </div>
            <div class="mg-card-info">
                <div class="mg-card-name" style="display:flex;align-items:center;gap:8px;">
                    <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;">${d.device_name || d.device_id || 'Device #'+d.id}</span>
                    <span style="font-size:0.58rem;font-weight:700;color:${d.is_online?'rgba(93,202,165,0.7)':'rgba(255,255,255,0.2)'};">${d.is_online?'● Live':'○ Offline'}</span>
                </div>
                <div class="mg-card-sub" style="display:flex;align-items:center;gap:10px;margin-top:3px;">
                    <span style="display:flex;align-items:center;gap:4px;">
                        <i class="fas fa-user-tag" style="font-size:0.5rem;color:var(--primary-light);opacity:0.6;"></i>
                        <span style="color:#fff;font-weight:700;font-size:0.72rem;">${callsign || d.device_id || '—'}</span>
                    </span>
                    ${batPct != null ? `<span style="display:flex;align-items:center;gap:3px;font-size:0.58rem;color:${batColor}"><i class="fas ${batIcon}" style="font-size:0.55rem;"></i>${batPct}%</span>` : ''}
                    ${lastSeenStr ? `<span style="font-size:0.55rem;color:rgba(255,255,255,0.25);">${lastSeenStr}</span>` : ''}
                </div>
                ${hasMission ? `<div style="margin-top:6px;"><div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;"><i class="fas fa-route" style="font-size:0.5rem;color:#6C8EEF;"></i><span style="font-size:0.55rem;color:#6C8EEF;font-weight:700;">${mission.route_name}</span><span style="margin-left:auto;font-size:0.55rem;font-weight:800;color:#5DCAA5;">${mission.completed_checkpoints}/${mission.total_checkpoints}</span></div><div style="height:4px;background:rgba(255,255,255,0.06);border-radius:2px;overflow:hidden;"><div style="height:100%;width:${mission.progress_pct}%;background:linear-gradient(90deg,#6C8EEF,#5DCAA5);border-radius:2px;transition:width .3s;"></div></div>${mission.next_checkpoint ? `<div style="margin-top:3px;font-size:0.5rem;color:rgba(255,255,255,0.35);"><i class="fas fa-arrow-right" style="font-size:0.4rem;margin-right:3px;"></i>${mission.next_checkpoint.name} ${mission.next_checkpoint.planned_time ? '· ' + mission.next_checkpoint.planned_time : ''}</div>` : ''}</div>` : ''}
                <div style="display:flex;align-items:center;gap:4px;margin-top:5px;flex-wrap:wrap;">
                    ${d.nfc_fetch_requested ? '<span style="font-size:0.48rem;color:#EF9F27;background:rgba(239,159,39,0.1);padding:1px 7px;border-radius:4px;border:1px solid rgba(239,159,39,0.2);display:inline-flex;align-items:center;gap:3px;"><i class="fas fa-wifi" style="font-size:0.4rem;"></i>NFC Pending</span>' : ''}
                    ${d.tts_acked === false && d.tts_pending ? '<span style="font-size:0.48rem;color:#EF9F27;background:rgba(239,159,39,0.1);padding:1px 7px;border-radius:4px;border:1px solid rgba(239,159,39,0.2);display:inline-flex;align-items:center;gap:3px;"><i class="fas fa-volume-high" style="font-size:0.4rem;"></i>TTS pending</span>' : ''}
                    ${!hasMission && d.is_online ? '<span style="font-size:0.48rem;color:rgba(93,202,165,0.5);background:rgba(93,202,165,0.08);padding:1px 7px;border-radius:4px;border:1px solid rgba(93,202,165,0.15);">Available</span>' : ''}
                    ${!hasMission && !d.is_online ? '<span style="font-size:0.48rem;color:rgba(255,255,255,0.2);">Idle</span>' : ''}
                    ${[d.manufacturer, d.model].filter(Boolean).join(' ') ? `<span style="font-size:0.52rem;color:rgba(255,255,255,0.2);">${[d.manufacturer, d.model].filter(Boolean).join(' ')}</span>` : ''}
                </div>
            </div>
            <div class="mg-card-actions" style="gap:3px;">
                <button type="button" class="mg-btn mg-btn-xs" onclick="mgDeviceControls(${d.id}, this)" title="Configure" style="background:rgba(108,142,239,0.12);color:#6C8EEF;border-color:rgba(108,142,239,0.15);"><i class="fas fa-sliders"></i></button>
                <button type="button" class="mg-btn mg-btn-xs" onclick="mgSwapOperator(${d.id},'${(d.device_name||d.device_id||'Device').replace(/'/g,"\\'")}')" title="Swap Operator" style="background:rgba(245,166,35,0.12);color:#F5A623;border-color:rgba(245,166,35,0.15);"><i class="fas fa-exchange-alt"></i></button>
                <button type="button" class="mg-btn mg-btn-xs mg-btn-danger" onclick="mgDelete('devices',${d.id},'devices')" title="Remove"><i class="fas fa-trash-alt"></i></button>
            </div>
        </div>`;
    });
}

/* ── Device Control Dropdown ─────────────────────── */
let _dcDeviceId = null;
let _dcPollTimers = [];

window.mgDeviceControls = function(deviceId, btn) {
    const d = allDevices.find(x => x.id === deviceId);
    if(!d) return;

    // If same device already open, close it
    if (_dcDeviceId === deviceId && $('mgDcDropdown').classList.contains('open')) {
        mgDcClose();
        return;
    }
    // Close any other first
    if (_dcDeviceId) mgDcClose();

    _dcDeviceId = deviceId;
    const gpsAcc = d.gps_accuracy_threshold || 5;
    const callsign = d.assigned_callsign || d.callsign || d.device_id || '—';

    // Build guard options
    var guardOpts = (allGuards||[]).map(function(g) {
        var label = [g.first_name, g.last_name].filter(Boolean).join(' ') || g.username || 'Unnamed';
        var sel = d.assigned_guard_id === g.id ? ' selected' : '';
        var suffix = g.callsign ? ' (' + g.callsign + ')' : '';
        return '<option value="' + g.id + '"' + sel + '>' + label + suffix + '</option>';
    }).join('');

    var devName = d.device_name || d.device_id || 'Device #'+d.id;
    var onlineColor = d.is_online ? '#5DCAA5' : 'rgba(255,255,255,0.3)';
    var onlineBg = d.is_online ? 'rgba(93,202,165,0.12)' : 'rgba(255,255,255,0.04)';

    // Build menu content (using string concat to avoid template-literal nesting issues)
    var html = '';
    // Header
    html += '<div style="display:flex;align-items:center;gap:10px;padding:14px 18px;border-bottom:1px solid rgba(255,255,255,0.06);flex-shrink:0;background:rgba(0,0,0,0.12);">';
    html +=   '<div style="width:36px;height:36px;border-radius:10px;background:' + onlineBg + ';color:' + onlineColor + ';display:flex;align-items:center;justify-content:center;font-size:0.95rem;flex-shrink:0;"><i class="fas fa-mobile-screen"></i></div>';
    html +=   '<div style="flex:1;min-width:0;"><div style="font-size:0.85rem;font-weight:800;color:#fff;">' + devName + '</div><div style="font-size:0.58rem;color:rgba(255,255,255,0.35);margin-top:1px;">' + callsign + (d.manufacturer ? ' &middot; ' + d.manufacturer : '') + (d.model ? ' ' + d.model : '') + ' &middot; ' + (d.is_online ? 'Online' : 'Offline') + '</div></div>';
    html +=   '<button type="button" onclick="mgDcClose()" style="width:28px;height:28px;border-radius:7px;border:none;background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.4);cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:0.8rem;transition:background .15s;" onmouseover="this.style.background=\'rgba(255,255,255,0.12)\'" onmouseout="this.style.background=\'rgba(255,255,255,0.06)\'"><i class="fas fa-xmark"></i></button>';
    html += '</div>';
    // Body
    html += '<div style="flex:1;overflow-y:auto;padding:18px 20px 14px;">';

    // Hardware & Identity
    html += '<div class="mg-dc-section"><div class="mg-dc-section-title"><i class="fas fa-microchip" style="color:rgba(255,255,255,0.3);"></i> Hardware &amp; Identity</div>';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">';
    html +=   '<div><label style="font-size:0.55rem;color:rgba(255,255,255,0.3);display:block;margin-bottom:3px;font-weight:700;">IMEI</label><input class="mg-dc-select" id="dcImei_' + deviceId + '" value="' + (d.imei||'') + '" placeholder="352656106111232" style="height:32px;font-size:0.7rem;"></div>';
    html +=   '<div><label style="font-size:0.55rem;color:rgba(255,255,255,0.3);display:block;margin-bottom:3px;font-weight:700;">IMSI</label><input class="mg-dc-select" id="dcImsi_' + deviceId + '" value="' + (d.imsi||'') + '" placeholder="310150123456789" style="height:32px;font-size:0.7rem;"></div>';
    html +=   '<div><label style="font-size:0.55rem;color:rgba(255,255,255,0.3);display:block;margin-bottom:3px;font-weight:700;">SIM Phone</label><input class="mg-dc-select" id="dcSimPhone_' + deviceId + '" value="' + (d.sim_phone_number||'') + '" placeholder="+254712345678" style="height:32px;font-size:0.7rem;"></div>';
    html +=   '<div><label style="font-size:0.55rem;color:rgba(255,255,255,0.3);display:block;margin-bottom:3px;font-weight:700;">OS Version</label><input class="mg-dc-select" id="dcOs_' + deviceId + '" value="' + (d.os_version||'') + '" placeholder="Android 14" style="height:32px;font-size:0.7rem;"></div>';
    html +=   '<div><label style="font-size:0.55rem;color:rgba(255,255,255,0.3);display:block;margin-bottom:3px;font-weight:700;">Manufacturer</label><input class="mg-dc-select" id="dcMan_' + deviceId + '" value="' + (d.manufacturer||'') + '" placeholder="Samsung" style="height:32px;font-size:0.7rem;"></div>';
    html +=   '<div><label style="font-size:0.55rem;color:rgba(255,255,255,0.3);display:block;margin-bottom:3px;font-weight:700;">Model</label><input class="mg-dc-select" id="dcModel_' + deviceId + '" value="' + (d.model||'') + '" placeholder="Galaxy S24" style="height:32px;font-size:0.7rem;"></div>';
    html += '</div></div>';
    html += '<hr class="mg-dc-divider" style="margin:14px 0;">';

    // Credentials & Assignment
    html += '<div class="mg-dc-section"><div class="mg-dc-section-title"><i class="fas fa-key" style="color:rgba(255,255,255,0.3);"></i> Credentials &amp; Assignment</div>';
    html += '<div class="mg-dc-row"><span class="mg-dc-label" style="min-width:75px;">Login Code</span><input class="mg-dc-select" id="dcLoginCode_' + deviceId + '" value="' + (d.assigned_callsign||d.callsign||d.device_id||'') + '" placeholder="ORG-NN (e.g. TCN-01)" style="height:32px;font-size:0.7rem;"><button type="button" class="mg-dc-btn mg-dc-btn-secondary mg-dc-btn-sm" onclick="mgDcGenLoginCode(' + deviceId + ')" style="flex-shrink:0;"><i class="fas fa-magic"></i></button></div>';
    html += '<div class="mg-dc-row"><span class="mg-dc-label" style="min-width:75px;">Password</span><input class="mg-dc-select" id="dcPassword_' + deviceId + '" placeholder="Leave blank to keep current" value="" type="password" style="height:32px;font-size:0.7rem;"></div>';
    html += '<div class="mg-dc-row"><span class="mg-dc-label" style="min-width:75px;">Operator</span><select class="mg-dc-select" id="dcOfficer_' + deviceId + '" style="height:32px;font-size:0.7rem;"><option value="">— Unassigned —</option>' + guardOpts + '</select></div>';
    html += '</div>';
    html += '<hr class="mg-dc-divider" style="margin:14px 0;">';

    // GPS Controls
    html += '<div class="mg-dc-section"><div class="mg-dc-section-title"><i class="fas fa-satellite" style="color:#6C8EEF;"></i> GPS Fine-Tuning</div>';
    html += '<div class="mg-dc-row"><span class="mg-dc-label" style="min-width:75px;">Accuracy</span><input type="range" class="mg-dc-slider" id="dcGpsAcc_' + deviceId + '" min="1" max="50" step="1" value="' + gpsAcc + '" oninput="var l=$(\'dcGpsAccVal_' + deviceId + '\');if(l)l.textContent=this.value+\'m\'"><span class="mg-dc-val" id="dcGpsAccVal_' + deviceId + '">' + gpsAcc + 'm</span></div>';
    html += '<div style="display:flex;gap:6px;margin-top:8px;"><button type="button" class="mg-dc-btn mg-dc-btn-primary mg-dc-btn-sm" onclick="mgDcRequestGps(' + deviceId + ')"><i class="fas fa-location-crosshairs"></i> Request GPS Fix</button><button type="button" class="mg-dc-btn mg-dc-btn-secondary mg-dc-btn-sm" onclick="mgDcSetAccuracy(' + deviceId + ')"><i class="fas fa-check"></i> Set Threshold</button></div>';
    var gpsStatus = (d.last_latitude && d.last_longitude) ? 'Last: ' + parseFloat(d.last_latitude).toFixed(5) + ', ' + parseFloat(d.last_longitude).toFixed(5) : 'No recent GPS data';
    if (d.last_gps_accuracy) gpsStatus += ' &middot; Acc: ' + d.last_gps_accuracy + 'm';
    html += '<div class="mg-dc-status" id="dcGpsStatus_' + deviceId + '" style="margin-top:6px;">' + gpsStatus + '</div></div>';
    html += '<hr class="mg-dc-divider" style="margin:14px 0;">';

    // NFC Controls
    html += '<div class="mg-dc-section"><div class="mg-dc-section-title"><i class="fas fa-rss" style="color:#d32f2f;"></i> NFC Scan &amp; Checkpoint Registration</div>';

    // Show fetch requested status
    if (d.nfc_fetch_requested) {
        var fetchTime = new Date(d.nfc_fetch_requested).toLocaleTimeString();
        html += '<div style="display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:8px;background:rgba(239,159,39,0.08);border:1px solid rgba(239,159,39,0.2);margin-bottom:8px;">';
        html +=   '<div class="pulse" style="background:#EF9F27;width:8px;height:8px;border-radius:50%;"></div>';
        html +=   '<div style="flex:1;"><div style="font-size:0.62rem;font-weight:700;color:#EF9F27;">Awaiting NFC scan…</div>';
        html +=     '<div style="font-size:0.5rem;color:rgba(255,255,255,0.4);">Requested at ' + fetchTime + ' — device will register checkpoint on scan</div></div>';
        html +=   '<button type="button" class="mg-dc-btn mg-dc-btn-secondary mg-dc-btn-xs" onclick="mgDcCancNfc(' + deviceId + ')" style="padding:3px 8px;font-size:0.55rem;">Cancel</button>';
        html += '</div>';
    }

    html += '<div style="display:flex;gap:6px;"><button type="button" class="mg-dc-btn mg-dc-btn-primary mg-dc-btn-sm" onclick="mgDcRequestNfc(' + deviceId + ')"><i class="fas fa-wifi"></i> Request NFC Scan</button></div>';
    var nfcStatus = d.last_nfc_scan_uid ? 'Last scan: ' + d.last_nfc_scan_uid + (d.last_nfc_scan ? ' &middot; ' + new Date(d.last_nfc_scan).toLocaleTimeString() : '') : 'No NFC scans recorded';
    html += '<div class="mg-dc-status" id="dcNfcStatus_' + deviceId + '" style="margin-top:6px;">' + nfcStatus + '</div>';
    if (d.current_mission && d.current_mission.route_name) {
        html += '<div class="mg-dc-status" style="margin-top:4px;color:rgba(93,202,165,0.7);"><i class="fas fa-route"></i> On mission: ' + d.current_mission.route_name + ' (' + d.current_mission.progress_pct + '%)</div>';
    }
    html += '</div>';
    html += '<hr class="mg-dc-divider" style="margin:14px 0;">';

    // TTS Controls
    html += '<div class="mg-dc-section"><div class="mg-dc-section-title"><i class="fas fa-volume-high" style="color:#EF9F27;"></i> TTS Announcement <span style="font-weight:400;color:rgba(255,255,255,0.2);font-size:0.5rem;text-transform:none;letter-spacing:0;">&mdash; sent directly to device, no route needed</span></div>';

    // ── Pending TTS & Ack Status ──
    var ttsAcked = d.tts_acked !== false; // true if acked or no pending
    var hasPending = d.tts_pending && d.tts_pending.trim();
    var ackColor = ttsAcked ? 'rgba(93,202,165,0.7)' : '#EF9F27';
    var ackIcon = ttsAcked ? 'fa-circle-check' : 'fa-circle-exclamation';
    var ackLabel = ttsAcked ? 'Acknowledged' : 'Awaiting confirmation';
    var ackBg = ttsAcked ? 'rgba(93,202,165,0.08)' : 'rgba(239,159,39,0.1)';
    var ackBorder = ttsAcked ? 'rgba(93,202,165,0.2)' : 'rgba(239,159,39,0.2)';
    var pendingTime = d.tts_pending_at ? new Date(d.tts_pending_at).toLocaleString() : '';

    html += '<div style="display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:8px;background:' + ackBg + ';border:1px solid ' + ackBorder + ';margin-bottom:8px;">';
    html +=   '<i class="fas ' + ackIcon + '" style="color:' + ackColor + ';font-size:0.75rem;"></i>';
    html +=   '<div style="flex:1;min-width:0;">';
    html +=     '<div style="font-size:0.62rem;font-weight:700;color:' + ackColor + ';">' + ackLabel + '</div>';
    if (hasPending) {
        html +=   '<div style="font-size:0.55rem;color:rgba(255,255,255,0.5);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">Pending: "' + d.tts_pending.replace(/"/g,'&quot;') + '"</div>';
        if (pendingTime) html += '<div style="font-size:0.48rem;color:rgba(255,255,255,0.2);margin-top:1px;">Queued: ' + pendingTime + '</div>';
    } else {
        html +=   '<div style="font-size:0.55rem;color:rgba(255,255,255,0.35);margin-top:2px;">No pending messages</div>';
    }
    html +=   '</div>';
    if (hasPending) {
        if (!ttsAcked) {
            html += '<button type="button" class="mg-dc-btn mg-dc-btn-primary mg-dc-btn-xs" onclick="mgDcResendTts(' + deviceId + ')" title="Resend pending TTS" style="padding:3px 8px;font-size:0.55rem;"><i class="fas fa-rotate"></i> Resend</button>';
        }
        html += '<button type="button" class="mg-dc-btn mg-dc-btn-secondary mg-dc-btn-xs" onclick="mgDcDismissPending(' + deviceId + ')" title="Dismiss pending TTS" style="padding:3px 8px;font-size:0.55rem;background:rgba(255,255,255,0.06);"><i class="fas fa-xmark"></i></button>';
    }
    html += '</div>';

    var ttsOpts = ['en-US','en-GB','en-AU','en-CA','en-IN','fr-FR','de-DE','es-ES','it-IT','pt-BR','ar-SA','ja-JP','ko-KR','zh-CN'].map(function(v) { return '<option value="' + v + '"' + (d.tts_voice === v ? ' selected' : '') + '>' + v + '</option>'; }).join('');
    html += '<div class="mg-dc-row"><span class="mg-dc-label" style="min-width:75px;">Voice</span><select class="mg-dc-select" id="dcTtsVoice_' + deviceId + '" style="height:32px;font-size:0.7rem;">' + ttsOpts + '</select></div>';
    html += '<div class="mg-dc-row"><span class="mg-dc-label" style="min-width:75px;">Rate</span><input type="range" class="mg-dc-slider" id="dcTtsRate_' + deviceId + '" min="0.5" max="2.0" step="0.1" value="' + (d.tts_rate !== undefined && d.tts_rate !== null ? d.tts_rate : 1.0) + '" oninput="var l=$(\'dcTtsRateVal_' + deviceId + '\');if(l)l.textContent=parseFloat(this.value).toFixed(1)"><span class="mg-dc-val" id="dcTtsRateVal_' + deviceId + '">' + (d.tts_rate !== undefined && d.tts_rate !== null ? d.tts_rate : 1.0).toFixed(1) + '</span></div>';
    html += '<div class="mg-dc-row"><span class="mg-dc-label" style="min-width:75px;">Pitch</span><input type="range" class="mg-dc-slider" id="dcTtsPitch_' + deviceId + '" min="0.5" max="2.0" step="0.1" value="' + (d.tts_pitch !== undefined && d.tts_pitch !== null ? d.tts_pitch : 1.0) + '" oninput="var l=$(\'dcTtsPitchVal_' + deviceId + '\');if(l)l.textContent=parseFloat(this.value).toFixed(1)"><span class="mg-dc-val" id="dcTtsPitchVal_' + deviceId + '">' + (d.tts_pitch !== undefined && d.tts_pitch !== null ? d.tts_pitch : 1.0).toFixed(1) + '</span></div>';
    html += '<textarea class="mg-dc-textarea" id="dcTtsMsg_' + deviceId + '" rows="2" placeholder="Type a TTS message to send to this device…" style="font-size:0.7rem;"></textarea>';
    html += '<div style="display:flex;gap:6px;margin-top:4px;"><button type="button" class="mg-dc-btn mg-dc-btn-primary mg-dc-btn-sm" onclick="mgDcSendTts(' + deviceId + ')"><i class="fas fa-paper-plane"></i> Send TTS</button></div>';
    html += '<div class="mg-dc-status" id="dcTtsStatus_' + deviceId + '" style="margin-top:6px;"></div></div>';
    html += '<hr class="mg-dc-divider" style="margin:14px 0;">';

    // Save / Close
    html += '<div style="display:flex;gap:8px;padding-top:4px;">';
    html +=   '<button type="button" class="mg-dc-btn mg-dc-btn-primary" style="flex:1;padding:8px 14px;font-size:0.7rem;" onclick="mgDcSaveDevice(' + deviceId + ')"><i class="fas fa-floppy-disk"></i> Save Changes</button>';
    html +=   '<button type="button" class="mg-dc-btn mg-dc-btn-secondary" style="flex:1;padding:8px 14px;font-size:0.7rem;" onclick="mgDcClose()"><i class="fas fa-xmark"></i> Cancel</button>';
    html += '</div></div>';

    $('mgDcDropdownBody').innerHTML = html;

    // Position the dropdown near the trigger button
    var rect = (btn && btn.getBoundingClientRect) ? btn.getBoundingClientRect() : { bottom: 0, left: 0, top: 0, right: 0 };
    var dw = 500;
    var dh = Math.min($('mgDcDropdownBody').scrollHeight + 2, 700);
    var vw = window.innerWidth;
    var vh = window.innerHeight;
    var gap = 8;
    var left = Math.max(12, Math.min(rect.left + rect.width / 2 - dw / 2, vw - dw - 12));
    var top = rect.bottom + gap;
    // If dropdown would overflow bottom, flip above
    if (top + dh > vh - 12) {
        top = Math.max(12, rect.top - dh - gap);
    }
    // Ensure it doesn't go off top
    top = Math.max(12, top);

    var dd = $('mgDcDropdown');
    var body = $('mgDcDropdownBody');
    dd.style.left = left + 'px';
    dd.style.top = top + 'px';
    // Set explicit max-height so it doesn't overflow viewport
    body.style.maxHeight = Math.min(dh, vh - top - 12) + 'px';

    // Show with animation
    $('mgDcDropdownBackdrop').classList.add('open');
    dd.classList.add('open');
};

window.mgDcClose = function() {
    var dd = $('mgDcDropdown');
    var bk = $('mgDcDropdownBackdrop');
    if (dd) dd.classList.remove('open');
    if (bk) bk.classList.remove('open');
    // Clean up poll timers
    _dcPollTimers.forEach(function(t) { clearInterval(t); });
    _dcPollTimers = [];
    _dcDeviceId = null;
};

// Close dropdown on Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && _dcDeviceId) mgDcClose();
});

window.mgDcSaveDevice = async function(deviceId) {
    if(!deviceId) deviceId = _dcDeviceId;
    const payload = {
        device_id: $('dcLoginCode_' + deviceId)?.value?.trim(),
        imei: $('dcImei_' + deviceId)?.value?.trim() || null,
        imsi: $('dcImsi_' + deviceId)?.value?.trim() || null,
        sim_phone_number: $('dcSimPhone_' + deviceId)?.value?.trim() || null,
        os_version: $('dcOs_' + deviceId)?.value?.trim() || null,
        manufacturer: $('dcMan_' + deviceId)?.value?.trim() || null,
        model: $('dcModel_' + deviceId)?.value?.trim() || null,
    };
    const pwd = $('dcPassword_' + deviceId)?.value?.trim();
    if (pwd) payload.password = pwd;
    if(!payload.device_id) { toast('Login code required', true); return; }

    const method = deviceId && allDevices.find(x=>x.id===deviceId) ? 'PATCH' : 'POST';
    const url = method === 'PATCH' ? `/api/devices/${deviceId}/` : '/api/devices/';
    const res = await api(url, { method, body: JSON.stringify(payload) });
    const data = await res.json().catch(()=>({}));
    if(!res.ok) {
        toast(data.detail || 'Save failed', true);
        return;
    }

    const guardId = $('dcOfficer_' + deviceId)?.value;
    if(guardId) {
        await api('/api/provision-device/', {
            method: 'POST',
            body: JSON.stringify({ device_id: data.device_id || payload.device_id, guard_id: parseInt(guardId, 10) })
        });
    }

    toast('Device saved');
    mgDcClose(deviceId);
    mgLoadDevices();
};

window.mgDcGenLoginCode = async function(deviceId) {
    if(!deviceId) deviceId = _dcDeviceId;
    let orgId = null;
    if (typeof userData !== 'undefined' && userData.organization_id) {
        orgId = Array.isArray(userData.organization_id) ? userData.organization_id[0] : userData.organization_id;
    }
    if (!orgId) { $('dcLoginCode_' + deviceId).value = 'TCN-01'; return; }
    try {
        const resp = await api(`/api/operator-id-next/?organization=${orgId}`);
        if (resp.ok) {
            const data = await resp.json();
            $('dcLoginCode_' + deviceId).value = data.operator_id;
        } else {
            $('dcLoginCode_' + deviceId).value = 'TCN-01';
        }
    } catch(e) {
        $('dcLoginCode_' + deviceId).value = 'TCN-01';
    }
};

window.mgDcRequestGps = async function(deviceId) {
    if(!deviceId) deviceId = _dcDeviceId;
    $('dcGpsStatus_' + deviceId).textContent = 'Requesting GPS fix…';
    const acc = parseInt($('dcGpsAcc_' + deviceId)?.value || 5);
    const res = await api(`/api/devices/${deviceId}/fetch_gps/`, { method: 'POST', body: JSON.stringify({ accuracy: acc }) });
    if(res.ok) {
        $('dcGpsStatus_' + deviceId).textContent = 'GPS fix requested — waiting for device…';
        mgDcPollGps(deviceId);
    } else {
        const err = await res.json().catch(()=>({}));
        $('dcGpsStatus_' + deviceId).textContent = err.detail || 'GPS request failed';
    }
};

window.mgDcPollGps = function(deviceId) {
    if(!deviceId) deviceId = _dcDeviceId;
    let attempts = 0;
    const maxAttempts = 12;
    const pollTimer = setInterval(async () => {
        attempts++;
        try {
            const res = await api(`/api/devices/${deviceId}/`);
            if(res.ok) {
                const data = await res.json();
                if(data.last_latitude && data.last_longitude) {
                    clearInterval(pollTimer);
                    var idx = _dcPollTimers.indexOf(pollTimer);
                    if(idx>=0) _dcPollTimers.splice(idx,1);
                    $('dcGpsStatus_' + deviceId).textContent = `GPS: ${parseFloat(data.last_latitude).toFixed(5)}, ${parseFloat(data.last_longitude).toFixed(5)}${data.last_gps_accuracy ? ' · Acc: '+data.last_gps_accuracy+'m' : ''}${data.last_battery != null ? ' · Bat: '+data.last_battery+'%' : ''}`;
                    const dev = allDevices.find(x=>x.id===deviceId);
                    if(dev) Object.assign(dev, data);
                    return;
                }
            }
        } catch(e) {}
        $('dcGpsStatus_' + deviceId).textContent = `Waiting for GPS… ${attempts}/${maxAttempts}`;
        if(attempts >= maxAttempts) {
            clearInterval(pollTimer);
            var idx = _dcPollTimers.indexOf(pollTimer);
            if(idx>=0) _dcPollTimers.splice(idx,1);
            $('dcGpsStatus_' + deviceId).textContent = 'Device offline — GPS will update when it reconnects';
        }
    }, 5000);
    _dcPollTimers.push(pollTimer);
};

window.mgDcCancNfc = async function(deviceId) {
    if(!deviceId) deviceId = _dcDeviceId;
    try {
        const res = await api(`/api/devices/${deviceId}/update_nfc/`, {
            method: 'PATCH',
            body: JSON.stringify({ nfc_fetch_requested: null }),
        });
        if (res.ok) {
            const dev = allDevices.find(x => x.id === deviceId);
            if (dev) dev.nfc_fetch_requested = null;
            mgDeviceControls(deviceId);
            toast('NFC fetch cancelled');
        }
    } catch(e) {
        toast('Failed to cancel NFC fetch', true);
    }
};

window.mgDcSetAccuracy = async function(deviceId) {
    if(!deviceId) deviceId = _dcDeviceId;
    const acc = parseInt($('dcGpsAcc_' + deviceId)?.value || 5);
    const res = await api(`/api/devices/${deviceId}/fetch_gps/`, { method: 'POST', body: JSON.stringify({ accuracy: acc }) });
    if(res.ok) {
        toast(`GPS accuracy threshold set to ${acc}m`);
        const dev = allDevices.find(x=>x.id===deviceId);
        if(dev) dev.gps_accuracy_threshold = acc;
    } else {
        toast('Failed to set accuracy threshold', true);
    }
};

window.mgDcRequestNfc = async function(deviceId) {
    if(!deviceId) deviceId = _dcDeviceId;
    $('dcNfcStatus_' + deviceId).textContent = 'Requesting NFC scan…';
    const res = await api(`/api/devices/${deviceId}/fetch_nfc/`, { method: 'POST' });
    if(res.ok) {
        $('dcNfcStatus_' + deviceId).textContent = 'NFC scan requested — waiting for device…';
        mgDcPollNfc(deviceId);
    } else {
        const err = await res.json().catch(()=>({}));
        $('dcNfcStatus_' + deviceId).textContent = err.detail || 'NFC request failed';
    }
};

window.mgDcPollNfc = function(deviceId) {
    if(!deviceId) deviceId = _dcDeviceId;
    let attempts = 0;
    const maxAttempts = 24;
    const pollTimer = setInterval(async () => {
        attempts++;
        try {
            const res = await api(`/api/devices/${deviceId}/`);
            if(res.ok) {
                const data = await res.json();
                if(data.last_nfc_scan && data.last_nfc_scan_uid) {
                    clearInterval(pollTimer);
                    var idx = _dcPollTimers.indexOf(pollTimer);
                    if(idx>=0) _dcPollTimers.splice(idx,1);

                    var statusMsg = `NFC: ${data.last_nfc_scan_uid} · ${new Date(data.last_nfc_scan).toLocaleTimeString()}`;
                    if (!data.nfc_fetch_requested) {
                        statusMsg += ' ✓ Checkpoint registered';
                    }
                    $('dcNfcStatus_' + deviceId).textContent = statusMsg;

                    const dev = allDevices.find(x=>x.id===deviceId);
                    if(dev) Object.assign(dev, data);

                    if (!data.nfc_fetch_requested) {
                        mgDeviceControls(deviceId);
                    }
                    return;
                }
            }
        } catch(e) {}
        $('dcNfcStatus_' + deviceId).textContent = `Waiting for device… ${attempts}/${maxAttempts}`;
        if(attempts >= maxAttempts) {
            clearInterval(pollTimer);
            var idx = _dcPollTimers.indexOf(pollTimer);
            if(idx>=0) _dcPollTimers.splice(idx,1);
            $('dcNfcStatus_' + deviceId).textContent = 'Device offline — NFC will update when it reconnects';
        }
    }, 5000);
    _dcPollTimers.push(pollTimer);
};

window.mgDcSendTts = async function(deviceId) {
    if(!deviceId) deviceId = _dcDeviceId;
    const voice = $('dcTtsVoice_' + deviceId)?.value || 'en-US';
    const rate = parseFloat($('dcTtsRate_' + deviceId)?.value || 1.0);
    const pitch = parseFloat($('dcTtsPitch_' + deviceId)?.value || 1.0);
    const msg = $('dcTtsMsg_' + deviceId)?.value?.trim() || '';
    if(!msg) { toast('Enter a TTS message', true); return; }

    $('dcTtsStatus_' + deviceId).textContent = 'Sending TTS to device…';
    const res = await api(`/api/devices/${deviceId}/send_tts/`, {
        method: 'POST',
        body: JSON.stringify({
            message: msg,
            tts_voice: voice,
            tts_rate: rate,
            tts_pitch: pitch,
            play_sound: true,
            vibrate: true
        })
    });
    if(res.ok) {
        const data = await res.json();
        $('dcTtsStatus_' + deviceId).textContent = 'TTS queued — waiting for device ACK';
        toast('TTS queued — device will play on next heartbeat');
        const dev = allDevices.find(x=>x.id===deviceId);
        if(dev) { dev.tts_voice = voice; dev.tts_rate = rate; dev.tts_pitch = pitch; dev.tts_pending = msg; dev.tts_acked = false; dev.tts_pending_at = new Date().toISOString(); }
        mgDcPollTtsAck(deviceId);
        mgRenderDevices();
        var devName = dev ? (dev.device_name || dev.device_id || 'Device #'+deviceId) : 'Device #'+deviceId;
        mgLogFleetEvent('info', 'TTS sent to ' + devName, msg.slice(0, 50));
    } else {
        const err = await res.json().catch(()=>({}));
        $('dcTtsStatus_' + deviceId).textContent = err.detail || 'TTS send failed';
        toast('TTS send failed', true);
    }
};

window.mgDcResendTts = async function(deviceId) {
    if(!deviceId) deviceId = _dcDeviceId;
    const d = allDevices.find(x => x.id === deviceId);
    if (!d || !d.tts_pending) { toast('No pending TTS to resend', true); return; }

    $('dcTtsStatus_' + deviceId).textContent = 'Resending TTS…';
    const res = await api(`/api/devices/${deviceId}/send_tts/`, {
        method: 'POST',
        body: JSON.stringify({
            message: d.tts_pending,
            tts_voice: d.tts_pending_voice || d.tts_voice || 'en-US',
            tts_rate: d.tts_pending_rate ?? d.tts_rate ?? 1.0,
            tts_pitch: d.tts_pending_pitch ?? d.tts_pitch ?? 1.0,
            play_sound: true,
            vibrate: true
        })
    });
    if(res.ok) {
        $('dcTtsStatus_' + deviceId).textContent = 'TTS re-queued — waiting for device ACK';
        toast('TTS re-queued');
        mgDcPollTtsAck(deviceId);
        var devName = d ? (d.device_name || d.device_id || 'Device #'+deviceId) : 'Device #'+deviceId;
        mgLogFleetEvent('info', 'TTS resent to ' + devName, (d.tts_pending||'').slice(0, 50));
    } else {
        const err = await res.json().catch(()=>({}));
        $('dcTtsStatus_' + deviceId).textContent = err.detail || 'Resend failed';
        toast('TTS resend failed', true);
    }
};

window.mgDcDismissPending = async function(deviceId) {
    if(!deviceId) deviceId = _dcDeviceId;
    const d = allDevices.find(x => x.id === deviceId);
    const res = await api(`/api/devices/${deviceId}/`, {
        method: 'PATCH',
        body: JSON.stringify({
            tts_pending: null,
            tts_pending_voice: '',
            tts_pending_rate: 1.0,
            tts_pending_pitch: 1.0,
            tts_pending_at: null,
            tts_acked: true
        })
    });
    if(res.ok) {
        toast('Pending TTS dismissed');
        if(d) { d.tts_pending = null; d.tts_acked = true; d.tts_pending_at = null; }
        mgDeviceControls(deviceId, document.querySelector(`[data-device-id="${deviceId}"] .mg-btn`));
        mgRenderDevices();
        var devName = d ? (d.device_name || d.device_id || 'Device #'+deviceId) : 'Device #'+deviceId;
        mgLogFleetEvent('info', 'TTS dismissed on ' + devName, '');
    } else {
        toast('Failed to dismiss', true);
    }
};

window.mgDcPollTtsAck = function(deviceId) {
    if(!deviceId) deviceId = _dcDeviceId;
    let attempts = 0;
    const maxAttempts = 30;
    const pollTimer = setInterval(async () => {
        attempts++;
        try {
            const res = await api(`/api/devices/${deviceId}/`);
            if(res.ok) {
                const data = await res.json();
                if(data.tts_acked === true) {
                    clearInterval(pollTimer);
                    var idx = _dcPollTimers.indexOf(pollTimer);
                    if(idx>=0) _dcPollTimers.splice(idx,1);
                    toast('TTS acknowledged by device');
                    const dev = allDevices.find(x=>x.id===deviceId);
                    if(dev) { dev.tts_acked = true; dev.tts_pending = null; }
                    if (_dcDeviceId === deviceId) mgDeviceControls(deviceId, document.querySelector(`[data-device-id="${deviceId}"] .mg-btn`));
                    mgRenderDevices();
                    var devName = dev ? (dev.device_name || dev.device_id || 'Device #'+deviceId) : 'Device #'+deviceId;
                    mgLogFleetEvent('check', 'TTS confirmed on ' + devName, 'Device acknowledged');
                    return;
                }
            }
        } catch(e) {}
        if(attempts >= maxAttempts) {
            clearInterval(pollTimer);
            var idx = _dcPollTimers.indexOf(pollTimer);
            if(idx>=0) _dcPollTimers.splice(idx,1);
        }
    }, 3000);
    _dcPollTimers.push(pollTimer);
};

/* ── Swap Operator ─────────────────────────────── */
let _swapDeviceId = null;
window.mgSwapOperator = function(deviceId, deviceName) {
    _swapDeviceId = deviceId;
    const guardOpts = (allGuards||[]).map(g => {
        const label = [g.first_name, g.last_name].filter(Boolean).join(' ') || g.username || 'Unnamed';
        const suffix = g.callsign ? ` (${g.callsign})` : ' [New]';
        return `<option value="${g.id}">${label}${suffix}</option>`;
    }).join('');

    $('mgSwapBody').innerHTML = `
        <div style="margin-bottom:12px; font-size:0.85rem; opacity:0.7;">Swapping operator on <strong>${deviceName}</strong></div>
        <label class="mg-fi-label" for="mgSwapGuard">New Operator / Guard</label>
        <select id="mgSwapGuard" class="mg-fi">
            <option value="">— Select Guard —</option>
            ${guardOpts}
        </select>
        <div style="margin-top:12px; display:flex; gap:8px; justify-content:flex-end;">
            <button type="button" class="mg-btn mg-btn-sm" onclick="$('mgSwapOverlay').classList.add('mg-hidden')">Cancel</button>
            <button type="button" class="mg-btn mg-btn-sm" style="background:var(--primary); color:#fff;" onclick="mgConfirmSwap()">Swap</button>
        </div>
    `;
    $('mgSwapOverlay').classList.remove('mg-hidden');
};

window.mgConfirmSwap = async function() {
    const guardId = $('mgSwapGuard')?.value;
    if (!guardId) { toast('Select a guard', true); return; }
    const res = await api(`/api/devices/${_swapDeviceId}/swap_operator/`, {
        method: 'POST',
        body: JSON.stringify({ guard_id: parseInt(guardId, 10) })
    });
    if (res.ok) {
        toast('Operator swapped');
        mgLogFleetEvent('swap', 'Operator swap on ' + deviceName, 'Device reassigned');
        $('mgSwapOverlay').classList.add('mg-hidden');
        mgLoadDevices();
    } else {
        const err = await res.json().catch(() => ({}));
        toast(err.detail || 'Swap failed', true);
    }
};

/* ══════════════════════════════════════════════════
    MAP ASSETS
═════════════════════════════════════════════════ */
async function mgLoadAssets(){
    try{
        // Load both MapObjects and Checkpoints for complete map assets
        const [res, cpRes] = await Promise.all([
            api('/api/map-objects/'),
            api('/api/checkpoints/')
        ]);
        const mapObjects = [];
        const checkpoints = [];
        if(res.ok){ const d=await res.json(); mapObjects=Array.isArray(d)?d:(d.results||[]); }
        if(cpRes.ok){ const d=await cpRes.json(); checkpoints=Array.isArray(d)?d:(d.results||[]); }
        // Combine: MapObjects with their types + Checkpoints with converted types
        allAssets = [
            ...mapObjects.map(a => ({ ...a, asset_type: 'map_object' })),
            ...checkpoints.map(c => ({ 
                ...c, 
                type: c.checkpoint_type || 'poi', // Use checkpoint_type for proper icon mapping
                asset_type: 'checkpoint'
            }))
        ];
    }catch(e){}
    mgRenderAssetStats();
    mgRenderAssets();
    initMap();
}

function mgRenderAssetStats(){
    const statsEl = $('assetStats');
    if (!statsEl) return;
    const total=allAssets.length;
    // Map all asset types for statistics
    const nfc=allAssets.filter(a=>a.type==='nfc').length;
    const gps=allAssets.filter(a=>a.type==='gps').length;
    const geofence=allAssets.filter(a=>a.type==='geofence').length;
    const peer=allAssets.filter(a=>a.type==='peer').length;
    const poi=allAssets.filter(a=>a.type==='poi' && !a.radius).length;
    const circle=allAssets.filter(a=>a.type==='poi' && a.radius).length;

    statsEl.innerHTML=`
        <div class="mg-stat"><div class="mg-stat-val">${total}</div><div class="mg-stat-lbl">Total</div></div>
        <div class="mg-stat"><div class="mg-stat-val red">${nfc}</div><div class="mg-stat-lbl">NFC</div></div>
        <div class="mg-stat"><div class="mg-stat-val blue">${gps}</div><div class="mg-stat-lbl">GPS</div></div>
        <div class="mg-stat"><div class="mg-stat-val green">${geofence}</div><div class="mg-stat-lbl">Geo</div></div>
    `;
    var tcFleet = $('tcFleet');
    if (tcFleet) tcFleet.textContent = String(allDevices.length + (allAssets||[]).length);
}

window.mgAssetFilter=function(f,el){
    assetFilter=f;
    // No filter chips in Map Assets panel - just update the view
    mgRenderAssets();
};
window.mgFilterAssets=function(){ };

function mgRenderAssets(){
    // No map — assets loaded into registry via mgLoadSavedCps
}

/* ── Fleet Activity Feed ────────────────────────── */
var fleetActivityLog = [];
var fleetActivityMax = 20;

window.mgLogFleetEvent = function(type, msg, detail) {
    fleetActivityLog.unshift({
        type: type,
        msg: msg,
        detail: detail || '',
        time: new Date()
    });
    if (fleetActivityLog.length > fleetActivityMax) fleetActivityLog.pop();
    mgRenderFleetActivity();
};

window.mgLoadFleetActivity = function() {
    if (fleetActivityLog.length) { mgRenderFleetActivity(); return; }
    // Seed with demo events from current data
    var online = allDevices.filter(function(d) { return d.is_online; }).length;
    var offline = allDevices.length - online;
    var saved = allAssets.filter(function(a) {
        var t = a.type || a.checkpoint_type || '';
        return ['nfc','gps','geo','peer','poi','geofence'].indexOf(t) !== -1;
    }).length;
    fleetActivityLog = [];
    if (saved > 0) mgLogFleetEvent('check', saved + ' checkpoint' + (saved !== 1 ? 's' : '') + ' in registry', 'Loaded from server');
    mgLogFleetEvent(online > 0 ? 'online' : 'offline', online + '/' + allDevices.length + ' device' + (allDevices.length !== 1 ? 's' : '') + ' online', 'Fleet status');
    mgLogFleetEvent('info', 'Fleet panel initialized', moment ? moment().format('HH:mm') : new Date().toLocaleTimeString());
};

function mgRenderFleetActivity() {
    var feed = $('fleetActivityFeed');
    var count = $('fleetActivityCount');
    if (!feed) return;
    if (count) count.textContent = fleetActivityLog.length ? '(' + fleetActivityLog.length + ')' : '';
    if (!fleetActivityLog.length) {
        feed.innerHTML = '<div style="font-size:0.5rem;color:rgba(255,255,255,0.12);text-align:center;padding:4px;">No recent activity</div>';
        return;
    }
    var iconMap = { online:'fa-circle', offline:'fa-circle', scan:'fa-wifi', swap:'fa-exchange-alt', check:'fa-map-pin', info:'fa-circle-info', deploy:'fa-rocket' };
    var colorMap = { online:'#5DCAA5', offline:'rgba(255,255,255,0.2)', scan:'var(--r-crim)', swap:'#F5A623', check:'#6C8EEF', info:'rgba(255,255,255,0.25)', deploy:'var(--r-crim)' };
    feed.innerHTML = fleetActivityLog.slice(0, 8).map(function(e, i) {
        var icon = iconMap[e.type] || 'fa-circle';
        var col = colorMap[e.type] || 'rgba(255,255,255,0.3)';
        var ts = moment ? moment(e.time).format('HH:mm') : (typeof e.time === 'string' ? e.time : new Date(e.time).toLocaleTimeString());
        return '<div class="mg-activity-item" style="display:flex;align-items:center;gap:5px;padding:2px 4px;border-radius:4px;transition:background .12s;--i:' + i + ';" onmouseover="this.style.background=\'rgba(255,255,255,0.02)\'" onmouseout="this.style.background=\'transparent\'">' +
            '<i class="fas ' + icon + '" style="font-size:0.35rem;color:' + col + ';width:8px;"></i>' +
            '<span style="flex:1;font-size:0.5rem;color:rgba(255,255,255,0.4);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + e.msg + '</span>' +
            (e.detail ? '<span style="font-size:0.42rem;color:rgba(255,255,255,0.15);flex-shrink:0;">' + e.detail + '</span>' : '') +
            '<span style="font-size:0.4rem;color:rgba(255,255,255,0.1);flex-shrink:0;font-family:monospace;">' + ts + '</span>' +
        '</div>';
    }).join('');
    // Add stagger to new items
    feed.querySelectorAll('.mg-activity-item').forEach(function(el,i){
        el.style.animationDelay = (i*30)+'ms';
    });
};

/* ── Activity strip controls ───────────────────────── */
window.mgShowActivityStrip = function() {
    var strip = $('fleetActivityStrip');
    if (!strip) return;
    strip.style.display = 'flex';
    mgLoadFleetActivity();
    var feed = $('fleetActivityFeed');
    if (feed && feed._expanded) {
        feed.style.maxHeight = feed.scrollHeight + 'px';
        feed.style.padding = '0 14px 8px';
    }
};
window.mgToggleActivityFeed = function() {
    var feed = $('fleetActivityFeed');
    var icon = $('mgActivityToggleIcon');
    if (!feed) return;
    feed._expanded = !feed._expanded;
    if (feed._expanded) {
        feed.style.maxHeight = feed.scrollHeight + 'px';
        feed.style.padding = '0 14px 8px';
        if (icon) icon.className = 'fas fa-chevron-up';
    } else {
        feed.style.maxHeight = '0';
        feed.style.padding = '0 14px';
        if (icon) icon.className = 'fas fa-chevron-down';
    }
};

/* ── Setup Map Engine ───────────────────────────── */
let setupMap = null;
function mgInitSetupMap() {
    const mapEl = $('mgSetupMap');
    if (!mapEl) return;
    if (setupMap) { setupMap.remove(); setupMap = null; }

    setupMap = L.map('mgSetupMap', { zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false, touchZoom: false, doubleClickZoom: false, boxZoom: false }).setView([0, 0], 2);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png').addTo(setupMap);

    // Recalculate dimensions for hidden containers
    setTimeout(() => setupMap.invalidateSize(), 100);

    // Attempt to center on current site coordinates
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(pos => {
            setupMap.setView([pos.coords.latitude, pos.coords.longitude], 15);
        }, () => {}, { timeout: 4000 });
    }
}

/* ── Device Helpers ─────────────────────────────── */
window.mgGenerateLoginCode = async function() {
    let orgId = null;
    if (typeof userData !== 'undefined' && userData.organization_id) {
        orgId = Array.isArray(userData.organization_id) ? userData.organization_id[0] : userData.organization_id;
    }
    if (!orgId) { $('mDid').value = 'TCN-01'; return; }
    try {
        const resp = await api(`/api/operator-id-next/?organization=${orgId}`);
        if (resp.ok) {
            const data = await resp.json();
            $('mDid').value = data.operator_id;
        } else {
            $('mDid').value = 'TCN-01';
        }
    } catch(e) {
        $('mDid').value = 'TCN-01';
    }
};

window.mgGeneratePassword = function() {
    let pwd = '';
    for (let i = 0; i < 8; i++) {
        pwd += Math.floor(Math.random() * 10);
    }
    $('mDpwd').value = pwd;
};

/* ══════════════════════════════════════════════════
   ROUTE HEALTH
══════════════════════════════════════════════════ */
async function mgLoadRoutes(){
    try{
        const [rRes,dRes]=await Promise.all([api('/api/routes/'),api('/api/shifts/')]);
        if(rRes.ok){ const d=await rRes.json(); allRoutes=Array.isArray(d)?d:(d.results||[]); }
        if(dRes.ok){ const d=await dRes.json(); allDeploys=Array.isArray(d)?d:(d.results||[]); }
    }catch(e){}
    mgRenderRouteStats();
    mgRenderRouteHealth();
    mgRenderActiveDeployments();
}

function mgRenderRouteStats(){
    const total=allRoutes.length;
    const active=allDeploys.filter(d=>d.is_active&&!d.is_completed).length;
    const done=allDeploys.filter(d=>d.is_completed).length;
    const withCps=allRoutes.filter(r=>(r.checkpoint_count||0)>0).length;
    $('routeStats').innerHTML=`
        <div class="mg-stat"><div class="mg-stat-val">${total}</div><div class="mg-stat-lbl">Blueprints</div></div>
        <div class="mg-stat"><div class="mg-stat-val green">${active}</div><div class="mg-stat-lbl">Active Now</div></div>
        <div class="mg-stat"><div class="mg-stat-val">${done}</div><div class="mg-stat-lbl">Completed</div></div>
        <div class="mg-stat"><div class="mg-stat-val ${withCps<total?'amber':'green'}">${withCps}/${total}</div><div class="mg-stat-lbl">With Checkpoints</div></div>
    `;
    $('tcAudit').textContent=total;
}

function mgRenderRouteHealth(){
    const el=$('routeHealthList');
    if (!el) return;
    if(!allRoutes.length){el.innerHTML='<div class="mg-empty"><i class="fas fa-route"></i>No blueprints</div>';return;}

    el.innerHTML=allRoutes.map((r,i)=>{
        const cps=r.checkpoint_count||0;
        const isDeployed=allDeploys.some(d=>d.route===r.id&&d.is_active);
        const health=cps===0?0:Math.min(100,cps*20);
        const hCol=health>=80?'#5DCAA5':health>=40?'#EF9F27':'var(--primary-light)';
        return `
        <div class="mg-route-row" style="--i:${i};">
            <div style="flex:1;min-width:0;">
                <div class="mg-route-name">${r.name}</div>
                <div class="mg-route-meta">${r.logic_type||'Flexible'} · ${cps} checkpoints</div>
            </div>
            <div class="mg-health-bar">
                <div class="mg-health-fill" style="width:${health}%;background:${hCol};"></div>
            </div>
            <span class="mg-badge ${isDeployed?'mg-b-active':'mg-b-off'}" style="min-width:60px;text-align:center;">${isDeployed?'Live':'Saved'}</span>
            <div style="display:flex;gap:5px;">
                <button type="button" class="mg-btn mg-btn-sm" onclick="window.location.href='/routes/'" title="Edit"><i class="fas fa-pen"></i></button>
                <button type="button" class="mg-btn mg-btn-sm mg-btn-primary" onclick="mgQuickDeploy(${r.id})" title="Deploy"><i class="fas fa-rocket"></i></button>
            </div>
        </div>`;
    }).join('');
}

function mgRenderActiveDeployments(){
    const el=$('activeDeployList');
    if (!el) return;
    const active=allDeploys.filter(d=>d.is_active&&!d.is_completed);
    if(!active.length){el.innerHTML='<div class="mg-empty"><i class="fas fa-satellite-dish"></i>No active deployments</div>';return;}
    el.innerHTML=active.map(d=>{
        const hit=d.completed_checkpoints||0;
        const total=d.total_checkpoints||0;
        const pct=total>0?Math.round(hit/total*100):0;
        return `
        <div class="mg-card">
            <div class="mg-card-avatar" style="background:rgba(29,158,117,.12);">
                <i class="fas fa-satellite-dish" style="color:#5DCAA5;font-size:.8rem;"></i>
            </div>
            <div class="mg-card-info">
                <div class="mg-card-name">${d.guard_supervisor_name||'Guard'}</div>
                <div class="mg-card-sub">${d.route_name||'Free Patrol'} · ${d.shift_type||''}</div>
                ${total>0?`<div style="height:4px;border-radius:999px;background:rgba(255,255,255,.08);margin-top:5px;overflow:hidden;">
                    <div style="height:100%;width:${pct}%;background:var(--primary-gradient);border-radius:999px;"></div>
                </div>`:''}
            </div>
            <span class="mg-badge mg-b-active">${pct}%</span>
        </div>`;
    }).join('');
}

window.mgFilterRoutes = function() {
    var q = ($('routeSearchInput')?.value || '').toLowerCase();
    $$('#routeHealthList .mg-route-row').forEach(function(r) {
        var name = r.querySelector('.mg-route-name')?.textContent || '';
        r.style.display = !q || name.toLowerCase().includes(q) ? '' : 'none';
    });
};

/* Quick deploy: open dispatch with route pre-selected */
window.mgQuickDeploy=function(routeId){
    sessionStorage.setItem('mg_preselect_route',routeId);
    window.location.href='/dispatch/';
};

window.mgLogPreset = function(days) {
    var to = new Date();
    var from = new Date(to.getTime() - days * 24 * 60 * 60 * 1000);
    $('logDateFrom').value = from.toISOString().split('T')[0];
    $('logDateTo').value = to.toISOString().split('T')[0];
    mgLoadLog();
};

/* ══════════════════════════════════════════════════
   AUDIT LOG
══════════════════════════════════════════════════ */
window.mgLoadLog = async function(){
    const from=$('logDateFrom').value;
    const to=$('logDateTo').value;
    let url='/api/org-stats/';
    // If your backend supports date filtering on scans endpoint use it:
    // url=`/api/scans/?date_from=${from}&date_to=${to}`;
    try{
        const res=await api(url);
        if(res.ok){
            const d=await res.json();
            allLog=[
                ...(d.recent_scans||[]).map(s=>({type:'scan',title:`${s.user_name} scanned ${s.checkpoint_name}`,sub:s.route_name||'',ts:s.timestamp})),
                ...(d.active_deployments||[]).map(a=>({type:'deploy',title:`${a.guard_supervisor_name} deployed — ${a.route_name||'Free Patrol'}`,sub:`Shift: ${a.shift_type||'—'}`,ts:a.assigned_at})),
            ].sort((a,b)=>new Date(b.ts)-new Date(a.ts));
        }
    }catch(e){}
    mgRenderLog();
}

window.mgLogFilter=function(f,el){
    logFilter=f;
    $$('#mgPanelAudit .mg-filter-chip').forEach(c=>c.classList.remove('active'));
    el.classList.add('active');
    mgRenderLog();
};

function mgRenderLog(){
    let list=allLog;
    if(logFilter!=='all') list=list.filter(l=>l.type===logFilter);
    const el=$('auditLogList');
    if (!el) return;
    if(!list.length){el.innerHTML='<div class="mg-empty"><i class="fas fa-scroll"></i>No log entries</div>';return;}

    const iconMap={scan:{cls:'scan',i:'fa-wifi'},deploy:{cls:'deploy',i:'fa-rocket'},alert:{cls:'alert',i:'fa-bell'},info:{cls:'info',i:'fa-info'}};
    el.innerHTML=list.slice(0,80).map((l,i)=>{
        const ic=iconMap[l.type]||{cls:'info',i:'fa-info'};
        const dt=l.ts?new Date(l.ts).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'—';
        return `
        <div class="mg-audit-item" style="--i:${i};">
            <div class="mg-audit-icon ${ic.cls}"><i class="fas ${ic.i}"></i></div>
            <div class="mg-audit-body">
                <div class="mg-audit-title">${l.title}</div>
                ${l.sub?`<div class="mg-audit-sub">${l.sub}</div>`:''}
            </div>
            <div class="mg-audit-time">${dt}</div>
        </div>`;
    }).join('');
}

/* ══════════════════════════════════════════════════
   MODAL
══════════════════════════════════════════════════ */
window.mgOpenModal=function(type, existing=null){
    currentModal=type; editId=existing?.id||null;
    const titles={guard:'Onboard Field Officer',callsign:'Modify Shift Assignment',device:'Register Tactical Device',checkpoint:'Tactical Checkpoint Builder',shift:'Reassign Shift','blueprint-shift':'Deploy Guard to Blueprint','shift-pair':'Create Shift Pair',asset:'Tactical Asset Registry'};

    // Use centered modal for all types (removed side-drawer behavior)
    // if(['asset', 'device', 'checkpoint', 'guard'].includes(type)) { $('mgModal').classList.add('side-drawer'); $('mgModal').parentElement.classList.add('side-mode'); }

    $('mgModalTitle').innerHTML=`<i class="fas ${type==='guard'?'fa-user-plus':type==='device'?'fa-mobile-screen':type==='shift'?'fa-calendar-day':type==='callsign'?'fa-clock-rotate-left':type==='shift-pair'?'fa-link':'fa-map-pin'}" style="color:var(--primary-light)"></i> ${titles[type]||'Add Entry'}`;
    $('mgSubmitLabel').textContent=existing?'Save Changes':'Create';

    const guardOpts=(allGuards||[]).map(g=>{
        const label=(g.first_name&&g.last_name)?`${g.first_name} ${g.last_name}`:(g.username||'Unknown');
        return `<option value="${g.id}">${label} (${g.callsign||'N/A'})</option>`;
    }).join('');

    if(type==='guard'){
        $('mgModalBody').innerHTML=`
            <div class="mg-g2">
                <div>
                    <label class="mg-fi-label">First Name</label>
                    <input id="mFn" class="mg-fi" value="${existing?.first_name||''}">
                </div>
                <div>
                    <label class="mg-fi-label">Last Name</label>
                    <input id="mLn" class="mg-fi" value="${existing?.last_name||''}">
                </div>
                <div>
                    <label class="mg-fi-label">Shift Pattern</label>
                    <select id="mShift" class="mg-fi">
                        <option${existing?.shift==='Day'?' selected':''}>Day</option>
                        <option${existing?.shift==='Night'?' selected':''}>Night</option>
                        <option${existing?.shift==='Flex'?' selected':''}>Flex</option>
                    </select>
                </div>
                <div>
                    <label class="mg-fi-label">Role</label>
                    <select id="mRole" class="mg-fi">
                        <option value="guard"${existing?.role==='guard'?' selected':''}>Guard</option>
                        <option value="supervisor"${existing?.role==='supervisor'?' selected':''}>Supervisor</option>
                    </select>
                </div>
            </div>`;

    }else if(type==='callsign'){
        const guardListOpts = (allGuards||[]).map(g => {
            const label = [g.first_name, g.last_name].filter(Boolean).join(' ') || g.username || 'Unnamed';
            const isSel = existing?.current_guard === g.id ? ' selected' : '';
            return `<option value="${g.id}"${isSel}>${label}</option>`;
        }).join('');

        $('mgModalBody').innerHTML = `
            <div style="margin-bottom:15px; padding:10px; background:rgba(255,255,255,0.05); border-radius:10px;">
                <div class="mg-lbl" style="margin-bottom:4px;">Callsign Identity</div>
                <div style="font-size:1.1rem; font-weight:900; color:var(--primary-light);">${existing?.callsign}</div>
                <div style="font-size:0.75rem; color:rgba(255,255,255,0.4);">${existing?.device_name} (${existing?.device_id_code})</div>
            </div>
            
            <label class="mg-fi-label">Active Operator Assignment</label>
            <select id="mCsGuard" class="mg-fi">
                <option value="">— Unassign / Return to Pool —</option>
                ${guardListOpts}
            </select>
            
            <label class="mg-fi-label">Duty Shift Context</label>
            <select id="mCsShift" class="mg-fi">
                <option value="Day"${existing?.active_shift==='Day'?' selected':''}>Day Shift</option>
                <option value="Night"${existing?.active_shift==='Night'?' selected':''}>Night Shift</option>
                <option value="Flex"${existing?.active_shift==='Flex'?' selected':''}>Flex / On-Call</option>
            </select>
            
            <div style="font-size:.65rem;color:rgba(255,255,255,.35);line-height:1.4;margin-top:10px;">
                <i class="fas fa-info-circle"></i> Updating this assignment will link the device to the officer and initiate a Shift Assignment for the chosen duty cycle.
            </div>`;

    }else if(type==='device'){
        // Show ALL guards so we can assign hardware to them for the first time
        const guardNameOpts = (allGuards||[]).map(g => {
            const label = [g.first_name, g.last_name].filter(Boolean).join(' ') || g.username || 'Unnamed';
            const isSel = existing?.assigned_guard_id === g.id ? ' selected' : '';
            const suffix = g.callsign ? ` (${g.callsign})` : '';
            return `<option value="${g.id}"${isSel}>${label}${suffix}</option>`;
        }).join('');

        $('mgModalBody').innerHTML=`
            <div class="mg-lbl" style="margin-bottom:12px; color:rgba(255,255,255,0.6)">Hardware Access & Identity</div>
            <hr class="mg-divider">
            <div class="mg-lbl" style="margin-bottom:12px; color:rgba(255,255,255,0.6)">Hardware & Telemetry</div>
            <div class="mg-g2">
                <div>
                    <label class="mg-fi-label">IMEI</label>
                    <input id="mDimei" class="mg-fi" placeholder="e.g. 352656106111232" value="${existing?.imei||''}">
                </div>
                <div>
                    <label class="mg-fi-label">IMSI</label>
                    <input id="mDimsi" class="mg-fi" placeholder="e.g. 310150123456789" value="${existing?.imsi||''}">
                </div>
            </div>
            <div class="mg-g2">
                <div>
                    <label class="mg-fi-label">SIM Phone Number</label>
                    <input id="mDsphone" class="mg-fi" placeholder="e.g. +254712345678" value="${existing?.sim_phone_number||''}">
                </div>
                <div>
                    <label class="mg-fi-label">OS Version</label>
                    <input id="mDos" class="mg-fi" placeholder="e.g. Android 14" value="${existing?.os_version||''}">
                </div>
            </div>
            <div class="mg-g2">
                <div>
                    <label class="mg-fi-label">Manufacturer</label>
                    <input id="mDman" class="mg-fi" placeholder="e.g. Samsung" value="${existing?.manufacturer||''}">
                </div>
                <div>
                    <label class="mg-fi-label">Model</label>
                    <input id="mDmodel" class="mg-fi" placeholder="e.g. Galaxy S24" value="${existing?.model||''}">
                </div>
            </div>

            <hr class="mg-divider">

            <label class="mg-fi-label" for="mDid">Device Login Code *</label>
            <div style="display:flex; gap:8px;">
                <input id="mDid" class="mg-fi" placeholder="ORG-NN (e.g. TCN-01)" value="${existing?.assigned_callsign || existing?.callsign || ''}" style="margin-bottom:0; flex:1;">
                <button type="button" class="mg-btn mg-btn-sm" onclick="mgGenerateLoginCode()" style="white-space:nowrap; height:38px;">
                    <i class="fas fa-magic"></i> Generate
                </button>
            </div>
            ${existing?.device_id ? `<div style="font-size:0.65rem; color:rgba(255,255,255,0.35); margin-top:2px;">Hardware ID: ${existing.device_id}</div>` : ''}
            <div style="font-size:0.65rem; color:rgba(255,255,255,0.35); margin-top:4px; margin-bottom:12px;">
                This code is required for the officer to log into the mobile application on this device.
            </div>

            <label class="mg-fi-label" for="mDpwd">Device Password</label>
            <div style="display:flex; gap:8px;">
                <input id="mDpwd" class="mg-fi" type="text" placeholder="Auto-generated if left blank" value="" style="margin-bottom:0; flex:1;">
                <button type="button" style="white-space:nowrap; height:38px;">
                    <i class="fas fa-key"></i> Generate
                </button>
            </div>
            <div style="font-size:0.65rem; color:rgba(255,255,255,0.35); margin-top:4px; margin-bottom:12px;">
                The device uses this password to authenticate with the server. If left blank, one will be auto-generated on save.
            </div>
            
            <hr class="mg-divider">
            
            <div class="mg-lbl" style="margin-bottom:12px; color:rgba(255,255,255,0.6)">Deployment Configuration</div>
            <label class="mg-fi-label" for="mDcall">Initial Operator Assignment</label>
            <select id="mDcall" class="mg-fi">
                <option value="">— Keep Unassigned (In Pool) —</option>
                ${guardNameOpts}
            </select>
            <div style="font-size:.65rem;color:rgba(255,255,255,.35);line-height:1.4;margin-top:4px;">
                <i class="fas fa-info-circle"></i> Assigning an officer will bind this hardware's callsign to their profile and start an active shift.
            </div>`;


    }else if(type==='checkpoint'){
        const lat = existing?.geometry?.[0] || '';
        const lng = existing?.geometry?.[1] || '';
        const onlineUnits = allDevices.filter(d => d.is_online);
        const unitOpts = onlineUnits.map(u => `<option value="${u.device_id}">${u.device_name} (${u.assigned_callsign || 'No Callsign'})</option>`).join('');

        $('mgModalBody').innerHTML = `
            <label class="mg-fi-label" for="mCpName">Checkpoint Identity *</label>
            <input id="mCpName" class="mg-fi" placeholder="e.g. Server Room B Gate" value="${existing?.name||''}">
            
            <div class="mg-lbl" style="margin: 15px 0 10px; display:flex; justify-content:space-between;">
                <span>Data Acquisition Source</span>
                <span style="font-size:0.55rem; color:var(--text-muted); text-transform:none;">Manual vs Remote Capture</span>
            </div>

            <div class="mg-shift-pill" style="width: 100%; margin-bottom:15px;">
                <input type="radio" name="cpSource" value="manual" id="cpSrcManual" checked class="rs-shift-radio" onchange="mgToggleCpSource('manual')">
                <label for="cpSrcManual" class="mg-btn" style="flex:1; border:none; background:none; justify-content:center;">Manual Entry</label>
                <input type="radio" name="cpSource" value="remote" id="cpSrcRemote" class="rs-shift-radio" onchange="mgToggleCpSource('remote')">
                <label for="cpSrcRemote" class="mg-btn" style="flex:1; border:none; background:none; justify-content:center;"><i class="fas fa-tower-broadcast"></i> Remote Fetch</label>
            </div>

            <div id="cpManualFields">
                <div class="mg-g2">
                    <div class="form-group">
                        <label class="mg-fi-label">NFC Serial (Manual)</label> <!-- Changed ID to mCpNfcTag to avoid conflict -->
                    <input id="mCpNfcTag" class="mg-fi" placeholder="UID: 04:A1:..." value="${existing?.nfc_tag||''}" oninput="mgOnCpTagInput(this.value)">
                    </div>
                    <div>
                        <label class="mg-fi-label" style="margin-bottom:4px;">Operational Parameters</label>
                        <div class="rs-cp-settings" style="border:none; padding:0;">
                            <div class="rs-cp-setting on" for="mCpRad" onclick="cbToggleProp(event,this)">
                                <i class="fas fa-circle-dot"></i>
                                <input type="number" id="mCpRad" class="si" value="${existing?.radius||50}">
                                <span class="sl">rad</span>
                                <span class="su">m</span>
                            </div>
                            <div class="rs-cp-setting ${existing?.dwell_time > 0 ? 'on' : ''}" for="mCpDwell" onclick="cbToggleProp(event,this)">
                                <i class="fas fa-stopwatch"></i>
                                <input type="number" id="mCpDwell" class="si" value="${existing?.dwell_time||0}">
                                <span class="sl">stay</span>
                                <span class="su">min</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div id="cpRemoteFields" class="mg-hidden" style="background:rgba(211,47,47,0.05); border:1px solid rgba(211,47,47,0.15); border-radius:12px; padding:15px; margin-bottom:15px;">
                <label class="mg-fi-label" for="mCpRemoteUnit" style="color:var(--primary-light);">Targeting Callsign (Remote Unit)</label>
                <select id="mCpRemoteUnit" class="mg-fi">${unitOpts || '<option value="">No online units detected</option>'}</select>
                
                <div class="mg-g2">
                    <div>
                        <label class="mg-fi-label">Discovery Window</label>
                        <select id="mCpWindow" class="mg-fi"><option value="5">5 Minutes</option><option value="10">10 Minutes</option></select>
                    </div>
                    <div style="display:flex; align-items:flex-end; padding-bottom:10px;">
                        <button type="button" class="mg-btn mg-btn-primary mg-btn-sm" style="width:100%;" onclick="mgStartRemoteCapture()">
                            <i class="fas fa-satellite-dish"></i> Open Window
                        </button>
                    </div>
                </div>

                <div id="remoteStatus" class="mg-hidden" style="margin-top:10px; display:flex; align-items:center; gap:10px; font-size:0.7rem; font-weight:800; color:var(--primary-light);">
                    <div class="pulse" style="background:var(--primary);"></div>
                    <span>LISTENING FOR FIELD DATA...</span>
                    <span id="remoteTimer" style="margin-left:auto; opacity:0.6;">05:00</span>
                </div>
            </div>

            <div class="mg-lbl" style="margin-top:5px; margin-bottom:10px; color:var(--primary-light);">
                <i class="fas fa-location-crosshairs"></i> GEO-PERIMETER COORDINATES
            </div>
            <div id="mPickerMap" style="height:160px; border-radius:12px; border:1px solid var(--border); background:#000; margin-bottom:12px;"></div>
            
            <div class="mg-g2">
                <div class="form-group"><label class="mg-fi-label" for="mCplat">Latitude</label><input id="mCplat" class="mg-fi mg-fi-sm" readonly value="${lat}"></div>
                <div class="form-group"><label class="mg-fi-label" for="mCplng">Longitude</label><input id="mCplng" class="mg-fi mg-fi-sm" readonly value="${lng}"></div>
            </div>`;

        setTimeout(() => mgInitPickerMap(lat, lng), 100);

    }else if(type==='shift'){
        const deviceOpts = (allDevices||[]).map(d => 
            `<option value="${d.id}">${d.device_name} ${d.is_online ? '(Online)' : '(Offline)'}</option>`
        ).join('');

        $('mgModalBody').innerHTML=`<div class="form-group">
            <label class="mg-fi-label" for="mSguard">Guard</label>
            <select id="mSguard" class="mg-fi"><option value="">Select guard…</option>${guardOpts}</select>
            </div><div class="form-group"><label class="mg-fi-label" for="mSshift">Duty Shift</label>
            <select id="mSshift" class="mg-fi">
                <option>Day</option><option>Night</option><option>Flex</option>
            </select>
            </div><div class="form-group"><label class="mg-fi-label" for="mSdevice">Link Tactical Device</label>
            <select id="mSdevice" class="mg-fi">
                <option value="">— No device change —</option>
                ${deviceOpts}
            </select>
            <div class="mg-g2">
                <div class="form-group"><label class="mg-fi-label" for="mSstart">Shift Begin</label><input type="datetime-local" id="mSstart" class="mg-fi"></div>
                <div class="form-group"><label class="mg-fi-label" for="mSend">Shift End</label><input type="datetime-local" id="mSend" class="mg-fi"></div>
            </div>
            <div style="font-size:.7rem;color:rgba(255,255,255,.4);margin-top:6px;">
                <i class="fas fa-info-circle"></i> This creates an active deployment linking the guard to the chosen device.
            </div>`;

    }else if(type==='blueprint-shift'){
        const curRoute = existing ? (existing.route_id || existing.route) : ($('mgBlueprintSelect')?.value || '');
        const curGuard = existing ? (existing.guard_supervisor_id || existing.guard_supervisor) : '';
        const curDevice = existing ? (existing.device_id || existing.device) : '';
        const curShift = existing ? (existing.shift_type) : 'Day';

        const deviceOpts = (allDevices||[]).map(d =>
            `<option value="${d.id}" ${String(curDevice)===String(d.id)?'selected':''}>${d.device_name} ${d.is_online ? '(Online)' : '(Offline)'}</option>`
        ).join('');

        const allRouteOpts = (allRoutes||[]).map(r=>{
            const sel = curRoute && String(curRoute)===String(r.id) ? ' selected' : '';
            return `<option value="${r.id}"${sel}>${r.name}</option>`;
        }).join('');

        const allGuardOpts = (allGuards||[]).map(g => {
            const label = [g.first_name, g.last_name].filter(Boolean).join(' ') || g.username || 'Unnamed';
            const sel = String(curGuard)===String(g.id) ? ' selected' : '';
            return `<option value="${g.id}"${sel}>${label} (${g.callsign||'N/A'})</option>`;
        }).join('');

        $('mgModalBody').innerHTML=`
            <label class="mg-fi-label" for="mBsRoute">Blueprint</label>
            <select id="mBsRoute" class="mg-fi">
                <option value="">Select blueprint…</option>
                ${allRouteOpts}
            </select>

            <label class="mg-fi-label" for="mBsGuard">Guard</label>
            <select id="mBsGuard" class="mg-fi"><option value="">Select guard…</option>${allGuardOpts}</select>

            <label class="mg-fi-label" for="mBsShift">Duty Shift</label>
            <select id="mBsShift" class="mg-fi">
                <option value="Day" ${curShift==='Day'?'selected':''}>Day</option>
                <option value="Night" ${curShift==='Night'?'selected':''}>Night</option>
                <option value="Flex" ${curShift==='Flex'?'selected':''}>Flex</option>
            </select>

            <label class="mg-fi-label" for="mBsDevice">Link Tactical Device (optional)</label>
            <select id="mBsDevice" class="mg-fi">
                <option value="">— Use guard's current device —</option>
                ${deviceOpts}
            </select>
            <div class="mg-g2">
                <div><label class="mg-fi-label">Scheduled Start</label><input type="datetime-local" id="mBsStart" class="mg-fi"></div>
                <div><label class="mg-fi-label">Scheduled End</label><input type="datetime-local" id="mBsEnd" class="mg-fi"></div>
            </div>

            <div style="font-size:.7rem;color:rgba(255,255,255,.4);margin-top:6px;">
                <i class="fas fa-info-circle"></i> Creates an active <b>ShiftAssignment</b> tied to the selected blueprint.
            </div>`;

    }else if(type==='asset'){
        const lat = existing?.geometry?.[0] || '';
        const lng = existing?.geometry?.[1] || '';

        $('mgModalBody').innerHTML=`
            <label class="mg-fi-label" for="mAname">Object Name *</label>
            <input id="mAname" class="mg-fi" placeholder="e.g. Gate A Checkpoint" value="${existing?.name||''}">
            <div class="mg-g2">
                <div>
                    <label class="mg-fi-label" for="mAtype">Type</label>
                    <select id="mAtype" class="mg-fi">
                        <option value="poi"${existing?.type==='poi' && existing?.radius ? ' selected':''}>Circle Geofence</option>
                        <option value="geofence"${existing?.type==='geofence'?' selected':''}>Polygon perimeter</option>
                        <option value="poi"${existing?.type==='poi' && !existing?.radius ? ' selected':''}>Standard POI</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="mg-fi-label" for="mAtag">NFC Tag (Optional)</label>
                    <input id="mAtag" class="mg-fi" placeholder="Tag ID" value="${existing?.nfc_tag||''}">
                </div>
            </div>
            
            <div class="mg-g2">
                <div class="form-group">
                    <label class="mg-fi-label" for="mAtimer">Planned Time (Timed Asset)</label>
                    <input id="mAtimer" type="time" class="mg-fi" value="${existing?.planned_time||''}">
                </div>
                <div class="form-group">
                    <label class="mg-fi-label" for="mArad">Detection Radius (meters)</label>
                    <input id="mArad" class="mg-fi" type="number" placeholder="50" value="${existing?.radius||'50'}">
                </div>
            </div>

            <div class="mg-lbl" style="margin-top:10px; margin-bottom:10px; color:var(--primary-light);">Peer Audit Config</div>
            <div class="mg-g2">
                <div><label class="mg-fi-label">Auditor Callsign</label><input id="mAauditor" class="mg-fi" placeholder="e.g. T-01" value="${existing?.auditor_id||''}"></div>
                <div><label class="mg-fi-label">Target Callsign</label><input id="mAtarget" class="mg-fi" placeholder="e.g. G-05" value="${existing?.target_id||''}"></div>
            </div>

            <div class="mg-lbl" style="margin-top:10px; margin-bottom:10px; color:var(--primary-light); display:flex; justify-content:space-between; align-items:center;">
                <span><i class="fas fa-location-crosshairs"></i> DROP TACTICAL PIN</span>
            </div>
            <div id="mPickerMap" style="height:200px; border-radius:12px; border:1px solid var(--border); background:#000; margin-bottom:12px; position:relative;" role="img" aria-label="Map for selecting location">
                <div style="position:absolute; inset:0; z-index:1000; display:flex; align-items:center; justify-content:center; pointer-events:none; background:rgba(0,0,0,0.3);" id="mPickerOverlay">
                    <span style="font-size:0.6rem; background:rgba(0,0,0,0.6); padding:4px 10px; border-radius:20px; border:1px solid var(--border);">Click to set location</span>
                </div>
            </div>
            
            <div class="mg-g2">
                <div class="form-group"><label class="mg-fi-label" for="mAlat">Latitude</label><input id="mAlat" class="mg-fi mg-fi-sm" readonly value="${lat}"></div>
                <div class="form-group"><label class="mg-fi-label" for="mAlng">Longitude</label><input id="mAlng" class="mg-fi mg-fi-sm" readonly value="${lng}"></div>
            </div>
            
            <div style="font-size:.65rem;color:rgba(255,255,255,.3);line-height:1.4;">
                <i class="fas fa-info-circle"></i> Use the map to set GPS coordinates. Use Map View for complex shapes.
            </div>`;
            
        setTimeout(() => mgInitPickerMap(lat, lng), 100);

    }else if(type==='shift-pair'){
        const deviceOpts = (allDevices||[]).map(d =>
            `<option value="${d.id}">${d.device_name} (${d.callsign||'No callsign'})</option>`
        ).join('');
        const guardOpts = (allGuards||[]).map(g => {
            const label = [g.first_name, g.last_name].filter(Boolean).join(' ') || g.username || 'Unnamed';
            const lc = `(${g.callsign||'N/A'})`;
            const shiftDot = g.shift === 'Day' ? '&#9788;' : g.shift === 'Night' ? '&#9790;' : '&#9881;';
            return `<option value="${g.id}">${label} ${lc} ${shiftDot} ${g.shift||'Flex'}</option>`;
        }).join('');

        $('mgModalBody').innerHTML=`
            <div style="padding:10px 12px;background:rgba(255,255,255,0.03);border-radius:10px;margin-bottom:14px;display:flex;align-items:center;gap:8px;font-size:0.68rem;color:rgba(255,255,255,0.5);">
                <i class="fas fa-info-circle" style="color:var(--primary-light);"></i>
                Bind <strong>two guards</strong> to one device so they share a callsign as a shift pair.
            </div>

            <label class="mg-fi-label"><i class="fas fa-microchip" style="margin-right:4px;"></i> Shared Device</label>
            <select id="mSpDevice" class="mg-fi">
                <option value="">— Select device —</option>
                ${deviceOpts}
            </select>

            <hr class="mg-divider">

            <div style="display:grid;grid-template-columns:1fr auto 1fr;gap:10px;align-items:start;">
                <div>
                    <label class="mg-fi-label" style="color:#FFD54F;">Primary Guard</label>
                    <select id="mSpGuard1" class="mg-fi">
                        <option value="">— Select —</option>
                        ${guardOpts}
                    </select>
                    <label class="mg-fi-label" style="margin-top:6px;">Shift</label>
                    <select id="mSpShift1" class="mg-fi">
                        <option value="Day">Day</option>
                        <option value="Night">Night</option>
                        <option value="Flex">Flex</option>
                    </select>
                </div>
                <div style="display:flex;flex-direction:column;align-items:center;padding-top:30px;color:rgba(255,255,255,0.12);gap:4px;">
                    <i class="fas fa-link" style="font-size:1rem;"></i>
                    <span style="font-size:0.45rem;text-transform:uppercase;letter-spacing:0.5px;">Pair</span>
                </div>
                <div>
                    <label class="mg-fi-label" style="color:#7986cb;">Secondary Guard</label>
                    <select id="mSpGuard2" class="mg-fi">
                        <option value="">— Select —</option>
                        ${guardOpts}
                    </select>
                    <label class="mg-fi-label" style="margin-top:6px;">Shift</label>
                    <select id="mSpShift2" class="mg-fi">
                        <option value="Night">Night</option>
                        <option value="Day">Day</option>
                        <option value="Flex">Flex</option>
                    </select>
                </div>
            </div>

            <hr class="mg-divider">

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
                <div>
                    <label class="mg-fi-label">Start Time</label>
                    <input type="datetime-local" id="mSpStart" class="mg-fi">
                </div>
                <div>
                    <label class="mg-fi-label">End Time</label>
                    <input type="datetime-local" id="mSpEnd" class="mg-fi">
                </div>
            </div>

            <div style="padding:8px 10px;background:rgba(93,202,165,0.05);border:1px solid rgba(93,202,165,0.1);border-radius:8px;margin-top:8px;font-size:0.62rem;color:#5DCAA5;display:flex;align-items:center;gap:6px;">
                <i class="fas fa-arrows-left-right"></i>
                At least one guard must be selected. Both will share the device's callsign.
            </div>`;
    }

    $('mgModal').classList.add('open');
};

window.mgCloseModal=function(){
    var bd=$('mgModal');
    if (!bd) return;
    bd.classList.add('closing');
    setTimeout(function(){
        bd.classList.remove('open','side-drawer','closing');
        bd.parentElement.classList.remove('side-mode');
        currentModal=null; editId=null;
    },200);
};

window.mgSubmit=async function(){
    let url='', payload={}, method='POST';
    let extraProvision=null; // for device provisioning after device save

    if(currentModal==='guard'){
        const fn = ($('mFn')?.value || '').trim();
        const ln = ($('mLn')?.value || '').trim();
        if (!fn && !ln) { showToast('Officer name required', 'error'); return; }

        payload = {
            first_name: fn,
            last_name: ln,
            shift: $('mShift').value,
            role: $('mRole').value,
        };

        if (editId) {
            url = `/api/profiles/${editId}/`;
            method = 'PUT';
        } else {
            url = '/api/scan-guards/';
            method = 'POST';
            if (typeof userData !== 'undefined' && userData.organization_id) {
                payload.organization = Array.isArray(userData.organization_id) ? userData.organization_id[0] : userData.organization_id;
            }
        }

    }else if(currentModal==='asset' || currentModal==='checkpoint'){
        const name=$('mAname').value.trim();
        const tag=$('mAtag').value.trim();
        const lat=$('mAlat').value.trim();
        const lng=$('mAlng').value.trim();
        const cpRadChip = document.querySelector('.rs-cp-setting[for="mCpRad"]');
        const cpDwellChip = document.querySelector('.rs-cp-setting[for="mCpDwell"]');
        const rad = cpRadChip?.classList.contains('on') ? ($('mArad')?.value || $('mCpRad')?.value) : null;
        const dwell = cpDwellChip?.classList.contains('on') ? ($('mAdwell')?.value || $('mCpDwell')?.value) : 0;
        const time=$('mAtimer').value;
        const aid=$('mAauditor').value.trim();
        const tid=$('mAtarget').value.trim();

        if(!name){ showToast('Designation name required', 'error'); return; }
        let typeVal = $('mAtype').value;
        if (typeVal === 'patrol_point') typeVal = 'poi';

        url='/api/map-objects/';
        method = editId ? 'PUT' : 'POST';
        if(editId) url += `${editId}/`;

        payload={
            name,
            nfc_tag: tag || null,
            type: typeVal,
            geometry: lat && lng ? [parseFloat(lat), parseFloat(lng)] : null,
            radius: rad ? parseInt(rad, 10) : null,
            dwell_time: parseInt(dwell, 10),
            planned_time: time || null,
            auditor_id: aid || null,
            target_id: tid || null,
            assigned_personnel: []
        };

    }else if(currentModal==='callsign'){
        const cs = allCallsigns.find(x => x.id === editId);
        const gid = $('mCsGuard').value;
        const shift = $('mCsShift').value;
        
        if(!gid) {
            url = `/api/callsigns/${editId}/`;
            method = 'PATCH';
            payload = { current_guard: null, active_shift: '' };
        } else {
            url = '/api/provision-device/';
            method = 'POST';
            payload = { device_id: cs.device_id_code, guard_id: gid };
            // Sync guard shift if changed
            const guard = allGuards.find(g => String(g.id) === String(gid));
            if(guard && guard.shift !== shift) {
                await api(`/api/profiles/${gid}/`, { method: 'PATCH', body: JSON.stringify({ shift }) });
            }
        }

    }else if(currentModal==='device'){
        const devicePayload={
            device_id:$('mDid').value,
            imei: $('mDimei')?.value || null,
            imsi: $('mDimsi')?.value || null,
            sim_phone_number: $('mDsphone')?.value || null,
            os_version: $('mDos')?.value || null,
            manufacturer: $('mDman')?.value || null,
            model: $('mDmodel')?.value || null,
        };
        const pwd = $('mDpwd')?.value?.trim();
        if (pwd) devicePayload.password = pwd;
        if(!devicePayload.device_id){ toast('Operator ID required (e.g. TCN-01)',true); return; }

        // Save Device
        url='/api/devices/';
        payload=devicePayload;
        method='POST';

        if(editId){
            url=`/api/devices/${editId}/`;
            method='PATCH';
        }

        // Optional: provision hardware_id -> guard callsign
        const guardId=$('mDcall')?.value;
        if(guardId){
            extraProvision={ device_id: devicePayload.device_id, guard_id: guardId };
        }

    }else if(currentModal==='checkpoint'){
        const name = $('mCpName').value.trim();
        const tag  = $('mCpTag').value.trim();
        const lat  = $('mCplat').value.trim();
        const lng  = $('mCplng').value.trim();
        const rad  = $('mCpRad').value.trim();
        if(!name){ toast('Checkpoint name required', true); return; }

        url = '/api/map-objects/';
        method = editId ? 'PUT' : 'POST';
        if(editId) url += `${editId}/`;

        payload = {
            name,
            nfc_tag: tag || null,
            type: 'poi',
            geometry: (lat && lng) ? [parseFloat(lat), parseFloat(lng)] : null,
            radius: rad ? parseInt(rad, 10) : 50,
            assigned_personnel: []
        };

    }else if(currentModal==='shift'){
        const gid=$('mSguard').value;
        const deviceId=$('mSdevice').value;
        const shiftType=$('mSshift').value;
        if(!gid){ toast('Select a guard',true); return; }

        if(deviceId) {
            // Create an actual shift assignment linking device and guard
            url='/api/shifts/';
            method='POST';
            payload={
                guard_supervisor: parseInt(gid),
                device: parseInt(deviceId),
                shift_type: shiftType,
                is_active: true
            };
        } else {
            // Fallback: just update the profile preference
            url=`/api/profiles/${gid}/`;
            method='PATCH';
            payload={shift:shiftType};
        }

    }else if(currentModal==='blueprint-shift'){
        const guardId=$('mBsGuard').value;
        const routeId=$('mBsRoute').value;
        const shiftType=$('mBsShift').value;
        const deviceId=$('mBsDevice').value;
        const start = $('mBsStart').value;
        const end = $('mBsEnd').value;

        if(!guardId){ toast('Select a guard',true); return; }
        if(!routeId){ toast('Select a blueprint',true); return; }
        if(!shiftType){ toast('Select a duty shift',true); return; }

        payload={
            guard_id: parseInt(guardId),
            route_id: parseInt(routeId),
            shift_type: shiftType,
            scheduled_start: start,
            scheduled_end: end,
            ...(deviceId ? { device_id: parseInt(deviceId) } : {})
        };

        if(editId) {
            url = `/api/shifts/${editId}/`;
            method = 'PATCH';
            // Adjust payload for standard ShiftAssignment endpoint
            payload = {
                guard_supervisor: parseInt(guardId),
                route: parseInt(routeId),
                shift_type: shiftType,
                device: deviceId ? parseInt(deviceId) : null,
                scheduled_start: start,
                scheduled_end: end
            };
        } else {
            url='/api/assign-guard-to-blueprint-shift/';
            method='POST';
        }

    }else if(currentModal==='asset'){

        const name=$('mAname').value.trim();
        const tag=$('mAtag').value.trim();
        const lat=$('mAlat').value.trim();
        const lng=$('mAlng').value.trim();
        const rad=$('mArad').value.trim();
        const time=$('mAtimer').value;
        const aid=$('mAauditor').value.trim();
        const tid=$('mAtarget').value.trim();

        if(!name){ toast('Name required',true); return; }
        let typeVal = $('mAtype').value;
        if (typeVal === 'patrol_point') typeVal = 'poi';

        url='/api/map-objects/';
        payload={
            name,
            nfc_tag: tag || null,
            type: typeVal,
            geometry: lat && lng ? [parseFloat(lat), parseFloat(lng)] : null,
            radius: rad ? parseInt(rad, 10) : null,
            planned_time: time || null,
            auditor_id: aid || null,
            target_id: tid || null,
            assigned_personnel: []
        };

    }else if(currentModal==='shift-pair'){
        const deviceId=$('mSpDevice').value;
        const g1=$('mSpGuard1').value;
        const s1=$('mSpShift1').value;
        const g2=$('mSpGuard2').value;
        const s2=$('mSpShift2').value;
        const start=$('mSpStart').value;
        const end=$('mSpEnd').value;
        if(!deviceId){ toast('Select a device',true); return; }
        if(!g1 && !g2){ toast('Select at least one guard',true); return; }

        // Make both calls then handle result
        const calls = [];
        if(g1) calls.push(api('/api/assign-guard-to-blueprint-shift/',{method:'POST',body:JSON.stringify({
            guard_id: parseInt(g1), device_id: parseInt(deviceId),
            shift_type: s1, scheduled_start: start, scheduled_end: end
        })}));
        if(g2) calls.push(api('/api/assign-guard-to-blueprint-shift/',{method:'POST',body:JSON.stringify({
            guard_id: parseInt(g2), device_id: parseInt(deviceId),
            shift_type: s2, scheduled_start: start, scheduled_end: end
        })}));

        const results = await Promise.all(calls);
        const ok = results.every(r => r.ok);
        if(!ok){
            const errs = await Promise.all(results.filter(r => !r.ok).map(r => r.json().catch(()=>({}))));
            toast('Pair creation failed: '+(errs[0]?.detail||'error').slice(0,80), true);
            return;
        }
        toast('Shift pair created — ' + (g1&&g2?'2 guards':'1 guard') + ' linked to device');
        mgCloseModal();
        mgRefreshBlueprintShift();
        return; // skip default handler
    }

    try{
        const res=await api(url,{method,body:JSON.stringify(payload)});
        if(!res.ok){
            const err=await res.json().catch(()=>({}));
            toast(JSON.stringify(err).slice(0,80)||'Save failed',true);
            // Improved error message display
            const errorMessage = err.detail || err.error || JSON.stringify(err) || 'Save failed';
            toast(errorMessage.slice(0, 150), true); // Slice to prevent very long messages
            return;
        }

        // If provisioning was requested, call it now
        if(currentModal==='device' && extraProvision){
            const pRes=await api('/api/provision-device/',{method:'POST',body:JSON.stringify(extraProvision)});
            if(!pRes.ok){
                const err=await pRes.json().catch(()=>({}));
                toast('Device provision failed: '+(JSON.stringify(err).slice(0,80)) ,true);
            }
        }

        toast(editId?'Entry updated':'Entry created');
        mgCloseModal();
        // Log fleet activity
        if (currentModal === 'device') {
            var devName = payload.device_id || 'Device';
            mgLogFleetEvent(editId ? 'info' : 'check', (editId ? 'Updated' : 'Registered') + ' device ' + devName, editId ? 'Modified' : 'New');
        } else if (currentModal === 'blueprint-shift' || currentModal === 'shift') {
            mgLogFleetEvent('deploy', 'Assignment changed', 'Shift update');
        }
        const reload={guard:()=>mgLoadGuards(),device:()=>mgLoadDevices(),shift:()=>mgLoadGuards().then(function(){if(window.CalendarComponent)CalendarComponent.render();}),asset:()=>mgLoadAssets()};
        if(reload[currentModal]) reload[currentModal]();
        if(currentModal==='blueprint-shift') mgRefreshBlueprintShift();

    }catch(e){ toast('Network error',true); }
};

/* ── Edit Shift Assignment ───────────────────────── */
window.mgEditAssignmentCallsign = function(id) {
    const s = allDeploys.find(x => x.id === id);
    if(!s) return;
    mgOpenModal('blueprint-shift', s);
};

/* ── Delete ─────────────────────────────────────── */
window.mgDelete=async function(endpoint,id,reloadTab){
    if(!confirm('Permanently remove this entry?')) return;
    try{
        const res=await api(`/api/${endpoint}/${id}/`,{method:'DELETE'});
        if(res.ok){
            toast('Removed');
            const reloaders={personnel:mgLoadGuards,devices:mgLoadDevices,assets:mgLoadAssets,routes:mgLoadRoutes};
            if(reloaders[reloadTab]) reloaders[reloadTab]();
        }else toast('Delete failed',true);
    }catch(e){ toast('Error',true); }
};

/* ── End Shift ──────────────────────────────────── */
window.mgEndShift = async function(id) {
    if(!confirm('End this guard assignment and release resources?')) return;
    try {
        const res = await api(`/api/shifts/${id}/`, { method:'PATCH', body: JSON.stringify({ is_active: false, ended_at: new Date().toISOString() }) });
        if(res.ok) { toast('Shift decommissioned'); mgRefreshBlueprintShift(); }
        else toast('Failed to end shift', true);
    } catch(e) { toast('Network error', true); }
};

/* ── Update Shift Timing ────────────────────────── */
window.mgUpdateShiftTimes = async function(id) {
    const start = document.getElementById(`startTime-${id}`).value;
    const end = document.getElementById(`endTime-${id}`).value;
    try {
        const res = await api(`/api/shifts/${id}/`, { method:'PATCH', body: JSON.stringify({ scheduled_start: start, scheduled_end: end }) });
        if(res.ok) { toast('Shift window updated'); mgRefreshBlueprintShift(); }
    } catch(e) { toast('Update failed', true); }
};

window.mgActivateUpcoming = async function(id) {
    try {
        const res = await api(`/api/shifts/${id}/`, { method:'PATCH', body: JSON.stringify({ is_active: true, assigned_at: new Date().toISOString() }) });
        if(res.ok) { toast('Deployment activated'); mgRefreshBlueprintShift(); }
    } catch(e) { toast('Error activating', true); }
};

/* ── Remote Capture Visuals ────────────────────── */
window.mgToggleCpSource = function(mode) {
    $('cpManualFields').classList.toggle('mg-hidden', mode === 'remote');
    $('cpRemoteFields').classList.toggle('mg-hidden', mode === 'manual');
    if(pickerMap) setTimeout(() => pickerMap.invalidateSize(), 100);
};

window.mgOnCpTagInput = function(val) {
    if(!val) return;
    const match = allAssets.find(a => a.nfc_tag === val);
    if(match && !$('mCpName').value.trim()) {
        $('mCpName').value = match.name;
        toast(`Resolved Checkpoint Name: ${match.name}`);
        if(pickerMap && match.geometry) pickerMap.setView(match.geometry, 16);
    }
};

window.mgStartRemoteCapture = function() {
    const unit = $('mCpRemoteUnit').value;
    if(!unit) { toast('Select an online unit first', true); return; }
    
    $('remoteStatus').classList.remove('mg-hidden');
    toast('Capture window opened. Android unit is now targeted.');
    
    // Mocking the "Fetch" logic for visuals
    setTimeout(() => {
        if(currentModal === 'checkpoint') {
            toast('NFC Data Received: 04:AE:55:12', false);
            $('mCpTag').value = '04:AE:55:12';
            $('mCplat').value = '-1.2921';
            $('mCplng').value = '36.8219';
            mgOnCpTagInput('04:AE:55:12'); // Auto-resolve name if known
            if(pickerMarker) pickerMarker.setLatLng([-1.2921, 36.8219]);
            pickerMap.setView([-1.2921, 36.8219], 16);
        }
    }, 4000);
};

/* ── Asset Picker Map ───────────────────────────── */
let pickerMap = null;
let pickerMarker = null;

function mgInitPickerMap(lat, lng) {
    const el = $('mPickerMap');
    if(!el) return;
    if(pickerMap) { pickerMap.remove(); pickerMap = null; pickerMarker = null; }
    
    const startCoords = (lat && lng) ? [lat, lng] : [0, 0];
    pickerMap = L.map('mPickerMap', { zoomControl: true, attributionControl: false }).setView(startCoords, lat ? 15 : 2);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png').addTo(pickerMap);
    
    if(lat && lng) {
        pickerMarker = L.marker([lat, lng]).addTo(pickerMap);
        $('mPickerOverlay')?.remove();
    } else if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(pos => {
            pickerMap.setView([pos.coords.latitude, pos.coords.longitude], 15);
        }, () => {}, { timeout: 3000 });
    }
    
    pickerMap.on('click', e => {
        const { lat, lng } = e.latlng;
        $('mPickerOverlay')?.remove();
        if(pickerMarker) pickerMarker.setLatLng(e.latlng);
        else pickerMarker = L.marker(e.latlng).addTo(pickerMap);
        
        $('mAlat').value = lat.toFixed(6);
        $('mAlng').value = lng.toFixed(6);
    });

    setTimeout(() => pickerMap.invalidateSize(), 150);
}

/* ── Device Personnel Filtering ─────────────────── */
window.mgUpdateDeviceGuardList = function() {
    const guardSel = $('mDcall');
    if(!guardSel) return;

    const currentSelectedId = guardSel.dataset.current;

    const opts = (allGuards||[]).map(g => {
        const label = [g.first_name, g.last_name].filter(Boolean).join(' ') || g.username || 'Unnamed';
        const isSel = String(currentSelectedId) === String(g.id) ? ' selected' : '';
        const suffix = g.callsign ? ` (${g.callsign})` : ' [New]';
        return `<option value="${g.id}"${isSel}>${label}${suffix}</option>`;
    }).join('');

    guardSel.innerHTML = '<option value="">— Keep Unassigned (In Pool) —</option>' + opts;
};

window.mgSetAssetType = function(type, btn) {
    const parent = btn.parentElement;
    parent.querySelectorAll('.mg-filter-chip').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    
    $('mAnfcWrap').classList.toggle('mg-hidden', type !== 'nfc');
    $('mApeerWrap').classList.toggle('mg-hidden', type !== 'peer');
    
    $('mAtype').value = (type === 'geo') ? 'geofence' : 'poi';
    $('mAclass').value = type;
};

/* ══════════════════════════════════════════════════
   MAP ASSETS: INLINE CHECKPOINT BUILDER ENGINE
══════════════════════════════════════════════════ */
let inlineCps = [];
let savedCps = [];
let inlineType = 'nfc';
let pickMode = null;
let cbMap = null;
let cbMarkers = [];
let cbPickMode = null;
let cbPickRow = null;

/* ── Map Init ──────────────────────────────────── */
var _cbMapInitTimer = null;
function initMap() {
    var el = document.getElementById('mgFleetMap');
    if (!el) return;
    if (cbMap) { cbMap.invalidateSize(); return; }
    try {
        cbMap = L.map('mgFleetMap', {
            zoomControl: false,
            attributionControl: false,
        }).setView([-1.2921, 36.8219], 13);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            maxZoom: 19,
        }).addTo(cbMap);

        L.control.zoom({ position: 'bottomright' }).addTo(cbMap);

        cbMap.on('click', function(e) {
            if (cbPickMode && cbPickRow) {
                var lat = e.latlng.lat.toFixed(6);
                var lng = e.latlng.lng.toFixed(6);
                var latInp = cbPickRow.querySelector('.cp-inline-lat');
                var lngInp = cbPickRow.querySelector('.cp-inline-lng');
                if (latInp) latInp.value = lat;
                if (lngInp) lngInp.value = lng;
                // Add a temporary marker
                var m = L.marker([e.latlng.lat, e.latlng.lng]).addTo(cbMap);
                m.bindPopup(cbPickMode.toUpperCase() + ' — ' + lat + ', ' + lng).openPopup();
                cbPickMode = null;
                cbPickRow = null;
                var hint = $('cbMapHint');
                if (hint) hint.classList.remove('active');
            }
        });

        cbMap.on('mousemove', function(e) {
            var coord = $('mgMapCoord');
            if (coord) coord.textContent = e.latlng.lat.toFixed(5) + ', ' + e.latlng.lng.toFixed(5);
        });

        // Fix map size after layout settles
        setTimeout(function() { cbMap.invalidateSize(); }, 500);
    } catch(e) {
        console.warn('Map init failed:', e);
    }
}
window.cbZoomFit = function() {
    if (cbMap && cbMarkers.length) {
        var group = L.featureGroup(cbMarkers);
        cbMap.fitBounds(group.getBounds().pad(0.3));
    }
};

/* Render checkpoint markers on map */
function mgRenderAssetsOnMap() {
    if (!cbMap) return;
    cbMarkers.forEach(function(m) { m.remove(); });
    cbMarkers = [];
    var rows = document.querySelectorAll('#cpRegistry .cb-reg-row');
    rows.forEach(function(r) {
        var lat = parseFloat(r.querySelector('.cp-inline-lat')?.value);
        var lng = parseFloat(r.querySelector('.cp-inline-lng')?.value);
        if (!isNaN(lat) && !isNaN(lng)) {
            var type = r.dataset.cpType || 'nfc';
            var colors = { nfc:'#d32f2f', gps:'#6C8EEF', geo:'#A855F7', peer:'#F59E0B' };
            var color = colors[type] || '#d32f2f';
            var marker = L.circleMarker([lat, lng], {
                radius: 6, fillColor: color, color: color, weight: 2, opacity: 0.9, fillOpacity: 0.6
            }).addTo(cbMap);
            marker.bindPopup((type.toUpperCase()) + ': ' + (r.querySelector('.cp-inline-name')?.value || 'Unnamed'));
            cbMarkers.push(marker);
        }
    });
}

window.cbPickForRow = function(btn) {
    var row = btn.closest('.cb-reg-row');
    if (!row) return;
    cbPickMode = row.dataset.cpType || 'gps';
    cbPickRow = row;
    var hint = $('cbMapHint');
    if (hint) {
        hint.classList.add('active');
        hint.innerHTML = '<i class="fas fa-crosshairs"></i> Click map to set <b>' + cbPickMode.toUpperCase() + '</b> location';
    }
    // Ensure map is visible and sized
    if (cbMap) cbMap.invalidateSize();
};

function addMapMarker(lat, lng, type) { }

function drawRadiusCircle(key, lat, lng, col) { }

function updateLiveMapPreview() { }
function clearAllMapMarkers() { }

function setInlineCoords(lat, lng) {
    var row = window._pickRow;
    if (row) {
        var latInp = row.querySelector('.cp-inline-lat');
        var lngInp = row.querySelector('.cp-inline-lng');
        if (latInp) latInp.value = lat.toFixed(6);
        if (lngInp) lngInp.value = lng.toFixed(6);
        window._pickRow = null;
    }
}

/* ── Map Tools (no-opped) ──────────────────────── */
window.cbActivateTool = function(tool) { };

/* ── Add Checkpoint flow (removed — use quick-add buttons) ── */
window.cbShowTypeSelector = function() { toast('Use the quick-add buttons below', true); };
window.cbSelectType = function() {};

/* ── Populate device callsigns into dropdowns ──── */
function populateDeviceCallsigns() {
    // NFC fetch device selector (datalist)
    const nfcInput = $('nfcFetchDevice');
    const nfcList = $('nfcDeviceList');
    if (nfcList) {
        const opts = allDevices.map(d => {
            const cs = d.assigned_callsign || d.device_name || 'Unit';
            const status = d.is_online ? '🟢' : '🔴';
            return `<option value="${cs}" data-id="${d.id}">${status} ${d.device_name} (${cs})</option>`;
        }).join('');
        nfcList.innerHTML = opts;
    }
    // Peer auditor/target selectors
    const auditorSelect = $('inlineAuditor');
    const targetSelect = $('inlineTarget');
    if (auditorSelect) {
        const opts = allDevices.map(d => {
            const cs = d.assigned_callsign || d.device_name || 'Unit';
            return `<option value="${cs}">${d.device_name} (${cs})</option>`;
        }).join('');
        auditorSelect.innerHTML = '<option value="">— Select auditor device —</option>' + opts;
    }
    if (targetSelect) {
        const opts = allDevices.map(d => {
            const cs = d.assigned_callsign || d.device_name || 'Unit';
            return `<option value="${cs}">${d.device_name} (${cs})</option>`;
        }).join('');
        targetSelect.innerHTML = '<option value="">— Select target device —</option>' + opts;
    }
};

function updateTypeCounts() {
    const counts = { nfc:0, gps:0, geo:0, peer:0, custom:0 };
    inlineCps.forEach(cp => { const t = cp.checkpoint_type || cp.type; if(counts[t] !== undefined) counts[t]++; });
    $$('.cb-shape-pill').forEach(pill => {
        const type = pill.dataset.type;
        let badge = pill.querySelector('.cb-type-count');
        const count = counts[type] || 0;
        if (count > 0) {
            if (!badge) { badge = document.createElement('span'); badge.className = 'cb-type-count'; pill.appendChild(badge); }
            badge.textContent = count;
        } else if (badge) { badge.remove(); }
    });
}

/* ── Toggle enforcement pill (fix: handle event + element args) ── */
window.cbToggleProp = function(event, el) {
    // Signature called as cbToggleProp(event, this) from HTML onclick
    if (!el && event) el = event.currentTarget || event.target?.closest('.rs-cp-setting');
    if (!el) return;
    if (event && (event.target.tagName === 'INPUT' || event.target.tagName === 'BUTTON')) return;
    el.classList.toggle('active');
};

window.cbUpdatePropDisplay = function(inputId, displayId, unit) {
    var slider = $(inputId);
    var display = $(displayId);
    if (!slider || !display) return;
    display.innerHTML = slider.value + '<span style="font-size:0.55rem;opacity:0.5;margin-left:2px;">' + unit + '</span>';
};


window.cbStepper = function(inputId, delta) {
    const slider = $(inputId);
    if (!slider) return;
    const min = parseFloat(slider.min) || 0;
    const max = parseFloat(slider.max) || 500;
    let val = parseFloat(slider.value) + delta;
    val = Math.max(min, Math.min(max, val));
    slider.value = val;
    slider.dispatchEvent(new Event('input'));
    const chip = slider.closest('.cb-prop-chip');
    if (chip) { chip.style.transform = 'scale(0.98)'; setTimeout(() => chip.style.transform = '', 100); }
};

window.cbStepProp = function(inputId, delta) {
    const slider = $(inputId);
    if (!slider) return;
    const min = parseFloat(slider.min) || 0;
    const max = parseFloat(slider.max) || 500;
    let val = parseFloat(slider.value) + delta;
    val = Math.max(min, Math.min(max, val));
    slider.value = val;
    slider.dispatchEvent(new Event('input'));
    // Visual feedback on enforce chip
    const chip = slider.closest('.cb-enforce-chip');
    if (chip) { chip.style.transform = 'scale(0.97)'; setTimeout(() => chip.style.transform = '', 100); }
};

// Update map marker info tooltip with dwell and gap values
function updateMarkerInfo() { }

/* ── Geo-Anchor interactions (no-opped without map) ── */
window.cbPickOnMapInline = function() { };


window.cbGeolocateInline = function() {
    if (!navigator.geolocation) { toast('Geolocation not available', true); return; }
    navigator.geolocation.getCurrentPosition(function(p) {
        setInlineCoords(p.coords.latitude, p.coords.longitude);
        toast('Location acquired');
    }, function() { toast('Could not get location', true); });
};

/* ── Fetch GPS for NFC point (on-site browser geolocation) */
window.cbFetchGPSForNFC = function() {
    if (!navigator.geolocation) { toast('Geolocation not supported on this device', true); return; }
    toast('Acquiring GPS fix…');
    navigator.geolocation.getCurrentPosition(p => {
        const lat = p.coords.latitude;
        const lng = p.coords.longitude;
        $('inlineLat').value = lat.toFixed(6);
        $('inlineLng').value = lng.toFixed(6);
        // Show coord status
        const status = $('cbCoordStatus');
        if (status) { status.style.display = 'block'; status.classList.remove('cb-coord-locked'); void status.offsetWidth; status.classList.add('cb-coord-locked'); }
        toast('GPS locked: ' + lat.toFixed(5) + ', ' + lng.toFixed(5));
    }, (err) => {
        toast('GPS acquisition failed — ' + (err.code === 1 ? 'Permission denied' : 'Unavailable'), true);
    }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 });
};

/* ── Fetch NFC tag from selected device ───────── */
/* ── Fetch NFC tag from selected device (works for offline too) ── */
window.cbFetchDeviceScan = async function() {
    const input = $('nfcFetchDevice');
    const deviceCallsign = input?.value?.trim();
    if (!deviceCallsign) { toast('Enter or select a device callsign', true); return; }
    
    // Try to find by callsign first, then by device name
    const device = allDevices.find(d => 
        d.assigned_callsign === deviceCallsign || 
        d.device_name === deviceCallsign ||
        String(d.id) === deviceCallsign
    );
    if (!device) { toast(`Device "${deviceCallsign}" not found`, true); return; }

    const statusEl = $('nfcDeviceStatus');
    const statusText = $('nfcDeviceStatusText');
    if (statusEl) { statusEl.style.display = 'block'; }
    if (statusText) { statusText.textContent = `Requesting NFC scan from ${device.device_name}…`; }

    try {
        // Send the fetch request to the device (works even if offline - stored in DB)
        const res = await api(`/api/devices/${device.id}/fetch_nfc/`, { method: 'POST' });
        if (res.ok) {
            toast(`NFC fetch request sent to ${device.device_name}`);
        } else {
            const data = await res.json().catch(() => ({}));
            toast((data.detail || 'Failed to send fetch request'), true);
        }
    } catch(e) {
        toast('Network error — request may still be queued', true);
    }

    // Start polling for the result (ongoing even for offline devices)
    let attempts = 0;
    const maxAttempts = 24; // 2 minutes
    const pollTimer = setInterval(async () => {
        attempts++;
        try {
            const res = await api(`/api/devices/${device.id}/`);
            if (res.ok) {
                const data = await res.json();
                if (data.last_nfc_scan && data.last_nfc_scan_uid) {
                    clearInterval(pollTimer);
                    const uid = data.last_nfc_scan_uid;
                    if ($('inlineNfcTag')) $('inlineNfcTag').value = uid;
                    if (statusEl) statusEl.style.display = 'none';
                    toast(`NFC tag received: ${uid}`);
                    return;
                }
            }
        } catch(e) {}
        if (statusText) statusText.textContent = `Waiting for device… ${attempts}/${maxAttempts}`;
        if (attempts >= maxAttempts) {
            clearInterval(pollTimer);
            if (statusEl) statusEl.style.display = 'none';
            toast('Still waiting — device may be offline. It will update when online.', true);
        }
    }, 5000);
};

/* ── Fetch GPS from selected device (works for offline too) ── */
window.cbFetchDeviceGPS = async function() {
    const input = $('nfcFetchDevice');
    const deviceCallsign = input?.value?.trim();
    if (!deviceCallsign) { toast('Enter or select a device callsign', true); return; }
    
    // Try to find by callsign first, then by device name
    const device = allDevices.find(d => 
        d.assigned_callsign === deviceCallsign || 
        d.device_name === deviceCallsign ||
        String(d.id) === deviceCallsign
    );
    if (!device) { toast(`Device "${deviceCallsign}" not found`, true); return; }

    const statusEl = $('nfcDeviceStatus');
    const statusText = $('nfcDeviceStatusText');
    if (statusEl) { statusEl.style.display = 'block'; }
    if (statusText) { statusText.textContent = `Requesting GPS from ${device.device_name}…`; }

    try {
        // Send the fetch request to the device (works even if offline - stored in DB)
        const res = await api(`/api/devices/${device.id}/fetch_gps/`, { method: 'POST' });
        if (res.ok) {
            toast(`GPS fetch request sent to ${device.device_name}`);
        } else {
            const data = await res.json().catch(() => ({}));
            toast((data.detail || 'Failed to send GPS request'), true);
        }
    } catch(e) {
        toast('Network error — request may still be queued', true);
    }

    // Start polling for the result (ongoing even for offline devices)
    let attempts = 0;
    const maxAttempts = 12;
    const pollTimer = setInterval(async () => {
        attempts++;
        try {
            const res = await api(`/api/devices/${device.id}/`);
            if (res.ok) {
                const data = await res.json();
                if (data.last_latitude && data.last_longitude) {
                    clearInterval(pollTimer);
                    const lat = parseFloat(data.last_latitude);
                    const lng = parseFloat(data.last_longitude);
                    if ($('inlineLat')) $('inlineLat').value = lat.toFixed(6);
                    if ($('inlineLng')) $('inlineLng').value = lng.toFixed(6);
                    toast(`GPS from device: ${lat.toFixed(5)}, ${lng.toFixed(5)}`);
                    if (statusEl) statusEl.style.display = 'none';
                    return;
                }
            }
        } catch(e) {}
        if (statusText) statusText.textContent = `Waiting for GPS… ${attempts}/${maxAttempts}`;
        if (attempts >= maxAttempts) {
            clearInterval(pollTimer);
            if (statusEl) statusEl.style.display = 'none';
            toast('Still waiting — device may be offline. Will update when online.', true);
        }
    }, 5000);
};

/* ── Fetch GPS from selected device ───────────── */
window.cbFetchDeviceGPS = function() {
    const select = $('nfcFetchCallsign');
    const deviceId = select?.value;
    if (!deviceId) { toast('Select a device callsign first', true); return; }
    const device = allDevices.find(d => String(d.id) === String(deviceId));
    if (!device) { toast('Device not found', true); return; }
    if (!device.is_online) { toast('Device is offline — cannot fetch GPS', true); return; }

    toast(`Requesting GPS fix from ${device.device_name}…`);

    let attempts = 0;
    const maxAttempts = 6;
    const pollTimer = setInterval(async () => {
        attempts++;
        try {
            const res = await api(`/api/devices/${device.id}/`);
            if (res.ok) {
                const data = await res.json();
                if (data.last_latitude && data.last_longitude) {
                    clearInterval(pollTimer);
                    const lat = parseFloat(data.last_latitude);
                    const lng = parseFloat(data.last_longitude);
                    if ($('inlineLat')) $('inlineLat').value = lat.toFixed(6);
                    if ($('inlineLng')) $('inlineLng').value = lng.toFixed(6);
                    toast('GPS from device: ' + lat.toFixed(5) + ', ' + lng.toFixed(5));
                    var status = $('cbCoordStatus');
                    if (status) { status.style.display = 'block'; status.classList.remove('cb-coord-locked'); void status.offsetWidth; status.classList.add('cb-coord-locked'); }
                    return;
                }
            }
        } catch(e) {}
        if (attempts >= maxAttempts) {
            clearInterval(pollTimer);
            toast('Device did not report GPS — try again', true);
        }
    }, 5000);
};

/* ── Fetch NFC tag from a remote device via API polling (legacy) ── */
let _remoteNFCPollTimer = null;
window.cbFetchRemoteNFC = function() {
    const onlineUnits = allDevices.filter(d => d.is_online);
    if (!onlineUnits.length) { toast('No online devices available for remote fetch', true); return; }
    // Pick first online device (or could show a selector)
    const device = onlineUnits[0];
    toast(`Requesting NFC scan from ${device.device_name}…`);
    
    // Poll the backend for the latest scan from this device
    let attempts = 0;
    const maxAttempts = 12; // 12 × 5s = 60s max wait
    
    if (_remoteNFCPollTimer) clearInterval(_remoteNFCPollTimer);
    
    _remoteNFCPollTimer = setInterval(async () => {
        attempts++;
        try {
            // Check device status endpoint for pending NFC scans
            const res = await api(`/api/devices/${device.id}/`);
            if (res.ok) {
                const data = await res.json();
                if (data.last_nfc_scan && data.last_nfc_scan_uid) {
                    clearInterval(_remoteNFCPollTimer);
                    const uid = data.last_nfc_scan_uid;
                    $('inlineNfcTag').value = uid;
                    toast(`NFC tag received: ${uid}`);
                    // If the device also reported GPS
                    if (data.last_latitude && data.last_longitude) {
                        $('inlineLat').value = parseFloat(data.last_latitude).toFixed(6);
                        $('inlineLng').value = parseFloat(data.last_longitude).toFixed(6);
                        toast('GPS from device: ' + data.last_latitude + ', ' + data.last_longitude);
                    }
                    return;
                }
            }
        } catch(e) {}
        
        if (attempts >= maxAttempts) {
            clearInterval(_remoteNFCPollTimer);
            toast('Remote fetch timed out — device did not respond', true);
        }
    }, 5000);
};

/* ── Registry Engine ──────────────────────────── */

// Inject registry row styles once
if (!document.getElementById('regStyle')) {
    var rs = document.createElement('style');
    rs.id = 'regStyle';
    rs.textContent = [
        '.cb-reg-row { display:flex; align-items:flex-start; gap:6px; padding:8px 10px; background:rgba(255,255,255,0.015); border-radius:8px; border:1px solid rgba(255,255,255,0.05); border-left:3px solid; margin-bottom:4px; transition:border-color .2s,background .2s,box-shadow .2s,transform .15s; position:relative; animation:regSlideIn .22s ease; cursor:pointer; }',
        '.cb-reg-row:hover { border-color:rgba(255,255,255,0.1); background:rgba(255,255,255,0.025); box-shadow:0 0 0 1px rgba(255,255,255,0.03), 0 2px 12px rgba(0,0,0,0.15); }',
        '.cb-reg-row.dragging { opacity:.3; border-style:dashed; transform:scale(.95); }',
        '.cb-reg-row[data-is-saved="0"] { border-left-width:4px; background:rgba(0,196,154,0.025); }',
        '.cb-reg-row[data-is-saved="0"]:hover { background:rgba(0,196,154,0.05); }',
        '.cb-reg-row[data-is-saved="1"] { border-left-width:3px; opacity:0.85; }',
        '.cb-reg-row[data-is-saved="1"]:hover { opacity:1; }',
        '.cb-reg-grip { cursor:grab; padding:2px 1px; font-size:0.55rem; color:rgba(255,255,255,0.08); display:flex; align-items:center; flex-shrink:0; transition:color .2s; touch-action:none; }',
        '.cb-reg-row:hover .cb-reg-grip { color:rgba(255,255,255,0.25); }',
        '.cb-reg-badge { display:flex; flex-direction:column; align-items:center; gap:2px; width:32px; flex-shrink:0; padding-top:3px; }',
        '.cb-reg-num { font-size:0.6rem; font-weight:900; color:rgba(255,255,255,0.15); line-height:1; }',
        '.cb-reg-ico { font-size:0.9rem; line-height:1; filter:drop-shadow(0 0 6px currentColor); display:flex; align-items:center; justify-content:center; width:24px; height:24px; }',
        '.cb-reg-body { flex:1; min-width:0; display:flex; flex-direction:column; }',
        '.cb-reg-hd { display:flex; align-items:center; gap:8px; cursor:pointer; padding:2px 4px; border-radius:5px; transition:background .12s; }',
        '.cb-reg-hd:hover { background:rgba(255,255,255,0.025); }',
        '.cb-reg-name { font-weight:800; font-size:0.78rem; color:rgba(255,255,255,0.9); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0; flex-shrink:1; cursor:text; padding:0 4px; border-radius:3px; transition:background .12s,color .12s; }',
        '.cb-reg-name:hover { background:rgba(255,255,255,0.03); }',
        '.cb-reg-name.editing { background:rgba(0,196,154,0.08); border:1px solid rgba(0,196,154,0.25); padding:0 4px; outline:none; white-space:normal; color:#0CC; }',
        '.cb-reg-tag { padding:1px 7px; border-radius:4px; font-weight:800; text-transform:uppercase; letter-spacing:0.4px; font-size:0.5rem; flex-shrink:0; line-height:1.5; }',
        // Color-coded settings pills in collapsed header
        '.cb-reg-dots { display:flex; gap:2px; align-items:center; margin-left:2px; flex-shrink:0; }',
        '.cb-reg-dot { display:inline-flex; align-items:center; gap:3px; font-size:0.45rem; padding:2px 6px; border-radius:5px; opacity:0.8; transition:opacity .15s,transform .12s; }',
        '.cb-reg-dot:hover { opacity:1; transform:scale(1.08); }',
        '.cb-reg-dot i { font-size:0.42rem; }',
        '.cb-reg-dot span { font-size:0.48rem; font-weight:800; letter-spacing:.2px; }',
        '.cb-reg-dot.rad { background:rgba(211,47,47,0.12); color:#d32f2f; border:1px solid rgba(211,47,47,0.15); }',
        '.cb-reg-dot.dwell { background:rgba(239,159,39,0.12); color:#EF9F27; border:1px solid rgba(239,159,39,0.15); }',
        '.cb-reg-dot.tol { background:rgba(108,142,239,0.12); color:#6C8EEF; border:1px solid rgba(108,142,239,0.15); }',
        '.cb-reg-dot.time { background:rgba(0,196,154,0.12); color:var(--r-teal); border:1px solid rgba(0,196,154,0.15); }',
        '.cb-reg-chev { font-size:0.58rem; opacity:0.12; transition:transform .3s cubic-bezier(.4,0,.2,1),opacity .2s; margin-left:auto; flex-shrink:0; display:flex; align-items:center; }',
        '.cb-reg-hd:hover .cb-reg-chev { opacity:0.35; }',
        '.cb-reg-config { transition:max-height .3s cubic-bezier(.4,0,.2,1); }',
        '.cb-reg-config-inner { padding-top:4px; }',
        // Type-specific field rows
        '.cb-reg-field-row { display:flex; flex-wrap:wrap; gap:8px; align-items:flex-end; padding:8px 4px 6px 4px; border-bottom:1px solid rgba(255,255,255,0.03); margin-bottom:4px; }',
        '.cb-reg-field { display:flex; flex-direction:column; gap:2px; min-width:70px; flex:1; }',
        '.cb-reg-field label { font-size:0.45rem; font-weight:800; color:rgba(255,255,255,0.2); text-transform:uppercase; letter-spacing:0.5px; padding-left:2px; }',
        '.cb-reg-field input { background:rgba(25,25,40,0.6); border:1px solid rgba(255,255,255,0.05); border-radius:5px; padding:5px 8px; font-size:0.68rem; color:#fff; outline:none; min-height:28px; transition:border-color .15s,background .15s,box-shadow .15s; }',
        '.cb-reg-field input:focus { border-color:rgba(0,196,154,0.3); background:rgba(0,20,20,0.5); box-shadow:0 0 0 2px rgba(0,196,154,0.05); }',
        '.cb-reg-field input::placeholder { color:rgba(255,255,255,0.08); font-style:italic; }',
        // Compact enf-slider cards inside registry
        '.cb-reg-enf .enf-card { margin-bottom:0 !important; border-radius:8px; border-color:rgba(255,255,255,0.04); }',
        '.cb-reg-enf .enf-card-head { padding:7px 9px !important; }',
        '.cb-reg-enf .enf-card-icon { width:28px !important; height:28px !important; border-radius:6px !important; font-size:0.6rem !important; }',
        '.cb-reg-enf .enf-card-label { font-size:0.55rem !important; }',
        '.cb-reg-enf .enf-card-desc { font-size:0.42rem !important; }',
        '.cb-reg-enf .enf-card-value { font-size:0.85rem !important; }',
        '.cb-reg-enf .enf-card-value small { font-size:0.48rem !important; }',
        '.cb-reg-enf .enf-card-body { padding:0 9px 6px !important; }',
        '.cb-reg-enf .enf-slider { height:5px !important; }',
        '.cb-reg-enf .enf-slider::-webkit-slider-thumb { width:16px !important; height:16px !important; border-width:1.5px !important; }',
        '.cb-reg-enf .enf-preset { padding:3px 2px !important; font-size:0.48rem !important; border-radius:4px !important; }',
        // Target time chip in registry
        '.cb-reg-setting { display:inline-flex; align-items:center; gap:3px; padding:3px 8px; border-radius:6px; border:1.5px dashed rgba(255,255,255,0.07); background:transparent; cursor:pointer; user-select:none; font-size:0.55rem; font-weight:800; color:rgba(255,255,255,0.25); transition:all .15s; }',
        '.cb-reg-setting:hover { border-color:rgba(255,255,255,0.12); background:rgba(255,255,255,0.015); }',
        '.cb-reg-setting.on { border-style:solid; border-color:rgba(0,196,154,0.3); background:rgba(0,196,154,0.06); color:var(--r-teal); }',
        '.cb-reg-setting.on:hover { border-color:rgba(0,196,154,0.45); background:rgba(0,196,154,0.1); }',
        '.cb-reg-setting i { font-size:0.55rem; opacity:.4; }',
        '.cb-reg-setting.on i { opacity:.8; }',
        '.cb-reg-setting .si { background:transparent !important; border:none !important; padding:0 !important; color:#fff !important; font-weight:700 !important; width:28px; text-align:center; font-size:0.58rem; pointer-events:none; opacity:.35; transition:opacity .2s; min-height:18px; outline:none; }',
        '.cb-reg-setting.on .si { opacity:1; pointer-events:auto; }',
        '.cb-reg-setting .sl { font-size:0.48rem; font-weight:800; letter-spacing:.3px; text-transform:uppercase; opacity:.5; }',
        '.cb-reg-setting.on .sl { opacity:1; }',
        '.cb-reg-actions { display:flex; flex-direction:column; align-items:center; gap:4px; flex-shrink:0; padding-top:2px; }',
        '.cb-reg-saved { font-size:0.5rem; color:rgba(255,255,255,0.15); padding:2px; }',
        '.cb-r-btn { background:none; border:none; color:rgba(255,255,255,0.15); cursor:pointer; padding:5px 7px; border-radius:6px; font-size:0.68rem; transition:all .12s; display:flex; align-items:center; justify-content:center; min-width:28px; min-height:28px; }',
        '.cb-r-btn:hover { color:var(--r-teal,#0CC); background:rgba(0,204,204,0.08); }',
        '.cb-r-del:hover { color:#d32f2f !important; background:rgba(211,47,47,0.12) !important; }',
        '.cb-manifest-exit { animation:cbManifestExit .15s ease forwards; }',
        '.rs-hidden { display:none !important; }',
        // Type count badges on quick-add pills
        '.cb-type-badge { position:absolute; top:-5px; right:-5px; min-width:15px; height:15px; border-radius:8px; font-size:0.4rem; font-weight:900; display:flex; align-items:center; justify-content:center; padding:0 4px; box-shadow:0 0 8px rgba(0,0,0,0.5); }',
        '.cb-type-badge.nfc { background:#d32f2f; color:#fff; border:1px solid rgba(255,255,255,0.1); }',
        '.cb-type-badge.gps { background:#3B82F6; color:#fff; border:1px solid rgba(255,255,255,0.1); }',
        '.cb-type-badge.geo { background:#A855F7; color:#fff; border:1px solid rgba(255,255,255,0.1); }',
        '.cb-type-badge.peer { background:#EC4899; color:#fff; border:1px solid rgba(255,255,255,0.1); }',
        '@keyframes regSlideIn { from { opacity:0; transform:translateY(-6px) scale(.96); } to { opacity:1; transform:translateY(0) scale(1); } }',
        '@keyframes cbManifestExit { to { opacity:0; transform:translateX(-10px); max-height:0; padding:0; margin:0; overflow:hidden; } }'
    ].join('\n');
    document.head.appendChild(rs);
}

// Add a staged or saved row to the registry (#cpRegistry)
window.addRegistryRow = function(type, data) {
    data = data || {};
    var list = $('cpRegistry');
    var empty = $('regEmpty');
    if (!list) return;
    if (empty) empty.style.display = 'none';

    var idx = list.querySelectorAll('.cb-reg-row').length;
    var icons = { nfc:'fa-wifi', gps:'fa-map-pin', geo:'fa-draw-polygon', peer:'fa-user-shield', custom:'fa-pen' };
    var cols  = { nfc:'var(--r-crim)', gps:'var(--r-indigo)', geo:'var(--r-violet)', peer:'var(--r-violet)', custom:'var(--r-teal)' };
    var col   = cols[type] || 'var(--r-crim)';
    var isSaved = !!data.id && data.id > 0;
    var name   = data.name || '';
    var lat    = data.lat || (data.geometry && data.geometry[0]) || '';
    var lng    = data.lng || (data.geometry && data.geometry[1]) || '';
    var tag    = data.nfc_tag || '';
    var auditor = data.auditor_id || '';
    var target  = data.target_id || '';
    var rad    = data.radius || 0;
    var dwell  = data.dwell_time || 0;
    var tol    = data.time_tolerance != null ? data.time_tolerance : 15;
    var time   = data.planned_time || '';
    var rowId = isSaved ? 's_' + data.id : 't_' + Date.now() + '_' + idx;

    var infoText = type === 'nfc' ? (tag ? tag : '\u2014') :
                   type === 'gps' ? (lat && lng ? parseFloat(lat).toFixed(5) + ', ' + parseFloat(lng).toFixed(5) : '\u2014') :
                   type === 'geo' ? (lat && lng ? parseFloat(lat).toFixed(5) + ', ' + parseFloat(lng).toFixed(5) : '\u2014') :
                   type === 'peer' ? (auditor && target ? auditor + ' \u2194 ' + target : '\u2014') :
                   type === 'custom' ? (lat && lng ? parseFloat(lat).toFixed(5) + ', ' + parseFloat(lng).toFixed(5) : '\u2014') : '\u2014';

    // Build color-coded settings pills for collapsed state
    var settingDots = [];
    if (rad > 0) settingDots.push('<span class="cb-reg-dot rad" title="Radius ' + rad + 'm"><i class="fas fa-circle-dot"></i><span>' + rad + '</span></span>');
    if (dwell > 0) settingDots.push('<span class="cb-reg-dot dwell" title="Dwell ' + dwell + 'min"><i class="fas fa-stopwatch"></i><span>' + dwell + '</span></span>');
    if (tol > 0) settingDots.push('<span class="cb-reg-dot tol" title="Gap ' + tol + 'min"><i class="fas fa-hourglass-start"></i><span>' + tol + '</span></span>');
    if (time) settingDots.push('<span class="cb-reg-dot time" title="Target ' + time + '"><i class="fas fa-clock"></i><span>' + time + '</span></span>');

    var div = document.createElement('div');
    div.className = 'cb-reg-row';
    div.dataset.cpType = type;
    div.dataset.rowId = rowId;
    div.dataset.isSaved = isSaved ? '1' : '0';
    div.dataset.serverId = data.id || '';
    div.style.borderLeftColor = col;

    var fieldArea = type === 'nfc' ? [
        '<div class="cb-reg-field-row">',
            '<div class="cb-reg-field"><label class="rs-lbl">Point Name</label><input class="rs-fi cp-inline-name" value="' + name + '" placeholder="e.g. Main Gate Checkpoint"></div>',
            '<div class="cb-reg-field"><label class="rs-lbl">NFC UID</label><div style="display:flex;gap:6px;"><input class="rs-fi cp-inline-tag" value="' + tag + '" placeholder="UID or scan" style="flex:1;font-family:monospace;"><button type="button" class="cb-r-btn" title="Scan" onclick="cbOpenScanWindow(this)" style="font-size:0.8rem;"><i class="fas fa-tower-broadcast"></i></button></div></div>',
        '</div>'
    ].join('') : type === 'gps' ? [
        '<div class="cb-reg-field-row">',
            '<div class="cb-reg-field"><label class="rs-lbl">Point Name</label><input class="rs-fi cp-inline-name" value="' + name + '" placeholder="e.g. North Perimeter"></div>',
            '<div class="cb-reg-field" style="flex:0 0 auto;"><label class="rs-lbl">Latitude</label><div style="display:flex;gap:6px;align-items:center;"><input class="rs-fi cp-inline-lat" value="' + lat + '" placeholder="0.000000" style="width:150px;"><button type="button" class="cb-r-btn" title="Pick on map" onclick="cbPickForRow(this)" style="font-size:0.8rem;color:#6C8EEF;"><i class="fas fa-map-pin"></i></button></div></div>',
            '<div class="cb-reg-field" style="flex:0 0 auto;"><label class="rs-lbl">Longitude</label><input class="rs-fi cp-inline-lng" value="' + lng + '" placeholder="0.000000" style="width:150px;"></div>',
        '</div>'
    ].join('') : type === 'geo' ? [
        '<div class="cb-reg-field-row">',
            '<div class="cb-reg-field"><label class="rs-lbl">Zone Name</label><input class="rs-fi cp-inline-name" value="' + name + '" placeholder="e.g. Restricted Area"></div>',
            '<div class="cb-reg-field" style="flex:0 0 auto;"><label class="rs-lbl">Latitude</label><div style="display:flex;gap:6px;align-items:center;"><input class="rs-fi cp-inline-lat" value="' + lat + '" placeholder="0.000000" style="width:150px;"><button type="button" class="cb-r-btn" title="Pick on map" onclick="cbPickForRow(this)" style="font-size:0.8rem;color:#A855F7;"><i class="fas fa-map-pin"></i></button></div></div>',
            '<div class="cb-reg-field" style="flex:0 0 auto;"><label class="rs-lbl">Longitude</label><input class="rs-fi cp-inline-lng" value="' + lng + '" placeholder="0.000000" style="width:150px;"></div>',
        '</div>'
    ].join('') : type === 'custom' ? [
        '<div class="cb-reg-field-row">',
            '<div class="cb-reg-field"><label class="rs-lbl">Point Name</label><input class="rs-fi cp-inline-name" value="' + name + '" placeholder="e.g. Custom Point"></div>',
            '<div class="cb-reg-field" style="flex:0 0 auto;"><label class="rs-lbl">Latitude</label><div style="display:flex;gap:6px;align-items:center;"><input class="rs-fi cp-inline-lat" value="' + lat + '" placeholder="0.000000" style="width:150px;"><button type="button" class="cb-r-btn" title="Pick on map" onclick="cbPickForRow(this)" style="font-size:0.8rem;color:var(--r-teal);"><i class="fas fa-map-pin"></i></button></div></div>',
            '<div class="cb-reg-field" style="flex:0 0 auto;"><label class="rs-lbl">Longitude</label><input class="rs-fi cp-inline-lng" value="' + lng + '" placeholder="0.000000" style="width:150px;"></div>',
        '</div>'
    ].join('') : [
        '<div class="cb-reg-field-row">',
            '<div class="cb-reg-field"><label class="rs-lbl">Point Name</label><input class="rs-fi cp-inline-name" value="' + name + '" placeholder="e.g. Peer Audit Point"></div>',
            '<div class="cb-reg-field"><label class="rs-lbl">Auditor</label><input class="rs-fi cp-inline-auditor" value="' + auditor + '" placeholder="Callsign"></div>',
            '<div class="cb-reg-field"><label class="rs-lbl">Target</label><input class="rs-fi cp-inline-target" value="' + target + '" placeholder="Callsign"></div>',
        '</div>'
    ].join('');

    div.innerHTML = [
        '<div class="cb-reg-grip"><i class="fas fa-grip-vertical"></i></div>',
        '<div class="cb-reg-badge">',
            '<span class="cb-reg-num">' + (idx + 1) + '</span>',
            '<span class="cb-reg-ico"><i class="fas ' + icons[type] + '" style="color:' + col + '"></i></span>',
        '</div>',
        '<div class="cb-reg-body">',
            '<div class="cb-reg-hd" onclick="mgToggleCpConfig(event,this)">',
                '<span class="cb-reg-name">' + (name || '<span style="opacity:0.35;font-style:italic;">Unnamed</span>') + '</span>',
                '<span class="cb-reg-tag" style="background:' + col + '18;color:' + col + ';border:1px solid ' + col + '30;">' + type.toUpperCase() + '</span>',
                '<span class="cb-reg-dots">' + settingDots.join('') + '</span>',
                '<span class="cb-reg-chev"><i class="fas fa-chevron-down"></i></span>',
            '</div>',
            '<div class="cb-reg-config" style="max-height:' + (isSaved ? '0' : '0') + 'px;overflow:hidden;"' + (isSaved ? '' : ' data-auto-expand="1"') + '>',
                '<div class="cb-reg-config-inner">',
                    fieldArea,
                    // Parameters grid — clean form layout
                    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:8px 4px 4px;">',
                        // Radius
                        '<div style="display:flex;flex-direction:column;gap:3px;">',
                            '<label class="rs-lbl" style="color:rgba(255,255,255,0.4);">Radius (m)</label>',
                            '<div style="display:flex;align-items:center;gap:6px;">',
                                '<input type="range" class="cp-inline-rad" min="0" max="500" value="' + (rad || 0) + '" step="5" style="flex:1;accent-color:#d32f2f;" oninput="regSliderSync(this)">',
                                '<span class="cp-rad-val" style="font-size:0.72rem;font-weight:700;color:#d32f2f;min-width:32px;text-align:right;">' + (rad || 0) + 'm</span>',
                            '</div>',
                        '</div>',
                        // Dwell
                        '<div style="display:flex;flex-direction:column;gap:3px;">',
                            '<label class="rs-lbl" style="color:rgba(255,255,255,0.4);">Dwell (min)</label>',
                            '<div style="display:flex;align-items:center;gap:6px;">',
                                '<input type="range" class="cp-inline-dwell" min="0" max="60" value="' + (dwell || 0) + '" step="1" style="flex:1;accent-color:#ffc107;" oninput="regSliderSync(this)">',
                                '<span class="cp-dwell-val" style="font-size:0.72rem;font-weight:700;color:#ffc107;min-width:32px;text-align:right;">' + (dwell || 0) + 'm</span>',
                            '</div>',
                        '</div>',
                        // Tolerance
                        '<div style="display:flex;flex-direction:column;gap:3px;">',
                            '<label class="rs-lbl" style="color:rgba(255,255,255,0.4);">Tolerance (min)</label>',
                            '<div style="display:flex;align-items:center;gap:6px;">',
                                '<input type="range" class="cp-inline-tol" min="0" max="60" value="' + (tol || 0) + '" step="1" style="flex:1;accent-color:#0d6efd;" oninput="regSliderSync(this)">',
                                '<span class="cp-tol-val" style="font-size:0.72rem;font-weight:700;color:#0d6efd;min-width:32px;text-align:right;">' + (tol || 0) + 'm</span>',
                            '</div>',
                        '</div>',
                        // Target time
                        '<div style="display:flex;flex-direction:column;gap:3px;">',
                            '<label class="rs-lbl" style="color:rgba(255,255,255,0.4);">Target Time</label>',
                            '<input type="time" class="rs-fi cp-inline-time" value="' + time + '" style="height:28px;font-size:0.72rem;padding:4px 8px;">',
                        '</div>',
                    '</div>',
                '</div>',
            '</div>',
        '</div>',
        '<div class="cb-reg-actions">',
            (isSaved ? '<span class="cb-reg-saved" title="Saved"><i class="fas fa-database"></i></span>' : ''),
            '<button type="button" class="cb-r-btn" title="Duplicate" onclick="duplicateRegistryRow(this)" style="color:rgba(255,255,255,0.2);"><i class="fas fa-copy"></i></button>',
            '<button type="button" class="cb-r-btn cb-r-del" title="Remove" onclick="removeRegistryRow(this)"><i class="fas fa-times"></i></button>',
        '</div>'
    ].join('');

    // Make draggable
    div.draggable = true;
    div.addEventListener('dragstart', function(e) {
        e.dataTransfer.setData('text/plain', div.dataset.rowId);
        div.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
    });
    div.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        var listEl = $('cpRegistry');
        var siblings = listEl ? listEl.querySelectorAll('.cb-reg-row:not(.dragging)') : [];
        var after = null;
        for (var i = 0; i < siblings.length; i++) {
            var rect = siblings[i].getBoundingClientRect();
            if (e.clientY < rect.top + rect.height / 2) { after = siblings[i]; break; }
        }
        siblings.forEach(function(s) { s.classList.remove('drag-over'); });
        if (after) after.classList.add('drag-over');
    });
    div.addEventListener('dragleave', function() { div.classList.remove('drag-over'); });
    div.addEventListener('drop', function(e) {
        e.preventDefault();
        var listEl = $('cpRegistry');
        if (!listEl) return;
        var dragId = e.dataTransfer.getData('text/plain');
        var dragRow = listEl.querySelector('[data-row-id="' + dragId + '"]');
        if (!dragRow || dragRow === div) return;
        var dropBefore = div;
        listEl.insertBefore(dragRow, dropBefore);
        $$('.cb-reg-row').forEach(function(r) { r.classList.remove('dragging', 'drag-over'); });
        renumberRegistryRows();
        syncRegistryFromRows();
        updateRegistryStats();
    });
    div.addEventListener('dragend', function() {
        $$('.cb-reg-row').forEach(function(r) { r.classList.remove('dragging', 'drag-over'); });
    });

    // Sync collapsed header name when config input changes
    var syncName = function() {
        var nameInput = div.querySelector('.cp-inline-name');
        var nameSpan = div.querySelector('.cb-reg-name');
        if (nameInput && nameSpan) {
            var v = nameInput.value.trim();
            nameSpan.innerHTML = v ? v.replace(/</g,'&lt;') : '<span style="opacity:0.35;font-style:italic;">Unnamed</span>';
        }
    };
    var nameInput = div.querySelector('.cp-inline-name');
    if (nameInput) {
        nameInput.addEventListener('blur', syncName);
        nameInput.addEventListener('input', syncName);
    }

    // Inline name editing (header): single-click to edit
    var nameEl = div.querySelector('.cb-reg-name');
    if (nameEl) {
        nameEl.addEventListener('click', function(e) {
            e.stopPropagation();
            if (nameEl.classList.contains('editing')) return;
            nameEl.classList.add('editing');
            nameEl.contentEditable = 'true';
            nameEl.focus();
            // Select all text
            var sel = window.getSelection();
            var range = document.createRange();
            range.selectNodeContents(nameEl);
            sel.removeAllRanges();
            sel.addRange(range);
        });
        nameEl.addEventListener('blur', function() {
            nameEl.classList.remove('editing');
            nameEl.contentEditable = 'false';
            syncRegistryFromRows();
            updateRegistryStats();
        });
        nameEl.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') { e.preventDefault(); nameEl.blur(); }
            if (e.key === 'Escape') { nameEl.textContent = name; nameEl.blur(); }
        });
    }

    list.appendChild(div);
    // Auto-expand config for new (staged) rows
    if (!isSaved) {
        requestAnimationFrame(function() {
            var config = div.querySelector('.cb-reg-config');
            var inner = config ? config.querySelector('.cb-reg-config-inner') : null;
            var chevron = div.querySelector('.cb-reg-chev i');
            if (config && inner) {
                config.style.maxHeight = inner.scrollHeight + 20 + 'px';
                if (chevron) chevron.style.transform = 'rotate(180deg)';
            }
            // Init slider displays & presets
            div.querySelectorAll('.enf-slider').forEach(function(s) { regSliderSync(s); });
            // Focus the name input
            var nameInp = div.querySelector('.cp-inline-name');
            if (nameInp) setTimeout(function() { nameInp.focus(); }, 100);
        });
    } else {
        // Still init slider displays for saved rows
        div.querySelectorAll('.enf-slider').forEach(function(s) { regSliderSync(s); });
    }
    renumberRegistryRows();
    syncRegistryFromRows();
    updateRegistryStats();
    autoFitMap();
    if (!isSaved) {
        toast(type.toUpperCase() + ' point added');
        // Scroll new row into view
        setTimeout(function() { div.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, 150);
    }
};

/* ── Duplicate a registry row ── */
window.duplicateRegistryRow = function(btn) {
    var row = btn.closest('.cb-reg-row');
    if (!row) return;
    var type = row.dataset.cpType || 'nfc';
    var nameInp = row.querySelector('.cp-inline-name');
    var tagInp = row.querySelector('.cp-inline-tag');
    var latInp = row.querySelector('.cp-inline-lat');
    var lngInp = row.querySelector('.cp-inline-lng');
    var auditorInp = row.querySelector('.cp-inline-auditor');
    var targetInp = row.querySelector('.cp-inline-target');
    var radSlider = row.querySelector('.cp-inline-rad');
    var dwellSlider = row.querySelector('.cp-inline-dwell');
    var tolSlider = row.querySelector('.cp-inline-tol');
    var timeInp = row.querySelector('.cp-inline-time');
    var cloned = {
        name: (nameInp ? nameInp.value : '') + ' (copy)',
        nfc_tag: tagInp ? tagInp.value : '',
        lat: latInp ? latInp.value : '',
        lng: lngInp ? lngInp.value : '',
        auditor_id: auditorInp ? auditorInp.value : '',
        target_id: targetInp ? targetInp.value : '',
        radius: radSlider ? parseInt(radSlider.value) || 0 : 0,
        dwell_time: dwellSlider ? parseInt(dwellSlider.value) || 0 : 0,
        time_tolerance: tolSlider ? parseInt(tolSlider.value) || 0 : 15,
        planned_time: timeInp ? timeInp.value : ''
    };
    addRegistryRow(type, cloned);
    toast('Duplicated');
};

/* ── Toggle a setting chip on/off (keep for target time) ── */
window.rsToggleProp = function(e, chip) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    var was = chip.classList.contains('on');
    chip.classList.toggle('on');
    chip.querySelectorAll('.su').forEach(function(u) { u.classList.toggle('rs-hidden', was); });
};

/* ── Sync enf-slider value display & presets ── */
window.regSliderSync = function(slider) {
    var row = slider.closest('.cb-reg-row');
    if (!row) return;
    var val = parseInt(slider.value) || 0;
    // Update value display with flash effect
    var valEl = slider.parentElement.parentElement.querySelector('.enf-card-value');
    if (valEl) {
        valEl.innerHTML = val + '<small>' + (valEl.classList.contains('cp-tol-val') || valEl.classList.contains('cp-dwell-val') ? 'min' : 'm') + '</small>';
        valEl.style.transition = 'color .1s';
        valEl.style.color = val > 0 ? '#fff' : 'rgba(255,255,255,0.15)';
    }
    // Update presets
    var presets = slider.parentElement.querySelectorAll('.enf-preset');
    presets.forEach(function(p) {
        p.classList.toggle('active', parseInt(p.getAttribute('data-v')) === val);
    });
    // Update collapsed header dots
    updateRowDots(row);
    syncRegistryFromRows();
    updateRegistryStats();
};

/* ── Update the color-coded settings pills in collapsed header ── */
function updateRowDots(row) {
    var dotsEl = row.querySelector('.cb-reg-dots');
    if (!dotsEl) return;
    var rad = parseInt(row.querySelector('.cp-inline-rad')?.value) || 0;
    var dwell = parseInt(row.querySelector('.cp-inline-dwell')?.value) || 0;
    var tol = parseInt(row.querySelector('.cp-inline-tol')?.value) || 0;
    var time = row.querySelector('.cp-inline-time')?.value || '';
    var parts = [];
    if (rad > 0) parts.push('<span class="cb-reg-dot rad" title="Radius ' + rad + 'm"><i class="fas fa-circle-dot"></i><span>' + rad + '</span></span>');
    if (dwell > 0) parts.push('<span class="cb-reg-dot dwell" title="Dwell ' + dwell + 'min"><i class="fas fa-stopwatch"></i><span>' + dwell + '</span></span>');
    if (tol > 0) parts.push('<span class="cb-reg-dot tol" title="Gap ' + tol + 'min"><i class="fas fa-hourglass-start"></i><span>' + tol + '</span></span>');
    if (time) parts.push('<span class="cb-reg-dot time" title="Target ' + time + '"><i class="fas fa-clock"></i><span>' + time + '</span></span>');
    dotsEl.innerHTML = parts.join('');
}

// Delegate preset clicks
document.addEventListener('click', function(e) {
    var preset = e.target.closest('.enf-preset');
    if (!preset) return;
    var card = preset.closest('.enf-card');
    if (!card) return;
    var slider = card.querySelector('.enf-slider');
    if (!slider) return;
    var val = parseInt(preset.getAttribute('data-v')) || 0;
    slider.value = val;
    regSliderSync(slider);
});

/* ── Toggle config panel on click (max-height animation) ── */
window.mgToggleCpConfig = function(ev, headEl) {
    if (ev.target.tagName === 'INPUT' || ev.target.closest('.cb-r-btn') || ev.target.closest('.cb-reg-setting')) return;
    var config = headEl?.closest('.cb-reg-row')?.querySelector('.cb-reg-config');
    var chevron = headEl?.closest('.cb-reg-hd')?.querySelector('.cb-reg-chev i');
    if (!config) return;
    var inner = config.querySelector('.cb-reg-config-inner');
    if (!inner) return;
    var isOpen = config.style.maxHeight !== '0px' && config.style.maxHeight !== '';
    if (isOpen) {
        config.style.maxHeight = '0px';
        if (chevron) chevron.style.transform = '';
    } else {
        config.style.maxHeight = inner.scrollHeight + 20 + 'px';
        if (chevron) chevron.style.transform = 'rotate(180deg)';
    }
};

/* ── Remove a registry row (staged: undo-friendly; saved: confirm first) ── */
window.removeRegistryRow = function(btn) {
    const row = btn.closest('.cb-reg-row');
    if (!row) return;
    const isSaved = row.dataset.isSaved === '1';
    const serverId = row.dataset.serverId;
    const type = row.dataset.cpType || 'point';

    if (isSaved && serverId) {
        if (!confirm('Delete this saved ' + type.toUpperCase() + ' from the server?')) return;
        api('/api/map-objects/' + serverId + '/', { method: 'DELETE' }).then(function(res) {
            if (res.ok) { toast(type.toUpperCase() + ' deleted from server'); mgLogFleetEvent('info', type.toUpperCase() + ' checkpoint deleted', 'Server removal'); }
            else toast('Delete failed', true);
        }).catch(function() { toast('Network error', true); });
    }

    row.classList.add('cb-manifest-exit');
    var removedHTML = row.outerHTML;
    var removedType = type;
    setTimeout(function() {
        row.remove(); renumberRegistryRows(); syncRegistryFromRows(); updateRegistryStats(); autoFitMap();
        if (!$$('#cpRegistry .cb-reg-row').length) {
            var empty = $('regEmpty');
            if (empty) empty.style.display = 'block';
        }
        // Show undo toast for staged (unsaved) items only
        if (!isSaved) {
            var undoToast = document.createElement('div');
            undoToast.className = 'mg-toast undo-toast';
            undoToast.innerHTML = '<span class="td"></span>' + removedType.toUpperCase() + ' removed <button type="button" class="mg-undo-btn" onclick="undoRemoveRegistryRow(this)">Undo</button>';
            $('mgToasts').appendChild(undoToast);
            undoToast._removedHTML = removedHTML;
            undoToast._removedType = removedType;
            setTimeout(function() { if (undoToast.parentNode) { undoToast.remove(); } }, 5000);
        }
    }, 150);
};

window.undoRemoveRegistryRow = function(btn) {
    var toast = btn.closest('.mg-toast');
    if (!toast) return;
    var html = toast._removedHTML;
    var list = $('cpRegistry');
    var empty = $('regEmpty');
    if (empty) empty.style.display = 'none';
    if (html) {
        var temp = document.createElement('div');
        temp.innerHTML = html;
        var restored = temp.firstElementChild;
        restored.classList.remove('cb-manifest-exit');
        var idx = list.querySelectorAll('.cb-reg-row').length;
        var numEl = restored.querySelector('.cb-reg-num');
        if (numEl) numEl.textContent = idx + 1;
        list.appendChild(restored);
        restored.querySelectorAll('.enf-slider').forEach(function(s) { regSliderSync(s); });
        renumberRegistryRows(); syncRegistryFromRows(); updateRegistryStats(); autoFitMap();
    }
    toast.remove();
    toast('Restored');
};

/* ── Quick Add ── */
window.cbQuickAdd = function(type) {
    addRegistryRow(type, {});
};

window.cbOpenCheckpointForm = function() {
    mgToggleCpAdders(true);
    cbQuickAdd('nfc');
};

window.mgToggleCpAdders = function(forceOpen) {
    var adders = document.getElementById('mgCpAdders');
    var icon = document.getElementById('mgCpTriggerIcon');
    if (!adders) return;
    var isOpen = adders.classList.contains('open');
    if (forceOpen || !isOpen) {
        adders.style.display = 'block';
        adders.classList.add('open');
        if (icon) icon.style.transform = 'rotate(180deg)';
    } else {
        adders.classList.remove('open');
        setTimeout(function() { adders.style.display = 'none'; }, 300);
        if (icon) icon.style.transform = '';
    }
};

window.cbClearStaged = function() {
    var registry = document.getElementById('cpRegistry');
    if (registry) {
        registry.querySelectorAll('.cb-reg-row').forEach(function(el) { el.remove(); });
    }
    inlineCps = [];
    savedCps = [];
    updateRegistryStats();
};

/* ── Direct inline add (like routes.html qAddPoint) ── */
/* (replaced by addRegistryRow) */

/* ── renumber rows after add/remove ── */
function renumberRegistryRows() {
    $$('#cpRegistry .cb-reg-row').forEach((r, i) => {
        const n = r.querySelector('.cb-reg-num');
        if (n) n.textContent = i + 1;
    });
}

/* ── Update type count badges on quick-add pills ── */
function updateRegistryStats() {
    var counts = { nfc:0, gps:0, geo:0, peer:0, custom:0 };
    $$('#cpRegistry .cb-reg-row').forEach(function(r) {
        var t = r.dataset.cpType;
        if (counts.hasOwnProperty(t)) counts[t]++;
    });
    var total = 0;
    Object.keys(counts).forEach(function(k) {
        total += counts[k];
        // Update new mg-cp-type-btn badges
        var typeBtn = document.querySelector('.mg-cp-type-btn[data-type="' + k + '"]');
        if (typeBtn) {
            var badge = typeBtn.querySelector('.mg-cp-type-badge');
            if (badge) {
                if (counts[k] > 0) { badge.textContent = counts[k]; badge.style.display = 'flex'; }
                else { badge.style.display = 'none'; }
            }
        }
        // Legacy cb-shape-pill badges (kept for safety)
        var pill = document.querySelector('.cb-shape-pill[data-type="' + k + '"]');
        if (!pill) return;
        var badge = pill.querySelector('.cb-type-badge');
        if (!badge) return;
        if (counts[k] > 0) { badge.textContent = counts[k]; badge.style.display = 'flex'; }
        else { badge.style.display = 'none'; }
    });
    var stg = $('regCountStaged');
    if (stg) stg.textContent = total;
}

window.mgFilterRegistry = function() {
    var q = ($('regSearch')?.value || '').toLowerCase();
    $$('#cpRegistry .cb-reg-row').forEach(function(r) {
        var name = r.querySelector('.cp-inline-name')?.value || '';
        var tag = r.querySelector('.cp-inline-tag')?.value || '';
        var match = !q || name.toLowerCase().includes(q) || tag.toLowerCase().includes(q);
        r.style.display = match ? '' : 'none';
    });
};

/* ── sync inlineCps array from rendered inputs ── */
function syncRegistryFromRows() {
    inlineCps = [];
    savedCps = [];
    $$('#cpRegistry .cb-reg-row').forEach(r => {
        const isSaved = r.dataset.isSaved === '1';
        const serverId = r.dataset.serverId;
        const type = r.dataset.cpType || 'nfc';
        const name = r.querySelector('.cp-inline-name')?.value?.trim() || '';
        function val(sel) { var v = r.querySelector(sel); return v ? v.value : ''; }
        function sliderVal(sel, def) {
            const s = r.querySelector(sel);
            return s ? parseInt(s.value) || 0 : def;
        }
        const entry = {
            name: name,
            checkpoint_type: type,
            lat: val('.cp-inline-lat'),
            lng: val('.cp-inline-lng'),
            nfc_tag: val('.cp-inline-tag') || null,
            auditor_id: type === 'peer' ? val('.cp-inline-auditor') : null,
            target_id: type === 'peer' ? val('.cp-inline-target') : null,
            radius: sliderVal('.cp-inline-rad', 0),
            dwell_time: sliderVal('.cp-inline-dwell', 0),
            time_tolerance: sliderVal('.cp-inline-tol', 0),
            planned_time: (function(){ var t=r.querySelector('.cp-inline-time'); return t && t.closest('.cb-reg-setting')?.classList.contains('on') ? t.value : null; })() || null,
            geo_shape: type === 'geo' ? 'circle' : null
        };
        if (!entry.name) return;
        if (isSaved && serverId) {
            entry.id = parseInt(serverId, 10);
            savedCps.push(entry);
        } else {
            entry.id = Date.now() + Math.random();
            inlineCps.push(entry);
        }
    });
}

/* ═══ syncRegistryFromRows also replaces syncInlineFromRows ═══ */
window.syncInlineFromRows = syncRegistryFromRows;

/* ── Pick map location for a specific row ── */
window.cbPickForRow = function(btn) {
    const row = btn.closest('.cb-reg-row');
    if (!row) return;
    const type = row.dataset.cpType || 'gps';
    inlineType = type;
    pickMode = type;
    // Expand the row config
    const config = row.querySelector('.cb-reg-config');
    const chevron = row.querySelector('.cb-reg-chev i');
    const inner = config ? config.querySelector('.cb-reg-config-inner') : null;
    if (config && inner) config.style.maxHeight = inner.scrollHeight + 20 + 'px';
    if (chevron) chevron.style.transform = 'rotate(180deg)';
    $('cbMapHint').classList.add('active');
    $('cbMapHint').innerHTML = '<i class="fas fa-crosshairs"></i> Click map to set <b>' + type.toUpperCase() + '</b> location';
    cbActivateTool(null);
    window._pickRow = row;
    window._origSetInlineCoords = window.setInlineCoords;
    window.setInlineCoords = function(lat, lng) {
        var r = window._pickRow;
        if (r) {
            var latInp = r.querySelector('.cp-inline-lat');
            var lngInp = r.querySelector('.cp-inline-lng');
            if (latInp) latInp.value = lat.toFixed(6);
            if (lngInp) lngInp.value = lng.toFixed(6);
            addMapMarker(lat, lng, r.dataset.cpType || 'gps');
        }
        if (window._origSetInlineCoords) window._origSetInlineCoords(lat, lng);
        window.setInlineCoords = window._origSetInlineCoords || window.setInlineCoords;
        window._pickRow = null;
    };
};

/* ── Update map markers from all registry rows with coords ── */
function autoFitMap() { }

/* ── Load saved checkpoints from allAssets into registry ── */
window.mgLoadSavedCps = function() {
    var list = $('cpRegistry');
    if (!list) return;
    $$('#cpRegistry .cb-reg-row[data-is-saved="1"]').forEach(function(r) { r.remove(); });
    var saved = allAssets.filter(function(a) {
        var t = a.type || a.checkpoint_type || '';
        // Include all checkpoint types — NFC may not have geometry
        return ['nfc','gps','geo','peer','custom','poi','geofence'].indexOf(t) !== -1;
    });
    saved.forEach(function(a) {
        var t = a.type === 'geofence' ? 'geo' : (a.type === 'poi' ? (a.radius ? 'geo' : 'nfc') : (a.checkpoint_type || a.type || 'nfc'));
        addRegistryRow(t, {
            id: a.id, name: a.name, geometry: a.geometry, nfc_tag: a.nfc_tag,
            auditor_id: a.auditor_id, target_id: a.target_id, radius: a.radius,
            dwell_time: a.dwell_time, time_tolerance: a.time_tolerance,
            planned_time: a.planned_time, geo_shape: a.geo_shape
        });
    });
    if (!saved.length && !$$('#cpRegistry .cb-reg-row[data-is-saved="0"]').length) {
        var empty = $('regEmpty');
        if (empty) empty.style.display = 'block';
    }
};

/* ── Legacy add (kept for backward compat) ── */
window.cbAddInlineCheckpoint = function() {
    inlineAddPoint(inlineType || 'nfc');
};

/* (replaced by addRegistryRow / updateRegistryStats) */

/* ── Geofence shape ────────────────────────────── */
window.cbSetInlineGeoShape = function(shape, el) {
    if (el) {
        el.parentElement.querySelectorAll('.cb-shape-pill').forEach(b => b.classList.remove('active'));
        el.classList.add('active');
    }
    if (shape === 'polygon') cbActivateTool('polygon');
    else cbActivateTool(null);
};

/* ── NFC Scan window (per-row) ─────────────────── */
window.cbOpenScanWindow = function(btn) {
    const row = btn?.closest('.cb-reg-row');
    const nameInp = row?.querySelector('.cp-inline-name');
    const name = nameInp?.value?.trim();
    if (!name) { toast('Enter a point name first', true); nameInp?.focus(); return; }
    const scanSelect = $('scanCallsign');
    if (scanSelect) {
        const opts = allDevices.map(function(d) {
            var cs = d.assigned_callsign || d.device_name || 'Unit';
            var status = d.is_online ? '\ud83d\udfe2' : '\ud83d\udd34';
            return '<option value="' + d.id + '">' + status + ' ' + d.device_name + ' (' + cs + ')</option>';
        }).join('');
        scanSelect.innerHTML = '<option value="">\u2014 Select device \u2014</option>' + opts;
    }
    resetScan();
    $('cbScanBackdrop').classList.add('open');
    startCountdown(30);
};
function resetScan() {
    if ($('cbCountdown')) $('cbCountdown').textContent = '30';
    if ($('cbCountdownBar')) $('cbCountdownBar').style.width = '100%';
    if ($('cbScanStatus')) $('cbScanStatus').textContent = 'Hold NFC tag near device to scan';
    const result = $('cbScanResult');
    if (result) result.classList.remove('show');
    const btn = $('cbAcceptScanBtn');
    if (btn) btn.style.display = 'none';
    const ring = $('cbScanRing');
    if (ring) ring.style.borderColor = 'rgba(211,47,47,.35)';
}

window.cbCloseScan = function() {
    clearInterval(scanTimer);
    var backdrop = $('cbScanBackdrop');
    if (backdrop) backdrop.classList.remove('open');
    resetScan();
};

let scanTimer = null;
let scanSecondsLeft = 30;

function startCountdown(secs) {
    scanSecondsLeft = secs;
    clearInterval(scanTimer);
    scanTimer = setInterval(() => {
        scanSecondsLeft--;
        if ($('cbCountdown')) $('cbCountdown').textContent = scanSecondsLeft;
        const bar = $('cbCountdownBar');
        if (bar) bar.style.width = (scanSecondsLeft / secs * 100) + '%';
        if (scanSecondsLeft <= 5 && bar) bar.style.background = '#d32f2f';
        if (scanSecondsLeft <= 0) {
            clearInterval(scanTimer);
            if ($('cbScanStatus')) $('cbScanStatus').textContent = 'Scan window expired.';
            toast('Scan window expired — try again', true);
        }
    }, 1000);

    const selectedDeviceId = $('scanCallsign')?.value;
    if (selectedDeviceId) {
        setTimeout(() => {
            if (scanSecondsLeft > 0) receiveTag('04:' + Math.random().toString(16).substr(2,11).toUpperCase().replace(/(..)/g,'$1:').slice(0,-1));
        }, 4000);
    }
}

function receiveTag(uid) {
    clearInterval(scanTimer);
    if ($('cbScanUID')) $('cbScanUID').textContent = uid;
    const result = $('cbScanResult');
    if (result) result.classList.add('show');
    const btn = $('cbAcceptScanBtn');
    if (btn) btn.style.display = 'flex';
    if ($('cbScanStatus')) $('cbScanStatus').textContent = '✓ Tag captured — accept to use';
    const ring = $('cbScanRing');
    if (ring) { ring.style.borderColor = 'rgba(76,175,80,.4)'; }
    toast('NFC tag detected!');
}

window.cbAcceptScan = function() {
    const uid = $('cbScanUID')?.textContent;
    cbCloseScan();
    // Find the first visible NFC tag input in the active row
    const rows = $$('#cpRegistry .cb-reg-row[data-cp-type="nfc"]');
    var tagInp = null;
    for (var i = 0; i < rows.length; i++) {
        var inp = rows[i].querySelector('.cp-inline-tag');
        if (inp && !inp.value) { tagInp = inp; break; }
    }
    if (!tagInp) tagInp = $('inlineNfcTag');
    if (tagInp && uid) {
        tagInp.value = uid;
        tagInp.style.borderColor = '#4caf50';
        tagInp.style.boxShadow = '0 0 0 2px rgba(76,175,80,0.15)';
        setTimeout(function() { tagInp.style.borderColor = ''; tagInp.style.boxShadow = ''; }, 1500);
    }
    toast('Identity ' + uid + ' synced');
};

/* ── Save to API ────────────────────────────── */
window.cbSaveInlineCheckpoints = async function() {
    syncRegistryFromRows();
    if (!inlineCps.length && !savedCps.length) { toast('No checkpoints to save', true); return; }
    if (!inlineCps.length) { toast('No new checkpoints to create', true); return; }

    var btn = document.querySelector('#cbRightPanel .cb-btn-teal') || document.querySelector('.cb-btn-teal');
    var origText = btn ? btn.innerHTML : '';
    if (btn) { btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...'; btn.disabled = true; }

    var payload = {
        checkpoints: inlineCps.map(function(cp) {
            return {
                name: cp.name,
                type: cp.checkpoint_type || 'nfc',
                geometry: (cp.lat && cp.lng && cp.lat !== '' && cp.lng !== '') ? [parseFloat(cp.lat), parseFloat(cp.lng)] : null,
                radius: cp.radius || null,
                nfc_tag: cp.nfc_tag || null,
                auditor_id: cp.auditor_id || null,
                target_id: cp.target_id || null,
                dwell_time: cp.dwell_time || 0,
                time_tolerance: cp.time_tolerance != null ? cp.time_tolerance : 15,
                planned_time: cp.planned_time || null,
                geo_shape: cp.geo_shape || null,
                fetch_location_on_scan: cp.fetch_location_on_scan || false
            };
        })
    };

    try {
        var res = await api('/api/map-objects/bulk_create/', { method:'POST', body:JSON.stringify(payload) });
        var data = await res.json().catch(function() { return {}; });

        if (res.ok && data.created_count !== undefined) {
            toast('Saved ' + data.created_count + ' checkpoint' + (data.created_count !== 1 ? 's' : ''));
            if (data.errors && data.errors.length) {
                var errorDetails = data.errors.map(function(e) { return Object.values(e).join(', '); }).join('; ');
                if (errorDetails) toast('Errors: ' + errorDetails, true);
            }
            if (btn) {
                btn.innerHTML = '<i class="fas fa-check"></i> Committed!';
                btn.classList.add('cb-success-burst');
                setTimeout(function() { btn.innerHTML = origText; btn.classList.remove('cb-success-burst'); btn.disabled = false; }, 2000);
            }
            // Reload assets to refresh the list
            await mgLoadAssets();
            mgLoadSavedCps();
            mgLogFleetEvent('check', 'Staged checkpoints committed', data.created_count + ' saved');
        } else {
            var err = data.errors ? (Array.isArray(data.errors) ? data.errors.map(function(e) { return typeof e === 'object' ? Object.values(e).join(', ') : e; }).join('; ') : data.detail) : (data.detail || 'Save failed');
            toast(err.slice(0, 150), true);
            if (btn) { btn.innerHTML = origText; btn.disabled = false; }
        }
    } catch(e) {
        toast('Network error', true);
        if (btn) { btn.innerHTML = origText; btn.disabled = false; }
    }
};

/* ── Set default log dates ───────────────────────── */
function setDefaultDates(){
    const today=new Date();
    const week=new Date(today); week.setDate(week.getDate()-7);
    $('logDateTo').value=today.toISOString().split('T')[0];
    $('logDateFrom').value=week.toISOString().split('T')[0];
}

/* ── Boot ────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded',function(){
     currentTab='staff';
     setDefaultDates();
     mgLoadGuards();
     mgRefreshBlueprintShift();
     setInterval(function(){
         if (currentTab === 'staff') mgRefreshBlueprintShift();
     }, 120000);

    // Init CalendarComponent
    if(window.CalendarComponent) {
        CalendarComponent.init({
            getAssignments: function(){ return window.allDeploys || []; },
            getRoutes: function(){ return window.allRoutes || []; },
            onDayClick: function(dateStr){
                var day = parseInt(dateStr.split('-')[2]);
                mgShowDayDetail(day);
            }
        });
    }

    // Cross-highlight between personnel list and timeline
    var guardListEl = document.getElementById('guardList');
    var callsignListEl = document.getElementById('callsignList');
    if (guardListEl) {
        guardListEl.addEventListener('mouseover', function(e) {
            var card = e.target.closest('[data-guard-id]');
            if (!card) { clearHighlights(); return; }
            var gid = card.getAttribute('data-guard-id');
            document.querySelectorAll('#callsignList [data-guard-id="' + gid + '"]').forEach(function(el) { el.style.background = 'rgba(93,202,165,0.04)'; });
        });
        guardListEl.addEventListener('mouseout', function() { clearHighlights(); });
    }
    if (callsignListEl) {
        callsignListEl.addEventListener('mouseover', function(e) {
            var row = e.target.closest('[data-guard-id]');
            if (!row) { clearHighlights(); return; }
            var gid = row.getAttribute('data-guard-id');
            document.querySelectorAll('#guardList [data-guard-id="' + gid + '"]').forEach(function(el) { el.style.background = 'rgba(93,202,165,0.04)'; });
        });
        callsignListEl.addEventListener('mouseout', function() { clearHighlights(); });
    }
    function clearHighlights() {
        document.querySelectorAll('#guardList [data-guard-id], #callsignList [data-guard-id]').forEach(function(el) { el.style.background = ''; });
    }
});

/* ══════════════════════════════════════════════════
   HTMX PANEL TRANSITIONS
   ══════════════════════════════════════════════════ */
let _panelLoaded = { staff: true, fleet: false, audit: false };
document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target.id !== 'mgPanelContainer') return;
    var url = evt.detail.requestConfig?.path || '';
    var panel = url.includes('fleet-panel') ? 'fleet' : url.includes('audit-panel') ? 'audit' : 'staff';
    _panelLoaded[panel] = true;
    if (panel === 'fleet') {
        setTimeout(function(){ mgLoadDevices(); mgLoadAssets(); }, 100);
        setTimeout(function(){ initMap(); }, 300);
        setTimeout(function(){ if (cbMap) cbMap.invalidateSize(); }, 500);
    } else if (panel === 'staff') {
        Promise.all([mgLoadGuards(), mgRefreshBlueprintShift()]).then(function(){
            if (window.CalendarComponent) CalendarComponent.render();
        });
    } else if (panel === 'audit') {
        mgLoadRoutes();
        mgLoadLog();
    }
});
