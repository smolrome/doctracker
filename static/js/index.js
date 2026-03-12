// ── Stats filter ──────────────────────────────────────────────────────────
function statFilter(status) {
  const params = new URLSearchParams(window.location.search);
  params.set('status', status);
  params.delete('page');
  window.location.href = '/?' + params.toString();
}

// ── Office QR Modal ───────────────────────────────────────────────────────
function openOqsModal() {
  document.getElementById('oqs-modal-overlay').classList.add('open');
  document.getElementById('oqs-search').focus();
}

function closeOqsModal() {
  document.getElementById('oqs-modal-overlay').classList.remove('open');
}

function filterOffices(query) {
  const q     = query.toLowerCase().trim();
  const cards = document.querySelectorAll('.oqs-card');
  let visible = 0;
  cards.forEach(function (card) {
    const show = !q || (card.dataset.name || '').includes(q);
    card.classList.toggle('hidden', !show);
    if (show) visible++;
  });
  document.getElementById('oqs-count').textContent =
    visible + ' office' + (visible !== 1 ? 's' : '') + (q ? ' found' : ' registered');
  document.getElementById('oqs-none').classList.toggle('visible', visible === 0);
}

document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') closeOqsModal();
  if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {
    e.preventDefault();
    openOqsModal();
    document.getElementById('oqs-search').focus();
  }
});


// ── Filter helpers ────────────────────────────────────────────────────────
function toggleTimeRange(on) {
  document.getElementById('time-range-row').style.display = on ? 'flex' : 'none';
  if (!on) {
    document.querySelector('[name="time_from"]').value = '';
    document.querySelector('[name="time_to"]').value   = '';
    document.getElementById('filter-form').submit();
  }
}

function setToday() {
  document.querySelector('[name="date"]').value = new Date().toISOString().slice(0, 10);
  document.getElementById('filter-form').submit();
}

function setType(val) {
  document.getElementById('type-hidden').value = val;
  document.getElementById('filter-form').submit();
}

function setSource(val) {
  const params = new URLSearchParams(window.location.search);
  params.set('source', val);
  params.delete('page');
  window.location.href = '/?' + params.toString();
}

function clearField(name, val) {
  if (val === undefined) val = '';
  const el = document.querySelector('[name="' + name + '"]');
  if (el) el.value = val;
  document.getElementById('filter-form').submit();
}


// ── Modal data ─────────────────────────────────────────────────────────────
var modalCurrentOffice  = null;
var currentUserName     = null;
var currentUserRole     = null;
var officesData         = {};
var sortedOffices       = [];
var transferSingleDocId = null;

function initModalData() {
  try {
    officesData   = JSON.parse(document.getElementById('offices-data')?.textContent   || '{}');
    sortedOffices = JSON.parse(document.getElementById('sorted-offices')?.textContent || '[]');

    const officeEl = document.getElementById('current-office-data');
    modalCurrentOffice = officeEl ? JSON.parse(officeEl.textContent || 'null') : null;

    if (typeof serverSessionData !== 'undefined') {
      currentUserName = serverSessionData.full_name || serverSessionData.username || null;
      currentUserRole = serverSessionData.role || null;
      if (!modalCurrentOffice && serverSessionData.office) {
        modalCurrentOffice = serverSessionData.office;
      }
    }
  } catch (e) {
    console.error('initModalData error:', e);
    officesData    = {};
    sortedOffices  = [];
    modalCurrentOffice = (typeof serverSessionData !== 'undefined' && serverSessionData.office)
      ? serverSessionData.office : null;
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initModalData);
} else {
  initModalData();
}


// ── Misc ──────────────────────────────────────────────────────────────────
(function () {
  const sd = document.getElementById('slip-date');
  if (sd) sd.value = new Date().toISOString().slice(0, 10);
})();

function changePerPage(val) {
  const url = new URL(window.location.href);
  url.searchParams.set('per_page', val);
  url.searchParams.set('page', 1);
  window.location = url.toString();
}

function rowClick(e, docId) {
  if (e.target.type === 'checkbox') return;
  window.location = '/view/' + docId;
}


// ── Routing Modal ─────────────────────────────────────────────────────────
function openRoutingModal() {
  openModal('routing-modal');
  updateSelectedPreview();
  const sd = document.getElementById('slip-date');
  if (sd && !sd.value) sd.value = new Date().toISOString().slice(0, 10);

  // Reset submit button in case it was disabled from a previous attempt
  const btn = document.querySelector('.btn-route');
  if (btn) {
    btn.disabled = false;
    btn.textContent = '🚀 Create Routing Slip';
  }
}

function closeRoutingModal() { closeModal('routing-modal'); }


// ── Transfer Modal ────────────────────────────────────────────────────────
function openTransferModal() {
  const checked = document.querySelectorAll('.doc-checkbox:checked');
  if (checked.length === 0) {
    alert('Please select at least one document to transfer.');
    return;
  }

  document.getElementById('transfer-sel-count').textContent = checked.length + ' selected';

  // Reset all steps
  document.getElementById('transfer-type').value   = '';
  document.getElementById('transfer-office').innerHTML = '<option value="">— Select Office —</option>';
  document.getElementById('transfer-office').disabled  = true;
  document.getElementById('transfer-office-info').textContent = '';
  document.getElementById('transfer-staff').innerHTML = '<option value="">— Select Staff —</option>';
  document.getElementById('transfer-staff').disabled  = true;

  // Reset transfer button
  const btn = document.getElementById('btn-do-transfer');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '🔄 Transfer Documents';
  }

  _hideTransferBlock('transfer-office-block');
  _hideTransferBlock('transfer-staff-block');
  _hideTransferBlock('transfer-submit-block');

  openModal('transfer-modal');
}

function closeTransferModal() { closeModal('transfer-modal'); }

// Internal helpers
function _showTransferBlock(id) { const el = document.getElementById(id); if (el) el.style.display = 'block'; }
function _hideTransferBlock(id) { const el = document.getElementById(id); if (el) el.style.display = 'none';  }

function onTransferTypeChangeIndex() {
  const type        = document.getElementById('transfer-type').value;
  const officeSelect = document.getElementById('transfer-office');
  const staffSelect  = document.getElementById('transfer-staff');

  staffSelect.innerHTML = '<option value="">— Select Staff —</option>';
  staffSelect.disabled  = true;
  const btn = document.getElementById('btn-do-transfer');
  if (btn) btn.disabled = true;

  if (!type) {
    _hideTransferBlock('transfer-office-block');
    _hideTransferBlock('transfer-staff-block');
    _hideTransferBlock('transfer-submit-block');
    return;
  }

  if (type === 'inside_office') {
    const label = document.getElementById('transfer-office-label');
    if (label) label.textContent = 'Step 2: Your Office';

    officeSelect.innerHTML = '<option value="' + modalCurrentOffice + '">' + modalCurrentOffice + '</option>';
    officeSelect.value     = modalCurrentOffice;
    officeSelect.disabled  = true;
    const info = document.getElementById('transfer-office-info');
    if (info) info.textContent = '📍 Auto-selected: your office';

    _showTransferBlock('transfer-office-block');
    _populateTransferStaff(modalCurrentOffice);
    _showTransferBlock('transfer-staff-block');
  } else {
    const label = document.getElementById('transfer-office-label');
    if (label) label.textContent = 'Step 2: Select Office';

    let options = '<option value="">— Select Office —</option>';
    for (const office of sortedOffices) {
      if (office === 'No Office' || office === modalCurrentOffice) continue;
      options += '<option value="' + office + '">' + office + '</option>';
    }
    officeSelect.innerHTML = options;
    officeSelect.disabled  = false;
    const info = document.getElementById('transfer-office-info');
    if (info) info.textContent = '';

    _showTransferBlock('transfer-office-block');
  }
}

function updateTransferStaffIndex() {
  const office = document.getElementById('transfer-office').value;
  _hideTransferBlock('transfer-staff-block');
  _hideTransferBlock('transfer-submit-block');
  if (!office) return;
  _populateTransferStaff(office);
  _showTransferBlock('transfer-staff-block');
}

function _populateTransferStaff(office) {
  const staffSelect = document.getElementById('transfer-staff');
  staffSelect.innerHTML = '<option value="">— Select Staff —</option>';
  if (!office || !officesData[office]) return;
  for (const s of officesData[office]) {
    const name = s.full_name || s.username;
    staffSelect.innerHTML += '<option value="' + s.username + '">' + name + ' (@' + s.username + ')</option>';
  }
  staffSelect.disabled = false;
}

function onTransferStaffChangeIndex() {
  const val = document.getElementById('transfer-staff').value;
  if (val) {
    _showTransferBlock('transfer-submit-block');
    const btn = document.getElementById('btn-do-transfer');
    if (btn) btn.disabled = false;
  } else {
    _hideTransferBlock('transfer-submit-block');
  }
}

function submitTransfer() {
  const csrfToken    = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const transferType = document.getElementById('transfer-type').value;
  const office       = document.getElementById('transfer-office').value || modalCurrentOffice;
  const staff        = document.getElementById('transfer-staff').value;
  const selectedIds  = Array.from(document.querySelectorAll('.doc-checkbox:checked')).map(function (c) { return c.value; });

  if (!transferType || !staff) {
    alert('Please complete all steps before transferring.');
    return;
  }

  if (!transferSingleDocId && !selectedIds.length) {
    alert('Please select at least one document to transfer.');
    return;
  }

  // ── GUARD: prevent double-submit ──
  const btn = document.getElementById('btn-do-transfer');
  if (btn) {
    if (btn.disabled) return;   // already submitted
    btn.disabled = true;
    btn.textContent = '⏳ Transferring…';
  }

  const form = document.createElement('form');
  form.method = 'POST';

  let fields;
  if (transferSingleDocId) {
    form.action = '/transfer/' + transferSingleDocId;
    fields = [['transfer_type', transferType], ['new_office', office], ['new_staff', staff], ['_csrf_token', csrfToken]];
  } else {
    form.action = '/transfer-batch';
    fields = [['doc_ids', selectedIds.join(',')], ['transfer_type', transferType], ['new_office', office], ['new_staff', staff], ['_csrf_token', csrfToken]];
  }

  fields.forEach(function ([name, value]) {
    const input = document.createElement('input');
    input.type = 'hidden'; input.name = name; input.value = value;
    form.appendChild(input);
  });

  document.body.appendChild(form);
  form.submit();
}


// ── Selection ──────────────────────────────────────────────────────────────
function updateSelectedPreview() {
  const checked = document.querySelectorAll('.doc-checkbox:checked');
  const n = checked.length;

  const countEl = document.getElementById('sel-count');
  if (countEl) countEl.textContent = n + ' selected';

  const preview = document.getElementById('selected-preview');
  const list    = document.getElementById('selected-list');
  if (preview && list) {
    if (n === 0) {
      preview.style.display = 'none';
      list.innerHTML = '';
    } else {
      preview.style.display = 'block';
      list.innerHTML = Array.from(checked).map(function (cb, i) {
        const row  = cb.closest('tr');
        const name = row ? row.querySelector('.doc-name') : null;
        return '<div style="padding:3px 0;border-bottom:1px solid rgba(255,255,255,.1)">' +
               (i + 1) + '. ' + (name ? name.textContent.trim() : cb.value) + '</div>';
      }).join('');
    }
  }
}

function updateSelection() {
  const checked = document.querySelectorAll('.doc-checkbox:checked');
  const n = checked.length;

  // Highlight selected rows
  document.querySelectorAll('.doc-checkbox').forEach(function (cb) {
    cb.closest('tr').classList.toggle('row-selected', cb.checked);
  });

  const slipBtn     = document.getElementById('btn-create-slip');
  const transferBtn = document.getElementById('btn-transfer');

  if (slipBtn) {
    slipBtn.classList.toggle('selection-active', n > 0);
    const badge = document.getElementById('slip-sel-badge');
    if (badge) badge.textContent = n > 0 ? n + ' doc' + (n > 1 ? 's' : '') : '';
  }

  if (transferBtn) {
    transferBtn.classList.toggle('selection-active', n > 0);
    const badge = document.getElementById('transfer-sel-badge');
    if (badge) badge.textContent = n > 0 ? n + ' doc' + (n > 1 ? 's' : '') : '';
  }

  updateSelectedPreview();
}

// Select-all checkbox
const selAll = document.getElementById('select-all');
if (selAll) {
  selAll.addEventListener('change', function () {
    document.querySelectorAll('.doc-checkbox').forEach(function (cb) {
      cb.checked = selAll.checked;
      cb.closest('tr').classList.toggle('row-selected', selAll.checked);
    });
    updateSelection();
  });
}


// ── Routing modal — time range ─────────────────────────────────────────────
function toggleModalTimeRange(on) {
  document.getElementById('time-from-field').style.display = on ? '' : 'none';
  document.getElementById('time-to-field').style.display   = on ? '' : 'none';
  document.getElementById('btn-auto-select').style.display = on ? '' : 'none';
  if (!on) {
    document.getElementById('time-from').value = '';
    document.getElementById('time-to').value   = '';
  }
}

function autoSelectByTime() {
  const useTime = document.getElementById('use-time-range').checked;
  const tf = document.getElementById('time-from').value;
  const tt = document.getElementById('time-to').value;
  const sd = document.getElementById('slip-date').value;

  if (useTime && (!tf || !tt)) {
    alert('Please set both a Time From and Time To, or uncheck Include Time Range.');
    return;
  }

  let count = 0;
  document.querySelectorAll('.doc-checkbox').forEach(function (cb) {
    const row = cb.closest('tr');
    const ts  = row.dataset.createdAt || '';
    let inRange = false;
    if (ts) {
      const dateOk = !sd || ts.slice(0, 10) === sd;
      const timeOk = ts.slice(11, 16) >= tf && ts.slice(11, 16) <= tt;
      inRange = dateOk && timeOk;
    }
    cb.checked = inRange;
    row.classList.toggle('row-selected', inRange);
    if (inRange) count++;
  });

  updateSelection();

  if (count === 0) {
    alert('No documents found in that date/time range.');
  } else {
    const btn  = document.querySelector('.btn-time-filter');
    const orig = btn.textContent;
    btn.textContent = '✅ ' + count + ' selected';
    setTimeout(function () { btn.textContent = orig; }, 2000);
  }
}


// ── Submit routing slip ────────────────────────────────────────────────────
function submitRouting() {
  const dest = document.getElementById('route-dest').value.trim();
  if (!dest) {
    const el = document.getElementById('route-dest');
    el.focus();
    el.style.borderColor = '#FCA5A5';
    el.style.background  = 'rgba(220,38,38,.15)';
    setTimeout(function () { el.style.borderColor = ''; el.style.background = ''; }, 2500);
    return;
  }

  const ids = Array.from(document.querySelectorAll('.doc-checkbox:checked')).map(function (cb) { return cb.value; });
  if (!ids.length) { alert('No documents selected.'); return; }

  // ── GUARD: prevent double-submit ──
  const btn = document.querySelector('.btn-route');
  if (btn) {
    if (btn.disabled) return;   // already submitted
    btn.disabled = true;
    btn.textContent = '⏳ Creating slip…';
  }

  // Prepare form data
  const formData = new FormData();
  formData.append('doc_ids', ids.join(','));
  formData.append('destination', dest);
  formData.append('notes', document.getElementById('route-notes').value || '');
  formData.append('slip_date', document.getElementById('slip-date').value || '');
  formData.append('time_from', document.getElementById('time-from').value || '');
  formData.append('time_to', document.getElementById('time-to').value || '');
  
  // Get CSRF token
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  if (csrfToken) {
    formData.append('_csrf_token', csrfToken);
  }

  // Use fetch API for AJAX request
  fetch('/routing-slip/create', {
    method: 'POST',
    body: formData,
    headers: {
      'X-Requested-With': 'XMLHttpRequest'
    }
  })
  .then(function (response) { return response.json(); })
  .then(function (data) {
    if (data.success) {
      // Close the routing modal
      closeRoutingModal();
      
      // Display the routing slip result in modal
      displayRoutingSlipModal(data);
      
      // Clear selections
      document.querySelectorAll('.doc-checkbox:checked').forEach(function (cb) {
        cb.checked = false;
        cb.closest('tr').classList.remove('row-selected');
      });
      updateSelection();
      
      // Reset the form
      document.getElementById('route-dest').value = '';
      document.getElementById('route-notes').value = '';
      document.getElementById('modal-dest-preview').textContent = '(enter destination below)';
    } else {
      alert(data.error || 'Failed to create routing slip.');
      if (btn) {
        btn.disabled = false;
        btn.textContent = '🚀 Create Routing Slip';
      }
    }
  })
  .catch(function (err) {
    console.error('Error creating routing slip:', err);
    alert('An error occurred while creating the routing slip.');
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🚀 Create Routing Slip';
    }
  });
}

// Display routing slip in modal
function displayRoutingSlipModal(data) {
  const content = document.getElementById('routing-slip-content');
  
  // Format date
  const slipDate = data.slip_date || data.created_at.slice(0, 10);
  const slipTime = data.created_at.slice(11, 19);
  const timeCovered = (data.time_from || data.time_to) ? 
    `<div class="meta-cell">
      <div class="meta-label">Time Covered</div>
      <div class="meta-val">${data.time_from || '—'} – ${data.time_to || '—'}</div>
    </div>` : '';
  
  // Build documents table
  let docsHtml = '';
  data.docs.forEach(function (doc, index) {
    docsHtml += `
      <tr>
        <td class="num-cell">${index + 1}</td>
        <td>
          <div class="doc-name">${doc.doc_name || '—'}</div>
          ${doc.doc_id ? `<div class="doc-ref">${doc.doc_id}</div>` : ''}
          ${doc.category ? `<div class="doc-cat">${doc.category}</div>` : ''}
        </td>
        <td style="font-size:13px">${doc.sender_org || '—'}</td>
        <td style="font-size:13px">${doc.sender_name || '—'}</td>
        <td style="font-size:13px">${doc.referred_to || '—'}</td>
        <td class="sig-cell">
          <div class="sig-line"></div>
          <div class="sig-sub">Date</div>
        </td>
      </tr>
    `;
  });
  
  // Build notes section if present
  const notesHtml = data.notes ? `
    <div class="notes-strip">
      <div class="notes-lbl">📝 Notes / Instructions</div>
      <div class="notes-text">${data.notes}</div>
    </div>
  ` : '';
  
  // Build the full modal content
  content.innerHTML = `
    <div class="slip-card" style="box-shadow:none;border:1px solid #e2e8f0;">
      <!-- Meta strip -->
      <div class="meta-strip" style="background:#f8fafc;">
        <div class="meta-cell highlight">
          <div class="meta-label">Slip No.</div>
          <div class="meta-val">${data.slip_no}</div>
        </div>
        <div class="meta-cell">
          <div class="meta-label">Date</div>
          <div class="meta-val">${slipDate}</div>
        </div>
        <div class="meta-cell">
          <div class="meta-label">Time Routed</div>
          <div class="meta-val">${slipTime}</div>
        </div>
        ${timeCovered}
        <div class="meta-cell">
          <div class="meta-label">No. of Documents</div>
          <div class="meta-val">${data.doc_count}</div>
        </div>
        <div class="meta-cell">
          <div class="meta-label">Prepared By</div>
          <div class="meta-val">${data.prepared_by}</div>
        </div>
      </div>
      
      <!-- Body -->
      <div class="slip-body">
        <!-- From → To route indicator -->
        <div style="display:flex;align-items:center;gap:0;margin-bottom:16px;
                    border:1.5px solid #cbd5e1;border-radius:12px;overflow:hidden;">
          <div style="flex:1;padding:12px 18px;background:#f8fafc;">
            <div style="font-size:10px;font-weight:700;text-transform:uppercase;
                        letter-spacing:.1em;color:#64748b;margin-bottom:2px;">From Office</div>
            <div style="font-weight:800;color:#0a2540;font-size:.95rem;">
              ${data.from_office}
            </div>
          </div>
          <div style="padding:0 14px;font-size:1.4rem;color:#0e7490;font-weight:900;">→</div>
          <div style="flex:1;padding:12px 18px;background:#eff6ff;border-left:1.5px solid #cbd5e1;">
            <div style="font-size:10px;font-weight:700;text-transform:uppercase;
                        letter-spacing:.1em;color:#64748b;margin-bottom:2px;">To Office</div>
            <div style="font-weight:800;color:#1d4ed8;font-size:.95rem;">${data.destination}</div>
          </div>
        </div>
        
        ${notesHtml}
        
        <!-- Documents table -->
        <div class="docs-header">
          <div class="docs-header-title">Documents Included</div>
          <div class="docs-count-pill">${data.doc_count}</div>
        </div>
        
        <div class="tbl-wrap">
          <table class="slip-table">
            <thead>
              <tr>
                <th style="width:38px;text-align:center">#</th>
                <th>Document / Content</th>
                <th>Unit / Office / School</th>
                <th>Sender</th>
                <th>Referred To</th>
                <th class="sig-cell" style="width:120px">Date Received</th>
              </tr>
            </thead>
            <tbody>
              ${docsHtml}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
  
  // Update the print and view buttons
  document.getElementById('routing-slip-print-btn').onclick = function() {
    printRoutingSlipContent(content);
  };
  document.getElementById('routing-slip-view-btn').href = '/routing-slip/' + data.slip_id;
  
  // Store slip data for printing
  window.currentRoutingSlipData = data;
  
  // Open the modal
  openModal('routing-slip-result-modal');
}

// Close the routing slip result modal
function closeRoutingSlipResultModal() {
  closeModal('routing-slip-result-modal');
}

// Print routing slip content
function printRoutingSlipContent(content) {
  const printWindow = window.open('', '_blank');
  if (!printWindow) {
    alert('Please allow popups to print.');
    return;
  }
  
  const data = window.currentRoutingSlipData;
  printWindow.document.write(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>Routing Slip ${data.slip_no}</title>
      <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Outfit:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet"/>
      <style>
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
        body{font-family:'Outfit',sans-serif;background:#fff;color:#0A2540;padding:20px;}
        .slip-card{border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;}
        .meta-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));border-bottom:2px solid #cbd5e1;}
        .meta-cell{padding:12px 16px;border-right:1.5px solid #cbd5e1;}
        .meta-cell:last-child{border-right:none}
        .meta-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#64748b;margin-bottom:4px}
        .meta-val{font-family:'JetBrains Mono',monospace;font-size:14px;font-weight:700;color:#0A2540}
        .meta-cell.highlight{background:#fef9ec}
        .meta-cell.highlight .meta-val{color:#c8922a}
        .slip-body{padding:20px}
        .route-indicator{display:flex;align-items:center;gap:0;margin-bottom:16px;border:1.5px solid #cbd5e1;border-radius:12px;overflow:hidden;}
        .route-from{flex:1;padding:12px 18px;background:#f8fafc;}
        .route-to{flex:1;padding:12px 18px;background:#eff6ff;border-left:1.5px solid #cbd5e1;}
        .route-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#64748b;margin-bottom:2px}
        .route-office{font-weight:800;font-size:14px}
        .route-arrow{padding:0 14px;font-size:1.4rem;color:#0e7490;font-weight:900}
        .notes-strip{background:#fffaeb;border:1.5px solid #fcd34d;border-radius:12px;padding:14px 18px;margin-bottom:16px}
        .notes-lbl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#92400e;margin-bottom:6px}
        .notes-text{font-size:14px;color:#78350f}
        .docs-header{display:flex;align-items:center;gap:12px;margin-bottom:12px}
        .docs-header-title{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:#0A2540}
        .docs-count-pill{background:#0A2540;color:#fff;border-radius:20px;padding:3px 12px;font-size:12px;font-weight:700}
        .slip-table{width:100%;border-collapse:collapse;font-size:12px}
        .slip-table thead tr{background:#0A2540}
        .slip-table th{padding:10px 12px;text-align:left;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:rgba(255,255,255,.85);border-right:1px solid rgba(255,255,255,.15)}
        .slip-table th:last-child{border-right:none}
        .slip-table td{padding:10px 12px;border-bottom:1.5px solid #e2eaf1;border-right:1.5px solid #e2eaf1;vertical-align:middle}
        .slip-table td:last-child{border-right:none}
        .slip-table tr:last-child td{border-bottom:none}
        .slip-table tbody tr:nth-child(even) td{background:#f8fafb}
        .doc-name{font-weight:700;font-size:13px}
        .doc-ref{font-family:'JetBrains Mono',monospace;font-size:10px;color:#64748b;margin-top:2px}
        .doc-cat{display:inline-block;margin-top:4px;padding:2px 8px;border-radius:6px;background:#dbeafe;color:#1d4ed8;font-size:10px;font-weight:700}
        .num-cell{font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:700;color:#64748b;text-align:center}
        .sig-cell{text-align:center;min-width:80px}
        .sig-line{border-bottom:1.5px solid #0A2540;margin:20px 6px 5px;height:1px}
        .sig-sub{font-size:9px;color:#64748b}
      </style>
    </head>
    <body>
      ${content.innerHTML}
    </body>
    </html>
  `);
  printWindow.document.close();
  printWindow.focus();
  setTimeout(function() { printWindow.print(); }, 500);
}

// Legacy function for print button
function printRoutingSlip() {
  const content = document.getElementById('routing-slip-content');
  printRoutingSlipContent(content);
}

// ── Pending banner ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  const origCheck = window.checkPendingDocuments;
  if (typeof origCheck === 'function') {
    window.checkPendingDocuments = function () {
      fetch('/api/pending-count')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          const badge       = document.getElementById('pending-badge');
          const banner      = document.getElementById('pending-banner');
          const bannerCount = document.getElementById('pending-banner-count');

          if (badge) badge.textContent = data.count;
          if (bannerCount) bannerCount.textContent = data.count + ' ›';
          if (banner) banner.classList.toggle('visible', data.count > 0);
        })
        .catch(function (err) { console.error('pending-count error:', err); });
    };
    window.checkPendingDocuments();
  }
});

/* ── Sticky offset calculator ──────────────────────────────────────────────
   Measures the real nav height and cascades every sticky layer below it.
────────────────────────────────────────────────────────────────────────── */
function recalcStickyOffsets() {
  const root = document.documentElement;

  const navbar  = document.querySelector('nav');
  const navH    = navbar ? navbar.offsetHeight : 0;
  root.style.setProperty('--navbar-h', navH + 'px');

  const statsBar = document.getElementById('stats-sticky-bar');
  const statsH   = statsBar ? statsBar.offsetHeight : 0;
  root.style.setProperty('--filter-top', navH + 'px');

  const filterBar = document.getElementById('filter-sticky-bar');
  const filterH   = filterBar ? filterBar.offsetHeight : 0;
  root.style.setProperty('--thead-top', (navH + statsH) + 'px');

  const tableHead  = document.getElementById('table-action-bar');
  const tableHeadH = tableHead ? tableHead.offsetHeight : 0;
  const colHeadTop = navH + statsH + filterH;
  root.style.setProperty('--col-head-top', colHeadTop + 'px');

  root.style.setProperty('--tbody-top', (colHeadTop + tableHeadH) + 'px');
}

document.addEventListener('DOMContentLoaded', recalcStickyOffsets);
window.addEventListener('resize', recalcStickyOffsets);
window.addEventListener('load',   recalcStickyOffsets);
setTimeout(recalcStickyOffsets, 150);
setTimeout(recalcStickyOffsets, 600);