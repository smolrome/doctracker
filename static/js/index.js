// ══════════════════════════════════════════════════════════════
//  DOCUMENT TRACKER — INDEX PAGE JAVASCRIPT
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

var SELECTION_STORAGE_KEY = 'doctracker_selected_docs';
var CART_STORAGE_KEY      = 'doctracker_cart_docs';
var CART_DETAILS_KEY      = 'doctracker_cart_details';


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
  setupPaginationWithSelection();
  initCart();

  // Apply stored selections to current page checkboxes
  var restoredCount = applyStoredSelections();
  if (restoredCount > 0) {
    syncSelectionBar();
    updateCartBadge();
  }

  // Restore from URL param (pagination navigation)
  restoreSelectionsFromUrl();

  var sd = document.getElementById('slip-date');
  if (sd && !sd.value) sd.value = new Date().toISOString().slice(0, 10);
}


// ─────────────────────────────────────────────────────────────
//  MODAL DATA
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
  var root   = document.documentElement;
  var navbar = document.querySelector('nav');
  var navH   = navbar ? navbar.offsetHeight : 0;
  root.style.setProperty('--navbar-h',   navH + 'px');
  root.style.setProperty('--filter-top', navH + 'px');

  var statsBar = document.getElementById('stats-sticky-bar');
  var statsH   = statsBar ? statsBar.offsetHeight : 0;
  root.style.setProperty('--thead-top', (navH + statsH) + 'px');

  var filterBar  = document.getElementById('filter-sticky-bar');
  var filterH    = filterBar ? filterBar.offsetHeight : 0;
  var colHeadTop = navH + statsH + filterH;
  root.style.setProperty('--col-head-top', colHeadTop + 'px');

  var tableHead  = document.getElementById('table-action-bar');
  var tableHeadH = tableHead ? tableHead.offsetHeight : 0;
  root.style.setProperty('--tbody-top', (colHeadTop + tableHeadH) + 'px');
}

window.addEventListener('resize', recalcStickyOffsets);
window.addEventListener('load', recalcStickyOffsets);
setTimeout(recalcStickyOffsets, 150);
setTimeout(recalcStickyOffsets, 600);


// ─────────────────────────────────────────────────────────────
//  SELECTION PERSISTENCE
//  Single source of truth: SELECTION_STORAGE_KEY
//  CART_STORAGE_KEY is kept in sync but never used as the source
// ─────────────────────────────────────────────────────────────

function restoreSelectionsFromLocalStorage() {
  try {
    var stored = localStorage.getItem(SELECTION_STORAGE_KEY);
    if (!stored) return [];
    var ids = JSON.parse(stored);
    return Array.isArray(ids) ? ids : [];
  } catch (e) {
    return [];
  }
}

function saveSelectionsToLocalStorage() {
  var currentPageIds    = getSelectedIds();
  var currentPageAllIds = Array.from(document.querySelectorAll('.doc-checkbox')).map(function(cb) { return cb.value; });

  // Save doc names for checked items
  var details = getCartDocDetails();
  document.querySelectorAll('.doc-checkbox:checked').forEach(function(cb) {
    var row    = cb.closest('tr');
    var nameEl = row ? row.querySelector('.doc-name') : null;
    if (nameEl && nameEl.textContent.trim()) {
      details[cb.value] = { title: nameEl.textContent.trim() };
    } else if (!details[cb.value]) {
      details[cb.value] = { title: cb.value };
    }
  });
  saveCartDocDetails(details);

  // Get existing stored IDs from other pages
  var existingIds = restoreSelectionsFromLocalStorage();

  // Remove IDs that are on the current page but now unchecked
  var filteredExisting = existingIds.filter(function(id) {
    return !currentPageAllIds.includes(id); // keep IDs from other pages only
  });

  // Merge: other-page IDs + currently checked on this page
  var merged = Array.from(new Set(filteredExisting.concat(currentPageIds)));

  if (merged.length > 0) {
    localStorage.setItem(SELECTION_STORAGE_KEY, JSON.stringify(merged));
  } else {
    localStorage.removeItem(SELECTION_STORAGE_KEY);
  }

  updateCartBadge();
}

function applyStoredSelections() {
  var ids   = restoreSelectionsFromLocalStorage();
  var count = 0;
  ids.forEach(function(id) {
    var cb = document.querySelector('.doc-checkbox[value="' + id + '"]');
    if (cb) {
      cb.checked = true;
      cb.closest('tr').classList.add('row-selected');
      count++;
    }
  });
  return count;
}

function restoreSelectionsFromUrl() {
  var params          = new URLSearchParams(window.location.search);
  var selectedIdParam = params.get('selected_docs');
  if (!selectedIdParam) return;

  var urlIds    = selectedIdParam.split(',').filter(Boolean);
  var storedIds = restoreSelectionsFromLocalStorage();
  var merged    = Array.from(new Set(storedIds.concat(urlIds)));

  if (merged.length > 0) {
    localStorage.setItem(SELECTION_STORAGE_KEY, JSON.stringify(merged));
  }

  var count = 0;
  merged.forEach(function(id) {
    var cb = document.querySelector('.doc-checkbox[value="' + id + '"]');
    if (cb) { cb.checked = true; cb.closest('tr').classList.add('row-selected'); count++; }
  });

  // Clean URL
  params.delete('selected_docs');
  var newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
  window.history.replaceState({}, '', newUrl);

  if (count > 0) { syncSelectionBar(); updateCartBadge(); }
}

function setupPaginationWithSelection() {
  var wrap = document.querySelector('.pagination-wrap');
  if (!wrap) return;
  wrap.addEventListener('click', function(e) {
    var link = e.target.closest('.page-btn');
    if (!link || link.classList.contains('active') || link.classList.contains('disabled')) return;
    var href = link.getAttribute('href');
    if (!href) return;
    e.preventDefault();

    // Save current page names before navigating
    saveSelectionsToLocalStorage();

    var allIds = restoreSelectionsFromLocalStorage();
    var url    = new URL(href, window.location.origin);
    if (allIds.length > 0) url.searchParams.set('selected_docs', allIds.join(','));
    window.location.href = url.toString();
  });
}

// Filter form: preserve selections on submit
(function() {
  function setupFilterFormWithSelection() {
    var form = document.getElementById('filter-form');
    if (!form) return;
    var submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) {
      submitBtn.addEventListener('click', function(e) {
        e.preventDefault();
        saveSelectionsToLocalStorage();
        var params = new URLSearchParams(new FormData(form));
        var allIds = restoreSelectionsFromLocalStorage();
        if (allIds.length > 0) params.set('selected_docs', allIds.join(','));
        window.location.href = '/?' + params.toString();
      });
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupFilterFormWithSelection);
  } else {
    setupFilterFormWithSelection();
  }
})();


// ─────────────────────────────────────────────────────────────
//  STAT / FILTER HELPERS
// ─────────────────────────────────────────────────────────────
function statFilter(status) {
  saveSelectionsToLocalStorage();
  var params = new URLSearchParams(window.location.search);
  params.set('status', status);
  params.delete('page');
  var allIds = restoreSelectionsFromLocalStorage();
  if (allIds.length > 0) params.set('selected_docs', allIds.join(','));
  window.location.href = '/?' + params.toString();
}

function toggleTimeRange(on) {
  var row = document.getElementById('time-range-row');
  if (!row) return;
  row.style.display = on ? 'flex' : 'none';
  if (!on) {
    var tf = document.querySelector('[name="time_from"]');
    var tt = document.querySelector('[name="time_to"]');
    if (tf) tf.value = '';
    if (tt) tt.value = '';
    saveSelectionsToLocalStorage();
    var params = new URLSearchParams(window.location.search);
    params.delete('time_from'); params.delete('time_to');
    var allIds = restoreSelectionsFromLocalStorage();
    if (allIds.length > 0) params.set('selected_docs', allIds.join(','));
    window.location.href = '/?' + params.toString();
  }
}

function setToday() {
  var el = document.querySelector('[name="date"]');
  if (el) {
    el.value = new Date().toISOString().slice(0, 10);
    saveSelectionsToLocalStorage();
    var params = new URLSearchParams(window.location.search);
    params.set('date', el.value);
    var allIds = restoreSelectionsFromLocalStorage();
    if (allIds.length > 0) params.set('selected_docs', allIds.join(','));
    window.location.href = '/?' + params.toString();
  }
}

function setType(val) {
  var el = document.getElementById('type-hidden');
  if (el) el.value = val;
  saveSelectionsToLocalStorage();
  var params = new URLSearchParams(window.location.search);
  params.set('type', val); params.delete('page');
  var allIds = restoreSelectionsFromLocalStorage();
  if (allIds.length > 0) params.set('selected_docs', allIds.join(','));
  window.location.href = '/?' + params.toString();
}

function setSource(val) {
  saveSelectionsToLocalStorage();
  var params = new URLSearchParams(window.location.search);
  if (!val || val === 'All') { params.delete('source'); } else { params.set('source', val); }
  params.delete('page');
  var allIds = restoreSelectionsFromLocalStorage();
  if (allIds.length > 0) params.set('selected_docs', allIds.join(','));
  window.location.href = '/?' + params.toString();
}

function clearField(name, val) {
  if (val === undefined) val = '';
  var el = document.querySelector('[name="' + name + '"]');
  if (el) el.value = val;
  saveSelectionsToLocalStorage();
  var params = new URLSearchParams(window.location.search);
  if (name) params.delete(name);
  params.delete('page');
  var allIds = restoreSelectionsFromLocalStorage();
  if (allIds.length > 0) params.set('selected_docs', allIds.join(','));
  window.location.href = '/?' + params.toString();
}

function onSearchInput(inp) {
  var btn = inp.parentElement.querySelector('.search-clear');
  if (btn) btn.style.display = inp.value.length > 0 ? '' : 'none';
}

function clearSearchField() {
  var inp = document.getElementById('search-input');
  if (inp) { inp.value = ''; inp.focus(); }
}

function changePerPage(val) {
  saveSelectionsToLocalStorage();
  var url = new URL(window.location.href);
  url.searchParams.set('per_page', val);
  url.searchParams.set('page', 1);
  var allIds = restoreSelectionsFromLocalStorage();
  if (allIds.length > 0) url.searchParams.set('selected_docs', allIds.join(','));
  window.location = url.toString();
}

function jumpToPage(val, qs) {
  var num = parseInt(val, 10);
  if (!isNaN(num) && num > 0) {
    saveSelectionsToLocalStorage();
    var params = new URLSearchParams(qs);
    params.set('page', num);
    var allIds = restoreSelectionsFromLocalStorage();
    if (allIds.length > 0) params.set('selected_docs', allIds.join(','));
    window.location.href = '/?' + params.toString();
  }
}

function clearAllFilters(e) {
  if (e) e.preventDefault();
  saveSelectionsToLocalStorage();
  var params = new URLSearchParams();
  var allIds = restoreSelectionsFromLocalStorage();
  if (allIds.length > 0) params.set('selected_docs', allIds.join(','));
  window.location.href = '/?' + params.toString();
}

function rowClick(e, docId) {
  if (e.target.type === 'checkbox') return;
  window.location = '/view/' + docId;
}


// ─────────────────────────────────────────────────────────────
//  RELATIVE DATE CHIPS
// ─────────────────────────────────────────────────────────────
function renderRelativeDates() {
  var chips     = document.querySelectorAll('.date-rel[data-ts]');
  var now       = new Date();
  var utcNow    = now.getTime() + (now.getTimezoneOffset() * 60000);
  var nowManila = new Date(utcNow + 8 * 3600000);

  chips.forEach(function(chip) {
    var ts = chip.getAttribute('data-ts');
    if (!ts) return;
    var dt;
    if (ts.includes('+08:00')) {
      var parts = ts.replace('+08:00', '').split(/[-T:]/);
      dt = new Date(parts[0], parts[1]-1, parts[2], parts[3], parts[4], parts[5]);
    } else if (ts.includes(' ')) {
      var parts = ts.split(/[- :]/);
      dt = new Date(parts[0], parts[1]-1, parts[2], parts[3], parts[4], parts[5]);
    } else {
      dt = new Date(ts);
    }
    if (isNaN(dt.getTime())) return;

    var diffMs   = nowManila - dt;
    var diffMins = Math.floor(diffMs / 60000);
    var diffHrs  = Math.floor(diffMs / 3600000);
    var diffDays = Math.floor(diffMs / 86400000);
    var label = '', cls = '';

    if (diffMins < 1)        { label = 'Just now';             cls = 'today';  }
    else if (diffHrs < 1)    { label = diffMins + 'm ago';     cls = 'today';  }
    else if (diffDays === 0) { label = 'Today';                cls = 'today';  }
    else if (diffDays === 1) { label = 'Yesterday';            cls = 'recent'; }
    else if (diffDays < 7)   { label = diffDays + ' days ago'; cls = 'recent'; }
    else { label = dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }); }

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
  selAll.addEventListener('change', function() {
    document.querySelectorAll('.doc-checkbox').forEach(function(cb) {
      cb.checked = selAll.checked;
      cb.closest('tr').classList.toggle('row-selected', selAll.checked);
    });
    updateSelection();
  });
}

function updateSelection() {
  var all     = document.querySelectorAll('.doc-checkbox');
  var checked = document.querySelectorAll('.doc-checkbox:checked');
  var n       = checked.length;

  all.forEach(function(cb) {
    cb.closest('tr').classList.toggle('row-selected', cb.checked);
  });

  var selAll = document.getElementById('select-all');
  if (selAll) {
    selAll.indeterminate = n > 0 && n < all.length;
    selAll.checked       = n === all.length && all.length > 0;
  }

  // Save doc names immediately
  var details = getCartDocDetails();
  checked.forEach(function(cb) {
    var row    = cb.closest('tr');
    var nameEl = row ? row.querySelector('.doc-name') : null;
    if (nameEl && nameEl.textContent.trim()) {
      details[cb.value] = { title: nameEl.textContent.trim() };
    } else if (!details[cb.value]) {
      details[cb.value] = { title: cb.value };
    }
  });
  saveCartDocDetails(details);

  // ── SAVE FIRST, then sync UI ──
  saveSelectionsToLocalStorage(); // updates localStorage with unchecked removed
  syncSelectionBar();             // now reads the correct updated count
  updateCartBadge();              // badge also reads updated count
  // ─────────────────────────────

  updateSelectedPreview();
  updateSelectAllLabel();
}

function syncSelectionBar() {
  // Total = all stored (cross-page) merged with current page
  var storedIds  = restoreSelectionsFromLocalStorage();
  var currentIds = getSelectedIds();
  var total      = Array.from(new Set(storedIds.concat(currentIds))).length;

  var bar = document.getElementById('selection-bar');
  if (bar) {
    bar.classList.toggle('visible', total > 0);
    bar.setAttribute('aria-hidden', total > 0 ? 'false' : 'true');
  }
  var lbl = document.getElementById('sel-count-label');
  if (lbl) lbl.textContent = total;
}

function deselectAll() {
  document.querySelectorAll('.doc-checkbox').forEach(function(cb) {
    cb.checked = false;
    cb.closest('tr').classList.remove('row-selected');
  });
  var selAll = document.getElementById('select-all');
  if (selAll) { selAll.checked = false; selAll.indeterminate = false; }

  localStorage.removeItem(SELECTION_STORAGE_KEY);
  localStorage.removeItem(CART_STORAGE_KEY);
  localStorage.removeItem(CART_DETAILS_KEY);

  syncSelectionBar();
  updateSelectedPreview();
  updateSelectAllLabel();
  updateCartBadge();
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
//  CART STORAGE HELPERS
// ─────────────────────────────────────────────────────────────
function getCartDocIds() {
  // Single source of truth
  return restoreSelectionsFromLocalStorage();
}

function getCartDocDetails() {
  try {
    var stored  = localStorage.getItem(CART_DETAILS_KEY);
    if (!stored) return {};
    var details = JSON.parse(stored);
    return typeof details === 'object' ? details : {};
  } catch (e) { return {}; }
}

function saveCartDocIds(ids) {
  if (ids.length > 0) {
    localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(ids));
  } else {
    localStorage.removeItem(CART_STORAGE_KEY);
  }
}

function saveCartDocDetails(details) {
  if (Object.keys(details).length > 0) {
    localStorage.setItem(CART_DETAILS_KEY, JSON.stringify(details));
  } else {
    localStorage.removeItem(CART_DETAILS_KEY);
  }
}


// ─────────────────────────────────────────────────────────────
//  CART BADGE
// ─────────────────────────────────────────────────────────────
function updateCartBadge() {
  var ids   = restoreSelectionsFromLocalStorage();
  var badge = document.getElementById('cart-badge');
  var headerBadge = document.getElementById('cart-badge-header');
  if (badge) {
    badge.textContent = ids.length;
    badge.classList.toggle('visible', ids.length > 0);
  }
  if (headerBadge) {
    headerBadge.textContent = ids.length;
    headerBadge.classList.toggle('visible', ids.length > 0);
  }
}


// ─────────────────────────────────────────────────────────────
//  CART MODAL
// ─────────────────────────────────────────────────────────────
function openCartModal() {
  var modal = document.getElementById('cart-modal');
  if (modal) {
    modal.classList.add('open');
    renderCartModal();
    document.body.style.overflow = 'hidden';
  }
}

function closeCartModal() {
  var modal = document.getElementById('cart-modal');
  if (modal) { modal.classList.remove('open'); document.body.style.overflow = ''; }
}

function renderCartModal() {
  var body = document.getElementById('cart-modal-body');
  if (!body) return;

  var ids           = getCartDocIds();
  var storedDetails = getCartDocDetails();

  if (ids.length === 0) {
    body.innerHTML = '<p class="cart-empty-msg">No documents selected</p>';
    return;
  }

  var html           = '';
  var updatedDetails = {};

  ids.forEach(function(id) {
    // Start with stored title — works on any page
    var title = (storedDetails[id] && storedDetails[id].title) ? storedDetails[id].title : id;

    // Upgrade with live DOM name if doc is on current page
    var cb = document.querySelector('.doc-checkbox[value="' + id + '"]');
    if (cb) {
      var row    = cb.closest('tr');
      var nameEl = row ? row.querySelector('.doc-name') : null;
      if (nameEl && nameEl.textContent.trim()) title = nameEl.textContent.trim();
    }

    updatedDetails[id] = { title: title };

    html += '<div class="cart-modal-item" data-doc-id="' + id + '">';
    html +=   '<div class="cart-modal-item-info">';
    html +=     '<div class="cart-modal-item-header">';
    html +=       '<span class="cart-modal-doc-num" style="font-family:var(--font-mono);font-size:10px;color:var(--muted);">' + id + '</span>';
    html +=     '</div>';
    html +=     '<div class="cart-modal-item-title" title="' + title.replace(/"/g, '&quot;') + '">' + title + '</div>';
    html +=   '</div>';
    html +=   '<button class="cart-modal-remove" onclick="removeFromCart(\'' + id + '\')" title="Remove">&#x2715;</button>';
    html += '</div>';
  });

  // Persist updated titles for next page navigation
  saveCartDocDetails(updatedDetails);
  body.innerHTML = html;
}

function addToCart(docId) {
  var ids = restoreSelectionsFromLocalStorage();
  if (!ids.includes(docId)) {
    ids.push(docId);
    localStorage.setItem(SELECTION_STORAGE_KEY, JSON.stringify(ids));
    var cb = document.querySelector('.doc-checkbox[value="' + docId + '"]');
    if (cb) {
      var row    = cb.closest('tr');
      var nameEl = row ? row.querySelector('.doc-name') : null;
      var details = getCartDocDetails();
      details[docId] = { title: nameEl ? nameEl.textContent.trim() : docId };
      saveCartDocDetails(details);
    }
    updateCartBadge();
  }
}

function removeFromCart(docId) {
  var ids   = restoreSelectionsFromLocalStorage();
  var index = ids.indexOf(docId);
  if (index > -1) ids.splice(index, 1);

  if (ids.length > 0) {
    localStorage.setItem(SELECTION_STORAGE_KEY, JSON.stringify(ids));
  } else {
    localStorage.removeItem(SELECTION_STORAGE_KEY);
  }

  var details = getCartDocDetails();
  delete details[docId];
  saveCartDocDetails(details);

  var cb = document.querySelector('.doc-checkbox[value="' + docId + '"]');
  if (cb) {
    cb.checked = false;
    cb.closest('tr').classList.remove('row-selected');
    syncSelectionBar();
    updateSelectAllLabel();
  }

  updateCartBadge();
  renderCartModal();
}

function clearCart() {
  restoreSelectionsFromLocalStorage().forEach(function(id) {
    var cb = document.querySelector('.doc-checkbox[value="' + id + '"]');
    if (cb) { cb.checked = false; cb.closest('tr').classList.remove('row-selected'); }
  });
  localStorage.removeItem(SELECTION_STORAGE_KEY);
  localStorage.removeItem(CART_STORAGE_KEY);
  localStorage.removeItem(CART_DETAILS_KEY);
  syncSelectionBar();
  updateSelectAllLabel();
  updateCartBadge();
  renderCartModal();
  showToast('Cart cleared', 'info');
}

function openRoutingModalFromCart() {
  var ids = getCartDocIds();
  if (ids.length === 0) { showToast('No documents in cart to route', 'warning'); return; }
  ids.forEach(function(id) {
    var cb = document.querySelector('.doc-checkbox[value="' + id + '"]');
    if (cb) { cb.checked = true; cb.closest('tr').classList.add('row-selected'); }
  });
  syncSelectionBar();
  closeCartModal();
  openRoutingModal();
}

function openTransferModalFromCart() {
  var ids = getCartDocIds();
  if (ids.length === 0) { showToast('No documents in cart to transfer', 'warning'); return; }
  ids.forEach(function(id) {
    var cb = document.querySelector('.doc-checkbox[value="' + id + '"]');
    if (cb) { cb.checked = true; cb.closest('tr').classList.add('row-selected'); }
  });
  syncSelectionBar();
  closeCartModal();
  openTransferModal();
}

function toggleCartItem(docId, checked) {
  if (checked) {
    addToCart(docId);
    var cb = document.querySelector('.doc-checkbox[value="' + docId + '"]');
    if (cb) { cb.checked = true; cb.closest('tr').classList.add('row-selected'); }
  } else {
    removeFromCart(docId);
  }
  syncSelectionBar();
}

function initCart() {
  updateCartBadge();
}


// ─────────────────────────────────────────────────────────────
//  SORTABLE HEADERS
// ─────────────────────────────────────────────────────────────
function setupSortableHeaders() {
  document.querySelectorAll('th.sortable').forEach(function(th) {
    th.addEventListener('click', function() {
      var cur = th.getAttribute('aria-sort');
      document.querySelectorAll('th.sortable').forEach(function(h) { h.setAttribute('aria-sort', 'none'); });
      th.setAttribute('aria-sort', cur === 'descending' ? 'ascending' : 'descending');
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
  setTimeout(function() {
    var first = modal.querySelector('input:not([type=hidden]), select, textarea, .rp-close');
    if (first) first.focus();
  }, 80);
  function onBackdrop(e) {
    if (e.target === modal) { closeModal(id); modal.removeEventListener('click', onBackdrop); }
  }
  modal.addEventListener('click', onBackdrop);
}

function closeModal(id) {
  var modal = document.getElementById(id);
  if (modal) modal.classList.remove('open');
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open').forEach(function(m) { m.classList.remove('open'); });
  }
  if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
    e.preventDefault(); openOqsModal();
  }
});


// ─────────────────────────────────────────────────────────────
//  ROUTING MODAL
// ─────────────────────────────────────────────────────────────
function openRoutingModal() {
  openModal('routing-modal');
  initSlipDate();

  var groupingInfo = analyzeReferredToGrouping();
  updateSelectedPreview();

  var hintEl = document.getElementById('routing-hint');
  if (hintEl) {
    if (groupingInfo.groupCount > 1) {
      hintEl.innerHTML = '&#128203; Documents will be grouped by "Referred To" &#8212; ' + groupingInfo.groupCount + ' routing slips will be created.';
    } else if (groupingInfo.totalDocs > 0 && groupingInfo.referredTo) {
      hintEl.innerHTML = '&#10003; All selected documents have the same "Referred To" &#8212; 1 routing slip will be created.';
    } else {
      hintEl.innerHTML = '&#128161; Enter a destination office above, or select documents with "Referred To" values.';
    }
  }

  var destInput = document.getElementById('route-dest');
  var prev      = document.getElementById('modal-dest-preview');
  if (destInput) {
    if (groupingInfo.allSame && groupingInfo.referredTo) {
      destInput.value = groupingInfo.referredTo;
      if (prev) prev.textContent = groupingInfo.referredTo;
    } else {
      destInput.value = '';
      if (prev) prev.textContent = '(enter below)';
    }
  }

  var titleEl = document.getElementById('routing-modal-title');
  if (titleEl) {
    if (groupingInfo.groupCount > 1) {
      titleEl.innerHTML = '&#128228; Create Routing Slip <span class="rp-count" id="sel-count">' + groupingInfo.totalDocs + ' selected (' + groupingInfo.groupCount + ' groups)</span>';
    } else {
      titleEl.innerHTML = '&#128228; Create Routing Slip <span class="rp-count" id="sel-count">' + groupingInfo.totalDocs + ' selected</span>';
    }
  }

  var btn = document.querySelector('#routing-modal .btn-route');
  if (btn) { btn.disabled = false; btn.textContent = (groupingInfo.groupCount > 1 ? 'Create Routing Slips' : 'Create Routing Slip'); }
}

function analyzeReferredToGrouping() {
  var checked   = document.querySelectorAll('.doc-checkbox:checked');
  var totalDocs = checked.length;
  if (totalDocs === 0) return { totalDocs: 0, groupCount: 0, allSame: false, referredTo: '', groups: {} };

  var groups = {}, referredTos = [];
  checked.forEach(function(cb) {
    var row        = cb.closest('tr');
    var referredTo = (row ? row.getAttribute('data-referred-to') : '') || '(No Referred To)';
    if (!groups[referredTo]) groups[referredTo] = [];
    groups[referredTo].push(cb.value);
    referredTos.push(referredTo);
  });

  var uniqueReferredTos = referredTos
    .filter(function(r) { return r !== '(No Referred To)'; })
    .filter(function(v, i, a) { return a.indexOf(v) === i; });
  var allSame      = uniqueReferredTos.length <= 1 && Object.keys(groups).length <= 1;
  var hasOnlyEmpty = Object.keys(groups).every(function(k) { return k === '(No Referred To)'; });
  if (hasOnlyEmpty) allSame = true;

  return {
    totalDocs:  totalDocs,
    groupCount: Object.keys(groups).length,
    allSame:    allSame,
    referredTo: uniqueReferredTos[0] || '',
    groups:     groups
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
    var tfv = document.getElementById('time-from'); if (tfv) tfv.value = '';
    var ttv = document.getElementById('time-to');   if (ttv) ttv.value = '';
  }
}

function autoSelectByTime() {
  var useTime = document.getElementById('use-time-range').checked;
  var tf = document.getElementById('time-from').value;
  var tt = document.getElementById('time-to').value;
  var sd = document.getElementById('slip-date').value;
  if (useTime && (!tf || !tt)) { showToast('Please set both From and To times.', 'warning'); return; }
  var count = 0;
  document.querySelectorAll('.doc-checkbox').forEach(function(cb) {
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
    showToast('No documents found in that range.', 'warning');
  } else {
    showToast(count + ' document' + (count > 1 ? 's' : '') + ' selected by time range.', 'success');
    var btn = document.getElementById('btn-auto-select');
    if (btn) { var orig = btn.textContent; btn.textContent = '&#10003; ' + count + ' selected'; setTimeout(function() { btn.textContent = orig; }, 2000); }
  }
  updateSelectedPreview();
}

function submitRouting() {
  var groupingInfo = analyzeReferredToGrouping();
  var groups       = groupingInfo.groups;
  var groupKeys    = Object.keys(groups);
  var useGrouped   = groupKeys.length > 1;
  var manualDest   = document.getElementById('route-dest').value.trim();

  if (manualDest && useGrouped) {
    if (!confirm('Route ALL documents to "' + manualDest + '"?\n\nOK = all to manual destination.\nCancel = separate slips per "Referred To".')) return;
    useGrouped = false;
  }

  if (!manualDest && useGrouped) {
    var hasEmpty = groupKeys.some(function(k) { return k === '(No Referred To)'; });
    if (hasEmpty) {
      showToast('Some documents have no "Referred To". Enter a destination manually.', 'warning');
      var el = document.getElementById('route-dest');
      el.focus(); el.style.borderColor = '#FCA5A5'; el.style.background = 'rgba(220,38,38,.15)';
      setTimeout(function() { el.style.borderColor = ''; el.style.background = ''; }, 2500);
      return;
    }
  }

  if (!useGrouped) {
    var dest = manualDest || groupingInfo.referredTo || '';
    if (!dest) {
      var el = document.getElementById('route-dest');
      el.focus(); el.style.borderColor = '#FCA5A5'; el.style.background = 'rgba(220,38,38,.15)';
      setTimeout(function() { el.style.borderColor = ''; el.style.background = ''; }, 2500);
      showToast('Please enter a destination office.', 'warning'); return;
    }
    // Use ALL stored IDs (cross-page)
    var ids = restoreSelectionsFromLocalStorage();
    if (!ids.length) { showToast('No documents selected.', 'warning'); return; }
    var btn = document.querySelector('#routing-modal .btn-route');
    if (btn) { if (btn.disabled) return; btn.disabled = true; btn.textContent = 'Creating slip...'; }
    document.getElementById('routing-doc-ids').value    = ids.join(',');
    document.getElementById('routing-dest-field').value = dest;
    document.getElementById('routing-notes').value      = document.getElementById('route-notes').value;
    document.getElementById('routing-slip-date').value  = document.getElementById('slip-date').value;
    document.getElementById('routing-time-from').value  = document.getElementById('time-from').value;
    document.getElementById('routing-time-to').value    = document.getElementById('time-to').value;
    document.getElementById('routing-form').submit();
    return;
  }

  var btn = document.querySelector('#routing-modal .btn-route');
  if (btn) { if (btn.disabled) return; btn.disabled = true; btn.textContent = 'Creating ' + groupKeys.length + ' slips...'; }

  var form = document.getElementById('routing-form');
  form.querySelectorAll('.grouped-data').forEach(function(el) { el.remove(); });

  function addHidden(name, val) {
    var inp = document.createElement('input');
    inp.type = 'hidden'; inp.name = name; inp.className = 'grouped-data'; inp.value = val;
    form.appendChild(inp);
  }
  addHidden('grouped_routing',   JSON.stringify(groups));
  addHidden('grouped_notes',     document.getElementById('route-notes').value || '');
  addHidden('grouped_slip_date', document.getElementById('slip-date').value);
  addHidden('grouped_time_from', document.getElementById('time-from').value);
  addHidden('grouped_time_to',   document.getElementById('time-to').value);
  form.action = '/routing-slip/create-grouped';
  form.submit();
}


// ─────────────────────────────────────────────────────────────
//  TRANSFER MODAL
// ─────────────────────────────────────────────────────────────
function openTransferModal() {
  var ids = getSelectedIds();
  if (!ids.length) { showToast('Please select at least one document to transfer.', 'warning'); return; }
  var countEl = document.getElementById('transfer-sel-count');
  if (countEl) countEl.textContent = ids.length + ' selected';
  resetTransferModal();
  openModal('transfer-modal');
}

function closeTransferModal() { closeModal('transfer-modal'); }

function resetTransferModal() {
  var el;
  el = document.getElementById('transfer-type');        if (el) el.value = '';
  el = document.getElementById('transfer-office');      if (el) { el.innerHTML = '<option value="">— Select Office —</option>'; el.disabled = true; }
  el = document.getElementById('transfer-office-info'); if (el) el.textContent = '';
  el = document.getElementById('transfer-staff');       if (el) { el.innerHTML = '<option value="">— Select Staff —</option>'; el.disabled = true; }
  _hideBlock('transfer-office-block');
  _hideBlock('transfer-staff-block');
  _hideBlock('transfer-submit-block');
  var btn = document.getElementById('btn-do-transfer');
  if (btn) { btn.disabled = true; btn.textContent = 'Transfer Documents'; }
  _setStep(1);
}

function onTransferTypeChangeIndex() {
  var type         = document.getElementById('transfer-type').value;
  var officeSelect = document.getElementById('transfer-office');
  var staffSelect  = document.getElementById('transfer-staff');
  staffSelect.innerHTML = '<option value="">— Select Staff —</option>'; staffSelect.disabled = true;
  var btn = document.getElementById('btn-do-transfer'); if (btn) btn.disabled = true;
  _hideBlock('transfer-staff-block'); _hideBlock('transfer-submit-block');
  if (!type) { _hideBlock('transfer-office-block'); _setStep(1); return; }
  _setStep(2);
  if (type === 'inside_office') {
    var lbl = document.getElementById('transfer-office-label'); if (lbl) lbl.textContent = 'Your Office';
    officeSelect.innerHTML = '<option value="' + modalCurrentOffice + '">' + modalCurrentOffice + '</option>';
    officeSelect.value = modalCurrentOffice; officeSelect.disabled = true;
    var info = document.getElementById('transfer-office-info'); if (info) info.textContent = 'Auto-selected: your office';
    _showBlock('transfer-office-block'); _populateTransferStaff(modalCurrentOffice); _showBlock('transfer-staff-block'); _setStep(3);
  } else {
    var lbl2 = document.getElementById('transfer-office-label'); if (lbl2) lbl2.textContent = 'Select Office';
    var opts = '<option value="">— Select Office —</option>';
    sortedOffices.forEach(function(office) {
      if (office === 'No Office' || office === modalCurrentOffice) return;
      opts += '<option value="' + office + '">' + office + '</option>';
    });
    officeSelect.innerHTML = opts; officeSelect.disabled = false;
    var info2 = document.getElementById('transfer-office-info'); if (info2) info2.textContent = '';
    _showBlock('transfer-office-block');
  }
}

function updateTransferStaffIndex() {
  var office = document.getElementById('transfer-office').value;
  _hideBlock('transfer-staff-block'); _hideBlock('transfer-submit-block');
  var btn = document.getElementById('btn-do-transfer'); if (btn) btn.disabled = true;
  if (!office) return;
  _populateTransferStaff(office); _showBlock('transfer-staff-block'); _setStep(3);
}

function _populateTransferStaff(office) {
  var sel = document.getElementById('transfer-staff');
  sel.innerHTML = '<option value="">— Select Staff —</option>';
  if (!office || !officesData[office]) return;
  officesData[office].forEach(function(s) {
    var name = s.full_name || s.username;
    sel.innerHTML += '<option value="' + s.username + '">' + name + ' (@' + s.username + ')</option>';
  });
  sel.disabled = false;
}

function onTransferStaffChangeIndex() {
  var val = document.getElementById('transfer-staff').value;
  if (val) {
    _showBlock('transfer-submit-block');
    var btn = document.getElementById('btn-do-transfer'); if (btn) btn.disabled = false;
  } else {
    _hideBlock('transfer-submit-block');
  }
}

function submitTransfer() {
  var csrfToken    = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
  var transferType = document.getElementById('transfer-type').value;
  var office       = document.getElementById('transfer-office').value || modalCurrentOffice;
  var staff        = document.getElementById('transfer-staff').value;
  var selectedIds  = transferSingleDocId ? [transferSingleDocId] : getSelectedIds();

  if (!transferType || !staff) { showToast('Please complete all steps.', 'warning'); return; }
  if (!selectedIds.length)     { showToast('Please select at least one document.', 'warning'); return; }

  var btn = document.getElementById('btn-do-transfer');
  if (btn) { if (btn.disabled) return; btn.disabled = true; btn.textContent = 'Transferring...'; }

  var form = document.createElement('form'); form.method = 'POST';
  var fields;
  if (transferSingleDocId) {
    form.action = '/transfer/' + transferSingleDocId;
    fields = [['transfer_type',transferType],['new_office',office],['new_staff',staff],['csrf_token',csrfToken]];
  } else {
    form.action = '/transfer-batch';
    fields = [['doc_ids',selectedIds.join(',')],['transfer_type',transferType],['new_office',office],['new_staff',staff],['csrf_token',csrfToken]];
  }
  fields.forEach(function(pair) {
    var inp = document.createElement('input'); inp.type = 'hidden'; inp.name = pair[0]; inp.value = pair[1]; form.appendChild(inp);
  });
  document.body.appendChild(form); form.submit();
}

function _setStep(active) {
  for (var i = 1; i <= 3; i++) {
    var el = document.getElementById('step-' + i); if (!el) continue;
    el.classList.remove('active', 'done');
    if (i < active) el.classList.add('done'); else if (i === active) el.classList.add('active');
  }
}


// ─────────────────────────────────────────────────────────────
//  STATUS MODAL
// ─────────────────────────────────────────────────────────────
function openStatusModal() {
  var ids = getSelectedIds();
  if (!ids.length) { showToast('Please select at least one document to update.', 'warning'); return; }
  var countEl = document.getElementById('status-sel-count'); if (countEl) countEl.textContent = ids.length + ' selected';
  var sel = document.getElementById('new-status'); if (sel) sel.value = '';
  var rem = document.getElementById('status-remarks'); if (rem) rem.value = '';
  var btn = document.getElementById('btn-do-status-update'); if (btn) btn.disabled = true;
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
  var form = document.createElement('form'); form.method = 'POST'; form.action = '/bulk-update-status';
  var pairs = [['doc_ids',ids.join(',')],['new_status',newStatus],['csrf_token',csrfToken]];
  if (remarks) pairs.push(['remarks', remarks]);
  pairs.forEach(function(pair) {
    var inp = document.createElement('input'); inp.type = 'hidden'; inp.name = pair[0]; inp.value = pair[1]; form.appendChild(inp);
  });
  document.body.appendChild(form); form.submit();
}


// ─────────────────────────────────────────────────────────────
//  SELECTED DOCUMENT PREVIEW
// ─────────────────────────────────────────────────────────────
function updateSelectedPreview() {
  var checked = document.querySelectorAll('.doc-checkbox:checked');
  var n       = checked.length;
  var countEl = document.getElementById('sel-count');
  if (countEl) {
    var gi = analyzeReferredToGrouping();
    countEl.textContent = gi.groupCount > 1 ? n + ' selected (' + gi.groupCount + ' groups)' : n + ' selected';
  }
  var preview = document.getElementById('selected-preview');
  var list    = document.getElementById('selected-list');
  if (!preview || !list) return;
  if (n === 0) { preview.style.display = 'none'; list.innerHTML = ''; return; }
  preview.style.display = 'block';
  var gi = analyzeReferredToGrouping();
  var groups = gi.groups; var groupKeys = Object.keys(groups);
  if (groupKeys.length > 1 || (groupKeys.length === 1 && groupKeys[0] === '(No Referred To)')) {
    var html = ''; var counter = 1;
    groupKeys.forEach(function(key) {
      var docs  = groups[key];
      var label = key === '(No Referred To)' ? 'No Referred To' : 'Referred To: ' + key;
      html += '<div style="padding:6px 0;border-bottom:1px solid rgba(255,255,255,.2);margin-top:8px;">';
      html += '<div style="font-weight:600;color:#FCD34D;font-size:11px;text-transform:uppercase;margin-bottom:4px;">' + label + ' (' + docs.length + ')</div>';
      docs.forEach(function(id) {
        var cb = document.querySelector('.doc-checkbox[value="' + id + '"]');
        var row = cb ? cb.closest('tr') : null; var name = row ? row.querySelector('.doc-name') : null;
        html += '<div style="padding:2px 0;padding-left:12px;font-size:12px;">' + counter++ + '. ' + (name ? name.textContent.trim() : id) + '</div>';
      });
      html += '</div>';
    });
    list.innerHTML = html;
  } else {
    list.innerHTML = Array.from(checked).map(function(cb, i) {
      var row = cb.closest('tr'); var name = row ? row.querySelector('.doc-name') : null;
      return '<div style="padding:3px 0;border-bottom:1px solid rgba(255,255,255,.1)">' + (i+1) + '. ' + (name ? name.textContent.trim() : cb.value) + '</div>';
    }).join('');
  }
}


// ─────────────────────────────────────────────────────────────
//  PENDING DOCUMENTS
// ─────────────────────────────────────────────────────────────
function checkPendingDocuments() {
  var badge   = document.getElementById('pending-badge');
  var banner  = document.getElementById('incoming-banner');
  var ibBadge = document.getElementById('ib-badge');
  var ibSub   = document.getElementById('ib-sub-text');
  if (!badge && !banner) return;
  fetch('/api/pending-count')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var count = data.count || 0;
      if (badge) { badge.textContent = count > 0 ? count : ''; badge.style.display = count > 0 ? 'block' : 'none'; }
      if (banner) {
        banner.style.display = count > 0 ? 'flex' : 'none';
        if (ibBadge) ibBadge.textContent = count;
        if (ibSub) ibSub.textContent = count + ' document' + (count !== 1 ? 's' : '') + ' transferred to you · Click to review and accept';
      }
    })
    .catch(function(err) { console.error('pending-count error:', err); });
}


// ─────────────────────────────────────────────────────────────
//  TOAST
// ─────────────────────────────────────────────────────────────
var _toastIcons = { success: '&#10003;', error: '&#10007;', info: '&#x2139;', warning: '&#9888;' };

function showToast(message, type) {
  type = type || 'info';
  var container = document.getElementById('toast-container');
  if (!container) return;
  var toast = document.createElement('div');
  toast.className = 'toast ' + type;
  toast.setAttribute('role', 'alert');
  toast.innerHTML =
    '<span class="toast-icon">' + (_toastIcons[type] || '') + '</span>' +
    '<span class="toast-msg">' + message + '</span>' +
    '<button class="toast-close" aria-label="Dismiss">&#x2715;</button>';
  toast.querySelector('.toast-close').addEventListener('click', function() { _dismissToast(toast); });
  container.appendChild(toast);
  var timer = setTimeout(function() { _dismissToast(toast); }, 3500);
  toast._timer = timer;
}

function _dismissToast(toast) {
  if (toast._timer) clearTimeout(toast._timer);
  toast.style.transition = 'opacity .3s, transform .3s';
  toast.style.opacity    = '0';
  toast.style.transform  = 'translateY(8px)';
  setTimeout(function() { if (toast.parentElement) toast.parentElement.removeChild(toast); }, 320);
}


// ─────────────────────────────────────────────────────────────
//  OFFICE QR MODAL
// ─────────────────────────────────────────────────────────────
function openOqsModal() {
  var overlay = document.getElementById('oqs-modal-overlay'); if (overlay) overlay.classList.add('open');
  var search  = document.getElementById('oqs-search');        if (search)  search.focus();
}
function closeOqsModal() {
  var overlay = document.getElementById('oqs-modal-overlay'); if (overlay) overlay.classList.remove('open');
}
function filterOffices(query) {
  var q       = (query || '').toLowerCase().trim();
  var cards   = document.querySelectorAll('.oqs-card');
  var visible = 0;
  cards.forEach(function(card) {
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
  return Array.from(document.querySelectorAll('.doc-checkbox:checked')).map(function(cb) { return cb.value; });
}
function _showBlock(id) { var el = document.getElementById(id); if (el) el.style.display = 'block'; }
function _hideBlock(id) { var el = document.getElementById(id); if (el) el.style.display = 'none'; }
function _showTransferBlock(id) { _showBlock(id); }
function _hideTransferBlock(id) { _hideBlock(id); }


// ─────────────────────────────────────────────────────────────
//  KEBAB MENU
// ─────────────────────────────────────────────────────────────
function toggleKebabMenu(btn) {
  var dropdown = btn.nextElementSibling;
  var isShown  = dropdown.classList.contains('show');
  document.querySelectorAll('.kebab-dropdown.show').forEach(function(d) { d.classList.remove('show'); });
  if (!isShown) dropdown.classList.add('show');
}

document.addEventListener('click', function(e) {
  if (!e.target.closest('.kebab-menu')) {
    document.querySelectorAll('.kebab-dropdown.show').forEach(function(d) {
      d.classList.remove('show');
      d.style.position = ''; d.style.left = ''; d.style.top = ''; d.style.right = ''; d.style.margin = '';
    });
  }
});

document.addEventListener('contextmenu', function(e) {
  var row = e.target.closest('.doc-row');
  if (row) {
    e.preventDefault();
    var kebabMenu = row.querySelector('.kebab-menu');
    if (kebabMenu) {
      var dropdown = kebabMenu.querySelector('.kebab-dropdown');
      document.querySelectorAll('.kebab-dropdown.show').forEach(function(d) { d.classList.remove('show'); });
      dropdown.style.position = 'fixed';
      dropdown.style.left     = e.clientX + 'px';
      dropdown.style.top      = e.clientY + 'px';
      dropdown.style.right    = 'auto';
      dropdown.style.margin   = '0';
      dropdown.classList.add('show');
    }
  }
});