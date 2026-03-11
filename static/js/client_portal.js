function filterOfficesC(query) {
  const q = query.toLowerCase().trim();
  const cards = document.querySelectorAll('.oqs-card-c');
  let visible = 0;
  cards.forEach(card => {
    const show = !q || (card.dataset.name||'').includes(q);
    card.classList.toggle('hidden', !show);
    if (show) visible++;
  });
  document.getElementById('oqs-count-c').textContent =
    visible + ' office' + (visible !== 1 ? 's' : '') + (q ? ' found' : ' available');
  document.getElementById('oqs-none-c').classList.toggle('visible', visible === 0);
}