document.getElementById('login-form').addEventListener('submit', () =>
  document.getElementById('loading-overlay').classList.add('active'));
window.addEventListener('pageshow', e => {
  if (e.persisted) document.getElementById('loading-overlay').classList.remove('active');
});

document.querySelectorAll('.password-toggle').forEach(btn => {
  btn.addEventListener('click', () => {
    const input = document.getElementById(btn.dataset.inputId);
    const isHidden = input.type === 'password';
    input.type = isHidden ? 'text' : 'password';
    btn.setAttribute('aria-label', isHidden ? 'Hide password' : 'Show password');
    // Swap icon: eye-off when visible, eye when hidden
    btn.innerHTML = isHidden
      ? `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`
      : `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
  });
});

(function () {
  'use strict';
 
  // ── Lockout countdown ────────────────────────────────────────────────────
 
  var lockoutBanner   = document.getElementById('lockout-banner');
  var countdownEl     = document.getElementById('lockout-countdown');
 
  if (lockoutBanner && countdownEl) {
    var remaining     = parseInt(countdownEl.textContent, 10) || 0;
    var submitBtn     = document.getElementById('login-submit');
    var usernameInput = document.getElementById('client-username');
    var passwordInput = document.getElementById('client-pw');
 
    if (remaining > 0) {
      var timer = setInterval(function () {
        remaining -= 1;
        countdownEl.textContent = remaining;
 
        if (remaining <= 0) {
          clearInterval(timer);
          if (submitBtn)     { submitBtn.disabled     = false; }
          if (usernameInput) { usernameInput.disabled = false; }
          if (passwordInput) { passwordInput.disabled = false; }
          lockoutBanner.style.display = 'none';
          // Return focus to the username field once the form is usable again
          if (usernameInput) { usernameInput.focus(); }
        }
      }, 1000);
    }
  }
 
  // ── Loading overlay ──────────────────────────────────────────────────────
 
  var loginForm      = document.getElementById('login-form');
  var loadingOverlay = document.getElementById('loading-overlay');
 
  if (loginForm && loadingOverlay) {
    loginForm.addEventListener('submit', function () {
      loadingOverlay.style.display = 'flex';
    });
  }
 
  // ── Password visibility toggle ────────────────────────────────────────────
 
  var pwToggle = document.getElementById('client-pw-toggle');
 
  if (pwToggle) {
    pwToggle.addEventListener('click', function () {
      var inputId = pwToggle.getAttribute('data-input-id');
      var input   = document.getElementById(inputId);
      if (!input) return;
 
      var isPassword = input.type === 'password';
      input.type = isPassword ? 'text' : 'password';
      pwToggle.setAttribute(
        'aria-label',
        isPassword ? 'Hide password' : 'Show password'
      );
    });
  }
 
}());