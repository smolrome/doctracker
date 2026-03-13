// ── LOADING
function showLoading(msg) {
  document.getElementById('loading-text').textContent = msg || 'Processing...';
  document.getElementById('loading-overlay').classList.add('active');
}
window.addEventListener('pageshow', e => {
  if (e.persisted) document.getElementById('loading-overlay').classList.remove('active');
});

// ── OFFICE QR MODAL
function toggleOfficeQR() {
  const modal = document.getElementById('office-qr-modal');
  if (!modal) return;
  const isOpen = modal.style.display !== 'none';
  modal.style.display = isOpen ? 'none' : 'flex';
  document.body.style.overflow = isOpen ? '' : 'hidden';
}

function filterOffices(query) {
  const cards   = document.querySelectorAll('.office-qr-card');
  const noneMsg = document.getElementById('office-qr-none');
  const q = query.toLowerCase().trim();
  let visible = 0;
  cards.forEach(card => {
    const name = card.getAttribute('data-name') || '';
    const show = q === '' || name.includes(q);
    card.style.display = show ? 'block' : 'none';
    if (show) visible++;
  });
  if (noneMsg) noneMsg.style.display = visible === 0 ? 'block' : 'none';
}

// ── CART MODAL
function openCartModal() {
  cancelEdit();
  document.getElementById('cart-modal-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeCartModal() {
  cancelEdit();
  document.getElementById('cart-modal-overlay').classList.remove('open');
  document.body.style.overflow = '';
}

function onCartOverlayClick(e) {
  if (e.target === document.getElementById('cart-modal-overlay')) closeCartModal();
}

// ── EDIT
function openEdit(tmpId, itemEl) {
  const panel = document.getElementById('cmp-edit-panel');
  const body  = document.getElementById('cmp-body');
  document.getElementById('edit-tmp-id').value      = itemEl.dataset.tmpId;
  document.getElementById('edit-doc-name').value    = itemEl.dataset.docName;
  document.getElementById('edit-unit-office').value = itemEl.dataset.unitOffice;
  document.getElementById('edit-referred-to').value = itemEl.dataset.referredTo;
  document.getElementById('edit-description').value = itemEl.dataset.description;
  const catSel = document.getElementById('edit-category');
  if (catSel) {
    for (let opt of catSel.options) opt.selected = (opt.value === itemEl.dataset.category);
  }
  panel.style.display = 'block';
  body.style.display  = 'none';
  document.getElementById('edit-doc-name').focus();
}

function cancelEdit() {
  const panel = document.getElementById('cmp-edit-panel');
  const body  = document.getElementById('cmp-body');
  if (panel) panel.style.display = 'none';
  if (body)  body.style.display  = 'block';
}

// ── AUTO-OPEN OFFICE MODAL if ?pick_office=1
(function () {
  const params = new URLSearchParams(window.location.search);
  if (params.get('pick_office') === '1') {
    window.addEventListener('load', toggleOfficeQR);
  }
})();