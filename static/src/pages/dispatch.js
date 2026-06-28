import '../styles/main.css';
import { $ as domId, bySel, escHtml as esc } from '../utils/dom.js';
import { api } from '../utils/api.js';

const $ = domId;
const escHtml = esc;

let allAssignments = [];
let allGuards      = [];
let allDispatchers = [];
let allRoutes      = [];
let allDevices     = [];
let currentTab = 'active';
let currentFilter = 'all';
let shiftMode = 'Day';
let redeployTarget = null;
let refreshTimer   = null;
let activityLog    = [];
window.__dc_live_next_by_assignment = {};
window.__dcActiveBpId = null;
window.__dcBpRefreshTimer = null;
window.__dcInBpView = false;
let __dcDeployMode = false;
let __dcInDayView = false;
let __dcSelectedMission = null;
let __dcPendingPayload = null;
let __dcOvMode = 'deploy';
let __dcOvRouteId = null;
let __dcOvAssignmentId = null;
let dcOvTagEntries = [];
let __mdCpOrig = {};
window.__mdCpLiveTimers = {};

function dcLog(msg, level = 'info') {
    activityLog.unshift({timestamp: new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}), msg, level});
    dcRenderLog();
}
function dcRenderLog() {
    const logEl = $('dcActivityLog');
    if (!logEl) return;
    var showDebug = ($('dcLogDebug') || {}).checked;
    const filtered = showDebug ? activityLog : activityLog.filter(e => e.level !== 'debug');
    logEl.innerHTML = filtered.slice(0, 50).map(e => `
        <div class="dc-log-entry dc-log-${e.level}">
            <span class="dc-log-time">${e.timestamp}</span>
            <span class="dc-log-msg">${e.msg}</span>
        </div>
    `).join('') || '<div class="dc-log-empty">No activity yet</div>';
}
function toast(msg, isErr) {
    const el = document.createElement('div');
    el.className = 'dc-toast';
    el.innerHTML = `<span class="dc-dot${isErr ? ' dc-dot-err' : ''}"></span>${msg}`;
    $('dcToasts').appendChild(el);
    setTimeout(() => el.remove(), 2800);
}

    window.dcLoadAll = async function () {
        // Clear live cache
        window.__dc_live_next_by_assignment = {};

        const icon = $('dcRefreshIcon');
        if (icon) icon.classList.add('dc-spinning');
        try {
            const [aRes, gRes, rRes, dRes, dispRes] = await Promise.all([
                api('/api/shifts/'),
                api('/api/guards/'),
                api('/api/routes/'),
                api('/api/devices/'),
                api('/api/dispatchers/')
            ]);

            if (!rRes.ok) {
                toast(`Routes load failed (${rRes.status})`, true);
            }
            if (!gRes.ok) {
                toast(`Guards load failed (${gRes.status})`, true);
            }
            if (!aRes.ok) {
                toast(`Assignments load failed (${aRes.status})`, true);
            }
            if (!dRes.ok) {
                toast(`Devices load failed (${dRes.status})`, true);
            }
            if (!dispRes.ok) {
                toast(`Dispatchers load failed (${dispRes.status})`, true);
            }


            const extractData = async (res) => {
                if (!res.ok) return [];
                const d = await res.json();
                return Array.isArray(d) ? d : (d.results || []);
            };

            // Use the helper to populate global arrays
            const liveRes = await api('/api/deployment-checkpoint-live/');
            if (liveRes && liveRes.ok) {
                const liveData = await liveRes.json().catch(() => null);
                if (liveData && Array.isArray(liveData.items)) {
                    window.__dc_live_next_by_assignment = {};
                    liveData.items.forEach(it => { window.__dc_live_next_by_assignment[it.assignment_id] = it; });
                }
            }

            [allAssignments, allGuards, allRoutes, allDevices, allDispatchers] = await Promise.all([

                extractData(aRes),
                extractData(gRes),
                extractData(rRes),
                extractData(dRes),
                extractData(dispRes)
            ]);

            const preselectRouteId = sessionStorage.getItem('mg_preselect_route');
            if (preselectRouteId) {
                sessionStorage.removeItem('mg_preselect_route');
                dcOpenDeployOverlay(preselectRouteId);
            }

            // Handoff from routes.html after a successful deploy: highlight deployed mission.
            const deployedRouteId = sessionStorage.getItem('dispatch_show_deployed_route');
            if (deployedRouteId) {
                // Keep value until we highlight successfully.
                try {
                    dcHighlightDeployedRoute(deployedRouteId);
                    sessionStorage.removeItem('dispatch_show_deployed_route');
                } catch (e) {
                    console.error('dcHighlightDeployedRoute failed', e);
                }
            }
        } catch (e) { toast('Load failed', true); }
        if (icon) icon.classList.remove('dc-spinning');
        try { dcPopulateDropdowns(); } catch(e) { console.error('dcPopulateDropdowns failed', e); toast('Dropdown render error', true); }
        dcRenderLsStats();
        dcLog(`Loaded ${allAssignments.length} assignments, ${allRoutes.length} routes`, 'info');
        try { CalendarComponent.init(); } catch(e) { console.error('CalendarComponent.init failed', e); }
        // Mission grid and blueprint library now rendered via htmx on page load
        if (window.__dcActiveBpId) {
            dcRenderBpProgress(window.__dcActiveBpId);
        }
        // Auto-refresh mission detail if open
        if (typeof __dcSelectedMission !== 'undefined' && __dcSelectedMission) {
            const updated = allAssignments.find(a => a.id === __dcSelectedMission.id);
            if (updated) dcShowMissionDetail(updated);
        }
    };

    
    function dcRebuildGuards() {
        const container = $('dcGuardList');
        if (!container) return;
        const filtered = allGuards.filter(p => 
            (!p.role || p.role === 'guard' || p.role === 'supervisor') &&
            (p.shift || 'Day') === shiftMode
        );

        container.innerHTML = filtered.map(g => {
            const name = (g.first_name && g.last_name) ? `${g.first_name} ${g.last_name}` : (g.username || 'Unknown');
            return `
                <label class="dc-guard-item">
                    <input type="checkbox" name="dcGuardCheck" value="${g.id}" data-name="${name}">
                    <span>${name}</span>
                    <span style="margin-left:auto; opacity:0.4; font-size:0.65rem;">${g.callsign || ''}</span>
                </label>
            `;
            }).join('') || `<div style="padding:10px; color:rgba(255,255,255,0.3); font-size:0.7rem;">No ${shiftMode} personnel</div>`;
    }

    window.dcToggleAllGuards = function() {
        const checks = document.querySelectorAll('input[name="dcGuardCheck"]');
        const allSet = Array.from(checks).every(c => c.checked);
        checks.forEach(c => c.checked = !allSet);
    };

    window.dcHandleShift = function() {
        shiftMode = ($('dcOvShiftDay') || {}).checked ? 'Day' : 'Night';
        dcRebuildGuards();
    };

    window.dcOnRouteSelect = async function() {
        // Legacy function — no longer active
    };

    function dcPopulateDropdowns() {
        dcRebuildGuards();
    }

    /* ── Left sidebar: compact stats ───────────────── */
    function dcRenderLsStats() {
        var routeExists = function(a) {
            var rid = a.route_id || a.route;
            return rid && Array.isArray(allRoutes) && allRoutes.some(function(r) { return String(r.id) === String(rid); });
        };
        var liveData = window.__dc_live_next_by_assignment || {};

        var active  = allAssignments.filter(function(a) { return a.is_active && !a.is_completed && routeExists(a); }).length;
        var done    = allAssignments.filter(function(a) { return a.is_completed; }).length;
        var pending = allAssignments.filter(function(a) { return !a.is_active && !a.is_completed && routeExists(a); }).length;
        var dailyRoutes = allRoutes.filter(function(r) { return r.is_daily && r.status !== 'archived'; }).length;
        var missed  = allAssignments.filter(function(a) {
            var lv = liveData[a.id];
            return a.is_active && !a.is_completed && lv && lv.has_missed_checkpoints === true && routeExists(a);
        }).length;

        var onDutyGuards = new Set();
        allAssignments.filter(function(a) { return a.is_active && !a.is_completed && routeExists(a); }).forEach(function(a) {
            if (a.guard_supervisor) onDutyGuards.add(String(a.guard_supervisor));
            if (a.guard_callsign) onDutyGuards.add(String(a.guard_callsign));
        });

        var activeEl  = $('dcLsActive');
        var onDutyEl  = $('dcLsOnDuty');
        var pendingEl = $('dcLsPending');
        var missedEl  = $('dcLsMissed');
        var dailyEl   = $('dcLsDaily');
        if (activeEl)  activeEl.textContent = active;
        if (onDutyEl)  onDutyEl.textContent = onDutyGuards.size || '\u2014';
        if (pendingEl) pendingEl.textContent = pending;
        if (missedEl)  missedEl.textContent = missed;
        if (dailyEl)   dailyEl.textContent = dailyRoutes;

        var setTab = function(id, count) { var el = $(id); if (el) el.textContent = count > 0 ? count : ''; };
        setTab('dcTabActive', active);
        setTab('dcTabUpcoming', pending);
        setTab('dcTabAll', allAssignments.length + dailyRoutes);
        setTab('dcTabDone', done);
        setTab('dcTabMissed', missed);
    }

    /* ── Tab switch ────────────────────────────────── */
    function refreshMissionsGrid() {
        if (window.htmx) {
            htmx.ajax('GET', '/api/missions-partial/?tab=' + (currentTab || 'active'), {
                target: '#dcLsGrid', swap: 'innerHTML'
            });
        }
    }
    window.dcSwitchTab = function (tab, el) {
        currentTab = tab;
        document.querySelectorAll('.dc-ls-tab:not(.filter-btn)').forEach(t => t.classList.remove('active'));
        currentFilter = 'all';
        document.querySelectorAll('.dc-ls-tab.filter-btn').forEach(t => t.classList.remove('active'));
        const allFilter = document.querySelector('.dc-ls-tab.filter-btn[data-filter="all"]');
        if (allFilter) allFilter.classList.add('active');
        if (el) el.classList.add('active');

        if (tab === 'calendar') {
            // Just focus the calendar on the right - scroll to it
            const calTitle = $('dcLsCalTitle');
            if (calTitle) calTitle.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            return;
        }
        refreshMissionsGrid();
    };

      /* ── (blueprints moved to center panel) ───────────── */

     window.dcQuickDeployRoute = function(routeId) {
         sessionStorage.setItem('mg_preselect_route', routeId);
         dcOpenDeployOverlay(routeId);
         dcLog(`Quick-deploy initiated for route ${routeId}`, 'info');
     };

      window.dcSetRouteForDeploy = function(routeId) {
          dcOpenDeployOverlay(routeId);
      };

      window.dcDeleteBlueprint = function(routeId, routeName) {
          if (!confirm(`Delete blueprint "${routeName}" and all its deployments?`)) return;
          dcLog(`Deleting blueprint ${routeId}`, 'info');
          api(`/api/routes/${routeId}/`, { method: 'DELETE' }).then(res => {
              if (res.ok || res.status === 204) {
                  toast('Blueprint deleted');
                  if (window.__dcActiveBpId === routeId) dcCloseBpProgress();
                  dcLoadAll();
              } else {
                  toast('Failed to delete blueprint', true);
              }
          }).catch(() => toast('Delete error', true));
      };

      /* ── Blueprint library now rendered via htmx ─────── */
      /* dcRenderBpLibrary() and dcFilterBlueprints() removed — see /api/blueprints-partial/ */

      /* ── Deploy mode toggle ──────────────────────────── */
      window.__dcDeployMode = false;

      window.dcToggleDeployMode = function() {
          __dcDeployMode = !__dcDeployMode;
          var btn = $('dcDeployToggle');
          var panel = $('dcDeployPanel');
          var cards = document.querySelectorAll('.dc-bp-card');

          if (__dcDeployMode) {
              if (btn) btn.style.background = 'rgba(211,47,47,0.25)';
              cards.forEach(function(c) { c.classList.add('dc-deploy-mode'); });
              dcLog('Deploy mode: click a blueprint card to deploy', 'info');
          } else {
              if (btn) btn.style.background = '';
              cards.forEach(function(c) { c.classList.remove('dc-deploy-mode'); });
              if (panel) panel.style.display = 'none';
          }
      };

      window.dcExitDeployMode = function() {
          if (window.__dcDeployMode) dcToggleDeployMode();
      };

      /* ── Select / deselect blueprint → show progress ──── */
      window.dcSelectBlueprint = function(routeId) {
          const prevCard = document.querySelector('.dc-bp-card.selected');
          if (prevCard) prevCard.classList.remove('selected');
          const card = document.querySelector(`.dc-bp-card[data-bp-id="${routeId}"]`);
          if (card) card.classList.add('selected');

          window.__dcActiveBpId = routeId;
          dcShowBpProgress(routeId);
          dcShowBpDeployments(routeId);
      };

      window.dcShowBpDeployments = function(routeId) {
          const container = $('dcBpDeployments');
          const list = $('dcBpDeploymentsList');
          if (!container || !list) return;

          const deployments = allAssignments.filter(a => String(a.route_id || a.route) === String(routeId));
          
          if (!deployments.length) {
              container.classList.add('dc-hidden');
              return;
          }

          container.classList.remove('dc-hidden');
          list.innerHTML = deployments.map(a => {
              const statusCls = a.is_completed ? 'done' : (a.is_active ? 'active' : 'sched');
              const guardName = a.guard_supervisor_name || 'Unassigned';
              return `
                  <div class="dc-bp-deploy-card">
                      <div class="dc-bp-deploy-head">
                          <span class="dc-bp-deploy-guard">${guardName}</span>
                          <span class="dc-bp-deploy-status ${statusCls}">${statusCls === 'done' ? 'Done' : (statusCls === 'active' ? 'Active' : 'Sched')}</span>
                      </div>
                      <div class="dc-bp-deploy-meta">
                          <span><i class="fas fa-clock"></i> ${a.shift_type || 'Day'}</span>
                          <span><i class="fas fa-tablet"></i> ${a.device_name || 'No Device'}</span>
                      </div>
                  </div>
              `;
          }).join('');
      };

      window.dcHideBpDeployments = function() {
          $('dcBpDeployments').classList.add('dc-hidden');
      };

      window.dcShowBpProgress = function(routeId) {
          window.__dcInBpView = true;
          const route = allRoutes.find(r => String(r.id) === String(routeId));
          if (!route) return;

          // Hide center default views, show bp progress
          const grid = $('dcLsGrid');
          const tabs = $('dcLsTabs');
          const stats = $('dcLsStats');
          const md = $('dcMissionDetail');
          const dv = $('dcDayView');
          if (grid) grid.classList.add('dc-hidden');
          if (tabs) tabs.classList.add('dc-hidden');
          if (stats) stats.classList.add('dc-hidden');
          if (md) md.classList.add('dc-hidden');
          if (dv) dv.classList.add('dc-hidden');

          const pv = $('dcBpProgressView');
          pv.classList.remove('dc-hidden');
          $('dcCenterTitle').innerHTML = `<i class="fas fa-map" style="color:var(--primary);margin-right:6px;"></i>${route.name}`;

          // Reuse existing render logic but target center panel IDs
          dcRenderBpProgress(routeId);
          dcLog(`Viewing blueprint: ${route.name}`, 'info');

          // Auto-refresh
          if (window.__dcBpRefreshTimer) clearInterval(window.__dcBpRefreshTimer);
          window.__dcBpRefreshTimer = setInterval(() => {
              if (!window.__dcActiveBpId) {
                  clearInterval(window.__dcBpRefreshTimer);
                  window.__dcBpRefreshTimer = null;
                  return;
              }
              dcRefreshBpTiming(window.__dcActiveBpId);
          }, 10000);
      };

      window.dcCloseBpProgress = function() {
          window.__dcInBpView = false;
          const prevCard = document.querySelector('.dc-bp-card.selected');
          if (prevCard) prevCard.classList.remove('selected');
          window.__dcActiveBpId = null;

          if (window.__dcBpRefreshTimer) {
              clearInterval(window.__dcBpRefreshTimer);
              window.__dcBpRefreshTimer = null;
          }

          const pv = $('dcBpProgressView');
          pv.classList.add('dc-hidden');
          const grid = $('dcLsGrid');
          const tabs = $('dcLsTabs');
          const stats = $('dcLsStats');
          if (grid) grid.classList.remove('dc-hidden');
          if (tabs) tabs.classList.remove('dc-hidden');
          if (stats) stats.classList.remove('dc-hidden');
          $('dcCenterTitle').innerHTML = '<i class="fas fa-satellite-dish" style="color:var(--primary);margin-right:6px;"></i>Missions';
          dcLog('Closed blueprint progress', 'info');
      };

      window.dcRenderBpProgress = function(routeId) {
          var route = allRoutes.find(function(r) { return String(r.id) === String(routeId); });
          if (!route) return;

          var deployments = allAssignments.filter(function(a) { return String(a.route_id || a.route) === String(routeId); });
          var liveData = window.__dc_live_next_by_assignment || {};

          var total = deployments.length;
          var active = deployments.filter(function(d) { return d.is_active && !d.is_completed; }).length;
          var done = deployments.filter(function(d) { return d.is_completed; }).length;
          var pending = deployments.filter(function(d) { return !d.is_active && !d.is_completed; }).length;
          var missed = deployments.filter(function(d) {
              var live = liveData[d.id];
              return d.is_active && !d.is_completed && live && live.next_checkpoint && live.next_checkpoint.is_window_missed;
          }).length;

          var scheduleStr = [route.scheduled_date || '', route.scheduled_start_time || ''].filter(Boolean).join(' @ ') || '';
          var dailyStr = route.is_daily ? ' · Daily' : '';
          $('dcBpPvTitle').textContent = route.name;
          $('dcBpPvSub').textContent = (route.logic_type || 'Flexible') + ' · ' + (route.checkpoint_count || 0) + ' CP · ' + total + ' deploy' + (total !== 1 ? 's' : '') + (scheduleStr ? ' · ' + scheduleStr : '') + dailyStr;

          var totalCP = route.checkpoint_count || 0;
          var assignedG = (route.assigned_guards && route.assigned_guards.length) || 0;

          $('dcBpPvSummary').innerHTML =
              '<div class=\"bp-summary-item bp-summary-active\"><div class=\"bp-summary-val\">' + active + '</div><div class=\"bp-summary-lbl\"><i class=\"fas fa-broadcast-tower\"></i> Active</div></div>' +
              '<div class=\"bp-summary-item bp-summary-pending\"><div class=\"bp-summary-val\">' + pending + '</div><div class=\"bp-summary-lbl\"><i class=\"fas fa-clock\"></i> Scheduled</div></div>' +
              '<div class=\"bp-summary-item bp-summary-done\"><div class=\"bp-summary-val\">' + done + '</div><div class=\"bp-summary-lbl\"><i class=\"fas fa-check-circle\"></i> Completed</div></div>' +
              '<div class=\"bp-summary-item bp-summary-missed\"><div class=\"bp-summary-val\">' + missed + '</div><div class=\"bp-summary-lbl\"><i class=\"fas fa-exclamation-triangle\"></i> Missed</div></div>' +
              '<div class=\"bp-summary-item\"><div class=\"bp-summary-val\">' + totalCP + '</div><div class=\"bp-summary-lbl\"><i class=\"fas fa-location-dot\"></i> Checkpoints</div></div>' +
              '<div class=\"bp-summary-item\"><div class=\"bp-summary-val\">' + assignedG + '</div><div class=\"bp-summary-lbl\"><i class=\"fas fa-users\"></i> Guards</div></div>';

          var listEl = $('dcBpPvAssignList');
          if (!deployments.length) {
              listEl.innerHTML = '<div class=\"bp-empty\"><i class=\"fas fa-route\"></i> No deployments yet. Deploy from the panel.</div>';
          } else {
              listEl.innerHTML = deployments.map(function(a) { return dcBpAssignmentCardHTML(a, route, liveData); }).join('');
          }
      };

     function dcBpAssignmentCardHTML(a, route, liveData) {
         var isActive = a.is_active && !a.is_completed;
         var isCompleted = a.is_completed;
         var isScheduled = !a.is_active && !a.is_completed && (a.scheduled_start || a.scheduled_end || a.scheduled_start_time);

         var statusLabel = 'Scheduled';
         var cardCls = '';
         if (isActive) { statusLabel = 'Active'; cardCls = 'is-active'; }
         else if (isCompleted) { statusLabel = 'Completed'; cardCls = 'is-done'; }
         else if (isScheduled) { statusLabel = 'Scheduled'; }

         var total = a.total_checkpoints || 0;
         var hit = a.completed_checkpoints || 0;
         var pct = total > 0 ? Math.round((hit / total) * 100) : 0;

          var guardName = a.guard_supervisor_name || a.operator_name || a.guard_callsign || 'Unknown Guard';
          var opId = a.guard_callsign || '';
          var deviceName = a.device_name || '';
          var shiftLabel = a.shift_type || '';
          var initial = guardName.charAt(0).toUpperCase();

         var routeCps = (route && route.checkpoints) ? route.checkpoints : [];
         var now = new Date();
         var datePart = (a.scheduled_date || a.assigned_at || '').split(/[T ]/)[0];
         var todayDate = new Date(now.toISOString().split('T')[0]);
         var hasMisses = false;

         // Build timing info from live data
          var live = (liveData[a.id] && liveData[a.id].next_checkpoint) || null;

         // Build checkpoint rows
         var cpRows = '';
         if (routeCps.length > 0) {
             var cpIdx;
             for (cpIdx = 0; cpIdx < routeCps.length; cpIdx++) {
                 var cp = routeCps[cpIdx];
                 var isHit = cpIdx < hit;
                 var isNext = cpIdx === hit && isActive && !isHit;
                 var state = 'pending';
                 if (isHit) state = 'hit';
                 else if (isNext) state = 'next';
                 else if (isActive && cp.planned_time && datePart) {
                     try {
                         var pt = new Date(datePart + 'T' + cp.planned_time);
                         var tolerance = ((cp.time_tolerance || 15) + (cp.dwell_time || 0)) * 60000;
                         if (!isNaN(pt.getTime()) && now.getTime() > pt.getTime() + tolerance) {
                             state = 'miss';
                         }
                     } catch(e) {}
                 } else if (!isActive && !isHit && datePart) {
                     var missionDate = new Date(datePart);
                     if (missionDate < todayDate) state = 'miss';
                 }
                 if (state === 'miss') hasMisses = true;

                 cpRows += '<div class="dc-bp-cp-row is-' + state + '">' +
                     '<span class="dc-bp-cp-index">' + (cpIdx + 1) + '</span>' +
                     '<span class="dc-bp-cp-name">' + (cp.name || 'Point ' + (cpIdx + 1)) + '</span>' +
                     '<span class="dc-bp-cp-type">' + dcBpCheckpointType(cp) + '</span>' +
                     '<span class="dc-bp-cp-time">' + (cp.planned_time ? '\u231A' + cp.planned_time : '\u2014') + '</span>' +
                     '<span class="dc-bp-cp-dwell">' + (cp.dwell_time ? '\u23F1' + cp.dwell_time + 'm' : '\u2014') + '</span>' +
                     '<span class="dc-bp-cp-status-text ' + state + '">' + (state === 'hit' ? 'Hit' : state === 'miss' ? 'Miss' : state === 'next' ? 'NEXT' : '') + '</span>' +
                 '</div>';
             }
         }

         // Timing grid
         var timingGrid = '';
         var sst = a.scheduled_start_time;
         var fmtTime = function(sec) {
             if (sec === null || sec === undefined) return '\u2014';
             sec = Math.max(0, Number(sec));
             var mf2 = Math.floor(sec / 60);
             var sf2 = sec % 60;
             return (mf2 > 0 ? mf2 + 'm ' : '') + sf2 + 's';
         };
         if (isActive && live) {
             var timeRem2 = live.time_remaining_seconds;
             var dwellRem2 = live.dwell_remaining_seconds;
             var dwellMin2 = live.dwell_time_minutes || 0;
             var plannedTime2 = live.planned_time ? live.planned_time.substring(0, 5) : '\u2014';
             var isPresent2 = live.is_present;
             var isMissed2 = live.is_window_missed;
             var cpName2 = live.name || 'Next point';
             var fmtTimeStr = live.time_remaining_seconds != null ? fmtTime(timeRem2) : 'T+';
             var dwellTimeStr = dwellMin2 > 0 ? dwellMin2 + 'm' : '\u2014';
             var dwellRemStr = isPresent2 ? fmtTime(dwellRem2) : 'Not present';
             var etaClass = isMissed2 ? 'miss' : (isPresent2 ? 'present' : '');
             var etaVal = isMissed2 ? 'MISSED' : (fmtTimeStr);
             var onTimeClass = (live && live.is_window_missed) ? 'miss' : 'present';
             var onTimeVal = (live && live.is_window_missed) ? 'No' : 'Yes';

             timingGrid = '<div class=\"dc-bp-timing-grid\">' +
                 '<div class=\"dc-bp-timing-item\"><div class=\"dc-bp-timing-lbl\">Next Objective</div><div class=\"dc-bp-timing-val\">' + cpName2 + '</div></div>' +
                 '<div class=\"dc-bp-timing-item\"><div class=\"dc-bp-timing-lbl\">Target Time</div><div class=\"dc-bp-timing-val\">' + plannedTime2 + '</div></div>' +
                 '<div class=\"dc-bp-timing-item\"><div class=\"dc-bp-timing-lbl\">Time Remaining</div><div class=\"dc-bp-timing-val ' + etaClass + '\">' + etaVal + '</div></div>' +
                 '<div class=\"dc-bp-timing-item\"><div class=\"dc-bp-timing-lbl\">Dwell Time</div><div class=\"dc-bp-timing-val\">' + dwellTimeStr + '</div></div>' +
                 '<div class=\"dc-bp-timing-item\"><div class=\"dc-bp-timing-lbl\">Dwell Remaining</div><div class=\"dc-bp-timing-val ' + (isPresent2 ? 'present' : '') + '\">' + dwellRemStr + '</div></div>' +
                 '<div class=\"dc-bp-timing-item\"><div class=\"dc-bp-timing-lbl\">On Time</div><div class=\"dc-bp-timing-val ' + onTimeClass + '\">' + onTimeVal + '</div></div>' +
             '</div>';
         } else if (isCompleted) {
             var startTimeStr = a.assigned_at ? new Date(a.assigned_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : '\u2014';
             var endTimeStr = a.ended_at ? new Date(a.ended_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : '\u2014';
             timingGrid = '<div class=\"dc-bp-timing-grid\">' +
                 '<div class=\"dc-bp-timing-item\"><div class=\"dc-bp-timing-lbl\">Status</div><div class=\"dc-bp-timing-val present\">Completed</div></div>' +
                 '<div class=\"dc-bp-timing-item\"><div class=\"dc-bp-timing-lbl\">Start Time</div><div class=\"dc-bp-timing-val\">' + startTimeStr + '</div></div>' +
                 '<div class=\"dc-bp-timing-item\"><div class=\"dc-bp-timing-lbl\">End Time</div><div class=\"dc-bp-timing-val\">' + endTimeStr + '</div></div>' +
                 '<div class=\"dc-bp-timing-item\"><div class=\"dc-bp-timing-lbl\">Checkpoints</div><div class=\"dc-bp-timing-val\">' + hit + ' / ' + total + '</div></div>' +
             '</div>';
         } else {
             var schedBlock = sst ? '<div class=\"dc-bp-timing-item\"><div class=\"dc-bp-timing-lbl\">Scheduled Start</div><div class=\"dc-bp-timing-val\">' + sst + '</div></div>' : '';
             timingGrid = '<div class=\"dc-bp-timing-grid\">' +
                 '<div class=\"dc-bp-timing-item\"><div class=\"dc-bp-timing-lbl\">Status</div><div class=\"dc-bp-timing-val overdue\">' + statusLabel + '</div></div>' +
                 schedBlock +
                 '<div class=\"dc-bp-timing-item\"><div class=\"dc-bp-timing-lbl\">Shift</div><div class=\"dc-bp-timing-val\">' + (a.shift_type || '\u2014') + '</div></div>' +
                 '<div class=\"dc-bp-timing-item\"><div class=\"dc-bp-timing-lbl\">Checkpoints</div><div class=\"dc-bp-timing-val\">' + hit + ' / ' + total + '</div></div>' +
             '</div>';
         }

         if (hasMisses && isActive) cardCls += ' is-failed';

          return '<div class=\"dc-bp-assign-card ' + cardCls + '\">' +
              '<div class=\"dc-bp-assign-top\">' +
                  '<div class=\"dc-bp-assign-guard\">' +
                      '<div class=\"dc-bp-assign-avatar\">' + initial + '</div>' +
                      '<div>' +
                          '<div class=\"dc-bp-assign-guard-name\">' + guardName + '</div>' +
                          '<div class=\"dc-bp-assign-opid\">' + (opId || deviceName || '') + '</div>' +
                      '</div>' +
                  '</div>' +
                  '<div style=\"display:flex;align-items:center;gap:8px;\">' +
                      (deviceName && !a.guard_supervisor_name ? '<span style=\"font-size:0.55rem;color:#6C8EEF;\"><i class=\"fas fa-microchip\"></i> ' + deviceName + '</span>' : '') +
                      (shiftLabel ? '<span style=\"font-size:0.5rem;color:rgba(255,255,255,0.25);\"><i class=\"fas ' + (shiftLabel === 'Night' ? 'fa-moon' : 'fa-sun') + '\"></i> ' + shiftLabel + '</span>' : '') +
                      '<span class=\"dc-status ' + (isActive ? 'dc-s-active' : isCompleted ? 'dc-s-done' : 'dc-s-scheduled') + '\"><span class=\"dc-status-dot\"></span>' + statusLabel + '</span>' +
                  '</div>' +
              '</div>' +
              (total > 0 ? '<div class=\"dc-progress-wrap\"><div class=\"dc-progress-label\"><span>' + hit + ' / ' + total + ' checkpoints</span><span>' + pct + '%</span></div><div class=\"dc-progress-track\"><div class=\"dc-progress-fill' + (pct >= 100 ? ' complete' : '') + '\" style=\"width:' + pct + '%\"></div></div></div>' : '') +
              timingGrid +
              (cpRows ? '<div class=\"dc-bp-cp-list\">' + cpRows + '</div>' : '') +
              '<div style=\"margin-top:12px;font-size:0.6rem;color:rgba(255,255,255,0.25);display:flex;gap:14px;flex-wrap:wrap;border-top:1px solid rgba(255,255,255,0.02);padding-top:8px;\">' +
                  '<span><i class=\"fas fa-calendar\"></i> ' + (a.scheduled_date || a.assigned_at ? new Date(a.scheduled_date || a.assigned_at).toLocaleDateString() : '\u2014') + '</span>' +
                  (a.assigned_at ? '<span><i class=\"fas fa-clock\"></i> Started ' + new Date(a.assigned_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) + '</span>' : '') +
                  (a.route_name ? '<span><i class=\"fas fa-route\"></i> ' + a.route_name + '</span>' : '') +
                  (deviceName && a.guard_supervisor_name ? '<span><i class=\"fas fa-microchip\"></i> ' + deviceName + '</span>' : '') +
              '</div>' +
          '</div>';
      }

     function dcBpCheckpointType(cp) {
         if (cp.nfc_tag) return 'NFC';
         if (cp.lat != null && cp.lng != null) return 'GPS';
         if (cp.auditor_id && cp.target_id) return 'Peer';
         if (cp.planned_time) return 'Time';
         return 'POI';
     }

      window.dcRefreshBpTiming = async function(routeId) {
          try {
              const res = await api('/api/deployment-checkpoint-live/');
              if (res.ok) {
                  const data = await res.json();
                  if (data && Array.isArray(data.items)) {
                      window.__dc_live_next_by_assignment = {};
                      data.items.forEach(it => { window.__dc_live_next_by_assignment[it.assignment_id] = it; });
                  }
              }
              const route = allRoutes.find(r => String(r.id) === String(routeId));
              if (!route) return;
              const deployments = allAssignments.filter(a => String(a.route_id || a.route) === String(routeId));
              const listEl = $('dcBpPvAssignList');
              if (listEl) {
                  listEl.innerHTML = deployments.map(a => dcBpAssignmentCardHTML(a, route, window.__dc_live_next_by_assignment || {})).join('');
              }
          } catch(e) {}
      };

      /* ── Mission grid now rendered via htmx ──────────── */
      /* dcRenderLsGrid() removed — see /api/missions-partial/ */

    window.dcSetLsFilter = function(f, btn) {
        currentFilter = f;
        document.querySelectorAll('.dc-ls-tab.filter-btn').forEach(el => el.classList.remove('active'));
        if (btn) btn.classList.add('active');
        refreshMissionsGrid();
    };

    /* ── dcLsCardHTML removed (was only used by dcRenderLsGrid, now htmx-driven) ── */

    /* ── Select mission from left sidebar ───────────── */
    window.dcSelectMission = function(assignId) {
        document.querySelectorAll('.dc-ls-card.selected').forEach(el => el.classList.remove('selected'));
        const card = document.querySelector(`.dc-ls-card[data-assign-id="${assignId}"]`);
        if (card) card.classList.add('selected');

        const assignment = allAssignments.find(a => String(a.id) === String(assignId));
        if (!assignment) return;

        dcShowMissionDetail(assignment);
        dcLog(`Selected mission ${assignId} ${assignment.route_name || ''}`, 'debug');
    };

    /* ── Show Mission Detail in center panel ────────── */
    window.dcShowMissionDetail = function(assignment) {
        __dcSelectedMission = assignment;
        const el = $('dcMissionDetail');
        const grid = $('dcLsGrid');
        const tabs = $('dcLsTabs');
        const stats = $('dcLsStats');
        const centerTitle = $('dcCenterTitle');

        if (grid) grid.classList.add('dc-hidden');
        if (tabs) tabs.classList.add('dc-hidden');
        if (stats) stats.classList.add('dc-hidden');
        el.classList.remove('dc-hidden');
        centerTitle.innerHTML = `<i class="fas fa-satellite-dish" style="color:var(--primary);margin-right:6px;"></i>Progress`;

        // ── Live data ──
        var ld = window.__dc_live_next_by_assignment;
        var live = (ld && ld[assignment.id]) || null;
        var isActive    = assignment.is_active && !assignment.is_completed;
        var isCompleted = assignment.is_completed;
        var isScheduled = (assignment.scheduled_start || assignment.scheduled_end || assignment.scheduled_start_time) && !assignment.is_active && !assignment.is_completed;
        var isDeviceOnly = !assignment.guard_supervisor_name && !assignment.operator_name && !assignment.guard_callsign;

        // ── Status badge ──
        var statusClass, statusLabel;
        if (isActive && live && live.has_missed_checkpoints) { statusClass='dc-s-missed'; statusLabel='Missed'; }
        else if (isActive) { statusClass='dc-s-active'; statusLabel='Active'; }
        else if (isCompleted) { statusClass='dc-s-done'; statusLabel='Completed'; }
        else if (isScheduled) { statusClass='dc-s-scheduled'; statusLabel='Scheduled'; }
        else { statusClass='dc-s-created'; statusLabel='Draft'; }
        const badge = $('dcMdStatusBadge');
        badge.className = 'dc-status ' + statusClass;
        badge.innerHTML = `<span class="dc-status-dot"></span>${statusLabel}`;

        // ── Header info cards ──
        var guardName = assignment.guard_supervisor_name || assignment.guard_callsign || '—';
        var deviceName = assignment.device_name || '—';
        var batPct = live && live.battery_pct;
        var isOnline = live && live.is_online;
        var batHtml = '';
        if (batPct != null) {
            var batColor = batPct > 50 ? '#5DCAA5' : batPct > 20 ? '#EF9F27' : '#d32f2f';
            var batIcon = batPct > 50 ? 'fa-battery-three-quarters' : batPct > 20 ? 'fa-battery-half' : 'fa-battery-quarter';
            batHtml = '<span style="color:' + batColor + ';font-weight:800;"><i class="fas ' + batIcon + '"></i> ' + batPct + '%</span>';
        } else {
            batHtml = '<span style="color:rgba(255,255,255,0.3);"><i class="fas fa-battery-slash"></i></span>';
        }
        var onlineDot = isOnline ? '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#5DCAA5;margin-right:4px;box-shadow:0 0 6px rgba(93,202,165,0.4);"></span>' : '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#d32f2f;margin-right:4px;"></span>';

        var routeData = allRoutes.find(function(r) { return String(r.id) === String(assignment.route_id || assignment.route); });
        var logicType = (routeData && routeData.logic_type) || assignment.logic_type || '';
        var totalCp = assignment.total_checkpoints || (routeData && routeData.checkpoint_count) || 0;
        var total = totalCp;
        var hit = assignment.completed_checkpoints || 0;
        var pct = totalCp > 0 ? Math.round((hit / totalCp) * 100) : 0;
        var guardOpId = assignment.guard_callsign || (isDeviceOnly ? '' : '');
        var deviceCode = assignment.device_id_code || '';

        $('dcMdGuard').innerHTML = isDeviceOnly
            ? '<span style="color:#6C8EEF;"><i class="fas fa-microchip"></i> ' + deviceName + '</span>'
            : '<i class="fas fa-user-shield"></i> ' + guardName;
        $('dcMdGuardOp').innerHTML = isDeviceOnly ? 'Device-operated' : (guardOpId ? 'ID: ' + guardOpId : '');

        var deviceStr = deviceName !== '—' ? onlineDot + deviceName + ' ' + batHtml : '—';
        $('dcMdDevice').innerHTML = deviceStr;
        $('dcMdDeviceId').innerHTML = deviceCode ? 'Code: ' + deviceCode : (live && live.gps_coords ? 'GPS: ' + (live.gps_coords.lat || '') + ', ' + (live.gps_coords.lng || '') : '');

        $('dcMdRoute').innerHTML = '<i class="fas fa-route" style="color:#EF9F27;margin-right:4px;"></i> ' + (assignment.route_name || '—');
        $('dcMdRouteDetail').innerHTML = (routeData && routeData.description) ? routeData.description.substring(0, 60) : '';

        $('dcMdShift').textContent = assignment.shift_type || '—';
        $('dcMdShiftDetail').textContent = assignment.is_daily ? 'Recurring daily' : (assignment.shift_type === 'Night' ? 'Night shift' : 'Day shift');

        $('dcMdLogic').textContent = logicType || '—';
        $('dcMdCpCount').textContent = totalCp > 0 ? hit + ' / ' + totalCp : '—';
        $('dcMdCpDetail').textContent = totalCp > 0 ? pct + '% complete' : 'No checkpoints';

        $('dcMdStarted').textContent = assignment.assigned_at ? new Date(assignment.assigned_at).toLocaleString() : '—';
        $('dcMdStartedDetail').textContent = assignment.assigned_at ? (function() {
            var diff = Date.now() - new Date(assignment.assigned_at).getTime();
            var h = Math.floor(diff / 3600000);
            var m = Math.floor((diff % 3600000) / 60000);
            return h > 0 ? h + 'h ' + m + 'm ago' : m + 'm ago';
        })() : '';

        $('dcMdSchedule').textContent = assignment.scheduled_start_time
            ? (assignment.scheduled_date || '') + ' @ ' + assignment.scheduled_start_time + (assignment.is_daily ? ' (Daily)' : '')
            : '—';
        $('dcMdScheduleDetail').textContent = assignment.scheduled_end
            ? 'Ends: ' + new Date(assignment.scheduled_end).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})
            : (assignment.is_daily ? 'End of day' : '');

        // ── Checkpoint progress ──
        $('dcMdProgressBar').innerHTML = total > 0 ? '<div style="display:flex;justify-content:space-between;font-size:0.62rem;color:rgba(255,255,255,0.5);margin-bottom:4px;"><span>' + hit + ' / ' + total + ' checkpoints</span><span>' + pct + '%</span></div><div class=\"dc-progress-track\"><div class=\"dc-progress-fill' + (pct>=100?' complete':'') + '\" style=\"width:' + pct + '%\"></div></div>' : '<div style=\"font-size:0.68rem;color:rgba(255,255,255,0.3);\">No checkpoints</div>';

        // ── Live next-objective block with dwell progress ──
        let liveBlock = '';
            if (isActive && live && live.next_checkpoint) {
            var lc = live.next_checkpoint;
            var dwellTotal = (lc.dwell_time_minutes || 0) * 60;
            var dwellRem = lc.dwell_remaining_seconds != null ? Math.max(0, Number(lc.dwell_remaining_seconds)) : null;
            var dwellPct = dwellTotal > 0 && dwellRem != null ? Math.round(((dwellTotal - dwellRem) / dwellTotal) * 100) : 0;
            var dwellLabel = lc.is_present ? (dwellRem != null ? Math.floor(dwellRem/60)+'m '+dwellRem%60+'s' : 'Checking...') : (lc.dwell_time_minutes > 0 ? 'Awaiting (need '+lc.dwell_time_minutes+'m stay)' : 'No stay required');
            var etaInit = (lc.time_remaining_seconds != null) ? Math.max(0, Number(lc.time_remaining_seconds)) : null;

            liveBlock = '<div class="md-live">' +
                '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">' +
                    '<span class="md-live-name"><i class="fas fa-location-crosshairs" style="margin-right:4px;"></i>Next: ' + (lc.name || 'Checkpoint '+(hit+1)) + '</span>' +
                    '<span class="md-live-eta" style="color:' + (lc.is_window_missed?'#d32f2f':lc.is_present?'#5DCAA5':'white') + ';" id="dcMdEtaCount">' + (lc.is_window_missed ? 'WINDOW MISSED' : (etaInit != null ? (Math.floor(etaInit/60)+'m '+etaInit%60+'s') : 'T+ (window)')) + '</span>' +
                '</div>' +
                '<div class="md-live-info">' +
                    '<span><i class="fas fa-layer-group" style="margin-right:3px;"></i>' + (lc.checkpoint_type || 'Checkpoint') + '</span>' +
                    (lc.planned_time ? '<span><i class="fas fa-clock" style="margin-right:3px;"></i>Target: '+lc.planned_time+'</span>' : '') +
                '</div>' +
                (lc.dwell_time_minutes > 0 ? '<div class="md-dwell-box" id="dcDwellBox" data-dwell-remaining="' + dwellRem + '" data-dwell-total="' + dwellTotal + '" data-is-present="' + lc.is_present + '">' +
                    '<div class="md-dwell-head"><span><i class="fas fa-person-walking"></i> Stay Time</span><span id="dcDwellLabel" style="font-weight:800;color:' + (lc.is_present?'#5DCAA5':'rgba(255,255,255,0.5)') + ';">' + dwellLabel + '</span></div>' +
                    '<div class="md-dwell-bar"><div class="md-dwell-fill" id="dcDwellFill" style="width:' + dwellPct + '%;background:' + (lc.is_present?'#5DCAA5':'#6C8EEF') + ';"></div></div>' +
                    '<div class="md-dwell-ticks"><span>0%</span><span id="dcDwellPct">' + dwellPct + '%</span><span>100% (' + lc.dwell_time_minutes + 'm)</span></div>' +
                '</div>' : '') +
            '</div>';
        }

        // ── Alert + TTS block with voice config and sound/vibration controls ──
        let alertBlock = '';
        var alertCfg2 = (live && live.alert_config) || {};
        var routeTTS = allRoutes.find(r => String(r.id) === String(assignment.route_id || assignment.route));
        var ctx = routeTTS || {};
        var hasAlert = alertCfg2.send_start_alert || ctx.send_start_alert;
        var hasTTS = alertCfg2.send_announcement || ctx.send_announcement;
        var readoutText = alertCfg2.readout_text || ctx.readout_text || '';
        var leadMin = alertCfg2.start_alert_lead_time ?? ctx.start_alert_lead_time ?? 15;
        var routeIdForTTS = ctx.id;
        var assignIdForTTS = assignment.id;
        var ttsVoice = ctx.tts_voice || 'en-US';
        var ttsRate = ctx.tts_rate !== undefined && ctx.tts_rate !== null ? ctx.tts_rate : 1.0;
        var ttsPitch = ctx.tts_pitch !== undefined && ctx.tts_pitch !== null ? ctx.tts_pitch : 1.0;
        var voiceOpts = ['en-US','en-GB','en-AU','en-CA','en-IN','fr-FR','de-DE','es-ES','it-IT','pt-BR','ar-SA','ja-JP','ko-KR','zh-CN'];
        if (routeTTS) {
            alertBlock = '<div class="md-tts-box" id="dcTtsBox">' +
                '<div class="md-tts-head"><span class="md-tts-label"><i class="fas fa-bullhorn"></i> Alerts &amp; TTS</span></div>' +
                '<div class="md-tts-badges">' +
                    (hasAlert ? '<span class="md-tts-badge" style="background:rgba(93,202,165,0.1);color:#5DCAA5;"><i class="fas fa-bell"></i> Alert '+leadMin+'m before</span>' : '') +
                    (hasTTS ? '<span class="md-tts-badge" style="background:rgba(108,142,239,0.1);color:#6C8EEF;"><i class="fas fa-volume-high"></i> TTS</span>' : '') +
                    (ttsVoice !== 'en-US' ? '<span class="md-tts-badge" style="background:rgba(239,159,39,0.1);color:#EF9F27;"><i class="fas fa-language"></i> '+ttsVoice+'</span>' : '') +
                '</div>' +
                '<textarea class="md-tts-textarea" id="dcTtsReadout" rows="2" placeholder="TTS announcement text…">'+readoutText.replace(/"/g,'&quot;')+'</textarea>' +
                // TTS voice config row
                '<div class="md-tts-voice-row">' +
                    '<div class="md-tts-voice-group">' +
                        '<label class="md-tts-label-sm">Voice</label>' +
                        '<select class="md-tts-select" id="dcTtsVoice">' +
                            voiceOpts.map(function(v) { return '<option value="'+v+'" '+(ttsVoice===v?'selected':'')+'>'+v+'</option>'; }).join('') +
                        '</select>' +
                    '</div>' +
                    '<div class="md-tts-voice-group">' +
                        '<label class="md-tts-label-sm">Rate <span id="dcTtsRateLabel">'+ttsRate.toFixed(1)+'</span></label>' +
                        '<input type="range" class="md-tts-slider" id="dcTtsRate" min="0.5" max="2.0" step="0.1" value="'+ttsRate+'" oninput="var l=$(\'dcTtsRateLabel\');if(l)l.textContent=parseFloat(this.value).toFixed(1)">' +
                    '</div>' +
                    '<div class="md-tts-voice-group">' +
                        '<label class="md-tts-label-sm">Pitch <span id="dcTtsPitchLabel">'+ttsPitch.toFixed(1)+'</span></label>' +
                        '<input type="range" class="md-tts-slider" id="dcTtsPitch" min="0.5" max="2.0" step="0.1" value="'+ttsPitch+'" oninput="var l=$(\'dcTtsPitchLabel\');if(l)l.textContent=parseFloat(this.value).toFixed(1)">' +
                    '</div>' +
                '</div>' +
                // Sound + vibration toggles
                '<div class="md-tts-toggle-row">' +
                    '<label class="md-tts-toggle"><input type="checkbox" id="dcTtsPlaySound" checked> <i class="fas fa-volume-up"></i> Sound</label>' +
                    '<label class="md-tts-toggle"><input type="checkbox" id="dcTtsVibrate" checked> <i class="fas fa-mobile-alt"></i> Vibrate</label>' +
                    '<span style="font-size:0.5rem;color:rgba(255,255,255,0.3);flex:1;text-align:right;">Fallback when no TTS</span>' +
                '</div>' +
                '<div class="md-tts-actions">' +
                    '<button type="button" class="dc-card-btn" style="font-size:0.5rem;padding:4px 10px;" onclick="dcResendTTS(' + assignIdForTTS + ')"><i class="fas fa-volume-high"></i> Send TTS</button>' +
                    '<button type="button" class="dc-card-btn" style="font-size:0.5rem;padding:4px 10px;" onclick="dcSaveTtsReadout(' + routeIdForTTS + ',' + assignIdForTTS + ')"><i class="fas fa-floppy-disk"></i> Save</button>' +
                '</div>' +
            '</div>';
        }

        // ── Count hit/missed/pending ──
        let hitCount = 0, missCount = 0, pendingCount = 0;

        // ── Manifest (checkpoint timeline) ──
        let manifestHtml = '';
        if (total > 0) {
            const route = allRoutes.find(r => String(r.id) === String(assignment.route_id || assignment.route));
            let cps = (route && route.checkpoints) ? route.checkpoints : [];
            if (!cps.length && assignment.checkpoints) {
                cps = assignment.checkpoints;
            }
            const datePart = (assignment.scheduled_date || assignment.assigned_at || new Date().toISOString()).split(/[T ]/)[0];
            const now = new Date();
            const missionDate = new Date(datePart);
            const todayOnly = new Date(now.toISOString().split('T')[0]);
            const isPastDay = missionDate < todayOnly;
            for (let i = 0; i < total; i++) {
                var cp = cps[i] || { name: 'Point '+(i+1) };
                var state = 'pending';
                var timeRemaining = null;
                if (i < hit) state = 'hit';
                else if (isPastDay) state = 'miss';
                else if (isActive && cp.planned_time) {
                    try {
                        var pt = new Date(datePart+'T'+cp.planned_time);
                        var tol = (cp.time_tolerance||15)*60000;
                        var dwellMs = (cp.dwell_time || 0)*60000;
                        if (!isNaN(pt.getTime())) {
                            var diff = pt.getTime() - now.getTime();
                            timeRemaining = diff;
                            if (now.getTime() > pt.getTime() + tol + dwellMs) state = 'miss';
                        }
                    } catch(e) {}
                }
                if (state === 'pending' && i === hit && isActive) state = 'next';
                if (state === 'hit') hitCount++;
                else if (state === 'miss') missCount++;
                else pendingCount++;
                var sColor = state === 'hit' ? '#5DCAA5' : state === 'miss' ? '#d32f2f' : state === 'next' ? '#EF9F27' : '#6C8EEF';
                var sLabel = state === 'hit' ? 'Success' : state === 'miss' ? 'Failed' : state === 'next' ? 'NOW' : 'Pending';
                var radVal = cp.radius || 0;
                var dwellVal = cp.dwell_time || 0;
                var tolVal = cp.time_tolerance || 15;
                var isEditable = !isActive && !isCompleted && !isPastDay;
                var cpTtsText = cp.next_announcement_text || '';
                var cpTtsDisabled = isEditable ? '' : 'disabled';
                var cpTtsPlaceholder = isEditable ? 'TTS message for this checkpoint…' : 'TTS unavailable (mission active/past)';
                /* Pill labels */
                var radLabel = radVal ? radVal+'m' : '—';
                var dwellLabel = dwellVal ? dwellVal+'m' : '—';
                var tolLabel = tolVal ? tolVal+'m' : '—';
                var radOn = radVal > 0 ? 'on' : '';
                var dwellOn = dwellVal > 0 ? 'on' : '';
                var tolOn = tolVal > 0 ? 'on' : '';
                var cpId = cp.id || null;
                manifestHtml +=
                    '<div class="md-cp-row' + (state === 'miss' ? ' is-miss' : state === 'next' ? ' is-next' : state === 'hit' ? ' is-done' : '') + '" data-cp-id="' + (cpId || '') + '">' +
                        '<div class="md-cp-main">' +
                            '<span class="dc-row-status" style="background:' + sColor + ';width:' + (state==='next'?'10px':'8px') + ';height:' + (state==='next'?'10px':'8px') + (state==='next' ? ';animation:dcPulse 1.5s ease-in-out infinite' : '') + ';flex-shrink:0;"></span>' +
                            '<div class="md-cp-name-sec">' +
                                '<span class="md-cp-name">' + cp.name + '</span>' +
                                '<span class="md-cp-num">#' + (i+1) + '</span>' +
                                (cp.planned_time ? '<span class="md-cp-time"><i class="fas fa-clock"></i>' + cp.planned_time + '</span>' : '') +
                            '</div>' +
                            '<span class="md-cp-status" style="color:' + sColor + ';">' + sLabel + '</span>' +
                            '<button type="button" class="md-cp-toggle" id="mdCpToggle_' + i + '" onclick="mdToggleCpConfig(' + i + ')" title="Edit checkpoint properties" ' + (isEditable ? '' : 'disabled') + '><i class="fas fa-sliders"></i></button>' +
                        '</div>' +
                        '<div class="md-cp-enf-wrap" id="mdCpSum_' + i + '">' +
                            mdCpEnfCard('bullseye','#d32f2f','Radius','Perimeter','rad',radVal,0,500,5,i) +
                            mdCpEnfCard('person-walking','#EF9F27','Dwell','Min stay','dwell',dwellVal,0,60,1,i) +
                            mdCpEnfCard('hourglass-start','#6C8EEF','Tolerance','Grace','tol',tolVal,0,60,1,i) +
                        '</div>' +
                        /* TTS row */
                        '<div class="md-cp-tts-wrap">' +
                            '<input class="md-cp-tts-input" type="text" id="dcCpAnnounce_' + i + '" value="' + cpTtsText.replace(/"/g,'&quot;') + '" placeholder="' + cpTtsPlaceholder + '" ' + cpTtsDisabled + ' data-cp-idx="' + i + '" data-cp-name="' + cp.name.replace(/"/g,'&quot;') + '">' +
                            '<button type="button" class="md-cp-tts-btn" onclick="dcCpResendTts(' + assignment.id + ',' + i + ')" title="Resend TTS for this checkpoint"><i class="fas fa-volume-high"></i> TTS</button>' +
                        '</div>' +
                        /* Collapsible config panel with view/edit mode */
                        '<div class="md-cp-config" id="mdCpConfig_' + i + '" data-mode="view" data-planned="' + (cp.planned_time || '') + '" data-tol="' + tolVal + '">' +
                            /* Enforcement cards now shown in summary above; config panel has only slider controls */
                            '<div class="md-cp-enf-grid" id="mdCpEnfGrid_' + i + '" data-nodup="1">' +
                                mdCpSliderOnly('bullseye','#d32f2f','Radius','rad',radVal,0,500,5,i) +
                                mdCpSliderOnly('person-walking','#EF9F27','Dwell','dwell',dwellVal,0,60,1,i) +
                                mdCpSliderOnly('hourglass-start','#6C8EEF','Tolerance','tol',tolVal,0,60,1,i) +
                            '</div>' +
                            /* Tolerance timeline (view mode only) */
                            '<div class="md-cp-tol-bar-wrap" id="mdCpTolBar_' + i + '">' +
                                '<div class="md-cp-tol-track">' +
                                    '<div class="md-cp-tol-fill" id="mdCpTolFill_' + i + '" style="width:50%;"></div>' +
                                    '<div class="md-cp-tol-cursor" id="mdCpTolCursor_' + i + '" style="left:50%;"></div>' +
                                '</div>' +
                                '<div class="md-cp-tol-labels" id="mdCpTolLbl_' + i + '">' +
                                    '<span class="md-cp-tol-label">Open</span>' +
                                    '<span class="md-cp-tol-label mid">0</span>' +
                                    '<span class="md-cp-tol-label">Close</span>' +
                                '</div>' +
                            '</div>' +
                            '<div class="md-cp-config-actions" id="mdCpActions_' + i + '">' +
                                '<div class="md-cp-view-actions" id="mdCpViewActs_' + i + '" style="display:flex;gap:4px;">' +
                                    '<button type="button" class="md-cp-config-btn" onclick="mdToggleCpEditMode(' + i + ')" style="flex:1;"><i class="fas fa-pen"></i> Edit Values</button>' +
                                    '<button type="button" class="md-cp-config-btn secondary" onclick="mdCpConfigClose(' + i + ')" style="flex:1;"><i class="fas fa-times"></i> Close</button>' +
                                '</div>' +
                                '<div class="md-cp-edit-actions" id="mdCpEditActs_' + i + '" style="display:none;gap:4px;">' +
                                    '<button type="button" class="md-cp-config-btn secondary" onclick="mdCpConfigCancel(' + i + ')" style="flex:1;"><i class="fas fa-times"></i> Cancel</button>' +
                                    '<button type="button" class="md-cp-config-btn primary" onclick="mdCpConfigSave(' + i + ',' + (cpId || 'null') + ',' + routeIdForTTS + ')" style="flex:1;"><i class="fas fa-check"></i> Apply</button>' +
                                '</div>' +
                            '</div>' +
                        '</div>' +
                    '</div>';
            }
        }

        // ── Summary bar ──
        var sumEl = $('dcMdSummary');
        if (sumEl && total > 0) {
            sumEl.innerHTML = '<span class="md-summary-pill hit"><i class="fas fa-check-circle"></i> ' + hitCount + ' Hit</span>' +
                '<span class="md-summary-pill miss"><i class="fas fa-times-circle"></i> ' + missCount + ' Missed</span>' +
                '<span class="md-summary-pill pending"><i class="fas fa-clock"></i> ' + pendingCount + ' Pending</span>';
        }
        var summaryBar = '';

        // ── Actions ──
        var actionsHtml = '';
        if (isActive || isCompleted) {
            actionsHtml = '<button type="button" class="dc-card-btn redeploy" onclick="dcStartRedeploy(' + assignment.id + ');dcCloseMissionDetail()">' +
                '<i class="fas fa-redo"></i> Redeploy</button>';
            if (isActive) {
                actionsHtml += '<button type="button" class="dc-card-btn danger" onclick="dcTerminate(' + assignment.id + ')">' +
                    '<i class="fas fa-stop"></i> End Mission</button>';
            }
        } else {
            actionsHtml = '<button type="button" class="dc-card-btn redeploy" onclick="dcStartRedeploy(' + assignment.id + ');dcCloseMissionDetail()">' +
                '<i class="fas fa-play"></i> Deploy Now</button>' +
                '<button type="button" class="dc-card-btn danger" onclick="dcTerminate(' + assignment.id + ')">' +
                '<i class="fas fa-times"></i> Cancel</button>';
        }
        actionsHtml += '<button type="button" class="dc-card-btn" style="background:rgba(255,255,255,0.04);border:1px solid var(--border);" onclick="dcCloseMissionDetail()">' +
            '<i class="fas fa-times"></i> Close</button>';

        // ── Assemble ──
        $('dcMdManifest').innerHTML = (summaryBar || '') + (liveBlock || '') + (alertBlock || '') + (manifestHtml || '<div style="font-size:0.68rem;color:rgba(255,255,255,0.3);margin-top:6px;">No checkpoint data</div>');
        $('dcMdActions').innerHTML = actionsHtml;
        $('dcCenterTitle').innerHTML = '<i class="fas fa-satellite-dish" style="color:var(--primary);margin-right:6px;"></i>Progress';

        // ── Start live countdowns via MissionDetailComponent ──
        if (window.MissionDetailComponent) {
        if (isActive && live && live.next_checkpoint) {
                var lc2 = live.next_checkpoint;
                if (lc2.time_remaining_seconds != null && !lc2.is_window_missed) {
                    MissionDetailComponent.startEtaCountdown(lc2.time_remaining_seconds, 'dcMdEtaCount');
                }
                var dwellBox = $('dcDwellBox');
                if (dwellBox && dwellBox.dataset.isPresent === 'true') {
                    var dwellRem2 = Number(dwellBox.dataset.dwellRemaining);
                    var dwellTotal2 = Number(dwellBox.dataset.dwellTotal);
                    MissionDetailComponent.startDwellCountdown(dwellRem2, dwellTotal2, true, 'dcDwellLabel', 'dcDwellFill', 'dcDwellPct');
                }
            }
        }
    };

    window.dcResendTTS = async function(assignmentId) {
        var textarea = $('dcTtsReadout');
        var msg = textarea ? textarea.value.trim() : '';
        try {
            var body = { assignment_id: assignmentId };
            if (msg) body.message = msg;
            // Voice config from form
            var voiceEl = $('dcTtsVoice');
            var rateEl = $('dcTtsRate');
            var pitchEl = $('dcTtsPitch');
            var soundEl = $('dcTtsPlaySound');
            var vibrateEl = $('dcTtsVibrate');
            if (voiceEl) body.tts_voice = voiceEl.value;
            if (rateEl) body.tts_rate = parseFloat(rateEl.value) || 1.0;
            if (pitchEl) body.tts_pitch = parseFloat(pitchEl.value) || 1.0;
            if (soundEl) body.play_sound = soundEl.checked;
            if (vibrateEl) body.vibrate = vibrateEl.checked;
            const res = await api('/api/resend-tts/', { method: 'POST', body: JSON.stringify(body) });
            if (res.ok) {
                var data = await res.json();
                toast('TTS sent: ' + (data.message || 'OK'));
                dcLog('TTS sent for assignment ' + assignmentId, 'info');
            } else {
                toast('TTS send failed', true);
            }
        } catch(e) { toast('TTS error', true); }
    };

    window.dcCpResendTts = function(assignId, cpIdx) {
        var input = $('dcCpAnnounce_' + cpIdx);
        if (!input) return;
        var msg = input.value.trim();
        var cpName = input.dataset.cpName || 'Checkpoint ' + (cpIdx + 1);
        var isDisabled = input.disabled;
        if (isDisabled) {
            toast('Per-checkpoint TTS is only available before the mission starts', true);
            return;
        }
        // Show confirmation overlay
        var confirmEl = $('dcTtsConfirm');
        var bodyEl = $('dcTtsConfirmBody');
        var btnEl = $('dcTtsConfirmBtn');
        if (!confirmEl || !btnEl) return;
        bodyEl.innerHTML = 'Send TTS announcement for <strong>' + cpName + '</strong>?<br><span style="font-size:0.58rem;color:rgba(255,255,255,0.4);">Message: "' + msg.replace(/"/g,'&quot;') + '"</span>';
        btnEl.onclick = function() {
            confirmEl.style.display = 'none';
            dcSendCpTts(assignId, cpIdx, msg);
        };
        confirmEl.style.display = 'flex';
    };

    window.dcSendCpTts = async function(assignId, cpIdx, message) {
        try {
            var voiceEl = $('dcTtsVoice');
            var rateEl = $('dcTtsRate');
            var pitchEl = $('dcTtsPitch');
            var soundEl = $('dcTtsPlaySound');
            var vibrateEl = $('dcTtsVibrate');
            var body = { assignment_id: assignId, message: message || 'Checkpoint announcement' };
            if (voiceEl) body.tts_voice = voiceEl.value;
            if (rateEl) body.tts_rate = parseFloat(rateEl.value) || 1.0;
            if (pitchEl) body.tts_pitch = parseFloat(pitchEl.value) || 1.0;
            if (soundEl) body.play_sound = soundEl.checked;
            if (vibrateEl) body.vibrate = vibrateEl.checked;
            var res = await api('/api/resend-tts/', {
                method: 'POST',
                body: JSON.stringify(body)
            });
            if (res.ok) {
                var data = await res.json();
                toast('TTS sent: ' + (data.message || 'OK'));
                dcLog('Per-checkpoint TTS sent for cp ' + cpIdx + ' of assignment ' + assignId, 'info');
            } else {
                toast('TTS send failed', true);
            }
        } catch(e) { toast('TTS error', true); }
    };

    /* ── Checkpoint config panel helpers ── */
    window.mdCpEnfCard = function(icon, color, label, desc, field, val, min, max, step, idx) {
        var presets = [];
        if (field === 'rad') presets = [0,25,50,100,250];
        else if (field === 'dwell') presets = [0,5,10,30,60];
        else presets = [0,5,15,30,60];
        var html = '<div class="md-cp-enf-card">' +
            '<div class="md-cp-enf-head">' +
                '<div class="md-cp-enf-icon" style="background:rgba(' + (field==='rad'?'226,61,61':field==='dwell'?'239,159,39':'108,142,239') + ',0.12);color:' + color + ';"><i class="fas fa-' + icon + '"></i></div>' +
                '<div class="md-cp-enf-info"><div class="md-cp-enf-lbl">' + label + '</div><div class="md-cp-enf-desc">' + desc + '</div></div>' +
                '<div class="md-cp-enf-val" id="mdCpVal_' + field + '_' + idx + '">' + val + '<small>' + (field==='rad'?'m':'min') + '</small></div>' +
            '</div>' +
            '<input type="range" class="md-cp-enf-slider" id="mdCpSlider_' + field + '_' + idx + '" min="' + min + '" max="' + max + '" step="' + step + '" value="' + val + '" oninput="mdCpSyncSlider(\'' + field + '\',' + idx + ')">' +
            '<div class="md-cp-enf-presets">';
        presets.forEach(function(p) {
            html += '<div class="md-cp-enf-preset' + (p === val ? ' active' : '') + '" data-v="' + p + '" onclick="mdCpSetPreset(\'' + field + '\',' + idx + ',' + p + ')">' + p + '</div>';
        });
        html += '</div></div>';
        return html;
    };

    /* Standalone slider for config panel (no card wrapper — avoids duplicate IDs with summary enforcement cards) */
    window.mdCpSliderOnly = function(icon, color, label, field, val, min, max, step, idx) {
        var presets = [];
        if (field === 'rad') presets = [0,25,50,100,250];
        else if (field === 'dwell') presets = [0,5,10,30,60];
        else presets = [0,5,15,30,60];
        var html = '<div class="md-cp-slider-only">' +
            '<div class="md-cp-sl-only-head">' +
                '<span class="md-cp-sl-only-lbl">' +
                    '<i class="fas fa-' + icon + '" style="color:' + color + ';width:16px;text-align:center;"></i> ' + label +
                '</span>' +
                '<span class="md-cp-sl-only-val" id="mdCpSlOnly_' + field + '_' + idx + '">' + val + '<small>' + (field==='rad'?'m':'min') + '</small></span>' +
            '</div>' +
            '<input type="range" class="md-cp-enf-slider" id="mdCpSlider_' + field + '_' + idx + '" min="' + min + '" max="' + max + '" step="' + step + '" value="' + val + '" oninput="mdCpSyncSlider(\'' + field + '\',' + idx + ')">' +
            '<div class="md-cp-enf-presets">';
        presets.forEach(function(p) {
            html += '<div class="md-cp-enf-preset' + (p === val ? ' active' : '') + '" data-v="' + p + '" onclick="mdCpSetPreset(\'' + field + '\',' + idx + ',' + p + ')">' + p + '</div>';
        });
        html += '</div></div>';
        return html;
    };

    window.mdCpSyncSlider = function(field, idx) {
        var slider = $('mdCpSlider_' + field + '_' + idx);
        var valEl = $('mdCpVal_' + field + '_' + idx);
        var slOnlyEl = $('mdCpSlOnly_' + field + '_' + idx);
        if (slider) {
            var v = Number(slider.value);
            var html = v + '<small>' + (field==='rad'?'m':'min') + '</small>';
            if (valEl) valEl.innerHTML = html;
            if (slOnlyEl) slOnlyEl.innerHTML = html;
        }
    };

    window.mdCpSetPreset = function(field, idx, val) {
        var slider = $('mdCpSlider_' + field + '_' + idx);
        if (slider) { slider.value = val; mdCpSyncSlider(field, idx); }
    };

    window.mdToggleCpConfig = function(idx) {
        var cfg = $('mdCpConfig_' + idx);
        var btn = $('mdCpToggle_' + idx);
        if (!cfg) return;
        var isOpen = cfg.classList.contains('open');
        if (isOpen) {
            mdCpStopLiveTimer(idx);
            cfg.classList.remove('open');
            if (btn) btn.classList.remove('open');
        } else {
            /* Open in view mode */
            cfg.dataset.mode = 'view';
            /* Store originals */
            __mdCpOrig[idx] = {
                rad: Number(($('mdCpSlider_rad_' + idx) || {}).value || 0),
                dwell: Number(($('mdCpSlider_dwell_' + idx) || {}).value || 0),
                tol: Number(($('mdCpSlider_tol_' + idx) || {}).value || 0)
            };
            cfg.classList.add('open');
            if (btn) btn.classList.add('open');
            mdCpStartLiveTimer(idx);
        }
    };

    window.mdToggleCpEditMode = function(idx) {
        var cfg = $('mdCpConfig_' + idx);
        if (!cfg) return;
        mdCpStopLiveTimer(idx);
        /* Restore value display from sliders (overwritten by live timer) */
        ['rad','dwell','tol'].forEach(function(f) {
            mdCpSyncSlider(f, idx);
        });
        /* Store originals */
        var curRad = Number(($('mdCpSlider_rad_' + idx) || {}).value || 0);
        var curDwell = Number(($('mdCpSlider_dwell_' + idx) || {}).value || 0);
        var curTol = Number(($('mdCpSlider_tol_' + idx) || {}).value || 0);
        __mdCpOrig[idx] = { rad: curRad, dwell: curDwell, tol: curTol };
        cfg.dataset.mode = 'edit';
    };

    window.mdCpConfigClose = function(idx) {
        var cfg = $('mdCpConfig_' + idx);
        var btn = $('mdCpToggle_' + idx);
        mdCpStopLiveTimer(idx);
        if (cfg) cfg.classList.remove('open');
        if (btn) btn.classList.remove('open');
    };

    window.mdCpConfigCancel = function(idx) {
        var cfg = $('mdCpConfig_' + idx);
        if (!cfg) return;
        /* Restore originals first */
        var orig = __mdCpOrig[idx];
        if (orig) {
            ['rad','dwell','tol'].forEach(function(f) {
                var slider = $('mdCpSlider_' + f + '_' + idx);
                if (slider) { slider.value = orig[f]; mdCpSyncSlider(f, idx); }
            });
        }
        /* Switch back to view mode */
        cfg.dataset.mode = 'view';
        mdCpStartLiveTimer(idx);
    };

    /* ── Live monitoring timers ─────────────────────────── */
    window.__mdCpLiveTimers = {};

    window.mdCpLiveUpdate = function(idx) {
        var cfg = $('mdCpConfig_' + idx);
        if (!cfg || cfg.dataset.mode !== 'view') return;
        var assignment = window.__dcSelectedMission;
        if (!assignment) return;
        var ldd = window.__dc_live_next_by_assignment;
        var live = (ldd && ldd[assignment.id]) || null;
        var hitIdx = assignment.completed_checkpoints || 0;
        var isCurrent = (idx === hitIdx);

        var radVal = $('mdCpVal_rad_' + idx);
        var dwellVal = $('mdCpVal_dwell_' + idx);
        var tolValEl = $('mdCpVal_tol_' + idx);
        var tolFill = $('mdCpTolFill_' + idx);
        var tolCursor = $('mdCpTolCursor_' + idx);
        var tolLbl = $('mdCpTolLbl_' + idx);

        if (!isCurrent || !live || !live.next_checkpoint) {
            if (radVal) radVal.innerHTML = '<span class="md-lv-dim">N/A</span>';
            if (dwellVal) dwellVal.innerHTML = '<span class="md-lv-dim">—</span>';
            if (tolValEl) tolValEl.innerHTML = '<span class="md-lv-dim">—</span>';
            return;
        }

        var lc = live.next_checkpoint;

        /* ── Radius ── */
        if (radVal) {
            radVal.innerHTML = lc.is_present
                ? '<span class="md-lv-on">● Within</span>'
                : '<span class="md-lv-off">○ Outside</span>';
        }

        /* ── Dwell countdown ── */
        var dwellMinutes = lc.dwell_time_minutes || 0;
        var dwellRem = (lc.dwell_remaining_seconds != null) ? Math.max(0, Number(lc.dwell_remaining_seconds)) : null;
        if (lc.is_present && dwellMinutes > 0 && dwellRem != null && dwellRem > 0) {
            var min = Math.floor(dwellRem/60);
            var sec = dwellRem % 60;
            if (dwellVal) dwellVal.innerHTML = '<span class="md-lv-count">' + min + 'm ' + (sec<10?'0':'') + sec + 's</span>';
        } else if (lc.is_present && dwellMinutes > 0 && dwellRem != null && dwellRem <= 0) {
            if (dwellVal) dwellVal.innerHTML = '<span class="md-lv-ok">✓ Done</span>';
        } else if (dwellMinutes > 0 && !lc.is_present) {
            if (dwellVal) dwellVal.innerHTML = '<span class="md-lv-dim">Awaiting</span>';
        } else {
            if (dwellVal) dwellVal.innerHTML = '<span class="md-lv-dim">N/A</span>';
        }

        /* ── Tolerance countdown ── */
        var planned = cfg.dataset.planned;
        var tolMins = Number(cfg.dataset.tol) || 15;
        var datePart = (assignment.scheduled_date || assignment.assigned_at || new Date().toISOString()).split(/[T ]/)[0];
        var tolSecs = tolMins * 60;
        var halfTol = Math.floor(tolSecs / 2);

        if (lc.time_remaining_seconds != null) {
            var timeRem = Number(lc.time_remaining_seconds);
            var absSec = Math.abs(timeRem);
            var sign = timeRem >= 0 ? '+' : '−';
            var h = Math.floor(absSec/3600);
            var m = Math.floor((absSec%3600)/60);
            var s = absSec % 60;
            var timeStr = (h > 0 ? h + 'h ' : '') + m + 'm ' + (s<10?'0':'') + s + 's';
            var fullStr = sign + timeStr;
            var isMissed = lc.is_window_missed || false;

            if (isMissed || timeRem < -halfTol) {
                if (tolValEl) tolValEl.innerHTML = '<span class="md-lv-miss">' + fullStr + ' · CLOSED</span>';
            } else if (timeRem <= 0) {
                if (tolValEl) tolValEl.innerHTML = '<span class="md-lv-warn">' + fullStr + ' · Window open</span>';
            } else {
                if (tolValEl) tolValEl.innerHTML = '<span class="md-lv-ok">' + fullStr + ' · On track</span>';
            }

            /* Timeline bar */
            if (tolFill && tolCursor) {
                var pct = 50;
                if (timeRem > halfTol) pct = 100;
                else if (timeRem < -halfTol) pct = 0;
                else pct = 50 + (timeRem / halfTol) * 50;
                pct = Math.max(0, Math.min(100, pct));
                tolFill.style.width = pct + '%';
                tolFill.className = 'md-cp-tol-fill' + (timeRem <= 0 ? ' past' : '');
                tolCursor.style.left = pct + '%';
            }
            if (tolLbl && planned) {
                var pt = new Date(datePart + 'T' + planned);
                var openDt = new Date(pt.getTime() - halfTol * 1000);
                var closeDt = new Date(pt.getTime() + halfTol * 1000);
                tolLbl.innerHTML = '<span class="md-cp-tol-label">' + ('0'+openDt.getHours()).slice(-2)+':'+('0'+openDt.getMinutes()).slice(-2) + '</span><span class="md-cp-tol-label mid">' + planned.substring(0,5) + '</span><span class="md-cp-tol-label">' + ('0'+closeDt.getHours()).slice(-2)+':'+('0'+closeDt.getMinutes()).slice(-2) + '</span>';
            }
        } else if (planned) {
            /* Fallback: compute from planned_time */
            var pt = new Date(datePart + 'T' + planned);
            var nowMs = Date.now();
            var diffSec = (pt.getTime() - nowMs) / 1000;
            if (!isNaN(diffSec)) {
                var absSec2 = Math.abs(diffSec);
                var sign2 = diffSec >= 0 ? '+' : '−';
                var h2 = Math.floor(absSec2/3600);
                var m2 = Math.floor((absSec2%3600)/60);
                var s2 = absSec2 % 60;
                var ts2 = (h2 > 0 ? h2 + 'h ' : '') + m2 + 'm ' + (s2<10?'0':'') + s2 + 's';
                var full2 = sign2 + ts2;
                if (diffSec > halfTol) {
                    if (tolValEl) tolValEl.innerHTML = '<span class="md-lv-ok">' + full2 + ' · On track</span>';
                } else if (diffSec >= 0) {
                    if (tolValEl) tolValEl.innerHTML = '<span class="md-lv-ok">' + full2 + ' · Approaching</span>';
                } else if (diffSec > -halfTol) {
                    if (tolValEl) tolValEl.innerHTML = '<span class="md-lv-warn">' + full2 + ' · Window open</span>';
                } else {
                    if (tolValEl) tolValEl.innerHTML = '<span class="md-lv-miss">' + full2 + ' · CLOSED</span>';
                }
                if (tolFill && tolCursor) {
                    var pct2 = 50 + (diffSec / halfTol) * 50;
                    pct2 = Math.max(0, Math.min(100, pct2));
                    tolFill.style.width = pct2 + '%';
                    tolFill.className = 'md-cp-tol-fill' + (diffSec <= 0 ? ' past' : '');
                    tolCursor.style.left = pct2 + '%';
                }
                if (tolLbl) {
                    var openDt2 = new Date(pt.getTime() - halfTol * 1000);
                    var closeDt2 = new Date(pt.getTime() + halfTol * 1000);
                    tolLbl.innerHTML = '<span class="md-cp-tol-label">' + ('0'+openDt2.getHours()).slice(-2)+':'+('0'+openDt2.getMinutes()).slice(-2) + '</span><span class="md-cp-tol-label mid">' + planned.substring(0,5) + '</span><span class="md-cp-tol-label">' + ('0'+closeDt2.getHours()).slice(-2)+':'+('0'+closeDt2.getMinutes()).slice(-2) + '</span>';
                }
            }
        }
    };

    window.mdCpStartLiveTimer = function(idx) {
        mdCpStopLiveTimer(idx);
        mdCpLiveUpdate(idx);
        __mdCpLiveTimers[idx] = setInterval(function() { mdCpLiveUpdate(idx); }, 1000);
    };

    window.mdCpStopLiveTimer = function(idx) {
        if (__mdCpLiveTimers[idx]) {
            clearInterval(__mdCpLiveTimers[idx]);
            delete __mdCpLiveTimers[idx];
        }
    };

    window.mdCpStopAllLiveTimers = function() {
        for (var k in __mdCpLiveTimers) mdCpStopLiveTimer(Number(k));
    };

    window.mdCpConfigSave = function(idx, cpId, routeId) {
        var cfg = $('mdCpConfig_' + idx);
        if (!cfg) return;
        var newRad = Number(($('mdCpSlider_rad_' + idx) || {}).value || 0);
        var newDwell = Number(($('mdCpSlider_dwell_' + idx) || {}).value || 0);
        var newTol = Number(($('mdCpSlider_tol_' + idx) || {}).value || 0);
        var orig = __mdCpOrig[idx] || {};
        if (newRad === orig.rad && newDwell === orig.dwell && newTol === orig.tol) {
            toast('No changes made');
            cfg.dataset.mode = 'view';
            var btn2 = $('mdCpToggle_' + idx);
            if (btn2) btn2.classList.add('open');
            mdCpStartLiveTimer(idx);
            return;
        }
        /* Build diff HTML */
        var diffHtml = '';
        if (newRad !== orig.rad) diffHtml += '<div style="display:flex;justify-content:space-between;padding:2px 0;"><span>Radius</span><span><span style="color:rgba(255,255,255,0.3);text-decoration:line-through;">' + orig.rad + 'm</span> → <span style="color:#5DCAA5;font-weight:800;">' + newRad + 'm</span></span></div>';
        if (newDwell !== orig.dwell) diffHtml += '<div style="display:flex;justify-content:space-between;padding:2px 0;"><span>Dwell</span><span><span style="color:rgba(255,255,255,0.3);text-decoration:line-through;">' + orig.dwell + 'min</span> → <span style="color:#5DCAA5;font-weight:800;">' + newDwell + 'min</span></span></div>';
        if (newTol !== orig.tol) diffHtml += '<div style="display:flex;justify-content:space-between;padding:2px 0;"><span>Tolerance</span><span><span style="color:rgba(255,255,255,0.3);text-decoration:line-through;">' + orig.tol + 'min</span> → <span style="color:#5DCAA5;font-weight:800;">' + newTol + 'min</span></span></div>';
        if (!diffHtml) { toast('No changes made'); cfg.classList.remove('open'); return; }

        var confirmEl = $('dcCpEditConfirm');
        var bodyEl = $('dcCpEditBody');
        var diffEl = $('dcCpEditDiff');
        var btnEl = $('dcCpEditConfirmBtn');
        if (!confirmEl || !btnEl) return;
        bodyEl.innerHTML = 'Review changes for <strong>Checkpoint #' + (idx + 1) + '</strong>:';
        diffEl.innerHTML = diffHtml;
        btnEl.onclick = function() {
            confirmEl.style.display = 'none';
            dcApplyCpConfig(idx, cpId, routeId, newRad, newDwell, newTol);
        };
        confirmEl.style.display = 'flex';
    };

    window.dcApplyCpConfig = async function(idx, cpId, routeId, rad, dwell, tol) {
        try {
            if (!cpId) { toast('Checkpoint ID missing, cannot save', true); return; }
            var res = await api('/api/checkpoints/' + cpId + '/', {
                method: 'PATCH',
                body: JSON.stringify({
                    radius: rad,
                    dwell_time: dwell,
                    time_tolerance: tol
                })
            });
            if (res.ok) {
                toast('Checkpoint updated');
                dcLog('Checkpoint #' + idx + ' updated on route ' + routeId, 'info');
                /* Switch back to view mode */
                var cfg = $('mdCpConfig_' + idx);
                if (cfg) cfg.dataset.mode = 'view';
                /* Keep gear open to show view mode */
                /* Refresh display */
                var sum = $('mdCpSum_' + idx);
                if (sum) {
                    sum.innerHTML =
                        '<span class="md-cp-pill ' + (rad > 0 ? 'on' : '') + '"><i class="fas fa-bullseye"></i> ' + (rad ? rad+'m' : '—') + '</span>' +
                        '<span class="md-cp-pill ' + (dwell > 0 ? 'on' : '') + '"><i class="fas fa-person-walking"></i> ' + (dwell ? dwell+'m' : '—') + '</span>' +
                        '<span class="md-cp-pill ' + (tol > 0 ? 'on' : '') + '"><i class="fas fa-hourglass-start"></i> ' + (tol ? tol+'m' : '—') + '</span>';
                }
                __mdCpOrig[idx] = { rad: rad, dwell: dwell, tol: tol };
                mdCpStartLiveTimer(idx);
                dcLog('Checkpoint display updated', 'info');
            } else {
                var errData = await res.json().catch(function() { return {}; });
                toast('Update failed: ' + (Object.values(errData)[0] || res.statusText), true);
            }
        } catch(e) { toast('Update error', true); dcLog('Cp config save error: ' + e.message, 'error'); }
    };

    window.dcSaveTtsReadout = async function(routeId, assignId) {
        var textarea = $('dcTtsReadout');
        if (!textarea) return;
        var msg = textarea.value.trim();
        var voiceEl = $('dcTtsVoice');
        var rateEl = $('dcTtsRate');
        var pitchEl = $('dcTtsPitch');
        try {
            var patchBody = { readout_text: msg };
            if (voiceEl) patchBody.tts_voice = voiceEl.value;
            if (rateEl) patchBody.tts_rate = parseFloat(rateEl.value) || 1.0;
            if (pitchEl) patchBody.tts_pitch = parseFloat(pitchEl.value) || 1.0;
            var res = await api('/api/routes/' + routeId + '/', {
                method: 'PATCH',
                body: JSON.stringify(patchBody)
            });
            if (res.ok) {
                toast('Readout & voice saved');
                dcLog('Readout + voice saved for route ' + routeId, 'info');
                dcResendTTS(assignId);
            } else {
                toast('Save failed', true);
            }
        } catch(e) { toast('Save error', true); }
    };

    window.dcCloseMissionDetail = function() {
        if (window.MissionDetailComponent) MissionDetailComponent.stopAll();
        mdCpStopAllLiveTimers();
        document.querySelectorAll('.dc-ls-card.selected').forEach(el => el.classList.remove('selected'));
        __dcSelectedMission = null;
        const el = $('dcMissionDetail');
        const grid = $('dcLsGrid');
        const tabs = $('dcLsTabs');
        const stats = $('dcLsStats');
        el.classList.add('dc-hidden');
        // If coming from day view, go back to day view
        if (window.__dcInDayView) {
            const dv = $('dcDayView');
            if (dv) {
                dv.classList.remove('dc-hidden');
                const label = ($('dcDvTitle') || {}).textContent;
                if (label) $('dcCenterTitle').innerHTML = '<i class="fas fa-calendar-day" style="color:var(--primary);margin-right:6px;"></i>' + label;
                return;
            }
        }
        // If coming from blueprint progress view, go back to it
        if (window.__dcInBpView && window.__dcActiveBpId) {
            const pv = $('dcBpProgressView');
            if (pv) {
                pv.classList.remove('dc-hidden');
                const route = allRoutes.find(r => String(r.id) === String(window.__dcActiveBpId));
                if (route) $('dcCenterTitle').innerHTML = '<i class="fas fa-map" style="color:var(--primary);margin-right:6px;"></i>' + route.name;
                return;
            }
        }
        grid.classList.remove('dc-hidden');
        if (tabs) tabs.classList.remove('dc-hidden');
        if (stats) stats.classList.remove('dc-hidden');
        $('dcCenterTitle').innerHTML = '<i class="fas fa-satellite-dish" style="color:var(--primary);margin-right:6px;"></i>Missions';
    };

    /* ── Day View ──────────────────────────────────── */
    window.dcShowDayView = function(dateStr) {
        var panel = $('dcDayPanel');
        var title = $('dcDayPanelTitle');
        var count = $('dcDayPanelCount');
        var list = $('dcDayPanelList');
        if (!panel || !list) return;

        var dt = new Date(dateStr + 'T12:00:00');
        var label = dt.toLocaleDateString('en-US', { weekday:'short', month:'short', day:'numeric', year:'numeric' });
        if (title) title.textContent = label;

        var dayAss = allAssignments.filter(function(a) {
            var aDate = (a.scheduled_date || a.assigned_at || '').split('T')[0];
            if (aDate !== dateStr) return false;
            var rid = a.route_id || a.route;
            return rid && Array.isArray(allRoutes) && allRoutes.some(function(r) { return String(r.id) === String(rid); });
        });
        var dailyRoutes = allRoutes.filter(function(r) { return r.is_daily && r.status !== 'archived'; });
        var todayDate = new Date();
        var targetDate = new Date(dateStr + 'T12:00:00');
        var isFutureDay = targetDate > todayDate;

        var totalCount = dayAss.length + dailyRoutes.length;
        if (count) count.textContent = totalCount + ' mission' + (totalCount !== 1 ? 's' : '');

        list.innerHTML = '';
        if (!totalCount) {
            list.innerHTML = '<div class=\"dc-rp-day-empty\"><i class=\"fas fa-calendar-day\"></i>No missions on this day</div>';
            panel.style.display = 'flex';
            return;
        }

        // Render explicit assignments
        dayAss.forEach(function(a) {
            var isActive    = a.is_active && !a.is_completed;
            var isCompleted = a.is_completed;
            var missedEv    = isActive && window.__dc_live_next_by_assignment && window.__dc_live_next_by_assignment[a.id] && window.__dc_live_next_by_assignment[a.id].next_checkpoint && window.__dc_live_next_by_assignment[a.id].next_checkpoint.is_window_missed;
            var isDeviceOnly = !a.guard_supervisor_name && !a.operator_name && !a.guard_callsign;
            var dotColor, badgeText, badgeCls;
            if (isCompleted) { dotColor = '#6C8EEF'; badgeText = 'Done'; badgeCls = 'done'; }
            else if (missedEv) { dotColor = '#FF5252'; badgeText = 'Miss'; badgeCls = 'done'; }
            else if (isActive) { dotColor = '#5DCAA5'; badgeText = 'Active'; badgeCls = 'active'; }
            else { dotColor = '#EF9F27'; badgeText = 'Sched'; badgeCls = 'sched'; }

            var total = a.total_checkpoints || 0;
            var hit   = a.completed_checkpoints || 0;
            var guardName = isDeviceOnly ? (a.device_name || 'Device') : (a.operator_name || a.guard_supervisor_name || a.guard_callsign || '—');

            list.innerHTML += '<div class=\"dc-rp-day-card ' + (isActive ? 'is-active' : isCompleted ? 'is-done' : '') + '\" onclick=\"dcShowMissionDetail(allAssignments.find(function(x){return x.id===' + a.id + '}))\">' +
                '<span class=\"dc-rp-day-card-dot\" style=\"background:' + dotColor + ';\"></span>' +
                '<span class=\"dc-rp-day-card-name\">' + escHtml(a.route_name || 'Mission #' + a.id) + '</span>' +
                '<span class=\"dc-rp-day-card-meta\">' +
                    (a.scheduled_start_time ? '<span><i class=\"fas fa-clock\"></i>' + a.scheduled_start_time + '</span>' : '') +
                    (total > 0 ? '<span>' + hit + '/' + total + '</span>' : '') +
                    '<span class=\"dc-rp-day-card-badge ' + badgeCls + '\">' + badgeText + '</span>' +
                '</span></div>';
        });

        // Render daily routes without assignment
        dailyRoutes.forEach(function(r) {
            var alreadyAssigned = dayAss.some(function(a) { return String(a.route_id || a.route) === String(r.id); });
            if (alreadyAssigned) return;
            var hasDevices = r.assigned_devices && r.assigned_devices.length > 0;
            var hasGuards = r.assigned_guards && r.assigned_guards.length > 0;
            var guardName = hasGuards ? r.assigned_guards.map(function(g) { return g.name || g; }).join(', ') : '';
            var deviceName = hasDevices ? r.assigned_devices.map(function(d) { return d.device_name || d; }).join(', ') : '';

            list.innerHTML += '<div class=\"dc-rp-day-card\" style=\"opacity:0.7;border-style:dashed;\">' +
                '<span class=\"dc-rp-day-card-dot\" style=\"background:#6C8EEF;animation:dcPulse 1.5s ease-in-out infinite;\"></span>' +
                '<span class=\"dc-rp-day-card-name\">' + escHtml(r.name) + '</span>' +
                '<span class=\"dc-rp-day-card-meta\">' +
                    (guardName ? '<span><i class=\"fas fa-user\"></i>' + guardName + '</span>' : '') +
                    (deviceName ? '<span><i class=\"fas fa-microchip\"></i>' + deviceName + '</span>' : '') +
                    '<span class=\"dc-rp-day-card-badge daily\">Daily</span>' +
                '</span></div>';
        });

        panel.style.display = 'flex';
    };

    window.dcCloseDayPanel = function() {
        var panel = $('dcDayPanel');
        if (panel) panel.style.display = 'none';
    };

    function dCPDots(a, total, hit, dateStr) {
        const route = allRoutes.find(r => String(r.id) === String(a.route_id || a.route));
        const cps = (route && route.checkpoints) ? route.checkpoints : [];
        const now = new Date();
        const missionDate = new Date(dateStr);
        const todayOnly = new Date(now.toISOString().split('T')[0]);
        const isPastDay = missionDate < todayOnly;
        let dots = '';
        const show = Math.min(total, 20);
        for (let i = 0; i < Math.min(total, show); i++) {
            const cp = cps[i] || { name: 'P'+(i+1) };
            let state = 'pending';
            if (i < hit) state = 'hit';
            else if (isPastDay) state = 'miss';
            else if (a.is_active && !a.is_completed && cp.planned_time) {
                try {
                    const pt = new Date(dateStr+'T'+cp.planned_time);
                    const tol = ((cp.time_tolerance||15) + (cp.dwell_time||0))*60000;
                    if (!isNaN(pt.getTime()) && now.getTime() > pt.getTime()+tol) state = 'miss';
                } catch(e) {}
            }
            if (state === 'pending' && i === hit && a.is_active && !a.is_completed) state = 'next';
            const color = state === 'hit' ? '#5DCAA5' : state === 'miss' ? '#d32f2f' : state === 'next' ? '#EF9F27' : 'rgba(255,255,255,0.1)';
            dots += `<span style="display:inline-block;width:${state==='next'?'7px':'5px'};height:${state==='next'?'7px':'5px'};border-radius:50%;background:${color};${state==='next'?'animation:dcPulse 1.5s ease-in-out infinite;':''}" title="${cp.name}"></span>`;
        }
        if (total > show) dots += `<span style="font-size:0.5rem;color:rgba(255,255,255,0.2);margin-left:2px;">+${total-show}</span>`;
        return dots;
    }

    window.dcCloseDayView = function() {
        window.__dcInDayView = false;
        const dv = $('dcDayView');
        const grid = $('dcLsGrid');
        const tabs = $('dcLsTabs');
        const stats = $('dcLsStats');
        dv.classList.add('dc-hidden');
        grid.classList.remove('dc-hidden');
        if (tabs) tabs.classList.remove('dc-hidden');
        if (stats) stats.classList.remove('dc-hidden');
        $('dcCenterTitle').innerHTML = '<i class="fas fa-satellite-dish" style="color:var(--primary);margin-right:6px;"></i>Missions';
    };

    /* ── Calendar delegates to CalendarComponent ── */
    window.dcRenderLsCalendar = function() {
        if (window.CalendarComponent) CalendarComponent.render();
    };

    /* ── Build one card ────────────────────────────── */
    function dcCardHTML(a) {
        const isActive    = a.is_active && !a.is_completed;
        const isCompleted = a.is_completed;
        const isScheduled = (a.scheduled_start || a.scheduled_end || a.scheduled_start_time) && !a.is_active && !a.is_completed;
        const isCreated   = !isActive && !isCompleted && !isScheduled;

        let statusClass, statusLabel;
        let cardClass = '';

        if (isActive) {
            statusClass = 'dc-s-active';
            statusLabel = 'Active';
            cardClass = 'is-active';
        } else if (isCompleted) {
            statusClass = 'dc-s-done';
            statusLabel = 'Completed';
            cardClass = 'is-done';
        } else if (isScheduled) {
            statusClass = 'dc-s-scheduled';
            statusLabel = 'Scheduled';
            cardClass = 'is-scheduled';
        } else {
            statusClass = 'dc-s-created';
            statusLabel = 'Draft';
            cardClass = 'is-created';
        }

        /* Progress */
        const total   = a.total_checkpoints || 0;
        const hit     = a.completed_checkpoints || 0;
        const pct     = total > 0 ? Math.round((hit / total) * 100) : 0;
        let fillCls   = pct >= 100 ? 'complete' : '';

        /* Checkpoint dots (max 12 shown) */
        let dots = '';
        let manifestRows = '';
        const now = new Date();
        let hasMisses = false;

        if (total > 0) {
            const route = allRoutes.find(r => String(r.id) === String(a.route_id || a.route));
            const cps = (route && route.checkpoints) ? route.checkpoints : [];
            const datePart = (a.scheduled_date || a.assigned_at || new Date().toISOString()).split(/[T ]/)[0];
            const missionDate = new Date(datePart);
            const todayOnly = new Date(now.toISOString().split('T')[0]);
            const isPastDay = missionDate < todayOnly;

            const show = Math.min(total, 16);
            for (let i = 0; i < total; i++) {
                const cp = cps[i] || { name: `Point ${i+1}` };
                let state = 'pending'; 

                // Success check
                if (i < hit) state = 'hit';
                // Failure check: Day expired
                else if (isPastDay) state = 'miss';
                // Failure check (Window Expired)
                else if (isActive && cp.planned_time) {
                    try {
                        const pt = new Date(`${datePart}T${cp.planned_time}`);
                        const tolerance = ((cp.time_tolerance || 15) + (cp.dwell_time || 0)) * 60000;
                        if (!isNaN(pt.getTime()) && now.getTime() > pt.getTime() + tolerance) {
                            state = 'miss';
                        }
                    } catch(e) {}
                }
                
                // Highlight next immediate objective if not hit and not failed
                if (state === 'pending' && i === hit && isActive) state = 'next';
                
                if (state === 'miss') hasMisses = true;

                if (i < show) {
                    dots += `<div class="dc-cp-dot ${state}" title="${cp.name}"></div>`;
                }

                var sLabel = state === 'hit' ? 'Success' : state === 'miss' ? 'Failed' : 'Pending';
                var sColor = state === 'hit' ? '#5DCAA5' : state === 'miss' ? '#d32f2f' : '#6C8EEF';
                var failReason = isPastDay ? 'Day Expired' : 'Window Missed';
                var timeHtml = cp.planned_time ? '<i class=\"fas fa-clock\" style=\"font-size:0.55rem;margin-right:3px;\"></i>' + cp.planned_time : '\u2014';
                
                manifestRows += '<div class=\"dc-manifest-row' + (state === 'miss' ? ' miss' : '') + '\">' +
                    '<span style=\"display:flex; align-items:center;\">' +
                        '<span class=\"dc-row-status\" style=\"background:' + sColor + '\"></span>' +
                        '<span style=\"font-weight:700; color:white;\">' + (cp.name || 'Point') + '</span>' +
                    '</span>' +
                    '<span style=\"color:rgba(255,255,255,0.4); font-size:0.65rem;\">' +
                        timeHtml + ' \u00B7 ' +
                        '<span style=\"color:' + sColor + '; font-weight:800;\">' + (state === 'miss' ? failReason : sLabel) + '</span>' +
                    '</span>' +
                '</div>';
            }
            if (total > 16) dots += `<div style="font-size:0.62rem; color:rgba(255,255,255,0.35); align-self:center;">+${total - 16}</div>`;
        }

        if (hasMisses && isActive) {
            cardClass += ' is-failed';
            fillCls = 'failed';
        }

        /* Timing */
        const started = a.assigned_at ? new Date(a.assigned_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : '—';
        const elapsed = a.assigned_at ? dcElapsed(a.assigned_at) : '';

        /* Progress Visuals (Ongoing ETA & Upcoming) */
        var progressAddon = '';
        if (isActive && total > 0) {
            var liveData2 = window.__dc_live_next_by_assignment || {};
            var live2 = liveData2[a.id] || null;
            var nxt = live2 ? live2.next_checkpoint : null;
            var cpType = nxt ? nxt.checkpoint_type || '' : '';
            var timeRem = nxt ? nxt.time_remaining_seconds : null;
            var dwellRem = nxt ? nxt.dwell_remaining_seconds : null;
            var isPresent = nxt ? nxt.is_present : false;
            var isMiss = nxt ? nxt.is_window_missed : false;
            var nxtName = nxt ? nxt.name : '';

            var fmtSeconds = function(sec) {
                if (sec == null) return '\u2014';
                sec = Math.max(0, Number(sec));
                var m = Math.floor(sec / 60);
                var s = sec % 60;
                return (m > 0 ? m + 'm ' : '') + s + 's';
            };

            var etaText = (timeRem == null) ? 'T+ (window)' : fmtSeconds(timeRem);
            var presenceText = isPresent ? 'Present (' + fmtSeconds(dwellRem) + ')' : 'Not present';

            var etaColor = 'rgba(255,255,255,0.9)';
            if (isMiss) etaColor = '#d32f2f';
            else if (isPresent) etaColor = '#5DCAA5';

            progressAddon = '<div class=\"dc-eta-block dc-eta-active\">' +
                '<div style=\"display:flex; justify-content:space-between; align-items:center; gap:10px;\">' +
                    '<span class=\"dc-eta-label\" style=\"color:var(--r-teal);\">Next Objective</span>' +
                    '<span style=\"font-size:0.62rem; font-weight:900; color:' + etaColor + '; background:rgba(0,0,0,0.2); padding:2px 6px; border-radius:4px;\">' + etaText + '</span>' +
                '</div>' +
                '<div class=\"dc-eta-val\">' +
                    '<i class=\"fas fa-location-crosshairs\" style=\"color:var(--r-teal); font-size:0.65rem;\"></i>' +
                    '<span style=\"font-weight:900;\">' + (nxtName || 'Point ' + (hit + 1)) + '</span>' +
                '</div>' +
                '<div style=\"display:flex; gap:10px; flex-wrap:wrap; margin-top:6px; color:rgba(255,255,255,0.55); font-size:0.65rem; font-weight:800;\">' +
                    '<span><i class=\"fas fa-layer-group\" style=\"opacity:0.7; margin-right:6px;\"></i>' + (cpType || 'Checkpoint') + '</span>' +
                    '<span><i class=\"fas fa-eye\" style=\"opacity:0.7; margin-right:6px;\"></i>' + presenceText + '</span>' +
                '</div>' +
            '</div>';
        } else if (isScheduled) {
            progressAddon = `
                <div class="dc-eta-block dc-eta-upcoming">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span class="dc-eta-label" style="color:var(--r-amber);">Launch Window</span>
                        <span style="font-size:0.62rem; font-weight:900; color:#fff;">T-Minus 12m</span>
                    </div>
                    <div class="dc-eta-val">
                        <i class="fas fa-clock" style="color:var(--r-amber); font-size:0.65rem;"></i>
                        Start @ ${a.scheduled_start_time}
                    </div>
                </div>
            `;
        } else if (isCreated) { // New block for created missions
            progressAddon = `
                <div class="dc-eta-block dc-eta-created">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span class="dc-eta-label" style="color:var(--primary-light);">Mission Draft</span>
                        <span style="font-size:0.62rem; font-weight:900; color:#fff;">Awaiting Config</span>
                    </div>
                    <div class="dc-eta-val">
                        <i class="fas fa-pencil-ruler" style="color:var(--primary-light); font-size:0.65rem;"></i>
                        Ready for Scheduling
                    </div>
                </div>
            `;
        }

        /* Action buttons */
        var actions = '';
        var statusLabelFinal = (isActive && hasMisses) ? 'Violation Detected' : statusLabel;

        var btnRedeploy = '<button type="button" class=\"dc-card-btn redeploy\" onclick=\"dcStartRedeploy(' + a.id + ')\"><i class=\"fas fa-redo\"></i> Redeploy</button>';
        var btnProgress = '<button type="button" class=\"dc-card-btn\" onclick=\"dcViewProgress(' + a.id + ')\"><i class=\"fas fa-chart-bar\"></i> Progress</button>';
        var btnEnd = '<button type="button" class=\"dc-card-btn danger\" onclick=\"dcTerminate(' + a.id + ')\"><i class=\"fas fa-stop\"></i> End</button>';
        var btnActivate = '<button type="button" class=\"dc-card-btn redeploy\" onclick=\"dcActivate(' + a.id + ')\"><i class=\"fas fa-play\"></i> Activate</button>';
        var btnCancel = '<button type="button" class=\"dc-card-btn danger\" onclick=\"dcTerminate(' + a.id + ')\"><i class=\"fas fa-times\"></i> Cancel</button>';
        var btnReport = '<button type="button" class=\"dc-card-btn\" onclick=\"dcViewProgress(' + a.id + ')\"><i class=\"fas fa-file-alt\"></i> Report</button>';

        if (isActive) {
            actions = btnRedeploy + btnProgress + btnEnd;
        } else if (isCompleted) {
            actions = btnRedeploy + btnReport;
        } else {
            actions = btnActivate + btnCancel;
        }

        var progSection = total > 0
            ? '<div class=\"dc-progress-wrap\"><div class=\"dc-progress-label\"><span>Checkpoints</span><span>' + hit + ' / ' + total + ' &nbsp;(' + pct + '%)</span></div><div class=\"dc-progress-track\"><div class=\"dc-progress-fill' + (fillCls ? ' ' + fillCls : '') + '\" style=\"width:' + pct + '%\"></div></div></div><div class=\"dc-cp-dots\">' + dots + '</div><div class=\"dc-manifest-details\" id=\"dcManifest-' + a.id + '\">' + manifestRows + '</div>'
            : '<div style=\"font-size:0.7rem; color:rgba(255,255,255,0.3); margin:8px 0;\">No checkpoints tracked</div>';

        return '<div class=\"dc-card ' + cardClass + '\" id=\"dcCard-' + a.id + '\" data-route-id=\"' + (a.route_id || a.route) + '\" onclick=\"dcViewProgress(' + a.id + ')\" style=\"cursor:pointer;\">' +
            '<div class=\"dc-card-top\">' +
                '<div>' +
                    '<div class=\"dc-guard-name\">' + (a.guard_supervisor_name || 'Unknown Guard') + '</div>' +
                    '<div class=\"dc-route-name\"><i class=\"fas fa-route\" style=\"font-size:0.6rem;\"></i> ' + (a.route_name || 'Free Patrol') + '</div>' +
                '</div>' +
                '<span class=\"dc-status ' + statusClass + '\"><span class=\"dc-status-dot\"></span>' + statusLabelFinal + '</span>' +
            '</div>' +
            progSection +
            progressAddon +
            '<div class=\"dc-meta-row\">' +
                '<span><i class=\"fas fa-clock\" style=\"margin-right:4px;\"></i>' + started + (elapsed ? ' \u00B7 ' + elapsed : '') + '</span>' +
                '<span>' + (a.shift_type || '') + (a.device_name ? ' \u00B7 ' + a.device_name : '') + '</span>' +
            '</div>' +
            '<div class=\"dc-card-actions\">' + actions + '</div>' +
        '</div>';
    }

    /* ── Elapsed helper ────────────────────────────── */
    function dcElapsed(dateStr) {
        const diff = Date.now() - new Date(dateStr).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1)  return 'just now';
        if (mins < 60) return `${mins}m ago`;
        const hrs = Math.floor(mins / 60);
        return `${hrs}h ${mins % 60}m`;
    }

    /* ── Deploy handoff highlight ───────────────────── */
    function dcHighlightDeployedRoute(routeId) {
        // Ensure view is rendered before scrolling/highlighting.
        // Shows missions in left sidebar, blueprint progress in center.

        // Choose tab based on assignment state for this route.
        const rid = String(routeId);
        const matches = (Array.isArray(allAssignments) ? allAssignments : [])
            .filter(a => String(a.route_id || a.route) === rid);

        if (!matches.length) {
            // Nothing to highlight; fallback to active grid.
            dcSwitchTab('active', document.querySelector('.dc-ls-tab'));
            return;
        }

        const hasActive = matches.some(a => a.is_active && !a.is_completed);
        const hasDone   = matches.some(a => a.is_completed);
        const hasPending= matches.some(a => !a.is_active && !a.is_completed);

        let targetTab = 'all';
        if (hasActive) targetTab = 'active';
        else if (hasPending) targetTab = 'upcoming';
        else if (hasDone) targetTab = 'done';

        // Switch tab without requiring user click.
        if (targetTab !== currentTab) {
            // Find tab by hx-get URL param (since onclick no longer has dcSwitchTab)
            const tabEl = document.querySelector(`.dc-ls-tab[hx-get*="${targetTab}"]`);
            if (tabEl) dcSwitchTab(targetTab, tabEl);
            else {
                // fallback: keep currentTab but re-render
                currentTab = targetTab;
            }
        }

        // Render the grid so cards exist in DOM.
        if (currentTab === 'calendar') {
            // Calendar is in left sidebar; render it if needed
            CalendarComponent.render();
            return;
        }
        refreshMissionsGrid();

        // Highlight and scroll to the first matching card.
        // Must wait for htmx to finish swapping the grid before querying DOM.
        const first = matches[0];
        const highlightCard = () => {
            const card = document.querySelector(`.dc-ls-card[data-assign-id="${first.id}"]`);
            if (!card) return;
            card.classList.add('dc-highlight');
            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => card.classList.remove('dc-highlight'), 3500);
        };
        // Listen for the next htmx swap on #dcLsGrid, then highlight
        document.body.addEventListener('htmx:afterSwap', function handler(e) {
            if (e.detail?.target?.id === 'dcLsGrid') {
                document.body.removeEventListener('htmx:afterSwap', handler);
                highlightCard();
            }
        });
        // Fallback: if grid already has cards (e.g. from initial load), highlight immediately
        setTimeout(() => {
            const card = document.querySelector(`.dc-ls-card[data-assign-id="${first.id}"]`);
            if (card) highlightCard();
        }, 500);
    }

    /* ── Deploy (show confirmation first) ───────────── */

    __dcPendingPayload = null;
    dcOvTagEntries = [];

    window.dcOvAddTag = function(id, label, type) {
        const container = $('dcOvGuardTags');
        if (!container) return;
        if (dcOvTagEntries.some(e => e.id === Number(id) && e.type === type)) return;
        const span = document.createElement('span');
        span.className = 'dc-overlay-person-tag' + (type === 'device' ? ' device' : '');
        span.dataset.id = id;
        span.dataset.type = type;
        span.innerHTML = `<span>${type === 'device' ? '<i class="fas fa-microchip"></i> ' : '<i class="fas fa-user-shield"></i> '}${label}</span><button type="button" onclick="this.parentElement.remove(); dcOvTagEntries = dcOvTagEntries.filter(x => !(x.id === ${id} && x.type === '${type}'));" style="background:none;border:none;color:inherit;cursor:pointer;padding:0;margin:0;font-size:0.7rem;">&times;</button>`;
        container.appendChild(span);
        dcOvTagEntries.push({ id: Number(id), type });
    }

    function dcOvSetupGuardInput() {
        const inp = $('dcOvGuardInput');
        if (!inp) return;
        const suggest = $('dcOvGuardSuggest');

        inp.oninput = function() {
            const val = this.value.trim().toLowerCase();
            if (val.length < 2) { $('dcOvGuardSuggest').classList.add('dc-hidden'); return; }

            const pM = allGuards.filter(g => 
                (g.username || '').toLowerCase().includes(val) || 
                (g.callsign || '').toLowerCase().includes(val)
            ).slice(0, 5);

            const dM = allDevices.filter(d => 
                (d.device_id || '').toLowerCase().includes(val) || 
                (d.device_name || '').toLowerCase().includes(val)
            ).slice(0, 5);

            if (!pM.length && !dM.length) { $('dcOvGuardSuggest').classList.add('dc-hidden'); return; }

            let html = dM.map(d => `
                <div class="dc-overlay-suggest-item" onclick="dcOvAddTag(${d.id}, '${d.device_id || d.device_name}', 'device'); $('dcOvGuardSuggest').classList.add('dc-hidden'); $('dcOvGuardInput').value='';">
                    <span><i class="fas fa-microchip" style="color:#5DCAA5"></i> ${d.device_id || d.device_name}</span>
                    <span style="opacity:.5;font-size:.6rem;text-transform:uppercase;">Device</span>
                </div>`).join('');

            html += pM.map(g => `
                <div class="dc-overlay-suggest-item" onclick="dcOvAddTag(${g.id}, '${g.callsign || g.username}', 'person'); $('dcOvGuardSuggest').classList.add('dc-hidden'); $('dcOvGuardInput').value='';">
                    <span><i class="fas fa-user-shield"></i> ${g.callsign || g.username}</span>
                    <span style="opacity:.5;font-size:.6rem;text-transform:uppercase;">${g.role || 'Guard'}</span>
                </div>`).join('');

            $('dcOvGuardSuggest').innerHTML = html;
            $('dcOvGuardSuggest').classList.remove('dc-hidden');
        };

        inp.onkeydown = function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                const val = this.value.trim().toLowerCase();
                if (!val) return;
                const gMatch = allGuards.find(g => (g.username || '').toLowerCase() === val || (g.callsign || '').toLowerCase() === val);
                const dMatch = allDevices.find(d => (d.device_id || '').toLowerCase() === val || (d.device_name || '').toLowerCase() === val);
                if (dMatch) dcOvAddTag(dMatch.id, dMatch.device_id || dMatch.device_name, 'device');
                else if (gMatch) dcOvAddTag(gMatch.id, gMatch.callsign || gMatch.username, 'person');
                this.value = '';
                suggest.classList.add('dc-hidden');
            }
        };

        document.addEventListener('click', function(e) {
            if (!inp.contains(e.target) && !suggest.contains(e.target)) {
                suggest.classList.add('dc-hidden');
            }
        });
    }

    // ── Overlay state helpers ──
    __dcOvMode = 'deploy';
    __dcOvRouteId = null;
    __dcOvAssignmentId = null;

    window.dcOvUpdateState = function() {
        const verified = $('dcOvVerify').checked;
        const btn = $('dcOvDeployBtn');
        if (verified) {
            btn.disabled = false;
            btn.style.opacity = '1';
        } else {
            btn.disabled = true;
            btn.style.opacity = '.35';
        }
    };

    window.dcOvSelectBlueprint = function() {
        const sel = $('dcDeployBlueprint');
        const routeId = sel.value;
        __dcOvRouteId = routeId || null;
        const route = routeId ? allRoutes.find(r => String(r.id) === String(routeId)) : null;
        if (route) {
            $('dcDeployStrat').textContent = route.logic_type || 'Flexible';
            const stratMap = {Flexible:'dc-conf-badge-teal',Sequential:'dc-conf-badge-amber',Scheduled:'dc-conf-badge-crim',Audit:'dc-conf-badge-violet',Custom:'dc-conf-badge-indigo'};
            $('dcDeployStrat').className = 'dc-conf-badge ' + (stratMap[route.logic_type] || 'dc-conf-badge-teal');
            if (route.scheduled_start_time) $('dcDeployTime').value = route.scheduled_start_time;
            // Pre-fill TTS/alert settings from route
            $('dcOvTriggerAlert').checked = !!route.send_start_alert;
            $('dcOvTriggerAnnounce').checked = !!route.send_announcement;
            $('dcOvLeadTime').value = route.start_alert_lead_time ?? 15;
            $('dcOvReadoutText').value = route.readout_text || '';
            dcOvRenderCheckpoints(route.checkpoints || []);
        } else {
            $('dcDeployStrat').textContent = 'Flexible';
            $('dcDeployStrat').className = 'dc-conf-badge dc-conf-badge-teal';
            $('dcDeployTime').value = '';
            $('dcOvTriggerAlert').checked = true;
            $('dcOvTriggerAnnounce').checked = false;
            $('dcOvLeadTime').value = 15;
            $('dcOvReadoutText').value = '';
            $('dcOvCpList').innerHTML = '<div style="padding:16px;text-align:center;color:rgba(255,255,255,0.2);font-size:0.75rem;">Select a blueprint to edit checkpoints</div>';
            $('dcOvCpCount').textContent = '';
            $('dcOvCpFooter').innerHTML = '';
        }
        dcOvUpdateState();
    };

    window.dcOvRenderCheckpoints = function(cps) {
        window['__dcOvCurrentCps'] = cps;
        const container = $('dcOvCpList');
        $('dcOvCpCount').textContent = cps.length ? `(${cps.length})` : '(0)';
        if (!cps.length) {
            container.innerHTML = '<div style="padding:16px;text-align:center;color:rgba(255,255,255,0.2);font-size:0.75rem;">No checkpoints — deploy will create an empty route</div>';
            $('dcOvCpFooter').innerHTML = '';
            return;
        }
        const typeOpts = [
            {v:'nfc',l:'NFC'},{v:'gps',l:'GPS'},{v:'geo',l:'GEO'},{v:'peer',l:'Peer'},{v:'custom',l:'Custom'}
        ].map(o => `<option value="${o.v}">${o.l}</option>`).join('');
        container.innerHTML = cps.map((cp, i) => {
            const planned = cp.planned_time ? cp.planned_time.substring(0,5) : '';
            const dwell = cp.dwell_time ?? 0;
            const tol = cp.time_tolerance ?? 15;
            const rad = cp.radius ?? 50;
            const lat = cp.lat ?? '';
            const lng = cp.lng ?? '';
            const nfcTag = cp.nfc_tag ?? '';
            const auditor = cp.auditor_id ?? '';
            const target = cp.target_id ?? '';
            const cpType = cp.checkpoint_type || 'gps';
            const showNfc = cpType === 'nfc';
            const showLatLng = cpType === 'gps' || cpType === 'geo' || cpType === 'custom';
            const showRadius = cpType === 'gps' || cpType === 'geo' || cpType === 'custom';
            const showPeer = cpType === 'peer';
            return `<div class="dc-ov-cp-row" data-cp-idx="${i}">
                <div class="dc-ov-cp-row-head">
                    <span class="cp-index">#${i+1}</span>
                    <select class="cp-type" onchange="dcOvUpdateCp(${i},'checkpoint_type',this.value);dcOvRenderCheckpoints(window['__dcOvCurrentCps'])">${typeOpts.replace(`value="${cpType}"`,`value="${cpType}" selected`)}</select>
                    <input class="cp-name" value="${escHtml(cp.name || '')}" placeholder="Name" onchange="dcOvUpdateCp(${i},'name',this.value)">
                    ${showNfc ? `<input class="cp-tag" value="${escHtml(nfcTag)}" placeholder="NFC UID" onchange="dcOvUpdateCp(${i},'nfc_tag',this.value)">` : ''}
                    <button type="button" class="cp-del" onclick="dcOvRemoveCp(${i})" title="Remove checkpoint"><i class="fas fa-xmark"></i></button>
                </div>
                <div class="dc-ov-cp-fields">
                    <input class="cp-time" type="time" value="${planned}" onchange="dcOvUpdateCp(${i},'planned_time',this.value)">
                    ${showLatLng ? `<span class="cp-label">Lat</span><input class="cp-lat" value="${lat}" placeholder="0.0000" onchange="dcOvUpdateCp(${i},'lat',this.value ? parseFloat(this.value) : null)">
                    <span class="cp-label">Lng</span><input class="cp-lng" value="${lng}" placeholder="0.0000" onchange="dcOvUpdateCp(${i},'lng',this.value ? parseFloat(this.value) : null)">` : ''}
                    ${showPeer ? `<span class="cp-label">Auditor</span><input style="width:50px" value="${escHtml(auditor)}" placeholder="Auditor" onchange="dcOvUpdateCp(${i},'auditor_id',this.value)">
                    <span class="cp-label">Target</span><input style="width:50px" value="${escHtml(target)}" placeholder="Target" onchange="dcOvUpdateCp(${i},'target_id',this.value)">` : ''}
                </div>
                <div class="dc-ov-cp-sliders">
                    ${showRadius ? `<label>R <input type="range" min="5" max="500" step="5" value="${rad}" oninput="dcOvUpdateCp(${i},'radius',Number(this.value));this.nextElementSibling.textContent=this.value+'m'"><span class="sv">${rad}m</span></label>` : ''}
                    <label>Dw <input type="range" min="0" max="60" step="1" value="${dwell}" oninput="dcOvUpdateCp(${i},'dwell_time',Number(this.value));this.nextElementSibling.textContent=this.value+'m'"><span class="sv">${dwell}m</span></label>
                    <label>Tol <input type="range" min="0" max="60" step="1" value="${tol}" oninput="dcOvUpdateCp(${i},'time_tolerance',Number(this.value));this.nextElementSibling.textContent=this.value+'m'"><span class="sv">${tol}m</span></label>
                </div>
            </div>`;
        }).join('');
        $('dcOvCpFooter').innerHTML = `<span><i class="fas fa-route"></i> ${cps.length} checkpoints</span>`;
    };

    window.dcOvUpdateCp = function(idx, field, val) {
        const routeId = $('dcDeployBlueprint').value;
        const route = routeId ? allRoutes.find(r => String(r.id) === String(routeId)) : null;
        if (!route || !route.checkpoints || !route.checkpoints[idx]) return;
        if (field === 'planned_time' && val) val += ':00';
        route.checkpoints[idx][field] = val;
    };

    window.dcOvRemoveCp = function(idx) {
        const routeId = $('dcDeployBlueprint').value;
        const route = routeId ? allRoutes.find(r => String(r.id) === String(routeId)) : null;
        if (!route || !route.checkpoints) return;
        route.checkpoints.splice(idx, 1);
        dcOvRenderCheckpoints(route.checkpoints);
    };

    window.dcPopulateBlueprintSelect = function(selectedId) {
        const sel = $('dcDeployBlueprint');
        const current = sel.value;
        sel.innerHTML = '<option value="">— Select Blueprint —</option>' +
            allRoutes.map(r =>
                `<option value="${r.id}" ${String(r.id) === String(selectedId || current) ? 'selected' : ''}>${escHtml(r.name)}</option>`
            ).join('');
    };

    window.dcOpenDeployOverlay = function(routeId) {
        __dcOvMode = 'deploy';
        __dcOvRouteId = routeId || null;
        __dcOvAssignmentId = null;
        dcOvTagEntries = [];
        $('dcOvGuardTags').innerHTML = '';
        $('dcOvRedeployFields').style.display = 'none';
        $('dcDeployOvTitle').textContent = 'MISSION INITIALIZATION';
        $('dcDeployOvSub').textContent = 'Final pre-flight — review and confirm deployment.';
        $('dcOvDeployBtnText').textContent = 'COMMENCE MISSION DEPLOYMENT';

        $('dcDeployDate').value = new Date().toISOString().split('T')[0];
        $('dcDeployTime').value = '';
        $('dcOvShiftDay').checked = true;

        dcPopulateBlueprintSelect(routeId);
        if (routeId) dcOvSelectBlueprint();

        $('dcOvVerify').checked = false;
        dcOvUpdateState();
        var panel = $('dcDeployPanel');
        if (panel) panel.style.display = 'flex';
        dcLog('Deploy overlay opened' + (routeId ? ' for route ' + routeId : ''), 'info');
    };

    window.dcOpenRedeployOverlay = function(assignmentId) {
        const a = allAssignments.find(x => x.id === assignmentId);
        if (!a) return;

        __dcOvMode = 'redeploy';
        __dcOvRouteId = a.route || a.route_id || null;
        __dcOvAssignmentId = assignmentId;
        dcOvTagEntries = [];
        $('dcOvGuardTags').innerHTML = '';
        $('dcDeployOvTitle').textContent = 'REDEPLOY MISSION';
        $('dcDeployOvSub').textContent = 'Adjust personnel and timing for redeployment.';
        $('dcOvDeployBtnText').textContent = 'CONFIRM REDEPLOYMENT';
        $('dcOvRedeployFields').style.display = 'flex';
        $('dcOvRedeployTime').value = a.scheduled_start_time || '';

        $('dcDeployDate').value = (a.scheduled_date || new Date().toISOString().split('T')[0]);
        if (a.shift_type === 'Night') $('dcOvShiftNight').checked = true;
        else $('dcOvShiftDay').checked = true;

        // Pre-fill existing guard if present
        if (a.guard_supervisor || a.guard_callsign) {
            const guardId = a.guard_supervisor || a.guard_callsign;
            const guard = allGuards.find(g => String(g.id) === String(guardId));
            if (guard) dcOvAddTag(guard.id, guard.callsign || guard.username, 'person');
        }
        // Pre-fill existing device
        if (a.device_id || a.device) {
            const devId = a.device_id || a.device;
            const device = allDevices.find(d => String(d.id) === String(devId));
            if (device) dcOvAddTag(device.id, device.device_id || device.device_name, 'device');
        }

        // Populate selector and select the route
        dcPopulateBlueprintSelect(__dcOvRouteId);
        if (__dcOvRouteId) dcOvSelectBlueprint();

        $('dcOvVerify').checked = false;
        dcOvUpdateState();
        var panel = $('dcDeployPanel');
        if (panel) panel.style.display = 'flex';
        dcLog('Redeploy overlay opened for mission ' + assignmentId, 'info');
    };

    window.dcCancelDeploy = function () {
        __dcPendingPayload = null;
        var panel = $('dcDeployPanel');
        if (panel) panel.style.display = 'none';
    };

    window.dcExecuteDeploy = async function () {
        const isRedeploy = __dcOvMode === 'redeploy';
        const shift = $('dcOvShiftDay').checked ? 'Day' : 'Night';
        let orgId = null;
        if (typeof userData !== 'undefined' && userData.organization_id) { orgId = Number(userData.organization_id); }

        const personEntries = dcOvTagEntries.filter(e => e.type === 'person');
        const deviceEntries = dcOvTagEntries.filter(e => e.type === 'device');
        const guardIds = personEntries.map(e => e.id);
        const deviceId = deviceEntries.length > 0 ? deviceEntries[0].id : null;
        const routeId = __dcOvRouteId;

        if (guardIds.length === 0 && !deviceId) {
            toast('Assign at least one guard or device', true);
            return;
        }
        if (!routeId) { toast('No blueprint selected', true); return; }

        const payload = {
            guard_ids: guardIds,
            guard_supervisor: guardIds.length > 0 ? guardIds[0] : null,
            route:            Number(routeId),
            dispatcher:       null,
            device:           deviceId ? Number(deviceId) : null,
            organization:     orgId,
            shift_type:       shift,
            is_active:        true,
            send_start_alert: $('dcOvTriggerAlert').checked,
            auto_complete:    $('dcOvTriggerAuto').checked,
            miss_alert:       $('dcOvTriggerMiss').checked,
        };

        // For redeploy, add scheduled time override
        if (isRedeploy) {
            const schedTime = $('dcOvRedeployTime').value;
            if (schedTime) {
                payload.scheduled_start = new Date().toISOString().split('T')[0] + 'T' + schedTime;
                payload.is_active = false;
            }
        } else {
            const ovTime = $('dcDeployTime').value;
            if (ovTime) {
                payload.scheduled_start = ($('dcDeployDate').value || new Date().toISOString().split('T')[0]) + 'T' + ovTime;
                payload.is_active = false;
            }
        }

        __dcPendingPayload = payload;

        const btn = $('dcOvDeployBtn');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Deploying...';

        try {
            // Save checkpoint + TTS/alert edits to the route before deploying
            const route = allRoutes.find(r => String(r.id) === String(routeId));
            if (route) {
                const cps = route.checkpoints || [];
                const cpPayload = cps.map((cp, i) => ({
                    id: cp.id || undefined,
                    name: cp.name || 'Point ' + (i+1),
                    checkpoint_type: cp.checkpoint_type || 'gps',
                    order: i,
                    planned_time: cp.planned_time || null,
                    dwell_time: cp.dwell_time ?? 0,
                    time_tolerance: cp.time_tolerance ?? 15,
                    radius: cp.radius ?? 50,
                    lat: cp.lat ?? null,
                    lng: cp.lng ?? null,
                    nfc_tag: cp.nfc_tag || null,
                    auditor_id: cp.auditor_id || null,
                    target_id: cp.target_id || null
                }));
                await api(`/api/routes/${routeId}/`, {
                    method: 'PATCH',
                    body: JSON.stringify({
                        checkpoints: cpPayload,
                        send_start_alert: $('dcOvTriggerAlert').checked,
                        send_announcement: $('dcOvTriggerAnnounce').checked,
                        start_alert_lead_time: Number($('dcOvLeadTime').value) || 15,
                        readout_text: $('dcOvReadoutText').value || ''
                    })
                });
            }

            const res = await api('/api/shifts/', { method: 'POST', body: JSON.stringify(payload) });
            if (res.ok) {
                toast(isRedeploy ? 'Mission redeployed' : 'Personnel deployed');
                dcLog((isRedeploy ? 'Redeployed' : 'Deployed') + ' route ' + payload.route, 'success');
                dcCancelDeploy();
                await dcLoadAll();
            } else {
                const errData = await res.json().catch(() => ({}));
                const errKey = Object.keys(errData)[0] || 'Unknown';
                const errMsg = errData[errKey] || res.statusText;
                toast((isRedeploy ? 'Redeploy' : 'Deploy') + ' failed: ' + errKey + ' - ' + errMsg, true);
            }
        } catch (e) { dcLog('Deploy error: ' + e.message, 'error'); toast('Deploy failed', true); }
        btn.disabled = false;
        btn.innerHTML = isRedeploy ? 'CONFIRM REDEPLOYMENT' : 'COMMENCE MISSION DEPLOYMENT';
        __dcPendingPayload = null;
    };

    /* ── Terminate ─────────────────────────────────── */
    window.dcTerminate = async function (id) {
        if (!confirm('End this deployment?')) return;
        dcLog(`Terminating deployment ${id}`, 'info');
        try {
            const res = await api(`/api/shifts/${id}/`, {
                method: 'PATCH',
                body: JSON.stringify({ is_active: false, is_completed: true })
            });
            if (res.ok) { dcLog(`Deployment ${id} ended`, 'success'); toast('Deployment ended'); await dcLoadAll(); }
            else { dcLog(`Terminate failed: ${res.status}`, 'error'); toast('Failed to end deployment', true); }
        } catch (e) { dcLog(`Terminate error: ${e.message}`, 'error'); toast('Error', true); }
    };

    /* ── Activate pending ──────────────────────────── */
    window.dcActivate = async function (id) {
        dcLog(`Activating deployment ${id}`, 'info');
        try {
            const res = await api(`/api/shifts/${id}/`, {
                method: 'PATCH',
                body: JSON.stringify({ is_active: true })
            });
            if (res.ok) { dcLog(`Deployment ${id} activated`, 'success'); toast('Deployment activated'); await dcLoadAll(); }
            else { dcLog(`Activate failed: ${res.status}`, 'error'); toast('Failed', true); }
        } catch (e) { dcLog(`Activate error: ${e.message}`, 'error'); toast('Error', true); }
    };

    /* ── Redeploy flow ─────────────────────────────── */
    window.dcStartRedeploy = function (id) {
        dcOpenRedeployOverlay(id);
    };

    window.dcShowCommand = function () {
        // No longer used; kept for backward compat
        dcOpenDeployOverlay(null);
    };

    window.dcCancelRedeploy = function () {
        dcCancelDeploy();
    };

    window.dcConfirmRedeploy = async function () {
        // No longer used separately; merged into dcExecuteDeploy
        dcExecuteDeploy();
    };

    /* ── View progress (links to detail if available) ── */
    window.dcViewProgress = function (id) {
        const a = allAssignments.find(x => x.id === id);
        if (!a) return;
        // Show the mission detail view with checkpoint progress
        dcShowMissionDetail(a);
        dcLog(`Viewing progress for mission ${id}`, 'info');
    };

    window.dcToggleManifest = function (id, event) {
        if (event.target.closest('button')) return;
        const el = document.getElementById(`dcManifest-${id}`);
        if (el) el.classList.toggle('open');
    };

    /* ── Auto-refresh every 30s ────────────────────── */
    function startAutoRefresh() {
        refreshTimer = setInterval(dcLoadAll, 30000);
    }

    /* ── Boot ──────────────────────────────────────── */
    dcLoadAll();
    startAutoRefresh();
    dcLog('Dispatch console initialized', 'info');
    dcOvSetupGuardInput();

    // Capture-phase handler for deploy mode on blueprint cards
    var bpGrid = $('dcBpGrid');
    if (bpGrid) {
        bpGrid.addEventListener('click', function(e) {
            if (!window.__dcDeployMode) return;
            var card = e.target.closest('.dc-bp-card');
            if (!card || e.target.closest('button')) return;
            e.stopPropagation();
            var routeId = card.getAttribute('data-bp-id');
            if (routeId) {
                dcToggleDeployMode();
                dcOpenDeployOverlay(routeId);
            }
        }, { capture: true });
    }
    
    // Check if redirected from routes.html after a deployment - switch to show all assignments
    if (sessionStorage.getItem('dispatch_show_new_deployment') === 'true') {
        sessionStorage.removeItem('dispatch_show_new_deployment');
        // After load, switch to all tab to show the deployment
        setTimeout(() => {
            const allTab = document.querySelector('.dc-ls-tab[hx-get*="tab=all"]');
            if (allTab) {
                dcSwitchTab('all', allTab);
                dcLog('Switched to All tab after routes.html deployment', 'info');
            }
        }, 1000);
    }
