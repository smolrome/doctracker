// ── CSRF: auto-inject token into every POST form ──
(function() {
  // TOKEN is injected by the template into a meta tag: <meta name="csrf-token" content="{{ csrf_token }}">
  const TOKEN = document.querySelector('meta[name="csrf-token"]')?.content || '';
  document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('form').forEach(function(form) {
      if ((form.method || '').toLowerCase() === 'post') {
        if (!form.querySelector('[name="_csrf_token"]')) {
          const inp = document.createElement('input');
          inp.type  = 'hidden';
          inp.name  = '_csrf_token';
          inp.value = TOKEN;
          form.appendChild(inp);
        }
      }
    });
  });
})();

// ── Mobile drawer ──
function toggleMenu(){ document.getElementById('nav-drawer').classList.toggle('open'); }
function closeMenu(){ document.getElementById('nav-drawer').classList.remove('open'); }
document.addEventListener('click', function(e){
  const d=document.getElementById('nav-drawer'), h=document.querySelector('.nav-hamburger');
  if(d&&d.classList.contains('open')&&!d.contains(e.target)&&!h.contains(e.target)) closeMenu();
});

// ── Dropdowns ──
function toggleDD(id) {
  const all = document.querySelectorAll('.nav-dropdown');
  all.forEach(function(dd) {
    if (dd.id !== id) dd.classList.remove('open');
  });
  document.getElementById(id).classList.toggle('open');
}
document.addEventListener('click', function(e) {
  if (!e.target.closest('.nav-dropdown')) {
    document.querySelectorAll('.nav-dropdown').forEach(function(dd){ dd.classList.remove('open'); });
  }
});

// ── Clear DB modal ──
function confirmClearDB() {
  document.getElementById('clear-db-modal').style.display = 'flex';
}

// ══════════════════════════════════════════════════════════
//  PER-ACTION THEMED LOADER
// ══════════════════════════════════════════════════════════
const LOADERS = {

  // ── Document actions ──
  'add': {
    icon: '📝', title: 'Saving Document...',
    steps: ['Validating fields', 'Generating reference number', 'Saving to database'],
    accent: '#0E7490', gradient: 'linear-gradient(90deg,#0E7490,#0891B2)',
    bg: 'rgba(14,116,144,.05)', duration: 1800,
  },
  'edit': {
    icon: '✏️', title: 'Updating Document...',
    steps: ['Checking changes', 'Writing to database', 'Done'],
    accent: '#7C3AED', gradient: 'linear-gradient(90deg,#7C3AED,#8B5CF6)',
    bg: 'rgba(124,58,237,.05)', duration: 1600,
  },
  'delete': {
    icon: '🗑️', title: 'Deleting Document...',
    steps: ['Checking permissions', 'Moving to trash'],
    accent: '#DC2626', gradient: 'linear-gradient(90deg,#DC2626,#EF4444)',
    bg: 'rgba(220,38,38,.04)', duration: 1400,
  },
  'restore': {
    icon: '♻️', title: 'Restoring Document...',
    steps: ['Locating document', 'Restoring from trash'],
    accent: '#059669', gradient: 'linear-gradient(90deg,#059669,#10B981)',
    bg: 'rgba(5,150,105,.05)', duration: 1400,
  },
  'update-status': {
    icon: '🔄', title: 'Updating Status...',
    steps: ['Applying new status', 'Logging change'],
    accent: '#D97706', gradient: 'linear-gradient(90deg,#D97706,#F59E0B)',
    bg: 'rgba(217,119,6,.05)', duration: 1200,
  },
  'view': {
    icon: '👁️', title: 'Opening Document...',
    steps: ['Loading details'],
    accent: '#0E7490', gradient: 'linear-gradient(90deg,#0E7490,#06B6D4)',
    bg: 'rgba(14,116,144,.04)', duration: 800,
  },

  // ── Routing ──
  'routing-slip': {
    icon: '📋', title: 'Creating Routing Slip...',
    steps: ['Collecting documents', 'Generating QR codes', 'Updating statuses', 'Finalising slip'],
    accent: '#1D4ED8', gradient: 'linear-gradient(90deg,#1D4ED8,#3B82F6)',
    bg: 'rgba(29,78,216,.05)', duration: 2400,
  },
  'slip-scan': {
    icon: '📡', title: 'Processing Slip Scan...',
    steps: ['Reading QR token', 'Updating all documents'],
    accent: '#0891B2', gradient: 'linear-gradient(90deg,#0891B2,#06B6D4)',
    bg: 'rgba(8,145,178,.05)', duration: 1600,
  },

  // ── Scanning ──
  'scan': {
    icon: '🤖', title: 'AI Scanning Document...',
    steps: ['Uploading image', 'Reading with AI', 'Extracting fields', 'Done'],
    accent: '#6D28D9', gradient: 'linear-gradient(90deg,#6D28D9,#8B5CF6)',
    bg: 'rgba(109,40,217,.05)', duration: 4000,
  },
  'upload-qr': {
    icon: '📷', title: 'Reading QR Code...',
    steps: ['Decoding image', 'Looking up document'],
    accent: '#0891B2', gradient: 'linear-gradient(90deg,#0891B2,#06B6D4)',
    bg: 'rgba(8,145,178,.05)', duration: 1800,
  },
  'doc-scan': {
    icon: '✅', title: 'Processing QR Scan...',
    steps: ['Verifying token', 'Updating status'],
    accent: '#059669', gradient: 'linear-gradient(90deg,#059669,#10B981)',
    bg: 'rgba(5,150,105,.05)', duration: 1400,
  },
  'receive': {
    icon: '📥', title: 'Recording Receipt...',
    steps: ['Logging receipt', 'Updating status'],
    accent: '#1D4ED8', gradient: 'linear-gradient(90deg,#1D4ED8,#3B82F6)',
    bg: 'rgba(29,78,216,.04)', duration: 1400,
  },

  // ── Import / Export ──
  'import-excel': {
    icon: '📊', title: 'Importing Spreadsheet...',
    steps: ['Reading file', 'Mapping columns', 'Inserting rows', 'Verifying data'],
    accent: '#15803D', gradient: 'linear-gradient(90deg,#15803D,#16A34A)',
    bg: 'rgba(21,128,61,.05)', duration: 6000,
  },
  'backup': {
    icon: '🗄️', title: 'Generating Backup...',
    steps: ['Collecting documents', 'Packaging data', 'Preparing download'],
    accent: '#374151', gradient: 'linear-gradient(90deg,#374151,#6B7280)',
    bg: 'rgba(55,65,81,.04)', duration: 2000,
  },
  'backup/restore': {
    icon: '📤', title: 'Restoring from Backup...',
    steps: ['Reading backup file', 'Validating data', 'Writing to database', 'Done'],
    accent: '#B45309', gradient: 'linear-gradient(90deg,#B45309,#D97706)',
    bg: 'rgba(180,83,9,.05)', duration: 3000,
  },

  // ── User management ──
  'send-invite': {
    icon: '📧', title: 'Sending Invite...',
    steps: ['Generating secure link', 'Sending email'],
    accent: '#0E7490', gradient: 'linear-gradient(90deg,#0E7490,#0891B2)',
    bg: 'rgba(14,116,144,.05)', duration: 2000,
  },
  'register': {
    icon: '🔐', title: 'Creating Account...',
    steps: ['Checking username', 'Hashing password', 'Creating account'],
    accent: '#7C3AED', gradient: 'linear-gradient(90deg,#7C3AED,#8B5CF6)',
    bg: 'rgba(124,58,237,.05)', duration: 2000,
  },
  'delete-user': {
    icon: '👤', title: 'Removing User...',
    steps: ['Verifying admin', 'Deleting account'],
    accent: '#DC2626', gradient: 'linear-gradient(90deg,#DC2626,#EF4444)',
    bg: 'rgba(220,38,38,.04)', duration: 1400,
  },
  'disable-user': {
    icon: '🔒', title: 'Disabling Account...',
    steps: ['Revoking access', 'Logging action'],
    accent: '#D97706', gradient: 'linear-gradient(90deg,#D97706,#F59E0B)',
    bg: 'rgba(217,119,6,.05)', duration: 1200,
  },
  'enable-user': {
    icon: '🔓', title: 'Enabling Account...',
    steps: ['Restoring access', 'Logging action'],
    accent: '#059669', gradient: 'linear-gradient(90deg,#059669,#10B981)',
    bg: 'rgba(5,150,105,.05)', duration: 1200,
  },

  // ── Auth ──
  'login': {
    icon: '🔑', title: 'Signing In...',
    steps: ['Checking credentials', 'Starting session'],
    accent: '#1D4ED8', gradient: 'linear-gradient(90deg,#0A2540,#1D4ED8)',
    bg: 'rgba(29,78,216,.05)', duration: 1600,
  },
  'logout': {
    icon: '👋', title: 'Signing Out...',
    steps: ['Ending session'],
    accent: '#6B7280', gradient: 'linear-gradient(90deg,#6B7280,#9CA3AF)',
    bg: 'rgba(107,114,128,.04)', duration: 800,
  },

  // ── Admin ──
  'clear-database': {
    icon: '⚠️', title: 'Clearing All Data...',
    steps: ['Verifying admin', 'Deleting all documents', 'Logging action'],
    accent: '#DC2626', gradient: 'linear-gradient(90deg,#991B1B,#DC2626)',
    bg: 'rgba(220,38,38,.06)', duration: 2000,
  },
  'office-qr-page': {
    icon: '🏢', title: 'Generating Office QR...',
    steps: ['Creating QR codes', 'Saving office'],
    accent: '#7C3AED', gradient: 'linear-gradient(90deg,#7C3AED,#8B5CF6)',
    bg: 'rgba(124,58,237,.05)', duration: 1600,
  },

  // ── Navigation / search ──
  'search': {
    icon: '🔍', title: 'Searching...',
    steps: ['Filtering records'],
    accent: '#0891B2', gradient: 'linear-gradient(90deg,#0891B2,#06B6D4)',
    bg: 'rgba(8,145,178,.04)', duration: 700,
  },

  // ── Client ──
  'submit': {
    icon: '📬', title: 'Submitting Document...',
    steps: ['Uploading details', 'Logging submission'],
    accent: '#059669', gradient: 'linear-gradient(90deg,#059669,#10B981)',
    bg: 'rgba(5,150,105,.05)', duration: 1800,
  },

  // ── Fallback ──
  'default': {
    icon: '⏳', title: 'Processing...',
    steps: ['Working on it'],
    accent: '#0E7490', gradient: 'linear-gradient(90deg,#0E7490,#0891B2)',
    bg: 'rgba(14,116,144,.04)', duration: 2000,
  },
};

function _getLoader(url, method) {
  if (method === 'get') {
    if (url.includes('/view/'))   return LOADERS['view'];
    if (url.includes('/logout'))  return LOADERS['logout'];
    return LOADERS['search'];
  }
  const order = ['backup/restore','clear-database','update-status','routing-slip',
                 'import-excel','send-invite','delete-user','disable-user','enable-user',
                 'upload-qr','doc-scan','slip-scan','office-qr','register','login',
                 'logout','delete','restore','backup','receive','submit','edit','add',
                 'scan'];
  for (const k of order) {
    if (url.includes(k)) return LOADERS[k] || LOADERS['default'];
  }
  return LOADERS['default'];
}

// ── Core loading functions ────────────────────────────────
let _sseSource = null;
let _progressInterval = null;
let _stepInterval = null;
let _currentSteps = [];
let _currentStep = 0;

function _applyTheme(loader) {
  const box = document.getElementById('loading-box');
  box.style.setProperty('--loader-accent',    loader.accent);
  box.style.setProperty('--loader-gradient',  loader.gradient);
  box.style.setProperty('--loader-bg',        loader.bg);
  document.getElementById('progress-bar').style.background = loader.gradient;
}

function _buildSteps(steps) {
  const el = document.getElementById('loader-steps');
  el.innerHTML = '';
  if (!steps || steps.length <= 1) { el.style.display = 'none'; return; }
  el.style.display = 'flex';
  steps.forEach(function(_, i) {
    const dot = document.createElement('div');
    dot.className = 'loader-step' + (i === 0 ? ' active' : '');
    dot.id = 'lstep-' + i;
    el.appendChild(dot);
  });
}

function _advanceStep(stepIndex) {
  const sub = document.getElementById('loading-sub');
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
  _currentStep  = 0;

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
  setTimeout(function() {
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
  if (bar) bar.style.width = pct + '%';
  if (lbl) lbl.textContent = Math.round(pct) + '%';
}

function startFakeProgress(loader) {
  if (_progressInterval) clearInterval(_progressInterval);
  if (_stepInterval)     clearInterval(_stepInterval);

  const endPct   = 90;
  const duration = loader.duration || 2000;
  const steps    = loader.steps || [];
  const stepCount = steps.length;

  let current = 0;
  _progressInterval = setInterval(function() {
    const remaining = endPct - current;
    current += remaining * 0.055 + 0.2;
    if (current >= endPct) { current = endPct; clearInterval(_progressInterval); _progressInterval = null; }
    setProgress(current);
  }, duration / 80);

  if (stepCount > 1) {
    const stepDelay = duration / stepCount;
    let step = 0;
    _stepInterval = setInterval(function() {
      step++;
      if (step >= stepCount) { clearInterval(_stepInterval); _stepInterval = null; return; }
      _advanceStep(step);
    }, stepDelay);
  }
}

function startSSEProgress() {
  if (_sseSource) { clearInterval(_sseSource); _sseSource = null; }
  _sseSource = setInterval(function() {
    fetch('/progress/status', {credentials: 'same-origin'})
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.pct !== undefined) setProgress(data.pct);
        if (data.msg) document.getElementById('loading-sub').textContent = data.msg;
        if (data.done) { hideLoading(); clearInterval(_sseSource); _sseSource = null; }
      })
      .catch(function() {});
  }, 600);
}

// ── Auto-attach to forms and nav links ───────────────────
document.addEventListener('DOMContentLoaded', function(){
  document.querySelectorAll('form').forEach(function(form){
    form.addEventListener('submit', function(){
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

  document.querySelectorAll('a.nav-btn, a.btn, a.btn-filter, a.page-back').forEach(function(link){
    link.addEventListener('click', function(){
      const h = (link.getAttribute('href') || '').toLowerCase();
      if (!h || h.startsWith('#') || h.startsWith('javascript') || h.startsWith('http')) return;
      if (link.hasAttribute('download') || h.endsWith('.png') || h.endsWith('.xlsx') || h.endsWith('.json')) return;
      const loader = _getLoader(h, 'get');
      showLoading(loader);
      startFakeProgress(loader);
    });
  });

  document.querySelectorAll('a[href$=".png"],a[href$=".xlsx"],a[href$=".json"]').forEach(function(l){
    l.addEventListener('click', function(e){ e.stopPropagation(); });
  });
  window.addEventListener('pageshow', function(e){ if (e.persisted) hideLoading(); });
  document.getElementById('loading-overlay').addEventListener('click', hideLoading);
});

// ── Pending Documents ────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
  checkPendingDocuments();
  setInterval(checkPendingDocuments, 30000);
});

function checkPendingDocuments() {
  fetch('/api/pending-count')
    .then(response => response.json())
    .then(data => {
      const notification = document.getElementById('floating-notification');
      const badge = document.getElementById('pending-badge');
      if (notification && badge) {
        if (data.count > 0) {
          badge.textContent = data.count;
          notification.style.display = 'block';
        } else {
          notification.style.display = 'none';
        }
      }
    })
    .catch(error => console.error('Error checking pending documents:', error));
}

function showPendingDocumentsModal() {
  const modal = document.getElementById('pending-documents-modal');
  const listContainer = document.getElementById('pending-documents-list');
  if (!modal || !listContainer) return;

  modal.style.display = 'flex';
  listContainer.innerHTML = '<div style="text-align: center; padding: 40px; color: #5A7A91;"><span style="font-size: 48px;">📭</span><p style="margin-top: 12px;">Loading documents...</p></div>';

  fetch('/api/pending-documents')
    .then(response => response.json())
    .then(docs => {
      if (docs.length === 0) {
        listContainer.innerHTML = '<div style="text-align: center; padding: 40px; color: #5A7A91;"><span style="font-size: 48px;">✅</span><p style="margin-top: 12px;">No pending documents</p></div>';
        return;
      }

      let html = '';
      docs.forEach(doc => {
        const docName = doc.doc_name || 'Unnamed Document';
        const docId = doc.doc_id || doc.id;
        const transferredBy = doc.transferred_by || 'Unknown';
        const transferredAt = doc.transferred_at || 'Unknown';
        const office = doc.transferred_to_office || doc.pending_at_office || 'N/A';

        html += `
          <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;padding:16px;margin-bottom:12px;">
            <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:10px;">
              <div>
                <h4 style="color:#0A2540;font-size:16px;font-weight:700;margin:0 0 4px 0;">${docName}</h4>
                <p style="color:#64748B;font-size:13px;margin:0;">ID: ${docId}</p>
              </div>
              <span style="background:#FEF3C7;color:#B45309;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:600;">Pending</span>
            </div>
            <div style="font-size:13px;color:#64748B;margin-bottom:12px;">
              <strong>From:</strong> ${transferredBy}<br>
              <strong>Office:</strong> ${office}<br>
              <strong>Transferred:</strong> ${transferredAt}
            </div>
            <div style="display:flex;gap:10px;">
              <button onclick="acceptDocument('${doc.id || doc.doc_id}')" style="width:100%;padding:10px;border-radius:8px;border:none;background:#059669;color:white;font-weight:600;font-size:14px;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px;">
                ✓ Accept
              </button>
              <button onclick="showRejectionModal('${doc.id || doc.doc_id}')" style="padding:10px 16px;border-radius:8px;border:1.5px solid #DC2626;background:white;color:#DC2626;font-weight:600;font-size:14px;cursor:pointer;">
                ✕ Reject
              </button>
            </div>
          </div>
        `;
      });
      listContainer.innerHTML = html;
    })
    .catch(error => {
      console.error('Error loading pending documents:', error);
      listContainer.innerHTML = '<div style="text-align: center; padding: 40px; color: #DC2626;"><p>Error loading documents</p></div>';
    });
}

function closePendingDocumentsModal() {
  document.getElementById('pending-documents-modal').style.display = 'none';
}

function acceptDocument(docId) {
  if (!confirm('Are you sure you want to accept this document?')) return;

  fetch('/accept-document/' + docId, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
  })
  .then(response => {
    if (response.ok) {
      closePendingDocumentsModal();
      window.location.reload();
    } else {
      alert('Error accepting document');
    }
  })
  .catch(error => {
    console.error('Error:', error);
    alert('Error accepting document');
  });
}

function showRejectionModal(docId) {
  const modal = document.getElementById('rejection-reason-modal');
  document.getElementById('reject-doc-id').value = docId;
  document.getElementById('rejection-reason-input').value = '';
  modal.style.display = 'flex';
}

function submitRejection() {
  const docId = document.getElementById('reject-doc-id').value;
  const reason = document.getElementById('rejection-reason-input').value.trim();

  if (!reason) {
    alert('Please provide a reason for rejection.');
    return;
  }

  const formData = new URLSearchParams();
  formData.append('rejection_reason', reason);

  fetch('/reject-document/' + docId, {
    method: 'POST',
    body: formData
  })
  .then(response => {
    if (response.ok) {
      closeRejectionModal();
      closePendingDocumentsModal();
      window.location.reload();
    } else {
      alert('Error rejecting document');
    }
  })
  .catch(error => {
    console.error('Error:', error);
    alert('Error rejecting document');
  });
}

function closeRejectionModal() {
  document.getElementById('rejection-reason-modal').style.display = 'none';
}

// Close modals when clicking outside
document.addEventListener('DOMContentLoaded', function() {
  const pendingModal = document.getElementById('pending-documents-modal');
  const rejectionModal = document.getElementById('rejection-reason-modal');

  if (pendingModal) {
    pendingModal.addEventListener('click', function(e) {
      if (e.target === this) closePendingDocumentsModal();
    });
  }
  if (rejectionModal) {
    rejectionModal.addEventListener('click', function(e) {
      if (e.target === this) closeRejectionModal();
    });
  }
});