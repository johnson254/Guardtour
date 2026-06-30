/**
 * Unified API client for GuardTour.
 * Source of truth for `window.apiFetch` and htmx auth headers.
 *
 * Auth: JWT token is stored in an httpOnly cookie set by the server.
 * The cookie is automatically sent with same-origin requests.
 * For fetch(), we use credentials: 'include' to ensure cookies are sent.
 */

import { logout } from './dom.js';

export async function api(url, options = {}) {
  const res = await fetch(url, {
    credentials: 'include',  // Send httpOnly auth cookie
    ...options,
    headers: {
      ...(options.body && typeof options.body === 'string' ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
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

/* htmx: redirect to login on 401 */
document.addEventListener('htmx:beforeOnLoad', (e) => {
  if (e.detail.xhr.status === 401) {
    logout();
  }
});
