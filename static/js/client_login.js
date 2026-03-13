(function () {
  'use strict';

  // ── Loading overlay ──────────────────────────────────────────────────────

  var loginForm      = document.getElementById('login-form');
  var loadingOverlay = document.getElementById('loading-overlay');

  if (loginForm && loadingOverlay) {
    loginForm.addEventListener('submit', function () {
      loadingOverlay.classList.add('active');
      loadingOverlay.style.display = 'flex';
    });
  }

  window.addEventListener('pageshow', function (e) {
    if (e.persisted && loadingOverlay) {
      loadingOverlay.classList.remove('active');
      loadingOverlay.style.display = 'none';
    }
  });

  // ── Password visibility toggle ────────────────────────────────────────────

  var EYE_OPEN = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
  var EYE_CLOSED = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

  document.querySelectorAll('.password-toggle').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var input = document.getElementById(btn.getAttribute('data-input-id'));
      if (!input) return;

      var showing = input.type === 'text';
      input.type  = showing ? 'password' : 'text';
      btn.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
      btn.innerHTML = showing ? EYE_OPEN : EYE_CLOSED;
      input.focus();
    });
  });

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
          if (usernameInput) { usernameInput.focus(); }
        }
      }, 1000);
    }
  }

}());