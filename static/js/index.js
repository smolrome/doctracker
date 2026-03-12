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
  // Use base.css openModal() helper — adds .open class
  openModal('routing-modal');
  updateSelectedPreview();
  const sd = document.getElementById('slip-date');
  if (sd && !sd.value) sd.value = new Date().toISOString().slice(0, 10);
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
  if (document.getElementById('btn-do-transfer')) document.getElementById('btn-do-transfer').disabled = true;

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
  const csrfToken   = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const transferType = document.getElementById('transfer-type').value;
  const office      = document.getElementById('transfer-office').value || modalCurrentOffice;
  const staff       = document.getElementById('transfer-staff').value;
  const selectedIds = Array.from(document.querySelectorAll('.doc-checkbox:checked')).map(function (c) { return c.value; });

  if (!transferType || !staff) {
    alert('Please complete all steps before transferring.');
    return;
  }

  if (!transferSingleDocId && !selectedIds.length) {
    alert('Please select at least one document to transfer.');
    return;
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

  // CHANGED: toggle .selection-active instead of display:none/flex
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

  document.getElementById('routing-doc-ids').value    = ids.join(',');
  document.getElementById('routing-dest-field').value = dest;
  document.getElementById('routing-notes').value      = document.getElementById('route-notes').value;
  document.getElementById('routing-slip-date').value  = document.getElementById('slip-date').value;
  document.getElementById('routing-time-from').value  = document.getElementById('time-from').value;
  document.getElementById('routing-time-to').value    = document.getElementById('time-to').value;
  document.getElementById('routing-form').submit();
}

// ── Pending banner ─────────────────────────────────────────────────────────
/*
  CHANGED: banner visibility now controlled with .visible class
  instead of inline style. The base.js checkPendingDocuments()
  still updates #pending-banner-count and controls banner
  visibility — but we patch it here so it uses the CSS class.
*/
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
    // Run immediately after patching
    window.checkPendingDocuments();
  }
});

/* ── Sticky offset calculator ──────────────────────────────────────────────
   Measures the real nav height (works with base.html's plain <nav> tag)
   and cascades every sticky layer below it.
────────────────────────────────────────────────────────────────────────── */
function recalcStickyOffsets() {
  const root = document.documentElement;

  /* Use offsetHeight — this is the CSS layout height, independent of
     scroll position (unlike getBoundingClientRect which shifts as you scroll).
     Each sticky layer's top = sum of all layers above it. */

  const navbar  = document.querySelector('nav');
  const navH    = navbar ? navbar.offsetHeight : 0;
  root.style.setProperty('--navbar-h', navH + 'px');

  /* Stats bar → sticks at navH */
  const statsBar = document.getElementById('stats-sticky-bar');
  const statsH   = statsBar ? statsBar.offsetHeight : 0;
  root.style.setProperty('--filter-top', navH + 'px');

  /* Filter bar → sticks at navH + statsH */
  const filterBar = document.getElementById('filter-sticky-bar');
  const filterH   = filterBar ? filterBar.offsetHeight : 0;
  root.style.setProperty('--thead-top', (navH + statsH) + 'px');

  /* Table action bar → sticks at navH + statsH + filterH */
  const tableHead  = document.getElementById('table-action-bar');
  const tableHeadH = tableHead ? tableHead.offsetHeight : 0;
  const colHeadTop = navH + statsH + filterH;
  root.style.setProperty('--col-head-top', colHeadTop + 'px');

  /* Note: #table-action-bar itself sticks at --thead-top = navH + statsH.
     Then <thead> sticks at --col-head-top = navH + statsH + filterH.
     That means there's a gap of filterH between them — filterH includes
     the filter bar's padding, so this is correct. */
  root.style.setProperty('--tbody-top', (colHeadTop + tableHeadH) + 'px');
}

document.addEventListener('DOMContentLoaded', recalcStickyOffsets);
window.addEventListener('resize', recalcStickyOffsets);
window.addEventListener('load',   recalcStickyOffsets);
setTimeout(recalcStickyOffsets, 150);
setTimeout(recalcStickyOffsets, 600);