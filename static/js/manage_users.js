function filterUsers() {
  var search = document.getElementById('user-search').value.toLowerCase().trim();
  var office = document.getElementById('user-office-filter').value.toLowerCase();
  var role   = document.getElementById('user-role-filter').value.toLowerCase();
  var rows   = document.querySelectorAll('.user-row[data-username]');
  var visible = 0;
  rows.forEach(function(row) {
    var matchSearch = !search ||
      row.dataset.name.includes(search) ||
      row.dataset.username.includes(search) ||
      row.dataset.email.includes(search);
    var matchOffice = !office || row.dataset.office === office;
    var matchRole   = !role   || row.dataset.role === role;
    var show = matchSearch && matchOffice && matchRole;
    row.style.display = show ? '' : 'none';
    if (show) visible++;
  });
  var countEl = document.getElementById('user-count');
  if (countEl) countEl.textContent = visible + ' user' + (visible !== 1 ? 's' : '');
}

document.addEventListener('DOMContentLoaded', function() {
  var search = document.getElementById('user-search');
  var office = document.getElementById('user-office-filter');
  var role   = document.getElementById('user-role-filter');
  if (search) search.addEventListener('input', filterUsers);
  if (office) office.addEventListener('change', filterUsers);
  if (role)   role.addEventListener('change', filterUsers);
  filterUsers();
});

function openPwdModal(username) {
  document.getElementById('pwdUser').textContent = username;
  document.getElementById('pwdForm').action = '/change-password/' + username;
  document.getElementById('pwdModal').classList.add('active');
  document.getElementById('new_password').focus();
}

function closePwdModal(event) {
  document.getElementById('pwdModal').classList.remove('active');
  document.getElementById('new_password').value = '';
  document.getElementById('confirm_password').value = '';
}

// Edit User Modal Functions
function openEditModal(btn) {
  var username  = btn.getAttribute('data-username');
  var fullName  = btn.getAttribute('data-fullname');
  var email     = btn.getAttribute('data-email') || '';
  var role      = btn.getAttribute('data-role');
  var office    = btn.getAttribute('data-office');
  var documents = btn.getAttribute('data-documents') || '';

  document.getElementById('editUser').textContent     = username;
  document.getElementById('editUsername').value       = username;
  document.getElementById('editNewUsername').value    = username;
  document.getElementById('editEmail').value          = email;
  document.getElementById('editFullName').value       = fullName;
  document.getElementById('editRole').value           = role;
  document.getElementById('editOffice').value         = office;
  document.getElementById('editDocuments').value      = documents;
  document.getElementById('editForm').action          = '/edit-user/' + username;
  document.getElementById('editModal').classList.add('active');
  document.getElementById('editNewUsername').focus();
}

function closeEditModal() {
  document.getElementById('editModal').classList.remove('active');
  document.getElementById('editDocuments').value = '';
}

// Close modal on Escape key
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    closePwdModal();
    closeEditModal();
  }
});