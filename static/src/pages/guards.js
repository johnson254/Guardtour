import '../styles/main.css';

// Guards page — all data fetching is handled by htmx.
// This module only handles UI interactions that htmx can't manage.

window.showGuardForm = function() {
  const form = document.getElementById('guardForm');
  if (form) form.style.display = 'block';
  const title = document.getElementById('guardFormTitle');
  if (title) title.innerText = 'Add Guard';
};

window.cancelGuard = function() {
  const form = document.getElementById('guardForm');
  if (form) form.style.display = 'none';
};
