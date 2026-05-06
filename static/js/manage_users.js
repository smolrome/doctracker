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