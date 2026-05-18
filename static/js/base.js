// ── Password visibility toggle ────────────────────────────────────────────
function togglePasswordVisibility(inputId, btnId) {
  const passwordInput = document.getElementById(inputId);
  const toggleBtn = document.getElementById(btnId);
  
  if (!passwordInput || !toggleBtn) return;
  
  const isPassword = passwordInput.type === 'password';
  passwordInput.type = isPassword ? 'text' : 'password';
  
  // Toggle icon between eye and eye-slash
  toggleBtn.innerHTML = isPassword 
    ? '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>' 
    : '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
}

// Auto-initialize password toggle buttons
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.password-toggle').forEach(function(btn) {
    const inputId = btn.getAttribute('data-input-id');
    if (inputId) {
      btn.addEventListener('click', function() {
        togglePasswordVisibility(inputId, btn.id);
      });
    }
  });
});


// ── CSRF: auto-inject token into every POST form ──────────────────────────
(function () {
  const TOKEN = document.querySelector('meta[name="csrf-token"]')?.content || '';
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('form').forEach(function (form) {
      if ((form.method || '').toLowerCase() === 'post') {
        if (!form.querySelector('[name="csrf_token"]')) {
          const inp = document.createElement('input');
          inp.type  = 'hidden';
          inp.name  = 'csrf_token';
          inp.value = TOKEN;
          form.appendChild(inp);
        }
      }
    });
  });
})();


/* ── Dark mode ── */
(function () {
  const stored = localStorage.getItem('theme');
  if (stored === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
})();

function toggleTheme() {
  const root = document.documentElement;
  const btn  = document.getElementById('theme-toggle');
  const isDark = root.getAttribute('data-theme') === 'dark';
  if (isDark) {
    root.removeAttribute('data-theme');
    localStorage.setItem('theme', 'light');
    if (btn) btn.textContent = '🌙';
  } else {
    root.setAttribute('data-theme', 'dark');
    localStorage.setItem('theme', 'dark');
    if (btn) btn.textContent = '☀️';
  }
}

// Sync icon on page load
document.addEventListener('DOMContentLoaded', function () {
  const btn = document.getElementById('theme-toggle');
  if (btn && document.documentElement.getAttribute('data-theme') === 'dark') {
    btn.textContent = '☀️';
  }
});

// ── Mobile drawer ─────────────────────────────────────────────────────────
function toggleMenu() {
  const drawer  = document.getElementById('nav-drawer');
  const overlay = document.getElementById('nav-drawer-overlay');
  const isOpen  = drawer.classList.contains('open');
  drawer.classList.toggle('open', !isOpen);
  overlay.classList.toggle('open', !isOpen);
  drawer.setAttribute('aria-hidden', isOpen ? 'true' : 'false');
}

function closeMenu() {
  document.getElementById('nav-drawer').classList.remove('open');
  document.getElementById('nav-drawer-overlay').classList.remove('open');
  document.getElementById('nav-drawer').setAttribute('aria-hidden', 'true');
}

// Close drawer on outside click (the overlay div already calls closeMenu(),
// but this covers keyboard Escape too)
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') {
    closeMenu();
    document.querySelectorAll('.nav-dropdown').forEach(function (dd) { dd.classList.remove('open'); });
    closeAllModals();
  }
});


// ── Dropdowns ─────────────────────────────────────────────────────────────
function toggleDD(id) {
  const all = document.querySelectorAll('.nav-dropdown');
  all.forEach(function (dd) { if (dd.id !== id) dd.classList.remove('open'); });
  document.getElementById(id).classList.toggle('open');
}

document.addEventListener('click', function (e) {
  if (!e.target.closest('.nav-dropdown')) {
    document.querySelectorAll('.nav-dropdown').forEach(function (dd) { dd.classList.remove('open'); });
  }
});


// ── Generic modal helpers ─────────────────────────────────────────────────
function openModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.add('open');
  setTimeout(function() {
    const first = el.querySelector('input:not([type=hidden]), select, textarea, .rp-close');
    if (first) first.focus();
  }, 80);
  function onBackdrop(e) {
    if (e.target === el) { closeModal(id); el.removeEventListener('click', onBackdrop); }
  }
  el.addEventListener('click', onBackdrop);
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('open');
}

function closeAllModals() {
  document.querySelectorAll('.modal-overlay.open').forEach(function (m) {
    m.classList.remove('open');
  });
}


// ── Flash auto-dismiss (5 s) ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.flash').forEach(function (flash) {
    setTimeout(function () {
      flash.style.transition = 'opacity .4s, transform .4s';
      flash.style.opacity    = '0';
      flash.style.transform  = 'translateY(-6px)';
      setTimeout(function () { flash.remove(); }, 420);
    }, 5000);
  });

  // Check if this page was redirected after a successful transfer/routing
  var urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('cart_cleared') === '1') {
    // Clear cart from localStorage
    var CART_STORAGE_KEY = 'doctracker_cart_docs';
    var CART_DETAILS_KEY = 'doctracker_cart_details';
    var SELECTION_STORAGE_KEY = 'doctracker_selected_docs';
    localStorage.removeItem(CART_STORAGE_KEY);
    localStorage.removeItem(CART_DETAILS_KEY);
    localStorage.removeItem(SELECTION_STORAGE_KEY);
    
    // Update cart badge if it exists
    var cartBadge = document.getElementById('cart-badge-header');
    if (cartBadge) cartBadge.textContent = '0';
    
    // Remove the query parameter from URL without reloading
    urlParams.delete('cart_cleared');
    var newUrl = window.location.pathname + (urlParams.toString() ? '?' + urlParams.toString() : '');
    window.history.replaceState({}, document.title, newUrl);
  }
});


// ── Clear DB modal ────────────────────────────────────────────────────────
function confirmClearDB() {
  // Reset the typed-confirmation input each time the modal opens
  const input = document.getElementById('cleardb-confirm-input');
  const btn   = document.getElementById('cleardb-confirm-btn');
  if (input) input.value = '';
  if (btn)   btn.disabled = true;
  openModal('clear-db-modal');
}

function closeClearDBModal() {
  closeModal('clear-db-modal');
}

// CHANGED: unlock the Delete button only after typing exactly "DELETE"
function onClearDBType(value) {
  const btn = document.getElementById('cleardb-confirm-btn');
  if (btn) btn.disabled = (value.trim() !== 'DELETE');
}


// ══════════════════════════════════════════════════════════
//  PER-ACTION THEMED LOADER
// ══════════════════════════════════════════════════════════
const LOADERS = {
  'add':            { icon:'📝', title:'Saving Document...',          steps:['Validating fields','Generating reference number','Saving to database'],      accent:'#0E7490', gradient:'linear-gradient(90deg,#0E7490,#0891B2)', bg:'rgba(14,116,144,.05)', duration:1800 },
  'edit':           { icon:'✏️', title:'Updating Document...',         steps:['Checking changes','Writing to database','Done'],                             accent:'#7C3AED', gradient:'linear-gradient(90deg,#7C3AED,#8B5CF6)', bg:'rgba(124,58,237,.05)', duration:1600 },
  'delete':         { icon:'🗑️', title:'Deleting Document...',         steps:['Checking permissions','Moving to trash'],                                    accent:'#DC2626', gradient:'linear-gradient(90deg,#DC2626,#EF4444)', bg:'rgba(220,38,38,.04)',  duration:1400 },
  'restore':        { icon:'♻️', title:'Restoring Document...',        steps:['Locating document','Restoring from trash'],                                  accent:'#059669', gradient:'linear-gradient(90deg,#059669,#10B981)', bg:'rgba(5,150,105,.05)',  duration:1400 },
  'update-status':  { icon:'🔄', title:'Updating Status...',           steps:['Applying new status','Logging change'],                                      accent:'#D97706', gradient:'linear-gradient(90deg,#D97706,#F59E0B)', bg:'rgba(217,119,6,.05)',  duration:1200 },
  'view':           { icon:'👁️', title:'Opening Document...',          steps:['Loading details'],                                                           accent:'#0E7490', gradient:'linear-gradient(90deg,#0E7490,#06B6D4)', bg:'rgba(14,116,144,.04)', duration:800  },
  'routing-slip':   { icon:'📋', title:'Creating Routing Slip...',     steps:['Collecting documents','Generating QR codes','Updating statuses','Finalising slip'], accent:'#1D4ED8', gradient:'linear-gradient(90deg,#1D4ED8,#3B82F6)', bg:'rgba(29,78,216,.05)',  duration:2400 },
  'slip-scan':      { icon:'📡', title:'Processing Slip Scan...',      steps:['Reading QR token','Updating all documents'],                                 accent:'#0891B2', gradient:'linear-gradient(90deg,#0891B2,#06B6D4)', bg:'rgba(8,145,178,.05)',  duration:1600 },
  'scan':           { icon:'🤖', title:'AI Scanning Document...',      steps:['Uploading image','Reading with AI','Extracting fields','Done'],               accent:'#6D28D9', gradient:'linear-gradient(90deg,#6D28D9,#8B5CF6)', bg:'rgba(109,40,217,.05)', duration:4000 },
  'upload-qr':      { icon:'📷', title:'Reading QR Code...',           steps:['Decoding image','Looking up document'],                                      accent:'#0891B2', gradient:'linear-gradient(90deg,#0891B2,#06B6D4)', bg:'rgba(8,145,178,.05)',  duration:1800 },
  'doc-scan':       { icon:'✅', title:'Processing QR Scan...',        steps:['Verifying token','Updating status'],                                         accent:'#059669', gradient:'linear-gradient(90deg,#059669,#10B981)', bg:'rgba(5,150,105,.05)',  duration:1400 },
  'receive':        { icon:'📥', title:'Recording Receipt...',         steps:['Logging receipt','Updating status'],                                         accent:'#1D4ED8', gradient:'linear-gradient(90deg,#1D4ED8,#3B82F6)', bg:'rgba(29,78,216,.04)',  duration:1400 },
  'import-excel':   { icon:'📊', title:'Importing Spreadsheet...',     steps:['Reading file','Mapping columns','Inserting rows','Verifying data'],           accent:'#15803D', gradient:'linear-gradient(90deg,#15803D,#16A34A)', bg:'rgba(21,128,61,.05)',  duration:6000 },
  'backup':         { icon:'🗄️', title:'Generating Backup...',         steps:['Collecting documents','Packaging data','Preparing download'],                 accent:'#374151', gradient:'linear-gradient(90deg,#374151,#6B7280)', bg:'rgba(55,65,81,.04)',   duration:2000 },
  'backup/restore': { icon:'📤', title:'Restoring from Backup...',     steps:['Reading backup file','Validating data','Writing to database','Done'],         accent:'#B45309', gradient:'linear-gradient(90deg,#B45309,#D97706)', bg:'rgba(180,83,9,.05)',   duration:3000 },
  'send-invite':    { icon:'📧', title:'Sending Invite...',            steps:['Generating secure link','Sending email'],                                     accent:'#0E7490', gradient:'linear-gradient(90deg,#0E7490,#0891B2)', bg:'rgba(14,116,144,.05)', duration:2000 },
  'register':       { icon:'🔐', title:'Creating Account...',          steps:['Checking username','Hashing password','Creating account'],                   accent:'#7C3AED', gradient:'linear-gradient(90deg,#7C3AED,#8B5CF6)', bg:'rgba(124,58,237,.05)', duration:2000 },
  'delete-user':    { icon:'👤', title:'Removing User...',             steps:['Verifying admin','Deleting account'],                                        accent:'#DC2626', gradient:'linear-gradient(90deg,#DC2626,#EF4444)', bg:'rgba(220,38,38,.04)',  duration:1400 },
  'disable-user':   { icon:'🔒', title:'Disabling Account...',         steps:['Revoking access','Logging action'],                                          accent:'#D97706', gradient:'linear-gradient(90deg,#D97706,#F59E0B)', bg:'rgba(217,119,6,.05)',  duration:1200 },
  'enable-user':    { icon:'🔓', title:'Enabling Account...',          steps:['Restoring access','Logging action'],                                         accent:'#059669', gradient:'linear-gradient(90deg,#059669,#10B981)', bg:'rgba(5,150,105,.05)',  duration:1200 },
  'login':          { icon:'🔑', title:'Signing In...',                steps:['Checking credentials','Starting session'],                                   accent:'#1D4ED8', gradient:'linear-gradient(90deg,#0A2540,#1D4ED8)', bg:'rgba(29,78,216,.05)',  duration:1600 },
  'logout':         { icon:'👋', title:'Signing Out...',               steps:['Ending session'],                                                            accent:'#6B7280', gradient:'linear-gradient(90deg,#6B7280,#9CA3AF)', bg:'rgba(107,114,128,.04)',duration:800  },
  'clear-database': { icon:'⚠️', title:'Clearing All Data...',         steps:['Verifying admin','Deleting all documents','Logging action'],                 accent:'#DC2626', gradient:'linear-gradient(90deg,#991B1B,#DC2626)', bg:'rgba(220,38,38,.06)',  duration:2000 },
  'office-qr-page': { icon:'🏢', title:'Generating Office QR...',      steps:['Creating QR codes','Saving office'],                                         accent:'#7C3AED', gradient:'linear-gradient(90deg,#7C3AED,#8B5CF6)', bg:'rgba(124,58,237,.05)', duration:1600 },
  'search':         { icon:'🔍', title:'Searching...',                 steps:['Filtering records'],                                                         accent:'#0891B2', gradient:'linear-gradient(90deg,#0891B2,#06B6D4)', bg:'rgba(8,145,178,.04)',  duration:700  },
  'submit':         { icon:'📬', title:'Submitting Document...',       steps:['Uploading details','Logging submission'],                                    accent:'#059669', gradient:'linear-gradient(90deg,#059669,#10B981)', bg:'rgba(5,150,105,.05)',  duration:1800 },
  'default':        { icon:'⏳', title:'Processing...',                steps:['Working on it'],                                                             accent:'#0E7490', gradient:'linear-gradient(90deg,#0E7490,#0891B2)', bg:'rgba(14,116,144,.04)', duration:2000 },
};

function _getLoader(url, method) {
  if (method === 'get') {
    if (url.includes('/view/'))  return LOADERS['view'];
    if (url.includes('/logout')) return LOADERS['logout'];
    return LOADERS['search'];
  }
  const order = ['backup/restore','clear-database','update-status','routing-slip',
                 'import-excel','send-invite','delete-user','disable-user','enable-user',
                 'upload-qr','doc-scan','slip-scan','office-qr','register','login',
                 'logout','delete','restore','backup','receive','submit','edit','add','scan'];
  for (const k of order) {
    if (url.includes(k)) return LOADERS[k] || LOADERS['default'];
  }
  return LOADERS['default'];
}

// ── Core loading functions ────────────────────────────────────────────────
let _sseSource        = null;
let _progressInterval = null;
let _stepInterval     = null;
let _currentSteps     = [];

function _applyTheme(loader) {
  const box = document.getElementById('loading-box');
  box.style.setProperty('--loader-accent',   loader.accent);
  box.style.setProperty('--loader-gradient', loader.gradient);
  box.style.setProperty('--loader-bg',       loader.bg);
  document.getElementById('progress-bar').style.background = loader.gradient;
}

function _buildSteps(steps) {
  const el = document.getElementById('loader-steps');
  el.innerHTML = '';
  if (!steps || steps.length <= 1) { el.style.display = 'none'; return; }
  el.style.display = 'flex';
  steps.forEach(function (_, i) {
    const dot = document.createElement('div');
    dot.className = 'loader-step' + (i === 0 ? ' active' : '');
    dot.id = 'lstep-' + i;
    el.appendChild(dot);
  });
}

function _advanceStep(stepIndex) {
  const sub   = document.getElementById('loading-sub');
  const steps = _currentSteps;
  if (!steps.length) return;
  const idx = Math.min(stepIndex, steps.length - 1);
  if (sub) sub.textContent = steps[idx];
  for (let i = 0; i < steps.length; i++) {
    const dot = document.getElementById('lstep-' + i);
    if (!dot) continue;
    dot.className = 'loader-step' + (i < idx ? ' done' : i === idx ? ' active' : '');
  }
}

function showLoading(loader) {
  if (typeof loader === 'string') loader = LOADERS[loader] || LOADERS['default'];
  _currentSteps = loader.steps || [];
  document.getElementById('loading-icon').textContent = loader.icon;
  document.getElementById('loading-text').textContent = loader.title;
  document.getElementById('loading-sub').textContent  = _currentSteps[0] || '';
  _applyTheme(loader);
  _buildSteps(_currentSteps);
  setProgress(0);
  document.getElementById('loading-overlay').classList.add('active');
}

function hideLoading() {
  setProgress(100);
  setTimeout(function () {
    document.getElementById('loading-overlay').classList.remove('active');
    setProgress(0);
    if (_progressInterval) { clearInterval(_progressInterval); _progressInterval = null; }
    if (_stepInterval)     { clearInterval(_stepInterval);     _stepInterval = null; }
    if (_sseSource)        { _sseSource.close(); _sseSource = null; }
  }, 350);
}

function setProgress(pct) {
  pct = Math.min(100, Math.max(0, pct));
  const bar = document.getElementById('progress-bar');
  const lbl = document.getElementById('progress-pct');
  if (bar) bar.style.width  = pct + '%';
  if (lbl) lbl.textContent  = Math.round(pct) + '%';
}

function startFakeProgress(loader) {
  if (_progressInterval) clearInterval(_progressInterval);
  if (_stepInterval)     clearInterval(_stepInterval);
  const endPct    = 90;
  const duration  = loader.duration || 2000;
  const steps     = loader.steps || [];
  const stepCount = steps.length;
  let current = 0;
  _progressInterval = setInterval(function () {
    const remaining = endPct - current;
    current += remaining * 0.055 + 0.2;
    if (current >= endPct) { current = endPct; clearInterval(_progressInterval); _progressInterval = null; }
    setProgress(current);
  }, duration / 80);
  if (stepCount > 1) {
    const stepDelay = duration / stepCount;
    let step = 0;
    _stepInterval = setInterval(function () {
      step++;
      if (step >= stepCount) { clearInterval(_stepInterval); _stepInterval = null; return; }
      _advanceStep(step);
    }, stepDelay);
  }
}

function startSSEProgress() {
  if (_sseSource) { clearInterval(_sseSource); _sseSource = null; }
  _sseSource = setInterval(function () {
    fetch('/progress/status', { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.pct !== undefined) setProgress(data.pct);
        if (data.msg) document.getElementById('loading-sub').textContent = data.msg;
        if (data.done) { hideLoading(); clearInterval(_sseSource); _sseSource = null; }
      })
      .catch(function () {});
  }, 600);
}

// ── Auto-attach loader to forms and nav links ─────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('form').forEach(function (form) {
    form.addEventListener('submit', function () {
      if (form.dataset.noLoading) return;
      const a = (form.action || '').toLowerCase();
      const m = (form.method || 'get').toLowerCase();
      const loader = _getLoader(a, m);
      showLoading(loader);
      if (a.includes('/import-excel/confirm')) {
        startSSEProgress();
      } else {
        startFakeProgress(loader);
      }
    });
  });

  document.querySelectorAll('a.nav-btn, a.btn, a.btn-filter, a.page-back').forEach(function (link) {
    link.addEventListener('click', function () {
      const h = (link.getAttribute('href') || '').toLowerCase();
      if (!h || h.startsWith('#') || h.startsWith('javascript') || h.startsWith('http')) return;
      if (link.hasAttribute('download') || h.endsWith('.png') || h.endsWith('.xlsx') || h.endsWith('.json')) return;
      const loader = _getLoader(h, 'get');
      showLoading(loader);
      startFakeProgress(loader);
    });
  });

  document.querySelectorAll('a[href$=".png"],a[href$=".xlsx"],a[href$=".json"]').forEach(function (l) {
    l.addEventListener('click', function (e) { e.stopPropagation(); });
  });

  window.addEventListener('pageshow', function (e) { if (e.persisted) hideLoading(); });
  document.getElementById('loading-overlay').addEventListener('click', hideLoading);
});


// ══════════════════════════════════════════════════════════
//  PENDING DOCUMENTS — poll + modal
// ══════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', function () {
  checkPendingDocuments();
  setInterval(checkPendingDocuments, 30000);
});

function checkPendingDocuments() {
  fetch('/pending-count')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      const badge         = document.getElementById('pending-badge');
      const headerBadge   = document.getElementById('pending-badge-header');
      const banner        = document.getElementById('incoming-banner');
      const bannerCount   = document.getElementById('ib-badge');
      const bannerSub     = document.getElementById('ib-sub-text');
      // Only show badge when count > 0
      if (badge) { badge.textContent = data.count > 0 ? data.count : ''; badge.style.display = data.count > 0 ? 'block' : 'none'; }
      if (headerBadge) { headerBadge.textContent = data.count > 0 ? data.count : ''; headerBadge.style.display = data.count > 0 ? 'block' : 'none'; }
      if (banner && bannerCount) {
        bannerCount.textContent = data.count;
        banner.style.display = data.count > 0 ? 'block' : 'none';
      }
      if (bannerSub && data.count > 0) {
        bannerSub.textContent = data.count + ' document' + (data.count !== 1 ? 's' : '') + ' awaiting your acceptance';
      }
    })
    .catch(function (err) { console.error('Error checking pending documents:', err); });
}

var _pendingTotalCount = 0;

function _getPendingFilterParams() {
  var cat  = ((document.getElementById('pending-cat-select')  || {}).value  || '');
  var date = ((document.getElementById('pending-date-input')  || {}).value  || '');
  return { cat: cat, date: date };
}

function _updatePendingFilterUI(filteredCount) {
  var params     = _getPendingFilterParams();
  var isFiltered = params.cat || params.date;

  var dot      = document.getElementById('pending-filter-dot');
  var clearBtn = document.getElementById('pending-clear-btn');
  var countEl  = document.getElementById('pending-filter-count');

  if (dot)      dot.style.display      = isFiltered ? 'inline-block' : 'none';
  if (clearBtn) clearBtn.style.display = isFiltered ? 'inline-block' : 'none';

  if (countEl) {
    if (isFiltered) {
      countEl.textContent = 'Showing ' + filteredCount + ' of ' + _pendingTotalCount + ' document' + (_pendingTotalCount !== 1 ? 's' : '');
    } else {
      countEl.textContent = _pendingTotalCount + ' document' + (_pendingTotalCount !== 1 ? 's' : '') + ' pending';
    }
    countEl.style.display = 'block';
  }
}

function reloadPendingDocs() {
  var listContainer = document.getElementById('pending-documents-list');
  if (!listContainer) return;

  var params = _getPendingFilterParams();
  var qs = [];
  if (params.cat)  qs.push('cat='  + encodeURIComponent(params.cat));
  if (params.date) qs.push('date=' + encodeURIComponent(params.date));
  var url = '/pending-documents' + (qs.length ? '?' + qs.join('&') : '');

  listContainer.innerHTML = '<div class="modal-loading-state"><span>📭</span><p>Loading…</p></div>';

  fetch(url)
    .then(function (r) { return r.json(); })
    .then(function (docs) {
      _updatePendingFilterUI(docs.length);
      if (!docs.length) {
        var isFiltered = params.cat || params.date;
        listContainer.innerHTML = '<div class="modal-loading-state"><span>' + (isFiltered ? '🔍' : '✅') + '</span><p>' + (isFiltered ? 'No documents match these filters.' : 'No pending documents') + '</p></div>';
        return;
      }
      _pendingDocStaffMap = {};
      window._pendingDocsList = docs;
      listContainer.innerHTML = docs.map(function (doc) {
        var docId = doc.id || doc.doc_id;
        _pendingDocStaffMap[docId] = {
          staff:     doc.intended_for_username || '',
          staffName: doc.intended_for_name     || '',
          office:    doc.pending_at_office     || '',
          docName:   doc.doc_name              || '',
        };
        var forLine = doc.intended_for_name
          ? '<br><strong style="color:#0038A8;">Intended for:</strong> ' + doc.intended_for_name
          : '';
        return '<div class="pending-doc-card">' +
          '<div class="pending-doc-top">' +
            '<div>' +
              '<h4 class="pending-doc-name">' + (doc.doc_name || 'Unnamed Document') + '</h4>' +
              '<p class="pending-doc-id">' + (docId || '') + '</p>' +
            '</div>' +
            '<span class="badge badge-pending">Pending</span>' +
          '</div>' +
          '<div class="pending-doc-meta">' +
            (doc.doc_id ? '<strong>Ref:</strong> ' + doc.doc_id + '<br>' : '') +
            (doc.sender_name || doc.sender_org ? '<strong>Sender:</strong> ' + (doc.sender_name || doc.sender_org) + '<br>' : '') +
            (doc.category ? '<strong>Category:</strong> ' + doc.category + '<br>' : '') +
            '<strong>From:</strong> ' + (doc.transferred_by || 'Unknown') + '<br>' +
            '<strong>Office:</strong> ' + (doc.transferred_to_office || doc.pending_at_office || 'N/A') + '<br>' +
            '<strong>Transferred:</strong> ' + (doc.transferred_at || 'Unknown') +
            forLine +
          '</div>' +
          '<div class="pending-doc-actions">' +
            '<a href="/view/' + docId + '" target="_blank" class="btn btn-ghost btn-sm">👁 View</a>' +
            '<button class="btn btn-success btn-sm" onclick="acceptDocument(\'' + docId + '\',\'' + (doc.intended_for_username||'') + '\',\'' + (doc.intended_for_name||'').replace(/\'/g,"&#39;") + '\',\'' + (doc.pending_at_office||'') + '\')">✓ Accept</button>' +
            '<button class="btn btn-danger  btn-sm" onclick="showRejectionModal(\'' + docId + '\')">✕ Reject</button>' +
          '</div>' +
        '</div>';
      }).join('');
      listContainer.innerHTML =
        '<div style="padding:0 0 12px;display:flex;justify-content:flex-end;">' +
          '<button class="btn btn-success" id="accept-all-btn" onclick="acceptAllDocuments()" style="font-weight:700;">' +
          '✓ Accept All (' + docs.length + ')</button>' +
        '</div>' +
        listContainer.innerHTML;
    })
    .catch(function (err) {
      console.error('Error loading pending documents:', err);
      listContainer.innerHTML = '<div class="modal-loading-state" style="color:#DC2626;"><span>⚠️</span><p>Error loading documents. Please refresh.</p></div>';
    });
}

function showPendingDocumentsModal() {
  var listContainer = document.getElementById('pending-documents-list');
  if (!listContainer) return;

  openModal('pending-documents-modal');

  // Fetch unfiltered total first so count display is always accurate
  fetch('/pending-documents')
    .then(function (r) { return r.json(); })
    .then(function (all) {
      _pendingTotalCount = all.length;
      reloadPendingDocs();
    })
    .catch(function () {
      _pendingTotalCount = 0;
      reloadPendingDocs();
    });
}

function clearPendingFilters() {
  var sel   = document.getElementById('pending-cat-select');
  var input = document.getElementById('pending-date-input');
  if (sel)   sel.value   = '';
  if (input) input.value = '';
  reloadPendingDocs();
}

function closePendingDocumentsModal() { closeModal('pending-documents-modal'); }


// ── Toast notifications ────────────────────────────────────────────────────
function showToast(message, type) {
  var existing = document.getElementById('_global-toast');
  if (existing) existing.remove();
  var bg   = type === 'error' ? '#DC2626' : '#16A34A';
  var icon = type === 'error' ? '✕' : '✓';
  var toast = document.createElement('div');
  toast.id = '_global-toast';
  toast.style.cssText =
    'position:fixed;top:20px;left:50%;transform:translateX(-50%) translateY(-20px);' +
    'background:' + bg + ';color:#fff;padding:12px 20px;border-radius:12px;' +
    'font-size:14px;font-weight:700;z-index:99999;opacity:0;' +
    'transition:opacity 0.25s ease,transform 0.25s ease;' +
    'box-shadow:0 4px 16px rgba(0,0,0,0.2);white-space:nowrap;' +
    'display:flex;align-items:center;gap:8px;pointer-events:none;';
  toast.innerHTML = '<span>' + icon + '</span><span>' + message + '</span>';
  document.body.appendChild(toast);
  requestAnimationFrame(function () {
    requestAnimationFrame(function () {
      toast.style.opacity = '1';
      toast.style.transform = 'translateX(-50%) translateY(0)';
    });
  });
  setTimeout(function () {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(-50%) translateY(-20px)';
    setTimeout(function () { if (toast.parentNode) toast.remove(); }, 300);
  }, 2500);
}

// ── Accept flow ────────────────────────────────────────────────────────────
var _pendingDocStaffMap = {};

function acceptDocument(docId, intendedForUsername, intendedForName, office) {
  var csrfToken = window.CSRF_TOKEN || '';
  fetch('/accept-document/' + docId, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-CSRF-Token': csrfToken,
    },
    body: 'csrf_token=' + encodeURIComponent(csrfToken),
  })
  .then(function (r) { return r.json(); })
  .then(function (data) {
    if (data.ok) {
      showToast('Document received successfully');
      reloadPendingDocs();
      var currentUser = window.CURRENT_USERNAME || '';
      if (intendedForUsername && intendedForUsername !== currentUser) {
        setTimeout(function () {
          closePendingDocumentsModal();
          _showPostAcceptDialog(docId, intendedForUsername, intendedForName, office || '');
        }, 800);
      } else {
        setTimeout(function () { window.location.reload(); }, 1500);
      }
    } else {
      showToast(data.error || 'Failed to accept document', 'error');
    }
  })
  .catch(function () { showToast('Network error. Please try again.', 'error'); });
}

function acceptAllDocuments() {
  var docs = window._pendingDocsList || [];
  if (!docs.length) return;
  if (!confirm('Accept all ' + docs.length + ' pending documents?')) return;
  var btn = document.getElementById('accept-all-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Accepting…'; }
  var csrfToken = window.CSRF_TOKEN || '';
  var success = 0;
  var failed  = 0;
  var promises = docs.map(function (doc) {
    var docId = doc.id || doc.doc_id;
    return fetch('/accept-document/' + docId, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRF-Token': csrfToken,
      },
      body: 'csrf_token=' + encodeURIComponent(csrfToken),
    })
    .then(function (r) { return r.json(); })
    .then(function (data) { if (data.ok) success++; else failed++; })
    .catch(function () { failed++; });
  });
  Promise.all(promises).then(function () {
    reloadPendingDocs();
    if (failed === 0) {
      showToast('All ' + success + ' documents accepted successfully');
    } else {
      showToast(success + ' accepted, ' + failed + ' failed', 'error');
    }
  });
}

function _showPostAcceptDialog(docId, toStaff, staffName, office) {
  var overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:9999;display:flex;align-items:center;justify-content:center;padding:16px;';
  overlay.innerHTML =
    '<div style="background:#fff;border-radius:20px;padding:28px;max-width:400px;width:100%;box-shadow:0 24px 64px rgba(0,0,0,.25);">' +
      '<div style="width:52px;height:52px;border-radius:26px;background:#DCFCE7;display:flex;align-items:center;justify-content:center;margin:0 auto 16px;font-size:26px;line-height:1;">✓</div>' +
      '<h3 style="margin:0 0 8px;font-size:17px;font-weight:800;color:#1E293B;text-align:center;">Forward to Intended Recipient?</h3>' +
      '<p style="margin:0 0 24px;font-size:14px;color:#64748B;text-align:center;line-height:1.5;">This document was intended for <strong style="color:#1E293B;">' + staffName + '</strong>. Transfer it to them now?</p>' +
      '<div style="display:flex;flex-direction:column;gap:10px;">' +
        '<button id="_pad-confirm" style="background:#10B981;color:#fff;border:none;border-radius:12px;padding:14px;font-size:14px;font-weight:700;cursor:pointer;width:100%;">✓ Transfer to ' + staffName + '</button>' +
        '<button id="_pad-change" style="background:#fff;color:#0038A8;border:2px solid #0038A8;border-radius:12px;padding:14px;font-size:14px;font-weight:700;cursor:pointer;width:100%;">⇄ Choose Different Staff</button>' +
        '<button id="_pad-skip" style="background:transparent;color:#94A3B8;border:none;border-radius:12px;padding:14px;font-size:14px;cursor:pointer;width:100%;">Skip — I\'ll route manually</button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(overlay);
  document.getElementById('_pad-confirm').addEventListener('click', function () {
    overlay.remove();
    _doTransferAfterAccept(docId, toStaff, staffName);
  });
  document.getElementById('_pad-change').addEventListener('click', function () {
    overlay.remove();
    _showStaffPicker(docId, office);
  });
  document.getElementById('_pad-skip').addEventListener('click', function () {
    overlay.remove();
    window.location.reload();
  });
}

function _doTransferAfterAccept(docId, toStaff, staffName) {
  var csrfToken = window.CSRF_TOKEN || '';
  var body = new URLSearchParams();
  body.append('new_staff', toStaff);
  body.append('transfer_type', 'inside_office');
  body.append('csrf_token', csrfToken);
  fetch('/transfer/' + docId, {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
    body: body,
  })
  .then(function () {
    showToast('Document forwarded to ' + (staffName || toStaff));
    setTimeout(function () { window.location.reload(); }, 1500);
  })
  .catch(function () { window.location.reload(); });
}

function _showStaffPicker(docId, office) {
  fetch('/api/office-staff' + (office ? '?office=' + encodeURIComponent(office) : ''))
    .then(function (r) { return r.json(); })
    .then(function (staffList) {
      var overlay = document.createElement('div');
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:9999;display:flex;align-items:center;justify-content:center;padding:16px;';
      var rows = (staffList || []).map(function (s) {
        return '<button class="_spd-btn" data-uname="' + s.username + '" data-fname="' + (s.full_name || s.username) + '" style="display:block;width:100%;text-align:left;padding:12px 14px;border:1px solid #E2E8F0;border-radius:10px;background:#fff;cursor:pointer;font-size:14px;margin-bottom:8px;">' +
          (s.full_name || s.username) + ' <span style="color:#94A3B8;font-size:12px;">@' + s.username + '</span>' +
        '</button>';
      }).join('');
      overlay.innerHTML =
        '<div style="background:#fff;border-radius:16px;padding:24px;max-width:400px;width:100%;max-height:70vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.3);">' +
          '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">' +
            '<h3 style="margin:0;font-size:16px;font-weight:700;color:#1E293B;">Select Staff</h3>' +
            '<button id="_spd-cancel" style="background:none;border:none;font-size:20px;color:#94A3B8;cursor:pointer;">✕</button>' +
          '</div>' +
          (rows || '<p style="color:#94A3B8;text-align:center;padding:20px 0;">No staff found.</p>') +
        '</div>';
      document.body.appendChild(overlay);
      document.getElementById('_spd-cancel').addEventListener('click', function () {
        overlay.remove();
        window.location.reload();
      });
      overlay.querySelectorAll('._spd-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
          overlay.remove();
          _doTransferAfterAccept(docId, btn.getAttribute('data-uname'), btn.getAttribute('data-fname'));
        });
      });
    })
    .catch(function () {
      window.location.href = '/transfer/' + docId;
    });
}


// ── Rejection flow ─────────────────────────────────────────────────────────
function showRejectionModal(docId) {
  document.getElementById('reject-doc-id').value = docId;
  document.getElementById('rejection-reason-input').value = '';
  openModal('rejection-reason-modal');
}

function closeRejectionModal() { closeModal('rejection-reason-modal'); }

function submitRejection() {
  const docId      = document.getElementById('reject-doc-id').value;
  const reason     = document.getElementById('rejection-reason-input').value.trim();
  const csrfToken  = window.CSRF_TOKEN || '';

  if (!reason) {
    document.getElementById('rejection-reason-input').focus();
    return;
  }

  const body = new URLSearchParams();
  body.append('rejection_reason', reason);
  body.append('csrf_token', csrfToken);

  fetch('/reject-document/' + docId, {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
    body: body,
  })
  .then(function (r) {
    if (r.ok) {
      closeRejectionModal();
      closePendingDocumentsModal();
      window.location.reload();
    } else {
      alert('Error rejecting document. Please try again.');
    }
  })
  .catch(function (err) {
    console.error('Reject error:', err);
    alert('Network error. Please try again.');
  });
}

(function() {
  const img = new Image();
  img.onload = function() {
    const c = document.createElement('canvas');
    c.width = c.height = 64;
    const ctx = c.getContext('2d');
    ctx.beginPath();
    ctx.arc(32, 32, 32, 0, Math.PI * 2);
    ctx.closePath();
    ctx.clip();
    ctx.drawImage(img, 0, 0, 64, 64);
    const link = document.querySelector("link[rel='icon']");
    link.href = c.toDataURL('image/png');
  };
  img.src = '/static/logo.png';
})();