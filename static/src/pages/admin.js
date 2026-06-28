import '../styles/main.css';
import { $ } from '../utils/dom.js';
import { toast } from '../utils/toast.js';

let usersData = [];
let orgsData = [];
let isLoading = false;
let editingUserId = null;
let editingOrgId = null;
let adminToken = null;

function getToken() {
  if (!adminToken) {
    try { adminToken = JSON.parse(localStorage.getItem('gt_user') || '{}').token; } catch {}
  }
  return adminToken;
}

function apiOpts(method, body) {
  const opts = {
    method,
    headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' }
  };
  if (body) opts.body = JSON.stringify(body);
  return opts;
}

window.loadAdminData = async function() {
  if (isLoading) return;
  isLoading = true;
  try {
    const [usersRes, orgsRes] = await Promise.all([
      fetch('/api/profiles/', apiOpts('GET')),
      fetch('/api/organizations/', apiOpts('GET'))
    ]);
    if (!usersRes.ok) throw new Error('Failed to load users');
    if (!orgsRes.ok) throw new Error('Failed to load organizations');

    usersData = await usersRes.json();
    orgsData = await orgsRes.json();

    updateUsersList();
    updateOrgsList();

    const orgSelect = $('newOrgId');
    if (orgSelect) orgSelect.innerHTML = '<option value="">-- No Organization (System Admin only) --</option>' +
      orgsData.map(o => `<option value="${o.id}">${o.name}</option>`).join('');
  } catch (error) {
    console.error('Error loading admin data:', error);
  } finally {
    isLoading = false;
  }
};

function updateUsersList() {
  const usersList = $('usersList');
  if (!usersList) return;
  let html = '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;min-width:600px;"><thead><tr><th>Username</th><th>Email</th><th>Role</th><th>Organization</th><th>Actions</th></tr></thead><tbody>';
  if (usersData && usersData.length > 0) {
    usersData.forEach(u => {
      const roleBadge = u.role === 'admin' ? '<span style="background:#f44336;color:white;padding:2px 6px;border-radius:3px;font-size:0.85em;">Admin</span>'
        : u.role === 'supervisor' ? '<span style="background:#ff9800;color:white;padding:2px 6px;border-radius:3px;font-size:0.85em;">Supervisor</span>'
        : '<span style="background:#4caf50;color:white;padding:2px 6px;border-radius:3px;font-size:0.85em;">Guard</span>';
      html += `<tr>
        <td>${u.username || 'N/A'}</td>
        <td>${u.email || 'N/A'}</td>
        <td>${roleBadge}</td>
        <td>${u.organization_name || '<em>None</em>'}</td>
        <td>
          <button type="button" onclick="showUserForm(true,'${u.id}')" style="margin-right:5px;padding:4px 8px;background:#2a2a35;color:white;border:none;border-radius:3px;cursor:pointer;">Edit</button>
          <button type="button" onclick="deleteUser('${u.id}')" style="padding:4px 8px;background:#c62828;color:white;border:none;border-radius:3px;cursor:pointer;">Delete</button>
        </td>
      </tr>`;
    });
  } else {
    html += '<tr><td colspan="5" style="text-align:center;padding:20px;">No users found</td></tr>';
  }
  html += '</tbody></table></div>';
  usersList.innerHTML = html;
}

function updateOrgsList() {
  const orgsList = $('orgsList');
  if (!orgsList) return;
  let html = '<table style="width:100%;border-collapse:collapse;"><thead><tr><th>Organization Name</th><th>Created</th><th>Actions</th></tr></thead><tbody>';
  if (orgsData && orgsData.length > 0) {
    orgsData.forEach(o => {
      html += `<tr>
        <td>${o.name || 'Unnamed'}</td>
        <td>${new Date(o.created_at).toLocaleDateString()}</td>
        <td>
          <button type="button" onclick="editOrganization('${o.id}')" style="margin-right:5px;padding:4px 8px;background:#2a2a35;color:white;border:none;border-radius:3px;cursor:pointer;">Edit</button>
          <button type="button" onclick="deleteOrganization('${o.id}')" style="padding:4px 8px;background:#c62828;color:white;border:none;border-radius:3px;cursor:pointer;">Delete</button>
        </td>
      </tr>`;
    });
  } else {
    html += '<tr><td colspan="3" style="text-align:center;padding:20px;">No organizations found</td></tr>';
  }
  html += '</tbody></table>';
  orgsList.innerHTML = html;
}

window.showUserForm = function(editMode, userId) {
  editingUserId = userId;
  const form = $('userForm');
  const title = $('userFormTitle');
  if (!form) return;
  if (editMode && userId) {
    if (title) title.innerText = 'Edit User';
    const user = usersData.find(u => String(u.id) === String(userId));
    if (user) {
      if ($('newUsername')) { $('newUsername').value = user.username || ''; $('newUsername').readOnly = true; $('newUsername').style.background = '#2a2a35'; }
      if ($('newEmail')) { $('newEmail').value = user.email || ''; $('newEmail').readOnly = true; $('newEmail').style.background = '#2a2a35'; }
      if ($('newPassword')) $('newPassword').value = '';
      if ($('newRole')) $('newRole').value = user.role;
      if ($('newOrgId')) $('newOrgId').value = user.organization || '';
    }
  } else {
    if (title) title.innerText = 'Add New User';
    if ($('newUsername')) { $('newUsername').value = ''; $('newUsername').readOnly = false; $('newUsername').style.background = '#14141c'; }
    if ($('newEmail')) { $('newEmail').value = ''; $('newEmail').readOnly = false; $('newEmail').style.background = '#14141c'; }
    if ($('newPassword')) $('newPassword').value = '';
    if ($('newRole')) $('newRole').value = 'guard';
    if ($('newOrgId')) $('newOrgId').value = '';
  }
  form.style.display = 'block';
};

window.cancelUserForm = function() {
  const form = $('userForm');
  if (form) form.style.display = 'none';
  editingUserId = null;
  if ($('newUsername')) { $('newUsername').readOnly = false; $('newUsername').style.background = '#14141c'; }
  if ($('newEmail')) { $('newEmail').readOnly = false; $('newEmail').style.background = '#14141c'; }
};

window.createUser = async function() {
  const username = $('newUsername')?.value?.trim();
  const email = $('newEmail')?.value?.trim();
  const password = $('newPassword')?.value;
  const role = $('newRole')?.value;
  const orgId = $('newOrgId')?.value;
  if (!username) { toast('Username is required', true); return; }
  if (!email) { toast('Email is required', true); return; }
  if (!password && !editingUserId) { toast('Password is required for new users', true); return; }
  if (!role) { toast('Role is required', true); return; }
  if (editingUserId) {
    toast('User editing limited to profile fields', true);
    cancelUserForm();
    loadAdminData();
    return;
  }
  try {
    const res = await fetch('/api/register/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, email, role, organization_id: orgId || null })
    });
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.error || 'Failed to create user');
    }
    cancelUserForm();
    toast('User created');
    loadAdminData();
  } catch (error) {
    toast('Failed to create user: ' + error.message, true);
  }
};

window.deleteUser = async function(id) {
  if (!confirm('Delete user?\n\nThis action cannot be undone.')) return;
  try {
    const res = await fetch(`/api/profiles/${id}/`, apiOpts('DELETE'));
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.error || 'Failed to delete user');
    }
    toast('User deleted');
    loadAdminData();
  } catch (error) {
    toast('Failed to delete user: ' + error.message, true);
  }
};

window.showOrgForm = function(editMode, orgId) {
  editingOrgId = orgId;
  const title = $('orgFormTitle');
  const form = $('orgForm');
  if (!form) return;
  if (editMode && orgId) {
    if (title) title.innerText = 'Edit Organization';
    const org = orgsData.find(o => o.id === orgId);
    if (org) {
      if ($('orgName')) $('orgName').value = org.name || '';
      if ($('orgDesc')) $('orgDesc').value = org.description || '';
    }
  } else {
    if (title) title.innerText = 'Add New Organization';
    if ($('orgName')) $('orgName').value = '';
    if ($('orgDesc')) $('orgDesc').value = '';
  }
  form.style.display = 'block';
};

window.cancelOrgForm = function() {
  const form = $('orgForm');
  if (form) form.style.display = 'none';
  editingOrgId = null;
};

window.createOrganization = async function() {
  const name = $('orgName')?.value?.trim();
  const desc = $('orgDesc')?.value;
  if (!name) { toast('Organization name is required', true); return; }
  try {
    const res = await fetch('/api/organizations/', apiOpts('POST', { name, address: desc }));
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.error || 'Failed to create organization');
    }
    cancelOrgForm();
    toast('Organization created');
    loadAdminData();
  } catch (error) {
    toast('Failed to create organization: ' + error.message, true);
  }
};

window.editOrganization = async function(orgId) {
  toast('Organization editing feature coming soon');
};

window.deleteOrganization = async function(orgId) {
  if (!confirm('Delete organization?\n\nThis will also delete all associated routes, checkpoints, and scan data.\n\nThis action cannot be undone.')) return;
  try {
    const res = await fetch(`/api/organizations/${orgId}/`, apiOpts('DELETE'));
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.error || 'Failed to delete organization');
    }
    toast('Organization deleted');
    loadAdminData();
  } catch (error) {
    toast('Failed to delete organization: ' + error.message, true);
  }
};

loadAdminData();
