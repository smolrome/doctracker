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