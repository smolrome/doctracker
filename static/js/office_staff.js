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
  document.getElementById('primaryRecipientSelect').value = currentRecipient || '';
  document.getElementById('recipientModal').classList.add('active');
}

function closeRecipientModal() {
  document.getElementById('recipientModal').classList.remove('active');
}

// Close modal when clicking outside
document.getElementById('deleteModal').addEventListener('click', function(e) {
  if (e.target === this) {
    closeDeleteModal();
  }
});

document.getElementById('recipientModal').addEventListener('click', function(e) {
  if (e.target === this) {
    closeRecipientModal();
  }
});