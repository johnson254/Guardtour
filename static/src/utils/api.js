/**
 * Unified API client for GuardTour.
 * Source of truth for `window.apiFetch` and htmx auth headers.
 * Replaces per-template/local `api(...)` wrappers and `window.apiFetch` in base_app.html.
 */

import { getToken, logout } from './dom.js';

export async function api(url, options = {}) {
  const token = getToken();
  const headers = { ...options.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (!options.body || typeof options.body === 'string') {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(url, {
    credentials: 'same-origin',
    ...options,
    headers,
  });

  if (res.status === 401) {
    logout();
    throw new Error('Session expired');
  }

  return res;
}

/**
 * Backward-compatible fetch wrapper used by older templates/pages.
 * Prefer `api()` for new code.
 */
export async function apiFetch(url, options = {}) {
  return api(url, options);
}

/* htmx global config — add auth header to every htmx request */
document.addEventListener('htmx:configRequest', (e) => {
  const token = getToken();
  if (token) {
    e.detail.headers['Authorization'] = `Bearer ${token}`;
  }
});

/* htmx: redirect to login on 401 */
document.addEventListener('htmx:beforeOnLoad', (e) => {
  if (e.detail.xhr.status === 401) {
    logout();
  }
});
