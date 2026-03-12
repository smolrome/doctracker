function showLoading(msg) {
  document.getElementById('loading-text').textContent = msg || 'Processing...';
  document.getElementById('loading-overlay').classList.add('active');
}
window.addEventListener('pageshow', e => {
  if (e.persisted) document.getElementById('loading-overlay').classList.remove('active');
});

function toggleOfficeQR() {
  const modal = document.getElementById('office-qr-modal');
  if (modal) {
    if (modal.style.display === 'none') {
      modal.style.display = 'flex';
      document.body.style.overflow = 'hidden';
    } else {
      modal.style.display = 'none';
      document.body.style.overflow = '';
    }
  }
}
function filterOffices(query) {
  const cards = document.querySelectorAll('.office-qr-card');
  const noneMsg = document.getElementById('office-qr-none');
  const q = query.toLowerCase().trim();
  let visible = 0;
  cards.forEach(card => {
    const name = card.getAttribute('data-name') || '';
    if (q === '' || name.includes(q)) {
      card.style.display = 'block';
      visible++;
    } else {
      card.style.display = 'none';
    }
  });
  if (noneMsg) {
    noneMsg.style.display = visible === 0 ? 'block' : 'none';
  }
}