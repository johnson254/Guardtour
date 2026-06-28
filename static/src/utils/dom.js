/**
 * Shared DOM utilities for GuardTour.
 * Replaces the per-template `$ = id => document.getElementById(id)` pattern.
 */

export const $ = (id) => document.getElementById(id);

export const byId = (id) => document.getElementById(id);

export const bySel = (sel) => Array.from(document.querySelectorAll(sel));

export const escHtml = (str) => {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
};

export const debounce = (fn, ms) => {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
};

export const getToken = () => {
  try {
    const raw = localStorage.getItem('gt_user');
    if (!raw) return null;
    return JSON.parse(raw).token || null;
  } catch {
    return null;
  }
};

export const logout = () => {
  localStorage.removeItem('gt_user');
  window.location.href = '/';
};
