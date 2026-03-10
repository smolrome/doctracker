/* form.js — Log New Documents page */

/* ── Cart modal ── */
function toggleCartModal() {
  var modal = document.getElementById('cart-modal');
  if (modal) modal.classList.toggle('active');
}

function closeCartModal(event) {
  var modal = document.getElementById('cart-modal');
  if (modal && (event === null || event.target === modal)) {
    modal.classList.remove('active');
  }
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeCartModal(null);
});

/* ── Loading overlay ── */
function showLoading(msg) {
  document.getElementById('loading-text').textContent = msg || 'Processing...';
  document.getElementById('loading-overlay').classList.add('active');
}

window.addEventListener('pageshow', function(e) {
  if (e.persisted) document.getElementById('loading-overlay').classList.remove('active');
});

/* ── Auto-focus doc name on add mode (no error present) ── */
document.addEventListener('DOMContentLoaded', function() {
  var hasError = !!document.querySelector('.error-box');
  if (!hasError) {
    var docNameInput = document.querySelector('#add-form input[name="doc_name"]');
    if (docNameInput) docNameInput.focus();
  }
});