import './styles/main.css';
import { toast } from './utils/toast.js';
import './utils/api.js';
import { $ } from './utils/dom.js';

/* ONE source of truth for global helpers consumed by templates/pages */
window.$ = $;
window.showToast = toast;

/* Backward compatibility: many templates inline `apiFetch(...)` */
window.apiFetch = (url, options) =>
  import('./utils/api.js').then(m => m.api(url, options));

console.log('GuardTour frontend v2 loaded');
