/**
 * Global toast notification system.
 * Source of truth for `window.showToast`.
 */

const TOAST_DURATION = 4000;

let container = null;

function ensureContainer() {
  if (!container) {
    container = document.createElement('div');
    container.id = 'gt-toast-container';
    container.className = 'fixed top-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none';
    document.body.appendChild(container);
  }
  return container;
}

export function toast(message, isError = false, duration = TOAST_DURATION) {
  const el = document.createElement('div');
  el.className = `pointer-events-auto px-4 py-3 rounded-lg shadow-lg text-sm font-medium transition-all duration-300 translate-x-0 opacity-0 ${
    isError
      ? 'bg-danger text-white'
      : 'bg-surface-3 text-text-primary border border-surface-4'
  }`;
  el.textContent = String(message).slice(0, 150);
  ensureContainer().appendChild(el);

  requestAnimationFrame(() => {
    el.classList.remove('opacity-0');
  });

  setTimeout(() => {
    el.classList.add('opacity-0', 'translate-x-2');
    setTimeout(() => el.remove(), 300);
  }, duration);
}

/* htmx integration: show server errors/toasts as toasts */
document.addEventListener('htmx:responseError', (e) => {
  const msg = e.detail?.xhr?.responseText || `Error ${e.detail?.xhr?.status}`;
  toast(msg, true);
});

document.addEventListener('htmx:sendError', () => {
  toast('Network error — check your connection', true);
});
