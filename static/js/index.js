// ══════════════════════════════════════════════════════════════
//  DOCUMENT TRACKER — INDEX PAGE JAVASCRIPT
//  Upgraded: toast system, relative dates, selection bar,
//  step indicators, inline search clear, jump-to-page,
//  sortable headers, focus trap, Escape close, pending banner
// ══════════════════════════════════════════════════════════════
'use strict';

// ─────────────────────────────────────────────────────────────
//  MODULE-LEVEL STATE
// ─────────────────────────────────────────────────────────────
var modalCurrentOffice  = null;
var currentUserName     = null;
var currentUserRole     = null;
var officesData         = {};
var sortedOffices       = [];
var transferSingleDocId = null;


// ─────────────────────────────────────────────────────────────
//  BOOT
// ─────────────────────────────────────────────────────────────
(function boot() {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady);
  } else {
    onReady();
  }
})();

function onReady() {
  initModalData();
  setupSelectAll();
  setupSortableHeaders();
  renderRelativeDates();
  recalcStickyOffsets();
  initSlipDate();
  checkPendingDocuments();

  // Slip date default
  var sd = document.getElementById('slip-date');
  if (sd && !sd.value) sd.value = new Date().toISOString().slice(0, 10);
}


// ─────────────────────────────────────────────────────────────
//  MODAL DATA — reads JSON blobs injected by Jinja
// ─────────────────────────────────────────────────────────────
function initModalData() {
  try {
    officesData   = JSON.parse((document.getElementById('offices-data')  || {}).textContent || '{}');
    sortedOffices = JSON.parse((document.getElementById('sorted-offices') || {}).textContent || '[]');

    var officeEl = document.getElementById('current-office-data');
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
    officesData        = {};
    sortedOffices      = [];
    modalCurrentOffice = (typeof serverSessionData !== 'undefined' && serverSessionData.office)
      ? serverSessionData.office : null;
  }
}


// ─────────────────────────────────────────────────────────────
//  STICKY OFFSET CALCULATOR
// ─────────────────────────────────────────────────────────────
function recalcStickyOffsets() {
  var root = document.documentElement;

  var navbar = document.querySelector('nav');
  var navH   = navbar ? navbar.offsetHeight : 0;
  root.style.setProperty('--navbar-h',   navH + 'px');
  root.style.setProperty('--filter-top', navH + 'px');

  var statsBar = document.getElementById('stats-sticky-bar');
  var statsH   = statsBar ? statsBar.offsetHeight : 0;
  root.style.setProperty('--thead-top', (navH + statsH) + 'px');

  var filterBar = document.getElementById('filter-sticky-bar');
  var filterH   = filterBar ? filterBar.offsetHeight : 0;
  var colHeadTop = navH + statsH + filterH;
  root.style.setProperty('--col-head-top', colHeadTop + 'px');

  var tableHead  = document.getElementById('table-action-bar');
  var tableHeadH = tableHead ? tableHead.offsetHeight : 0;
  root.style.setProperty('--tbody-top', (colHeadTop + tableHeadH) + 'px');
}

window.addEventListener('resize', recalcStickyOffsets);
window.addEventListener('load',   recalcStickyOffsets);
setTimeout(recalcStickyOffsets, 150);
setTimeout(recalcStickyOffsets, 600);


// ─────────────────────────────────────────────────────────────
//  STAT FILTER
// ─────────────────────────────────────────────────────────────
function statFilter(status) {
  var params = new URLSearchParams(window.location.search);
  params.set('status', status);
  params.delete('page');
  window.location.href = '/?' + params.toString();
}


// ─────────────────────────────────────────────────────────────
//  FILTER HELPERS
// ─────────────────────────────────────────────────────────────
function toggleTimeRange(on) {
  var row = document.getElementById('time-range-row');
  if (!row) return;
  row.style.display = on ? 'flex' : 'none';
  if (!on) {
    var tf = document.querySelector('[name="time_from"]');
    var tt = document.querySelector('[name="time_to"]');
    if (tf) tf.value = '';
    if (tt) tt.value = '';
    document.getElementById('filter-form').submit();
  }
}

function setToday() {
  var el = document.querySelector('[name="date"]');
  if (el) {
    el.value = new Date().toISOString().slice(0, 10);
    document.getElementById('filter-form').submit();
  }
}

function setType(val) {
  var el = document.getElementById('type-hidden');
  if (el) el.value = val;
  document.getElementById('filter-form').submit();
}

function setSource(val) {
  var params = new URLSearchParams(window.location.search);
  if (!val || val === 'All') {
    params.delete('source');
  } else {
    params.set('source', val);
  }
  params.delete('page');
  window.location.href = '/?' + params.toString();
}

function clearField(name, val) {
  if (val === undefined) val = '';
  var el = document.querySelector('[name="' + name + '"]');
  if (el) el.value = val;
  document.getElementById('filter-form').submit();
}

// Inline search clear button (NEW)
function onSearchInput(inp) {
  var btn = inp.parentElement.querySelector('.search-clear');
  if (btn) btn.style.display = inp.value.length > 0 ? '' : 'none';
}

function clearSearchField() {
  var inp = document.getElementById('search-input');
  if (inp) {
    inp.value = '';
    inp.focus();
    var btn = inp.parentElement.querySelector('.search-clear');
    if (btn) btn.style.display = 'none';
  }
}

function changePerPage(val) {
  var url = new URL(window.location.href);
  url.searchParams.set('per_page', val);
  url.searchParams.set('page', 1);
  window.location = url.toString();
}

// Jump to specific page (NEW)
function jumpToPage(val, qs) {
  var num = parseInt(val, 10);
  if (!isNaN(num) && num > 0) {
    window.location.href = '/?' + qs + '&page=' + num;
  }
}

function rowClick(e, docId) {
  if (e.target.type === 'checkbox') return;
  window.location = '/view/' + docId;
}


// ─────────────────────────────────────────────────────────────
//  RELATIVE DATE CHIPS (NEW)
//  Fills .date-rel[data-ts] spans with human-readable labels
// ─────────────────────────────────────────────────────────────
function renderRelativeDates() {
  var chips = document.querySelectorAll('.date-rel[data-ts]');
  var now   = new Date();

  chips.forEach(function (chip) {
    var ts = chip.getAttribute('data-ts');
    if (!ts) return;
    var dt = new Date(ts);
    if (isNaN(dt)) return;

    var diffMs   = now - dt;
    var diffMins = Math.floor(diffMs / 60000);
    var diffHrs  = Math.floor(diffMs / 3600000);
    var diffDays = Math.floor(diffMs / 86400000);

    var label = '';
    var cls   = '';

    if (diffMins < 1) {
      label = 'Just now'; cls = 'today';
    } else if (diffHrs < 1) {
      label = diffMins + 'm ago'; cls = 'today';
    } else if (diffDays === 0) {
      label = 'Today'; cls = 'today';
    } else if (diffDays === 1) {
      label = 'Yesterday'; cls = 'recent';
    } else if (diffDays < 7) {
      label = diffDays + ' days ago'; cls = 'recent';
    } else {
      label = dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }

    chip.textContent = label;
    if (cls) chip.classList.add(cls);
  });
}


// ─────────────────────────────────────────────────────────────
//  SELECTION — checkboxes + context bar
// ─────────────────────────────────────────────────────────────
function setupSelectAll() {
  var selAll = document.getElementById('select-all');
  if (!selAll) return;
  selAll.addEventListener('change', function () {
    document.querySelectorAll('.doc-checkbox').forEach(function (cb) {
      cb.checked = selAll.checked;
      cb.closest('tr').classList.toggle('row-selected', selAll.checked);
    });
    updateSelection();
    updateSelectAllLabel();
  });
}

function updateSelection() {
  var all     = document.querySelectorAll('.doc-checkbox');
  var checked = document.querySelectorAll('.doc-checkbox:checked');
  var n       = checked.length;

  // Highlight rows
  all.forEach(function (cb) {
    cb.closest('tr').classList.toggle('row-selected', cb.checked);
  });

  // Indeterminate state on select-all
  var selAll = document.getElementById('select-all');
  if (selAll) {
    selAll.indeterminate = n > 0 && n < all.length;
    selAll.checked       = n === all.length && all.length > 0;
  }

  syncSelectionBar();
  updateSelectedPreview();
  updateSelectAllLabel();
}

// Sync the sliding selection bar (NEW)
function syncSelectionBar() {
  var n   = document.querySelectorAll('.doc-checkbox:checked').length;
  var bar = document.getElementById('selection-bar');
  if (bar) {
    bar.classList.toggle('visible', n > 0);
    bar.setAttribute('aria-hidden', n > 0 ? 'false' : 'true');
  }
  var lbl = document.getElementById('sel-count-label');
  if (lbl) lbl.textContent = n;
}

// Deselect all from the selection bar (NEW)
function deselectAll() {
  document.querySelectorAll('.doc-checkbox').forEach(function (cb) {
    cb.checked = false;
    cb.closest('tr').classList.remove('row-selected');
  });
  var selAll = document.getElementById('select-all');
  if (selAll) { selAll.checked = false; selAll.indeterminate = false; }
  syncSelectionBar();
  updateSelectedPreview();
  updateSelectAllLabel();
  showToast('Selection cleared', 'info');
}

function updateSelectAllLabel() {
  var selAll = document.getElementById('select-all');
  var label  = selAll ? selAll.nextElementSibling : null;
  if (!label || !label.classList.contains('select-all-label')) return;
  var total   = document.querySelectorAll('.doc-checkbox').length;
  var checked = document.querySelectorAll('.doc-checkbox:checked').length;
  label.textContent = checked > 0 && checked < total ? checked : 'Select';
}


// ─────────────────────────────────────────────────────────────
//  SORTABLE COLUMN HEADERS (NEW)
// ─────────────────────────────────────────────────────────────
function setupSortableHeaders() {
  document.querySelectorAll('th.sortable').forEach(function (th) {
    th.addEventListener('click', function () {
      var cur = th.getAttribute('aria-sort');
      document.querySelectorAll('th.sortable').forEach(function (h) { h.setAttribute('aria-sort', 'none'); });
      th.setAttribute('aria-sort', cur === 'descending' ? 'ascending' : 'descending');
      // In production: add sort params to URL / submit form
    });
  });
}


// ─────────────────────────────────────────────────────────────
//  MODAL HELPERS
// ─────────────────────────────────────────────────────────────
function openModal(id) {
  var modal = document.getElementById(id);
  if (!modal) return;
  modal.classList.add('open');

  // Focus first interactive element (NEW)
  setTimeout(function () {
    var first = modal.querySelector('input:not([type=hidden]), select, textarea, .rp-close');
    if (first) first.focus();
  }, 80);

  // Close on backdrop click
  function onBackdrop(e) {
    if (e.target === modal) {
      closeModal(id);
      modal.removeEventListener('click', onBackdrop);
    }
  }
  modal.addEventListener('click', onBackdrop);
}

function closeModal(id) {
  var modal = document.getElementById(id);
  if (modal) modal.classList.remove('open');
}

// Escape closes any open modal (NEW)
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open').forEach(function (m) {
      m.classList.remove('open');
    });
  }
  // "/" opens office modal
  if (e.key === '/' && document.activeElement.tagName !== 'INPUT' &&
      document.activeElement.tagName !== 'TEXTAREA') {
    e.preventDefault();
    openOqsModal();
  }
});


// ─────────────────────────────────────────────────────────────
//  ROUTING MODAL
// ─────────────────────────────────────────────────────────────
function openRoutingModal() {
  openModal('routing-modal');
  initSlipDate();
  
  // Analyze selected documents for referred_to grouping
  var groupingInfo = analyzeReferredToGrouping();
  
  // Update the preview with grouping info
  updateSelectedPreview();
  
  // Update the hint text based on grouping
  var hintEl = document.getElementById('routing-hint');
  if (hintEl) {
    if (groupingInfo.groupCount > 1) {
      hintEl.innerHTML = '📋 Documents will be grouped by "Referred To" — ' + groupingInfo.groupCount + ' routing slips will be created.';
    } else if (groupingInfo.totalDocs > 0 && groupingInfo.referredTo) {
      hintEl.innerHTML = '✅ All selected documents have the same "Referred To" — 1 routing slip will be created.';
    } else {
      hintEl.innerHTML = '💡 Enter a destination office above, or select documents with "Referred To" values.';
    }
  }
  
  // Pre-fill destination if all documents have the same referred_to
  var destInput = document.getElementById('route-dest');
  if (destInput) {
    if (groupingInfo.allSame && groupingInfo.referredTo) {
      destInput.value = groupingInfo.referredTo;
      document.getElementById('modal-dest-preview').textContent = groupingInfo.referredTo;
    } else {
      destInput.value = '';
      document.getElementById('modal-dest-preview').textContent = '(enter below)';
    }
  }
  
  // Show grouping info in modal title if there are multiple groups
  var titleEl = document.getElementById('routing-modal-title');
  if (titleEl) {
    if (groupingInfo.groupCount > 1) {
      titleEl.innerHTML = '📤 Create Routing Slip <span class="rp-count" id="sel-count">' + groupingInfo.totalDocs + ' selected (' + groupingInfo.groupCount + ' groups)</span>';
    } else {
      titleEl.innerHTML = '📤 Create Routing Slip <span class="rp-count" id="sel-count">' + groupingInfo.totalDocs + ' selected</span>';
    }
  }
  
  var btn = document.querySelector('#routing-modal .btn-route');
  if (btn) { btn.disabled = false; btn.textContent = '🚀 Create Routing Slip' + (groupingInfo.groupCount > 1 ? 's' : ''); }
}

// Analyze selected documents and group by referred_to
function analyzeReferredToGrouping() {
  var checked = document.querySelectorAll('.doc-checkbox:checked');
  var totalDocs = checked.length;
  
  if (totalDocs === 0) {
    return { totalDocs: 0, groupCount: 0, allSame: false, referredTo: '', groups: {} };
  }
  
  var groups = {};
  var referredTos = [];
  
  checked.forEach(function(cb) {
    var row = cb.closest('tr');
    var referredTo = row ? row.getAttribute('data-referred-to') || '' : '';
    
    if (!referredTo) referredTo = '(No Referred To)';
    
    if (!groups[referredTo]) {
      groups[referredTo] = [];
    }
    groups[referredTo].push(cb.value);
    referredTos.push(referredTo);
  });
  
  // Check if all have the same referred_to
  var uniqueReferredTos = [...new Set(referredTos.filter(function(r) { return r !== '(No Referred To)'; }))];
  var allSame = uniqueReferredTos.length <= 1 && Object.keys(groups).length <= 1;
  
  // If all are empty/blank referred_to, treat as one group
  var hasOnlyEmptyGroups = Object.keys(groups).every(function(k) { return k === '(No Referred To)'; });
  if (hasOnlyEmptyGroups) {
    allSame = true;
  }
  
  return {
    totalDocs: totalDocs,
    groupCount: Object.keys(groups).length,
    allSame: allSame,
    referredTo: uniqueReferredTos[0] || '',
    groups: groups
  };
}

function closeRoutingModal() { closeModal('routing-modal'); }

function initSlipDate() {
  var sd = document.getElementById('slip-date');
  if (sd && !sd.value) sd.value = new Date().toISOString().slice(0, 10);
}

function toggleModalTimeRange(on) {
  var tf  = document.getElementById('time-from-field');
  var tt  = document.getElementById('time-to-field');
  var btn = document.getElementById('btn-auto-select');
  if (tf)  tf.style.display  = on ? '' : 'none';
  if (tt)  tt.style.display  = on ? '' : 'none';
  if (btn) btn.style.display = on ? '' : 'none';
  if (!on) {
    var tfv = document.getElementById('time-from');
    var ttv = document.getElementById('time-to');
    if (tfv) tfv.value = '';
    if (ttv) ttv.value = '';
  }
}

function autoSelectByTime() {
  var useTime = document.getElementById('use-time-range').checked;
  var tf = document.getElementById('time-from').value;
  var tt = document.getElementById('time-to').value;
  var sd = document.getElementById('slip-date').value;

  if (useTime && (!tf || !tt)) {
    showToast('Please set both From and To times.', 'warning');
    return;
  }

  var count = 0;
  document.querySelectorAll('.doc-checkbox').forEach(function (cb) {
    var row = cb.closest('tr');
    var ts  = row.dataset.createdAt || '';
    var inRange = false;
    if (ts) {
      var dateOk = !sd || ts.slice(0, 10) === sd;
      var timeOk = ts.slice(11, 16) >= tf && ts.slice(11, 16) <= tt;
      inRange = dateOk && timeOk;
    }
    cb.checked = inRange;
    row.classList.toggle('row-selected', inRange);
    if (inRange) count++;
  });

  syncSelectionBar();

  if (count === 0) {
    showToast('No documents found in that date/time range.', 'warning');
  } else {
    showToast(count + ' document' + (count > 1 ? 's' : '') + ' selected by time range.', 'success');
    var btn  = document.getElementById('btn-auto-select');
    var orig = btn ? btn.textContent : '';
    if (btn) {
      btn.textContent = '✅ ' + count + ' selected';
      setTimeout(function () { btn.textContent = orig; }, 2000);
    }
  }

  updateSelectedPreview();
}

function submitRouting() {
  var groupingInfo = analyzeReferredToGrouping();
  var groups = groupingInfo.groups;
  var groupKeys = Object.keys(groups);
  
  // Determine if we need to use grouped routing or single destination
  var useGroupedRouting = groupKeys.length > 1;
  var manualDest = document.getElementById('route-dest').value.trim();
  
  // If there's a manual destination but multiple groups, ask user what to do
  if (manualDest && useGroupedRouting) {
    // Show confirmation - will route all to the manual destination
    if (!confirm('You have selected documents with different "Referred To" values.\n\nDo you want to route ALL documents to "' + manualDest + '"?\n\nClick OK to route all to the manual destination.\nClick Cancel to create separate routing slips for each "Referred To" group.')) {
      return;
    }
    useGroupedRouting = false;
  }
  
  // If no manual destination and multiple groups, use grouped routing
  if (!manualDest && useGroupedRouting) {
    // Check if all groups have valid referred_to (not empty)
    var hasEmptyGroup = groupKeys.some(function(k) { return k === '(No Referred To)'; });
    if (hasEmptyGroup) {
      showToast('Some documents have no "Referred To". Please enter a destination office manually.', 'warning');
      var el = document.getElementById('route-dest');
      el.focus();
      el.style.borderColor = '#FCA5A5';
      el.style.background  = 'rgba(220,38,38,.15)';
      setTimeout(function () { el.style.borderColor = ''; el.style.background = ''; }, 2500);
      return;
    }
  }
  
  // Single destination mode
  if (!useGroupedRouting) {
    var dest = manualDest || (groupingInfo.referredTo || '');
    if (!dest) {
      var el = document.getElementById('route-dest');
      el.focus();
      el.style.borderColor = '#FCA5A5';
      el.style.background  = 'rgba(220,38,38,.15)';
      setTimeout(function () { el.style.borderColor = ''; el.style.background = ''; }, 2500);
      showToast('Please enter a destination office.', 'warning');
      return;
    }

    var ids = getSelectedIds();
    if (!ids.length) { showToast('No documents selected.', 'warning'); return; }

    var btn = document.querySelector('#routing-modal .btn-route');
    if (btn) {
      if (btn.disabled) return;
      btn.disabled    = true;
      btn.textContent = '⏳ Creating slip…';
    }

    document.getElementById('routing-doc-ids').value    = ids.join(',');
    document.getElementById('routing-dest-field').value = dest;
    document.getElementById('routing-notes').value      = document.getElementById('route-notes').value;
    document.getElementById('routing-slip-date').value  = document.getElementById('slip-date').value;
    document.getElementById('routing-time-from').value  = document.getElementById('time-from').value;
    document.getElementById('routing-time-to').value    = document.getElementById('time-to').value;
    document.getElementById('routing-form').submit();
    return;
  }
  
  // Grouped routing mode - create multiple routing slips
  var btn = document.querySelector('#routing-modal .btn-route');
  if (btn) {
    if (btn.disabled) return;
    btn.disabled    = true;
    btn.textContent = '⏳ Creating ' + groupKeys.length + ' slips…';
  }
  
  // Prepare grouped data
  var groupedData = JSON.stringify(groups);
  var notes = document.getElementById('route-notes').value || '';
  var slipDate = document.getElementById('slip-date').value;
  var timeFrom = document.getElementById('time-from').value;
  var timeTo = document.getElementById('time-to').value;
  
  // Create hidden form fields for grouped data
  var form = document.getElementById('routing-form');
  
  // Remove any existing grouped data fields
  var existingGrouped = form.querySelector('.grouped-data');
  if (existingGrouped) existingGrouped.remove();
  
  // Add grouped data field
  var groupedInput = document.createElement('input');
  groupedInput.type = 'hidden';
  groupedInput.name = 'grouped_routing';
  groupedInput.className = 'grouped-data';
  groupedInput.value = groupedData;
  form.appendChild(groupedInput);
  
  // Add notes field
  var existingNotes = form.querySelector('[name="grouped_notes"]');
  if (existingNotes) existingNotes.remove();
  var notesInput = document.createElement('input');
  notesInput.type = 'hidden';
  notesInput.name = 'grouped_notes';
  notesInput.className = 'grouped-data';
  notesInput.value = notes;
  form.appendChild(notesInput);
  
  // Add slip date
  var existingDate = form.querySelector('[name="grouped_slip_date"]');
  if (existingDate) existingDate.remove();
  var dateInput = document.createElement('input');
  dateInput.type = 'hidden';
  dateInput.name = 'grouped_slip_date';
  dateInput.className = 'grouped-data';
  dateInput.value = slipDate;
  form.appendChild(dateInput);
  
  // Add time range
  var existingTimeFrom = form.querySelector('[name="grouped_time_from"]');
  if (existingTimeFrom) existingTimeFrom.remove();
  var timeFromInput = document.createElement('input');
  timeFromInput.type = 'hidden';
  timeFromInput.name = 'grouped_time_from';
  timeFromInput.className = 'grouped-data';
  timeFromInput.value = timeFrom;
  form.appendChild(timeFromInput);
  
  var existingTimeTo = form.querySelector('[name="grouped_time_to"]');
  if (existingTimeTo) existingTimeTo.remove();
  var timeToInput = document.createElement('input');
  timeToInput.type = 'hidden';
  timeToInput.name = 'grouped_time_to';
  timeToInput.className = 'grouped-data';
  timeToInput.value = timeTo;
  form.appendChild(timeToInput);
  
  // Update form action to use grouped routing endpoint
  form.action = '/routing-slip/create-grouped';
  
  form.submit();
}


// ─────────────────────────────────────────────────────────────
//  TRANSFER MODAL (with step progress)
// ─────────────────────────────────────────────────────────────
function openTransferModal() {
  var ids = getSelectedIds();
  if (!ids.length) {
    showToast('Please select at least one document to transfer.', 'warning');
    return;
  }
  var countEl = document.getElementById('transfer-sel-count');
  if (countEl) countEl.textContent = ids.length + ' selected';
  resetTransferModal();
  openModal('transfer-modal');
}

function closeTransferModal() { closeModal('transfer-modal'); }

function resetTransferModal() {
  var el;
  el = document.getElementById('transfer-type');
  if (el) el.value = '';

  el = document.getElementById('transfer-office');
  if (el) { el.innerHTML = '<option value="">— Select Office —</option>'; el.disabled = true; }

  el = document.getElementById('transfer-office-info');
  if (el) el.textContent = '';

  el = document.getElementById('transfer-staff');
  if (el) { el.innerHTML = '<option value="">— Select Staff —</option>'; el.disabled = true; }

  _hideBlock('transfer-office-block');
  _hideBlock('transfer-staff-block');
  _hideBlock('transfer-submit-block');

  var btn = document.getElementById('btn-do-transfer');
  if (btn) { btn.disabled = true; btn.textContent = '🔄 Transfer Documents'; }

  _setStep(1);
}

function onTransferTypeChangeIndex() {
  var type         = document.getElementById('transfer-type').value;
  var officeSelect = document.getElementById('transfer-office');
  var staffSelect  = document.getElementById('transfer-staff');

  staffSelect.innerHTML = '<option value="">— Select Staff —</option>';
  staffSelect.disabled  = true;

  var btn = document.getElementById('btn-do-transfer');
  if (btn) btn.disabled = true;

  _hideBlock('transfer-staff-block');
  _hideBlock('transfer-submit-block');

  if (!type) { _hideBlock('transfer-office-block'); _setStep(1); return; }

  _setStep(2);

  if (type === 'inside_office') {
    var lbl = document.getElementById('transfer-office-label');
    if (lbl) lbl.textContent = 'Your Office';

    officeSelect.innerHTML = '<option value="' + modalCurrentOffice + '">' + modalCurrentOffice + '</option>';
    officeSelect.value     = modalCurrentOffice;
    officeSelect.disabled  = true;
    var info = document.getElementById('transfer-office-info');
    if (info) info.textContent = '📍 Auto-selected: your office';

    _showBlock('transfer-office-block');
    _populateTransferStaff(modalCurrentOffice);
    _showBlock('transfer-staff-block');
    _setStep(3);
  } else {
    var lbl2 = document.getElementById('transfer-office-label');
    if (lbl2) lbl2.textContent = 'Select Office';

    var opts = '<option value="">— Select Office —</option>';
    sortedOffices.forEach(function (office) {
      if (office === 'No Office' || office === modalCurrentOffice) return;
      opts += '<option value="' + office + '">' + office + '</option>';
    });
    officeSelect.innerHTML = opts;
    officeSelect.disabled  = false;
    var info2 = document.getElementById('transfer-office-info');
    if (info2) info2.textContent = '';

    _showBlock('transfer-office-block');
  }
}

function updateTransferStaffIndex() {
  var office = document.getElementById('transfer-office').value;
  _hideBlock('transfer-staff-block');
  _hideBlock('transfer-submit-block');
  var btn = document.getElementById('btn-do-transfer');
  if (btn) btn.disabled = true;
  if (!office) return;
  _populateTransferStaff(office);
  _showBlock('transfer-staff-block');
  _setStep(3);
}

function _populateTransferStaff(office) {
  var sel = document.getElementById('transfer-staff');
  sel.innerHTML = '<option value="">— Select Staff —</option>';
  if (!office || !officesData[office]) return;
  officesData[office].forEach(function (s) {
    var name = s.full_name || s.username;
    sel.innerHTML += '<option value="' + s.username + '">' + name + ' (@' + s.username + ')</option>';
  });
  sel.disabled = false;
}

function onTransferStaffChangeIndex() {
  var val = document.getElementById('transfer-staff').value;
  if (val) { _showBlock('transfer-submit-block'); var btn = document.getElementById('btn-do-transfer'); if (btn) btn.disabled = false; }
  else     { _hideBlock('transfer-submit-block'); }
}

function submitTransfer() {
  var csrfToken    = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
  var transferType = document.getElementById('transfer-type').value;
  var office       = document.getElementById('transfer-office').value || modalCurrentOffice;
  var staff        = document.getElementById('transfer-staff').value;
  var selectedIds  = transferSingleDocId ? [transferSingleDocId] : getSelectedIds();

  if (!transferType || !staff) { showToast('Please complete all steps before transferring.', 'warning'); return; }
  if (!selectedIds.length)     { showToast('Please select at least one document.', 'warning'); return; }

  var btn = document.getElementById('btn-do-transfer');
  if (btn) { if (btn.disabled) return; btn.disabled = true; btn.textContent = '⏳ Transferring…'; }

  var form = document.createElement('form');
  form.method = 'POST';

  var fields;
  if (transferSingleDocId) {
    form.action = '/transfer/' + transferSingleDocId;
    fields = [['transfer_type',transferType],['new_office',office],['new_staff',staff],['csrf_token',csrfToken]];
  } else {
    form.action = '/transfer-batch';
    fields = [['doc_ids',selectedIds.join(',')],['transfer_type',transferType],['new_office',office],['new_staff',staff],['csrf_token',csrfToken]];
  }

  fields.forEach(function (pair) {
    var inp = document.createElement('input');
    inp.type = 'hidden'; inp.name = pair[0]; inp.value = pair[1];
    form.appendChild(inp);
  });

  document.body.appendChild(form);
  form.submit();
}

// Update step indicator (NEW)
function _setStep(active) {
  for (var i = 1; i <= 3; i++) {
    var el = document.getElementById('step-' + i);
    if (!el) continue;
    el.classList.remove('active', 'done');
    if (i < active)      el.classList.add('done');
    else if (i === active) el.classList.add('active');
  }
}


// ─────────────────────────────────────────────────────────────
//  STATUS MODAL
// ─────────────────────────────────────────────────────────────
function openStatusModal() {
  var ids = getSelectedIds();
  if (!ids.length) { showToast('Please select at least one document to update.', 'warning'); return; }

  var countEl = document.getElementById('status-sel-count');
  if (countEl) countEl.textContent = ids.length + ' selected';

  var sel = document.getElementById('new-status');
  if (sel) sel.value = '';
  var rem = document.getElementById('status-remarks');
  if (rem) rem.value = '';
  var btn = document.getElementById('btn-do-status-update');
  if (btn) btn.disabled = true;

  openModal('status-modal');
}

function closeStatusModal() { closeModal('status-modal'); }

function onStatusChange() {
  var sel = document.getElementById('new-status');
  var btn = document.getElementById('btn-do-status-update');
  if (btn && sel) btn.disabled = !sel.value;
}

function submitBulkStatusUpdate() {
  var ids = getSelectedIds();
  if (!ids.length) { showToast('No documents selected.', 'warning'); return; }

  var newStatus = document.getElementById('new-status').value;
  if (!newStatus) { showToast('Please select a status.', 'warning'); return; }

  var remarks   = document.getElementById('status-remarks').value;
  var csrfToken = (document.getElementById('csrf-token-value') || {}).value || '';

  var form = document.createElement('form');
  form.method = 'POST';
  form.action = '/bulk-update-status';

  var pairs = [['doc_ids', ids.join(',')], ['new_status', newStatus], ['csrf_token', csrfToken]];
  if (remarks) pairs.push(['remarks', remarks]);

  pairs.forEach(function (pair) {
    var inp = document.createElement('input');
    inp.type = 'hidden'; inp.name = pair[0]; inp.value = pair[1];
    form.appendChild(inp);
  });

  document.body.appendChild(form);
  form.submit();
}


// ─────────────────────────────────────────────────────────────
//  SELECTED DOCUMENT PREVIEW (routing modal) - WITH GROUPING
// ─────────────────────────────────────────────────────────────
function updateSelectedPreview() {
  var checked = document.querySelectorAll('.doc-checkbox:checked');
  var n       = checked.length;

  var countEl = document.getElementById('sel-count');
  if (countEl) {
    var groupingInfo = analyzeReferredToGrouping();
    if (groupingInfo.groupCount > 1) {
      countEl.textContent = n + ' selected (' + groupingInfo.groupCount + ' groups)';
    } else {
      countEl.textContent = n + ' selected';
    }
  }

  var preview = document.getElementById('selected-preview');
  var list    = document.getElementById('selected-list');
  if (!preview || !list) return;

  if (n === 0) {
    preview.style.display = 'none';
    list.innerHTML = '';
  } else {
    preview.style.display = 'block';
    
    // Get grouping info
    var groupingInfo = analyzeReferredToGrouping();
    var groups = groupingInfo.groups;
    var groupKeys = Object.keys(groups);
    
    // If there are multiple groups, show them grouped
    if (groupKeys.length > 1 || (groupKeys.length === 1 && groupKeys[0] === '(No Referred To)')) {
      var html = '';
      var docCounter = 1;
      groupKeys.forEach(function(key) {
        var docsInGroup = groups[key];
        var groupLabel = key === '(No Referred To)' ? '📭 Documents without Referred To' : '📋 Referred To: ' + key;
        html += '<div style="padding:6px 0;border-bottom:1px solid rgba(255,255,255,.2);margin-top:8px;">';
        html += '<div style="font-weight:600;color:#FCD34D;font-size:11px;text-transform:uppercase;margin-bottom:4px;">' + groupLabel + ' (' + docsInGroup.length + ' docs)</div>';
        
        docsInGroup.forEach(function(docId) {
          var cb = document.querySelector('.doc-checkbox[value="' + docId + '"]');
          var row = cb ? cb.closest('tr') : null;
          var name = row ? row.querySelector('.doc-name') : null;
          html += '<div style="padding:2px 0;padding-left:12px;font-size:12px;">' +
                 docCounter + '. ' + (name ? name.textContent.trim() : docId) + '</div>';
          docCounter++;
        });
        html += '</div>';
      });
      list.innerHTML = html;
    } else {
      // Single group - show simple list
      list.innerHTML = Array.from(checked).map(function (cb, i) {
        var row  = cb.closest('tr');
        var name = row ? row.querySelector('.doc-name') : null;
        return '<div style="padding:3px 0;border-bottom:1px solid rgba(255,255,255,.1)">' +
               (i + 1) + '. ' + (name ? name.textContent.trim() : cb.value) + '</div>';
      }).join('');
    }
  }
}


// ─────────────────────────────────────────────────────────────
//  PENDING DOCUMENTS — FAB + banner (UPGRADED)
// ─────────────────────────────────────────────────────────────
function checkPendingDocuments() {
  var badge   = document.getElementById('pending-badge');
  var banner  = document.getElementById('incoming-banner');
  var ibBadge = document.getElementById('ib-badge');
  var ibSub   = document.getElementById('ib-sub-text');
  if (!badge && !banner) return;

  fetch('/api/pending-count')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var count = data.count || 0;

      // FAB badge
      if (badge) {
        badge.textContent   = count > 0 ? count : '';
        badge.style.display = count > 0 ? 'block' : 'none';
      }

      // Incoming banner (NEW)
      if (banner) {
        banner.style.display = count > 0 ? 'flex' : 'none';
        if (ibBadge) ibBadge.textContent = count;
        if (ibSub) ibSub.textContent = count + ' document' + (count !== 1 ? 's' : '') +
          ' transferred to you · Click to review and accept';
      }
    })
    .catch(function (err) { console.error('pending-count error:', err); });
}


// ─────────────────────────────────────────────────────────────
//  TOAST NOTIFICATIONS (NEW — replaces all alert() calls)
// ─────────────────────────────────────────────────────────────
var _toastIcons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };

function showToast(message, type) {
  type = type || 'info';
  var container = document.getElementById('toast-container');
  if (!container) return;

  var toast = document.createElement('div');
  toast.className = 'toast ' + type;
  toast.setAttribute('role', 'alert');

  toast.innerHTML =
    '<span class="toast-icon" aria-hidden="true">' + (_toastIcons[type] || 'ℹ️') + '</span>' +
    '<span class="toast-msg">' + message + '</span>' +
    '<button class="toast-close" aria-label="Dismiss notification">✕</button>';

  toast.querySelector('.toast-close').addEventListener('click', function () {
    _dismissToast(toast);
  });

  container.appendChild(toast);

  var timer = setTimeout(function () { _dismissToast(toast); }, 3500);
  toast._timer = timer;
}

function _dismissToast(toast) {
  if (toast._timer) clearTimeout(toast._timer);
  toast.style.transition = 'opacity .3s, transform .3s';
  toast.style.opacity    = '0';
  toast.style.transform  = 'translateY(8px)';
  setTimeout(function () { if (toast.parentElement) toast.parentElement.removeChild(toast); }, 320);
}


// ─────────────────────────────────────────────────────────────
//  OFFICE QR MODAL (unchanged from original)
// ─────────────────────────────────────────────────────────────
function openOqsModal() {
  var overlay = document.getElementById('oqs-modal-overlay');
  if (overlay) overlay.classList.add('open');
  var search = document.getElementById('oqs-search');
  if (search) search.focus();
}

function closeOqsModal() {
  var overlay = document.getElementById('oqs-modal-overlay');
  if (overlay) overlay.classList.remove('open');
}

function filterOffices(query) {
  var q       = (query || '').toLowerCase().trim();
  var cards   = document.querySelectorAll('.oqs-card');
  var visible = 0;
  cards.forEach(function (card) {
    var show = !q || (card.dataset.name || '').toLowerCase().includes(q);
    card.classList.toggle('hidden', !show);
    if (show) visible++;
  });
  var countEl = document.getElementById('oqs-count');
  if (countEl) countEl.textContent = visible + ' office' + (visible !== 1 ? 's' : '') + (q ? ' found' : ' registered');
  var noneEl = document.getElementById('oqs-none');
  if (noneEl) noneEl.classList.toggle('visible', visible === 0);
}


// ─────────────────────────────────────────────────────────────
//  HELPERS
// ─────────────────────────────────────────────────────────────
function getSelectedIds() {
  return Array.from(document.querySelectorAll('.doc-checkbox:checked')).map(function (cb) { return cb.value; });
}

function _showBlock(id) { var el = document.getElementById(id); if (el) el.style.display = 'block'; }
function _hideBlock(id) { var el = document.getElementById(id); if (el) el.style.display = 'none'; }

// Legacy aliases (kept for any inline HTML still using old names)
function _showTransferBlock(id) { _showBlock(id); }
function _hideTransferBlock(id) { _hideBlock(id); }

// ─────────────────────────────────────────────────────────────
// Kebab Menu Functions
function toggleKebabMenu(btn) {
  var dropdown = btn.nextElementSibling;
  var isShown = dropdown.classList.contains('show');
  
  // Close all other dropdowns first
  document.querySelectorAll('.kebab-dropdown.show').forEach(function(d) {
    d.classList.remove('show');
  });
  
  // Toggle current dropdown
  if (!isShown) {
    dropdown.classList.add('show');
  }
}

// Close dropdowns when clicking outside
document.addEventListener('click', function(e) {
  if (!e.target.closest('.kebab-menu')) {
    document.querySelectorAll('.kebab-dropdown.show').forEach(function(d) {
      d.classList.remove('show');
      // Reset position to default
      d.style.position = '';
      d.style.left = '';
      d.style.top = '';
      d.style.right = '';
      d.style.margin = '';
    });
  }
});

// Handle right-click to open kebab menu
document.addEventListener('contextmenu', function(e) {
  var row = e.target.closest('.doc-row');
  if (row) {
    e.preventDefault();
    var kebabMenu = row.querySelector('.kebab-menu');
    if (kebabMenu) {
      var btn = kebabMenu.querySelector('.kebab-btn');
      var dropdown = kebabMenu.querySelector('.kebab-dropdown');
      
      // Close all other dropdowns first
      document.querySelectorAll('.kebab-dropdown.show').forEach(function(d) {
        d.classList.remove('show');
      });
      
      // Position dropdown at cursor location
      dropdown.style.position = 'fixed';
      dropdown.style.left = e.clientX + 'px';
      dropdown.style.top = e.clientY + 'px';
      dropdown.style.right = 'auto';
      dropdown.style.margin = '0';
      
      dropdown.classList.add('show');
    }
  }
});