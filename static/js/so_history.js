// so_history.js — Filter logic for SO History file browser

function updateBulkBar() {
  var checked = document.querySelectorAll('.sh-card-checkbox:checked');
  var bar     = document.getElementById('sh-bulk-bar');
  var count   = document.getElementById('sh-bulk-count');
  if (!bar) return;
  if (checked.length > 0) {
    bar.style.display = 'flex';
    if (count) count.textContent = checked.length + ' selected';
  } else {
    bar.style.display = 'none';
  }
}

function toggleSelectAll(cb) {
  document.querySelectorAll('.sh-card-checkbox:not([disabled]):not([hidden])').forEach(function (c) {
    var card = c.closest('.sh-card');
    if (card && !card.hidden) c.checked = cb.checked;
  });
  updateBulkBar();
}

function clearSelection() {
  document.querySelectorAll('.sh-card-checkbox').forEach(function (c) { c.checked = false; });
  var selectAll = document.getElementById('sh-select-all');
  if (selectAll) selectAll.checked = false;
  var bar = document.getElementById('sh-bulk-bar');
  if (bar) bar.style.display = 'none';
}

async function bulkDeleteSelected() {
  var checked = document.querySelectorAll('.sh-card-checkbox:checked');
  var ids = Array.from(checked).map(function (c) { return c.dataset.id; });
  if (ids.length === 0) return;
  if (!confirm('Delete ' + ids.length + ' SO record(s)? This cannot be undone.')) return;

  var csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
  var deleted = 0;
  for (var i = 0; i < ids.length; i++) {
    try {
      var res  = await fetch('/api/so/delete/' + ids[i], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        credentials: 'same-origin',
      });
      var data = await res.json();
      if (data.success) {
        var card = document.querySelector('[data-record-id="' + ids[i] + '"]');
        if (card) card.remove();
        deleted++;
      }
    } catch (e) {}
  }

  clearSelection();
  alert(deleted + ' record(s) deleted successfully.');
}

function confirmDelete(recordId, employeeName) {
  if (!confirm('Delete SO record for ' + employeeName + '? This will permanently remove the file and database record.')) {
    return;
  }
  var csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
  fetch('/api/so/delete/' + recordId, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    credentials: 'same-origin',
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.success) {
        var card = document.querySelector('[data-record-id="' + recordId + '"]');
        if (card) card.remove();
        alert('SO record deleted successfully.');
      } else {
        alert('Error: ' + data.message);
      }
    })
    .catch(function (e) { alert('Error: ' + e); });
}

(function () {
  const searchInput  = document.getElementById('sh-search');
  const typeFilter   = document.getElementById('sh-type-filter');
  const visibleCount = document.getElementById('sh-visible-count');
  const cards        = Array.from(document.querySelectorAll('.sh-card[data-search]'));

  function applyFilters() {
    const q    = (searchInput  ? searchInput.value.trim().toLowerCase()  : '');
    const type = (typeFilter   ? typeFilter.value.trim().toLowerCase()   : '');

    let visible = 0;
    cards.forEach(function (card) {
      const searchText = (card.dataset.search || '').toLowerCase();
      const cardType   = (card.dataset.type   || '').toLowerCase();

      const matchSearch = !q    || searchText.includes(q);
      const matchType   = !type || cardType === type;

      if (matchSearch && matchType) {
        card.hidden = false;
        visible++;
      } else {
        card.hidden = true;
      }
    });

    if (visibleCount) {
      visibleCount.textContent = visible + ' record' + (visible !== 1 ? 's' : '');
    }
  }

  if (searchInput) searchInput.addEventListener('input',  applyFilters);
  if (typeFilter)  typeFilter.addEventListener('change', applyFilters);

  // Run once on load to set initial count
  applyFilters();
})();
