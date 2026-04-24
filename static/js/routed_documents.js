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
    const menu = cell.querySelector('.kebab-menu');
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
  if (!confirm('Are you sure you want to delete "' + docName + '"? This action cannot be undone.')) return;
  fetch('/document/' + docId + '/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) { alert('Document "' + docName + '" has been deleted.'); window.location.reload(); }
    else { alert('Error: ' + (data.message || 'Failed to delete document.')); }
  })
  .catch(err => alert('Error: ' + err.message));
}

/* Delete all documents in a slip */
function deleteAllDocs(slipId, slipNo, docCount) {
  if (!confirm('Are you sure you want to delete all ' + docCount + ' documents in slip ' + slipNo + '? This action cannot be undone.')) return;
  fetch('/routing-slip/' + slipId + '/delete-all-docs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) { alert('All documents in slip ' + slipNo + ' have been deleted.'); window.location.reload(); }
    else { alert('Error: ' + (data.message || 'Failed to delete documents.')); }
  })
  .catch(err => alert('Error: ' + err.message));
}

/* Archive single document */
function archiveDocument(docId, docName) {
  if (!confirm('Are you sure you want to archive "' + docName + '"?')) return;
  fetch('/document/' + docId + '/archive', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) { alert('Document "' + docName + '" has been archived.'); window.location.reload(); }
    else { alert('Error: ' + (data.message || 'Failed to archive document.')); }
  })
  .catch(err => alert('Error: ' + err.message));
}

/* Delete Routing Slip */
function deleteRoutingSlip(slipId, slipNo) {
  if (!confirm('Are you sure you want to delete routing slip ' + slipNo + '? This action cannot be undone.')) return;
  fetch('/routing-slip/' + slipId + '/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) { alert('Routing slip ' + slipNo + ' has been deleted.'); window.location.reload(); }
    else { alert('Error: ' + (data.message || 'Failed to delete routing slip.')); }
  })
  .catch(err => alert('Error: ' + err.message));
}

/* Archive Routing Slip */
function archiveRoutingSlip(slipId, slipNo) {
  if (!confirm('Are you sure you want to archive routing slip ' + slipNo + '?')) return;
  fetch('/routing-slip/' + slipId + '/archive', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) { alert('Routing slip ' + slipNo + ' has been archived.'); window.location.reload(); }
    else { alert('Error: ' + (data.message || 'Failed to archive routing slip.')); }
  })
  .catch(err => alert('Error: ' + err.message));
}

/* ── Re-route Modal ───────────────────────────────────────────────────────── */
var _currentRerouteSlipId = null;

function openRerouteModal(slipId, currentDest) {
  _currentRerouteSlipId = slipId;
  var destEl = document.getElementById('reroute-dest');
  var slipEl = document.getElementById('reroute-slip-id');
  var modal  = document.getElementById('reroute-modal');
  if (!destEl || !slipEl || !modal) {
    console.error('Re-route modal elements not found in DOM');
    return;
  }
  destEl.value = currentDest || '';
  slipEl.value = slipId;
  modal.style.display = 'flex';
}

function closeRerouteModal() {
  var modal = document.getElementById('reroute-modal');
  if (modal) modal.style.display = 'none';
  _currentRerouteSlipId = null;
}

function submitReroute() {
  var destEl = document.getElementById('reroute-dest');
  if (!destEl || !destEl.value.trim()) {
    alert('Please enter a destination office.');
    return;
  }
  var form = document.getElementById('reroute-form');
  if (form) form.submit();
}

/* Click outside modal overlay to close — uses window.load so modal exists */
window.addEventListener('load', function () {
  var modal = document.getElementById('reroute-modal');
  if (modal) {
    modal.addEventListener('click', function (e) {
      if (e.target === modal) closeRerouteModal();
    });
  }
});

/* Delete all routing slips */
function deleteAllSlips() {
  if (!confirm('Are you sure you want to delete ALL routing slips? This action cannot be undone and will remove all documents.')) return;
  fetch('/routing-slip/delete-all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': window.CSRF_TOKEN || '' }
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) { alert('All routing slips have been deleted.'); window.location.reload(); }
    else { alert('Error: ' + (data.message || 'Failed to delete routing slips.')); }
  })
  .catch(err => alert('Error: ' + err.message));
}

/* Archive all routing slips */
function archiveAllSlips() {
  if (!confirm('Are you sure you want to archive ALL routing slips?')) return;
  fetch('/routing-slip/archive-all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': window.CSRF_TOKEN || '' }
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) { alert('All routing slips have been archived.'); window.location.reload(); }
    else { alert('Error: ' + (data.message || 'Failed to archive routing slips.')); }
  })
  .catch(err => alert('Error: ' + err.message));
}