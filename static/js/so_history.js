// so_history.js — Filter logic for SO History file browser

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
