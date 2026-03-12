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
    
    // Handle office input - no special handling needed for datalist
    // The office value is sent directly as 'office' input
    
    document.getElementById('submit-btn').disabled = true;
    document.getElementById('loading-overlay').classList.add('active');
  });
}

// Datalist handles office suggestions automatically - no toggle needed
window.addEventListener('pageshow', e => {
  if (e.persisted) {
    document.getElementById('loading-overlay').classList.remove('active');
    const sb = document.getElementById('submit-btn');
    if (sb) sb.disabled = false;
  }
});