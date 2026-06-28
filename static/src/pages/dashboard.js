import '../styles/main.css';
import { $ } from '../utils/dom.js';
import { toast } from '../utils/toast.js';

/* ── Preferences ── */
const prefs = { sound: true, vibrate: true, poll: true };
try {
  const saved = JSON.parse(localStorage.getItem('dbNtPrefs'));
  if (saved) Object.assign(prefs, saved);
} catch {}

function savePrefs() {
  prefs.sound = ($('dbPrefSound') || {}).checked !== false;
  prefs.vibrate = ($('dbPrefVibrate') || {}).checked !== false;
  prefs.poll = ($('dbPrefPoll') || {}).checked !== false;
  try { localStorage.setItem('dbNtPrefs', JSON.stringify(prefs)); } catch {}
}
window.dbSavePrefs = savePrefs;

/* ── Alert sound (Web Audio beep) ── */
function playAlertSound() {
  if (!prefs.sound) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [0, 0.4].forEach((delay) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = 'sine';
      osc.frequency.setValueAtTime(delay === 0 ? 800 : 1000, ctx.currentTime + delay);
      gain.gain.setValueAtTime(0.25, ctx.currentTime + delay);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + delay + 0.3);
      osc.start(ctx.currentTime + delay);
      osc.stop(ctx.currentTime + delay + 0.3);
    });
  } catch {}
}
window.playAlertSound = playAlertSound;

/* ── Vibration ── */
function vibrateAlert() {
  if (!prefs.vibrate) return;
  try { if (navigator.vibrate) navigator.vibrate([200, 100, 200]); } catch {}
}
window.vibrateAlert = vibrateAlert;

/* Restore UI */
function restorePrefsUI() {
  const s = $('dbPrefSound'); if (s) s.checked = prefs.sound;
  const v = $('dbPrefVibrate'); if (v) v.checked = prefs.vibrate;
  const p = $('dbPrefPoll'); if (p) p.checked = prefs.poll;
}
restorePrefsUI();

/* ── htmx alert polling: detect new alerts and notify ── */
let knownCount = 0;
try {
  const el = document.querySelector('[data-alert-count]');
  if (el) knownCount = parseInt(el.dataset.alertCount, 10) || 0;
} catch {}

document.addEventListener('htmx:afterSwap', (e) => {
  if (e.detail.target.id === 'alerts-list') {
    const countEl = e.detail.target.querySelector('[data-alert-count]');
    const newCount = countEl ? parseInt(countEl.dataset.alertCount, 10) : 0;
    if (newCount > knownCount) {
      playAlertSound();
      vibrateAlert();
    }
    knownCount = newCount;
  }
});

/* ── Instant Scan Controller ── */
let countdownInterval = null;
let remainingSeconds = 0, totalSeconds = 0;

const scanForm = $('scan-form');
const scanCd = $('scan-countdown');
const cdTime = $('cd-time');
const cdFill = $('cd-fill');
const armBtn = $('scan-arm-btn');
const cancelBtn = $('scan-cancel-btn');
const guardSel = $('scan-guard');
const scanName = $('scan-name');
const cpSel = $('scan-checkpoint');
const minInput = $('scan-minutes');

if (scanName) {
  scanName.addEventListener('input', function () {
    this.classList.toggle('is-green', !!this.value.trim());
  });
}

document.querySelectorAll('.scan-preset').forEach((b) => {
  b.addEventListener('click', function () {
    document.querySelectorAll('.scan-preset').forEach((p) => p.classList.remove('active'));
    this.classList.add('active');
    if (minInput) minInput.value = this.getAttribute('data-mins');
  });
});

if (guardSel) {
  guardSel.addEventListener('change', function () {
    if (!cpSel) return;
    cpSel.innerHTML = '<option value="">Loading...</option>';
    window.apiFetch('/api/checkpoints/?guard_id=' + guardSel.value)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        cpSel.innerHTML = '<option value="">Select...</option>';
        if (d) {
          (Array.isArray(d) ? d : (d.results || [])).forEach((c) => {
            const o = document.createElement('option');
            o.value = c.id || c.name; o.textContent = c.name || c.id;
            cpSel.appendChild(o);
          });
        }
      })
      .catch(() => { cpSel.innerHTML = '<option value="">Select...</option>'; });
  });
}

if (armBtn) {
  armBtn.addEventListener('click', function () {
    if (!guardSel || !cpSel || !guardSel.value || !cpSel.value) {
      toast('Select a guard and checkpoint', true);
      return;
    }
    const m = parseInt(minInput?.value || '5', 10);
    if (!m || m < 1) { toast('Set at least 1 minute', true); return; }

    if ($('cd-guard')) $('cd-guard').textContent = guardSel.options[guardSel.selectedIndex].text;
    if ($('cd-name')) $('cd-name').textContent = (scanName?.value || '').trim() || 'Unnamed';
    if ($('cd-checkpoint')) $('cd-checkpoint').textContent = cpSel.options[cpSel.selectedIndex].text;

    totalSeconds = m * 60; remainingSeconds = totalSeconds;
    updateCD();
    if (scanForm) scanForm.style.display = 'none';
    if (scanCd) scanCd.style.display = 'block';

    countdownInterval = setInterval(() => {
      remainingSeconds--;
      updateCD();
      if (remainingSeconds <= 0) {
        clearInterval(countdownInterval);
        countdownInterval = null;
        if (cdTime) { cdTime.textContent = '00:00'; cdTime.style.color = 'var(--primary)'; }
        if (cdFill) cdFill.style.background = 'var(--primary)';
        playAlertSound();
        vibrateAlert();
        toast('Scan alert triggered!', true);
      }
    }, 1000);
  });
}

if (cancelBtn) {
  cancelBtn.addEventListener('click', function () {
    if (countdownInterval) { clearInterval(countdownInterval); countdownInterval = null; }
    resetScan();
    toast('Scan cancelled');
  });
}

function updateCD() {
  if (!cdTime || !cdFill) return;
  const m = Math.floor(remainingSeconds / 60);
  const s = remainingSeconds % 60;
  cdTime.textContent = String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  const pct = totalSeconds > 0 ? (remainingSeconds / totalSeconds) * 100 : 0;
  cdFill.style.width = pct + '%';
  if (remainingSeconds <= 10) {
    cdTime.style.color = 'var(--primary)'; cdFill.style.background = 'var(--primary)';
  } else if (remainingSeconds <= 30) {
    cdTime.style.color = 'var(--accent-amber)'; cdFill.style.background = 'var(--accent-amber)';
  } else {
    cdTime.style.color = 'var(--text)'; cdFill.style.background = 'var(--primary)';
  }
}

function resetScan() {
  if (scanForm) scanForm.style.display = 'block';
  if (scanCd) scanCd.style.display = 'none';
  if (cdTime) cdTime.style.color = 'var(--text)';
  if (cdFill) { cdFill.style.background = 'var(--primary)'; cdFill.style.width = '100%'; }
  const v = parseInt(minInput?.value || '5', 10);
  if (cdTime) cdTime.textContent = String(v).padStart(2, '0') + ':00';
}
