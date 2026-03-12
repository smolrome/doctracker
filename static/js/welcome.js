function filterOffices(q) {
  q = q.toLowerCase().trim();
  document.querySelectorAll('#offices-grid .office-card').forEach(card => {
    card.style.display = (!q || card.dataset.name.includes(q)) ? '' : 'none';
  });
}
