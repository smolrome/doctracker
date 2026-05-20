// so_history.js — Filter logic for SO History file browser

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
