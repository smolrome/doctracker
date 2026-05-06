/* form.js — Log New Documents page */

/* ── Simple Toast Notification (standalone) ── */
function showToast(message, type) {
  // Remove existing toast if any
  var existing = document.querySelector('.form-toast');
  if (existing) existing.remove();
  
  var toast = document.createElement('div');
  toast.className = 'form-toast toast-' + (type || 'info');
  toast.textContent = message;
  toast.style.cssText = 'position:fixed;bottom:20px;right:20px;padding:12px 20px;border-radius:8px;z-index:10000;font-family:inherit;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,0.15)';
  
  if (type === 'info') {
    toast.style.background = '#3B82F6';
    toast.style.color = '#fff';
  } else if (type === 'success') {
    toast.style.background = '#10B981';
    toast.style.color = '#fff';
  } else if (type === 'error') {
    toast.style.background = '#EF4444';
    toast.style.color = '#fff';
  } else {
    toast.style.background = '#6B7280';
    toast.style.color = '#fff';
  }
  
  document.body.appendChild(toast);
  
  setTimeout(function() {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s ease';
    setTimeout(function() { toast.remove(); }, 300);
  }, 3000);
}

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

/* ── Form field persistence ── */
var FORM_STORAGE_KEY = 'doctracker_adddoc_form';

// Save form fields to localStorage
function saveFormFields() {
  var form = document.getElementById('add-form');
  if (!form) return;
  
  var fields = {};
  var inputs = form.querySelectorAll('input[name], select[name], textarea[name]');
  inputs.forEach(function(input) {
    if (input.type === 'hidden') return; // Skip hidden fields
    fields[input.name] = input.value;
  });
  
  localStorage.setItem(FORM_STORAGE_KEY, JSON.stringify(fields));
}

// Restore form fields from localStorage
function restoreFormFields() {
  var form = document.getElementById('add-form');
  if (!form) return;
  
  var stored = localStorage.getItem(FORM_STORAGE_KEY);
  if (!stored) return;
  
  try {
    var fields = JSON.parse(stored);
    var restoredCount = 0;
    
    Object.keys(fields).forEach(function(name) {
      var input = form.querySelector('[name="' + name + '"]');
      if (input) {
        input.value = fields[name];
        restoredCount++;
      }
    });
    
    if (restoredCount > 0) {
      // Show toast notification
      showToast('Form data restored from previous session', 'info');
    }
  } catch (e) {
    console.error('Error restoring form fields:', e);
  }
}

// Clear saved form fields
function clearSavedFormFields() {
  localStorage.removeItem(FORM_STORAGE_KEY);
}

// Initialize form persistence
document.addEventListener('DOMContentLoaded', function() {
  var form = document.getElementById('add-form');
  if (!form) return;
  
  // Restore saved fields on page load
  restoreFormFields();
  
  // Auto-focus doc name on add mode (no error present)
  var hasError = !!document.querySelector('.error-box');
  if (!hasError) {
    var docNameInput = form.querySelector('input[name="doc_name"]');
    if (docNameInput) docNameInput.focus();
  }
  
  // Save fields on input change
  var inputs = form.querySelectorAll('input, select, textarea');
  inputs.forEach(function(input) {
    input.addEventListener('input', saveFormFields);
    input.addEventListener('change', saveFormFields);
  });
  
  // Clear saved fields after successful submission
  form.addEventListener('submit', function() {
    // Clear after a short delay to ensure form submits properly
    setTimeout(clearSavedFormFields, 500);
  });
  
  // Also clear when cart is submitted
  var submitAllForm = document.getElementById('submit-all-form');
  if (submitAllForm) {
    submitAllForm.addEventListener('submit', function() {
      setTimeout(clearSavedFormFields, 500);
    });
  }
});

/* ── Auto document type detection ────────────────────────────────────────────
   Listens on every input[name="doc_name"] in the page. When the user types,
   checks the value against the options in the associated <datalist> (reached
   via the sibling input[name="category"] in the same <form>). Auto-fills the
   category field if it is empty and a word-boundary match is found.
   ─────────────────────────────────────────────────────────────────────────── */
(function () {

  /* Escape special regex characters in a string. */
  function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  /* Return all non-empty option values from the <datalist> linked to a
     given input[name="category"] via its list="..." attribute. */
  function getDatalistOptions(categoryInput) {
    var listId = categoryInput.getAttribute('list');
    if (!listId) return [];
    var datalist = document.getElementById(listId);
    if (!datalist) return [];
    return Array.from(datalist.options)
      .map(function (opt) { return opt.value.trim(); })
      .filter(Boolean);
  }

  /* Core detection: given a doc_name input, find its paired category input
     (nearest input[name="category"] in the same <form>), then test each
     datalist option against the doc_name value using word boundaries.
     Only writes if the category field is currently empty.
     Longest match wins when multiple options match. */
  function detectDocType(docNameInput) {
    var form = docNameInput.closest('form');
    if (!form) return;

    var categoryInput = form.querySelector('input[name="category"]');
    if (!categoryInput) return;

    // Never overwrite what the user has already typed.
    if (categoryInput.value.trim()) return;

    var docName = docNameInput.value;
    if (!docName.trim()) return;

    var options = getDatalistOptions(categoryInput);
    if (!options.length) return;

    // Collect all word-boundary matches.
    var matches = options.filter(function (option) {
      var pattern = new RegExp('\\b' + escapeRegex(option) + '\\b', 'i');
      return pattern.test(docName);
    });

    if (!matches.length) return;

    // Longest match is most specific — use it.
    matches.sort(function (a, b) { return b.length - a.length; });
    categoryInput.value = matches[0];
  }

  /* Attach listeners once the DOM is ready.
     Covers all three doc_name inputs: add-form, edit-cart-form, edit-form. */
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('input[name="doc_name"]').forEach(function (docNameInput) {
      docNameInput.addEventListener('input', function () { detectDocType(docNameInput); });
      docNameInput.addEventListener('blur',  function () { detectDocType(docNameInput); });
    });
  });

}());