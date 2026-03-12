// Global variable to store office staff data
var officeStaffData = {};

function initOfficeStaff(data) {
    officeStaffData = data;
}

function confirmDeleteOffice(slug, name) {
  document.getElementById('deleteOfficeName').textContent = name;
  document.getElementById('deleteForm').action = '/delete-office/' + encodeURIComponent(slug);
  document.getElementById('deleteModal').classList.add('active');
}

function closeDeleteModal() {
  document.getElementById('deleteModal').classList.remove('active');
}

function openRecipientModal(slug, name, currentRecipient) {
  document.getElementById('recipientOfficeName').textContent = name;
  document.getElementById('recipientOfficeSlug').value = slug;

  const select = document.getElementById('primaryRecipientSelect');
  select.innerHTML = '<option value="">— Auto-assign to first staff —</option>';

  const staffList = officeStaffData[slug] || [];
  for (let i = 0; i < staffList.length; i++) {
    const staff = staffList[i];
    const option = document.createElement('option');
    option.value = staff.username;
    option.textContent = staff.full_name + ' (' + staff.username + ')';
    select.appendChild(option);
  }

  select.value = currentRecipient || '';
  document.getElementById('recipientModal').classList.add('active');
}

function closeRecipientModal() {
  document.getElementById('recipientModal').classList.remove('active');
}

// Close modal when clicking outside
document.addEventListener('DOMContentLoaded', function() {
  const deleteModal = document.getElementById('deleteModal');
  if (deleteModal) {
    deleteModal.addEventListener('click', function(e) {
      if (e.target === this) {
        closeDeleteModal();
      }
    });
  }

  const recipientModal = document.getElementById('recipientModal');
  if (recipientModal) {
    recipientModal.addEventListener('click', function(e) {
      if (e.target === this) {
        closeRecipientModal();
      }
    });
  }
});
