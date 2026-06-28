/**
 * Bridge from bundled module world to legacy inline scripts/templates.
 *
 * Loaded by base_app.html so `window.apiFetch`, `window.showToast`,
 * `window.$, window.api`, etc. are all defined from one place and
 * available to both inline handlers and htmx consumers.
 */

import '../utils/api.js';
import '../utils/dom.js';
import '../utils/toast.js';

export {};
