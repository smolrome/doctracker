const EYE_OPEN   = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
const EYE_CLOSED = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`;

const form = document.getElementById('reg-form');
form.addEventListener('submit', function(e) {
  const p1 = document.getElementById('pw1').value;
  const p2 = document.getElementById('pw2').value;
  if (p1 !== p2) {
    e.preventDefault();
    alert('Passwords do not match.');
    return;
  }
  if (p1.length < 8) {
    e.preventDefault();
    alert('Password must be at least 8 characters.');
    return;
  }
  document.getElementById('submit-btn').disabled = true;
  document.getElementById('loading-overlay').classList.add('active');
});

window.addEventListener('pageshow', e => {
  if (e.persisted) {
    document.getElementById('loading-overlay').classList.remove('active');
    document.getElementById('submit-btn').disabled = false;
  }
});

document.querySelectorAll('.password-toggle').forEach(btn => {
  btn.addEventListener('click', () => {
    const input = document.getElementById(btn.dataset.inputId);
    if (!input) return;
    const showing = input.type === 'text';
    input.type = showing ? 'password' : 'text';
    btn.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
    btn.innerHTML = showing ? EYE_OPEN : EYE_CLOSED;
    input.focus();
  });
});