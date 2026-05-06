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
     - If category holds a value the user typed manually, never touch it.
     - If category holds a value we auto-filled (tracked via dataset.autoFilled),
       allow re-detection to clear or replace it as the doc_name evolves.
     - Exactly one match → auto-fill and tag dataset.autoFilled.
     - Zero or multiple matches → clear only if we auto-filled it, then leave empty. */
  function detectDocType(docNameInput) {
    var form = docNameInput.closest('form');
    if (!form) return;

    var categoryInput = form.querySelector('input[name="category"]');
    if (!categoryInput) return;

    var currentVal   = categoryInput.value.trim();
    var autoFilledVal = (categoryInput.dataset.autoFilled || '').trim();

    // If the field has a value that we did NOT auto-fill, it was manually
    // typed — never overwrite the user's choice.
    if (currentVal && currentVal !== autoFilledVal) return;

    var docName = docNameInput.value;

    // doc_name is empty — unconditionally clear both category and referred-to
    // so the form resets fully when the user wipes the primary field.
    if (!docName.trim()) {
      categoryInput.value = '';
      delete categoryInput.dataset.autoFilled;
      detectReferredTo(categoryInput);   // cascades to clear referred-to too
      return;
    }

    var options = getDatalistOptions(categoryInput);
    if (!options.length) return;

    // Collect all word-boundary matches.
    var matches = options.filter(function (option) {
      var pattern = new RegExp('\\b' + escapeRegex(option) + '\\b', 'i');
      return pattern.test(docName);
    });

    if (matches.length === 1) {
      // Exactly one match — auto-fill and tag it.
      categoryInput.value = matches[0];
      categoryInput.dataset.autoFilled = matches[0];
    } else {
      // Zero or multiple matches — ambiguous or nothing found.
      // Clear only if the current value was previously auto-filled.
      if (currentVal === autoFilledVal) {
        categoryInput.value = '';
        delete categoryInput.dataset.autoFilled;
      }
    }

    // Always cascade into referred-to detection after category may have changed.
    detectReferredTo(categoryInput);
  }

  /* ── Auto referred-to detection ─────────────────────────────────────────────
     Given a category input, find the paired staff combobox in the same <form>
     and auto-fill the "Referred To" field with the staff member whose
     documents_handled list contains the selected category.
     Uses the same guard pattern as detectDocType:
     - Manual selection is never overwritten (dataset.autoFilledName tracks it).
     - Exactly one match → auto-fill.
     - Zero or multiple matches → clear only if we auto-filled it. */
  function detectReferredTo(categoryInput) {
    var staff = (typeof window.STAFF !== 'undefined') ? window.STAFF : [];
    if (!staff.length) return;

    var form = categoryInput.closest('form');
    if (!form) return;

    var comboWrapper = form.querySelector('.staff-combobox');
    if (!comboWrapper) return;

    var visibleInput = comboWrapper.querySelector('.staff-combo-input');
    var hiddenInput  = comboWrapper.querySelector('input[name="referred_to_username"]');
    if (!visibleInput || !hiddenInput) return;

    var category        = categoryInput.value.trim();
    var currentVisible  = visibleInput.value.trim();
    var autoFilledName  = (hiddenInput.dataset.autoFilledName || '').trim();

    // If the visible field has a value the user typed/selected manually, never touch it.
    if (currentVisible && currentVisible !== autoFilledName) return;

    // Category is empty — unconditionally clear referred-to so the form
    // resets fully when the category is wiped (whether by the user or by
    // detectDocType clearing the auto-filled category above).
    if (!category) {
      visibleInput.value = '';
      hiddenInput.value  = '';
      delete hiddenInput.dataset.autoFilledName;
      return;
    }

    // Find staff whose documents_handled contains this category (case-insensitive exact match).
    var catLower = category.toLowerCase();
    var matches = staff.filter(function (s) {
      return (s.documents_handled || []).some(function (doc) {
        return doc.trim().toLowerCase() === catLower;
      });
    });

    if (matches.length === 1) {
      visibleInput.value               = matches[0].full_name;
      hiddenInput.value                = matches[0].username;
      hiddenInput.dataset.autoFilledName = matches[0].full_name;
    } else {
      // Zero or multiple — clear only if we auto-filled it.
      if (currentVisible === autoFilledName) {
        visibleInput.value = '';
        hiddenInput.value  = '';
        delete hiddenInput.dataset.autoFilledName;
      }
    }
  }

  /* Attach listeners once the DOM is ready.
     Covers all three doc_name inputs: add-form, edit-cart-form, edit-form.
     Also watches each paired category input:
       - on manual change → disown the autoFilled tag so detectDocType never
         overwrites the user's choice, then cascade into detectReferredTo.
       - on input/blur → cascade into detectReferredTo so typing a category
         manually also triggers referred-to auto-fill.
     Also watches each referred_to visible input:
       - on input/change → disown the autoFilledName tag so detectReferredTo
         never overwrites a staff member the user picked manually. */
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('input[name="doc_name"]').forEach(function (docNameInput) {
      docNameInput.addEventListener('input', function () { detectDocType(docNameInput); });
      docNameInput.addEventListener('blur',  function () { detectDocType(docNameInput); });

      var form = docNameInput.closest('form');
      if (!form) return;

      // ── Category field guards ───────────────────────────────────────────────
      var categoryInput = form.querySelector('input[name="category"]');
      if (categoryInput) {
        categoryInput.addEventListener('change', function () {
          // User manually picked a value — disown auto-fill tag.
          delete categoryInput.dataset.autoFilled;
          // Still cascade so a manual category pick triggers referred-to fill.
          detectReferredTo(categoryInput);
        });
        categoryInput.addEventListener('input', function () {
          detectReferredTo(categoryInput);
        });
        categoryInput.addEventListener('blur', function () {
          detectReferredTo(categoryInput);
        });
      }

      // ── Referred-to visible input guard ────────────────────────────────────
      var comboWrapper = form.querySelector('.staff-combobox');
      if (comboWrapper) {
        var staffVisible = comboWrapper.querySelector('.staff-combo-input');
        var staffHidden  = comboWrapper.querySelector('input[name="referred_to_username"]');
        if (staffVisible && staffHidden) {
          staffVisible.addEventListener('input', function () {
            // User is typing manually — disown any auto-filled tracking.
            delete staffHidden.dataset.autoFilledName;
          });
          staffVisible.addEventListener('change', function () {
            delete staffHidden.dataset.autoFilledName;
          });
        }
      }
    });
  });

}());