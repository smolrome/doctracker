function changeRdPerPage(val) {
  window.location.href = '/routed-documents?page=1&per_page=' + val;
}

/* Close all kebab menus when clicking outside */
document.addEventListener('click', function(e) {
  if (!e.target.closest('.kebab-cell')) {
    document.querySelectorAll('.kebab-menu.show').forEach(m => m.classList.remove('show'));
  }
});

/* Toggle kebab menu */
function toggleKebab(btn, event) {
  if (event) {
    event.stopPropagation();
    event.preventDefault();
  }
  const menu = btn.nextElementSibling;
  // Close other menus first
  document.querySelectorAll('.kebab-menu.show').forEach(m => {
    if (m !== menu) m.classList.remove('show');
  });
  menu.classList.toggle('show');
}

/* Right-click to open kebab menu */
document.addEventListener('contextmenu', function(e) {
  const cell = e.target.closest('.kebab-cell');
  if (cell) {
    e.preventDefault();
    const btn = cell.querySelector('.kebab-btn');
    const menu = cell.querySelector('.kebab-menu');
    // Close other menus first
    document.querySelectorAll('.kebab-menu.show').forEach(m => {
      if (m !== menu) m.classList.remove('show');
    });
    menu.classList.toggle('show');
  }
});

/* Edit document */
function editDocument(docId) {
  window.location.href = '/dashboard/edit/' + docId;
}

/* Delete single document */
function deleteDocument(docId, docName) {
  if (!confirm('Are you sure you want to delete "' + docName + '"? This action cannot be undone.')) {
    return;
  }
  
  fetch('/document/' + docId + '/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      alert('Document "' + docName + '" has been deleted.');
      window.location.reload();
    } else {
      alert('Error: ' + (data.message || 'Failed to delete document.'));
    }
  })
  .catch(error => {
    alert('Error: ' + error.message);
  });
}

/* Delete all documents in a slip */
function deleteAllDocs(slipId, slipNo, docCount) {
  if (!confirm('Are you sure you want to delete all ' + docCount + ' documents in slip ' + slipNo + '? This action cannot be undone.')) {
    return;
  }
  
  fetch('/routing-slip/' + slipId + '/delete-all-docs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      alert('All documents in slip ' + slipNo + ' have been deleted.');
      window.location.reload();
    } else {
      alert('Error: ' + (data.message || 'Failed to delete documents.'));
    }
  })
  .catch(error => {
    alert('Error: ' + error.message);
  });
}

/* Archive single document */
function archiveDocument(docId, docName) {
  if (!confirm('Are you sure you want to archive "' + docName + '"?')) {
    return;
  }
  
  fetch('/document/' + docId + '/archive', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      alert('Document "' + docName + '" has been archived.');
      window.location.reload();
    } else {
      alert('Error: ' + (data.message || 'Failed to archive document.'));
    }
  })
  .catch(error => {
    alert('Error: ' + error.message);
  });
}

/* Delete Routing Slip */
function deleteRoutingSlip(slipId, slipNo) {
  if (!confirm('Are you sure you want to delete routing slip ' + slipNo + '? This action cannot be undone.')) {
    return;
  }
  
  fetch('/routing-slip/' + slipId + '/delete', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    }
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      alert('Routing slip ' + slipNo + ' has been deleted.');
      window.location.reload();
    } else {
      alert('Error: ' + (data.message || 'Failed to delete routing slip.'));
    }
  })
  .catch(error => {
    alert('Error: ' + error.message);
  });
}

/* Archive Routing Slip */
function archiveRoutingSlip(slipId, slipNo) {
  if (!confirm('Are you sure you want to archive routing slip ' + slipNo + '?')) {
    return;
  }
  
  fetch('/routing-slip/' + slipId + '/archive', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    }
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      alert('Routing slip ' + slipNo + ' has been archived.');
      window.location.reload();
    } else {
      alert('Error: ' + (data.message || 'Failed to archive routing slip.'));
    }
  })
  .catch(error => {
    alert('Error: ' + error.message);
  });
}

/* Re-route Modal */
var rerouteModal = null;
var currentSlipId = null;

function openRerouteModal(slipId, currentDest) {
  currentSlipId = slipId;
  document.getElementById('reroute-dest').value = currentDest;
  document.getElementById('reroute-slip-id').value = slipId;
  document.getElementById('reroute-modal').style.display = 'flex';
}

function closeRerouteModal() {
  document.getElementById('reroute-modal').style.display = 'none';
  currentSlipId = null;
}

function submitReroute() {
  const dest = document.getElementById('reroute-dest').value.trim();
  if (!dest) {
    alert('Please enter a destination office.');
    return;
  }
  document.getElementById('reroute-form').submit();
}

/* Delete all routing slips */
function deleteAllSlips() {
  if (!confirm('Are you sure you want to delete ALL routing slips? This action cannot be undone and will remove all documents.')) {
    return;
  }
  
  fetch('/routing-slip/delete-all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      alert('All routing slips have been deleted.');
      window.location.reload();
    } else {
      alert('Error: ' + (data.message || 'Failed to delete routing slips.'));
    }
  })
  .catch(error => {
    alert('Error: ' + error.message);
  });
}

/* Archive all routing slips */
function archiveAllSlips() {
  if (!confirm('Are you sure you want to archive ALL routing slips?')) {
    return;
  }
  
  fetch('/routing-slip/archive-all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      alert('All routing slips have been archived.');
      window.location.reload();
    } else {
      alert('Error: ' + (data.message || 'Failed to archive routing slips.'));
    }
  })
  .catch(error => {
    alert('Error: ' + error.message);
  });
}