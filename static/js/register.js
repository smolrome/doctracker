const form = document.getElementById('reg-form');
const pw1El = document.getElementById('pw1');

function checkRules(val) {
  const rules = {
    'rule-len': val.length >= 8,
    'rule-num': /[0-9]/.test(val),
  };
  let allOk = true;
  for (const [id, ok] of Object.entries(rules)) {
    const el = document.getElementById(id);
    if (!el) continue;
    const text = el.textContent.replace(/^[✓✗] /, '');
    el.textContent = (ok ? '✓ ' : '✗ ') + text;
    el.classList.toggle('ok', ok);
    el.classList.remove('fail');
    if (!ok) allOk = false;
  }
  return allOk;
}

if (pw1El) {
  pw1El.addEventListener('input', () => checkRules(pw1El.value));
}

if (form) {
  form.addEventListener('submit', function(e) {
    const p1 = document.getElementById('pw1').value;
    const p2 = document.getElementById('pw2').value;
    if (!checkRules(p1)) {
      e.preventDefault();
      // Mark failing rules red
      ['rule-len','rule-num'].forEach(id => {
        const el = document.getElementById(id);
        if (el && el.textContent.startsWith('✗')) el.classList.add('fail');
      });
      return;
    }
    if (p1 !== p2) {
      e.preventDefault();
      alert('Passwords do not match.');
      return;
    }
    
    // Handle office selection: dropdown + input
    const officeSelect = document.getElementById('office_select');
    const officeInput = document.getElementById('office_input');
    
    if (officeSelect && officeInput) {
      // If user selected an office from dropdown, use that value
      if (officeSelect.value) {
        officeInput.name = ''; // Don't use the input value
        // Create hidden input with selected office
        let hiddenOffice = document.querySelector('input[name="office"]');
        if (!hiddenOffice || hiddenOffice.id === 'office_input') {
          hiddenOffice = document.createElement('input');
          hiddenOffice.type = 'hidden';
          hiddenOffice.name = 'office';
          form.appendChild(hiddenOffice);
        }
        hiddenOffice.value = officeSelect.value;
      } else if (!officeInput.value.trim()) {
        // Neither dropdown nor input has value
        e.preventDefault();
        alert('Please select or enter your office name.');
        return;
      }
      // If dropdown is empty but input has value, use input (backend handles case-insensitive match)
    }
    
    document.getElementById('submit-btn').disabled = true;
    document.getElementById('loading-overlay').classList.add('active');
  });
}

window.addEventListener('pageshow', e => {
  if (e.persisted) {
    document.getElementById('loading-overlay').classList.remove('active');
    const sb = document.getElementById('submit-btn');
    if (sb) sb.disabled = false;
  }
});

// Update office input required state based on dropdown selection
function updateOfficeRequired() {
  const officeSelect = document.getElementById('office_select');
  const officeInput = document.getElementById('office_input');
  
  if (officeSelect && officeInput) {
    if (officeSelect.value) {
      // An office is selected from dropdown - input is optional
      officeInput.required = false;
      officeInput.placeholder = 'Or type to override with a different name...';
    } else {
      // No office selected - input is required
      officeInput.required = true;
      officeInput.placeholder = 'Type new office name if not in list...';
    }
  }
}