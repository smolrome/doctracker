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

// ── CART MODAL ──

function openCartModal() {
  renderCartModal();
  document.getElementById('cart-modal-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeCartModal() {
  document.getElementById('cart-modal-overlay').classList.remove('open');
  document.body.style.overflow = '';
}

function onCartOverlayClick(e) {
  if (e.target === document.getElementById('cart-modal-overlay')) closeCartModal();
}

function renderCartModal() {
  const body = document.getElementById('cmp-body');
  const submitBtn = document.getElementById('cmp-submit-btn');
  const countBadge = document.getElementById('cmp-count-badge');

  // Read cart items from the existing cart DOM (your .cart-item elements)
  const cartItems = document.querySelectorAll('.cart-item');
  countBadge.textContent = cartItems.length;

  if (cartItems.length === 0) {
    body.innerHTML = `
      <div class="cmp-empty">
        <div class="cmp-empty-icon">🛒</div>
        <p>No documents in your submission list yet.</p>
      </div>`;
    submitBtn.disabled = true;
    return;
  }

  submitBtn.disabled = false;
  let html = '';
  cartItems.forEach((item, i) => {
    const nameEl   = item.querySelector('.cart-item-name');
    const metaEl   = item.querySelector('.cart-item-meta');
    const removeBtn = item.querySelector('.btn-remove');
    const name = nameEl ? nameEl.textContent.trim() : '—';
    const meta = metaEl ? metaEl.innerHTML  : '';
    // Grab the remove button's onclick so we can mirror it
    const removeOnclick = removeBtn ? removeBtn.getAttribute('onclick') : null;
    const removeAttr = removeOnclick ? `onclick="${removeOnclick.replace(/"/g, "'")};closeCartModal();renderCartModal();"` : '';

    html += `
      <div class="cmp-item">
        <div class="cmp-item-num">${i + 1}</div>
        <div class="cmp-item-body">
          <div class="cmp-item-name">${name}</div>
          <div class="cmp-item-meta">${meta}</div>
        </div>
        ${removeOnclick ? `<button class="cmp-item-remove" ${removeAttr}>Remove</button>` : ''}
      </div>`;
  });
  body.innerHTML = html;
}

function submitAllFromModal() {
  closeCartModal();
  // Trigger your existing submit-all button
  const existingBtn = document.querySelector('.btn-submit-all');
  if (existingBtn) existingBtn.click();
}

// Keep FAB badge in sync with cart item count
function updateCartFabBadge() {
  const count = document.querySelectorAll('.cart-item').length;
  const badge = document.getElementById('cart-fab-badge');
  if (!badge) return;
  badge.textContent = count > 0 ? count : '';
  badge.classList.toggle('visible', count > 0);
}

// Call on load and hook into any cart mutations
document.addEventListener('DOMContentLoaded', () => {
  updateCartFabBadge();

  // Watch for cart additions/removals via MutationObserver
  const cartContainer = document.querySelector('.cart-section');
  if (cartContainer) {
    new MutationObserver(updateCartFabBadge).observe(cartContainer, { childList: true, subtree: true });
  }
});

// ── FAB badge init (server-rendered count)
(function() {
  const count = {{ cart|length if cart else 0 }};
  const badge = document.getElementById('cart-fab-badge');
  if (badge) {
    badge.textContent = count > 0 ? count : '';
    badge.classList.toggle('visible', count > 0);
  }
  // Auto-open modal if there are items and user just added one
  {% if cart and cart|length > 0 %}
  // Uncomment to auto-open on load: openCartModal();
  {% endif %}
})();

function openCartModal() {
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

// ── Edit
function openEdit(tmpId, itemEl) {
  const panel = document.getElementById('cmp-edit-panel');
  const body  = document.getElementById('cmp-body');

  document.getElementById('edit-tmp-id').value        = itemEl.dataset.tmpId;
  document.getElementById('edit-doc-name').value      = itemEl.dataset.docName;
  document.getElementById('edit-unit-office').value   = itemEl.dataset.unitOffice;
  document.getElementById('edit-referred-to').value   = itemEl.dataset.referredTo;
  document.getElementById('edit-description').value   = itemEl.dataset.description;

  const catSel = document.getElementById('edit-category');
  if (catSel) {
    for (let opt of catSel.options) {
      opt.selected = (opt.value === itemEl.dataset.category);
    }
  }

  panel.style.display = 'block';
  body.style.display  = 'none';
  document.getElementById('edit-doc-name').focus();
}

function cancelEdit() {
  document.getElementById('cmp-edit-panel').style.display = 'none';
  document.getElementById('cmp-body').style.display       = 'block';
}