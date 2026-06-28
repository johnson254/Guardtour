import '../styles/main.css';

window.register = async function() {
  const username = document.getElementById('username').value;
  const email = document.getElementById('email').value;
  const password = document.getElementById('password').value;
  try {
    const res = await fetch('/api/register/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, email, password })
    });
    const data = await res.json();
    if (res.ok) {
      if (!data.role || !data.organization_name) {
        const errEl = document.getElementById('errorMsg');
        if (errEl) errEl.innerText = 'Incomplete profile data from server';
        return;
      }
      const orgId = Array.isArray(data.organization_id) ? data.organization_id[0] : data.organization_id;
      try {
        localStorage.setItem('gt_user', JSON.stringify({
          token: data.access, username, role: data.role,
          userId: data.user?.id, organization_id: orgId,
          organization_name: data.organization_name
        }));
      } catch (e) {
        const errEl = document.getElementById('errorMsg');
        if (errEl) errEl.innerText = 'Failed to save session locally';
        return;
      }
      window.location.href = '/dashboard/';
    } else {
      const errEl = document.getElementById('errorMsg');
      if (errEl) errEl.innerText = data.error || 'Registration failed';
    }
  } catch (e) {
    const errEl = document.getElementById('errorMsg');
    if (errEl) errEl.innerText = 'Connection error';
  }
};
