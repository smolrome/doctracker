const video     = document.getElementById('staff-qr-video');
const statusEl  = document.getElementById('staff-scan-status');
const resultBtn = document.getElementById('staff-result-btn');
const cameraBox = document.getElementById('staff-camera-box');
const overlay   = document.getElementById('ss-overlay');
let scanning = true, lastDetected = null;
const c = document.createElement('canvas');
const ctx = c.getContext('2d', { willReadFrequently: true });

// ── Camera ────────────────────────────────────────────────────────────────────
async function startCamera(){
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:720}}
    });
    video.srcObject = stream;
    await video.play();
    statusEl.textContent = '📷 Scanning — point at a QR code';
    statusEl.className = 'staff-scan-status staff-status-idle';
    requestAnimationFrame(tick);
  } catch(err) {
    statusEl.className = 'staff-scan-status staff-status-error';
    statusEl.textContent = '❌ Camera access denied';
    cameraBox.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;height:100%;padding:24px;text-align:center;">
        <div>
          <div style="font-size:48px;margin-bottom:12px;">📷</div>
          <div style="font-family:Outfit,sans-serif;font-size:18px;font-weight:800;color:#fff;margin-bottom:8px;">Camera Access Needed</div>
          <p style="font-size:15px;color:rgba(255,255,255,.65);line-height:1.6;">
            Allow camera access in your browser settings, then refresh this page.
          </p>
        </div>
      </div>`;
  }
}

function tick(){
  if(!scanning) return;
  if(video.readyState === video.HAVE_ENOUGH_DATA){
    if(c.width !== video.videoWidth || c.height !== video.videoHeight){
      c.width = video.videoWidth; c.height = video.videoHeight;
    }
    ctx.drawImage(video,0,0,c.width,c.height);
    const img = ctx.getImageData(0,0,c.width,c.height);
    const code = jsQR(img.data,img.width,img.height,{inversionAttempts:'attemptBoth'});
    if(code) console.log('[staff-scan] detected:', code.data);
    else if(Math.random() < 0.01) console.log('[staff-scan] scanning... no code yet');
    if(code && code.data !== lastDetected){
      lastDetected = code.data;
      onDetected(code.data);
      return;
    }
  }
  requestAnimationFrame(tick);
}

// ── QR dispatch ───────────────────────────────────────────────────────────────
function onDetected(data){
  // ── Document QR: /receive/<id> or bare 8-char ID ─────────────────────────
  const mReceive = data.match(/\/receive\/([A-Z0-9]{8})/i);
  const mBare    = data.match(/^([A-Z0-9]{8})$/i);
  if(mReceive || mBare){
    const id = (mReceive ? mReceive[1] : mBare[1]).toUpperCase();
    scanning = false;
    if(navigator.vibrate) navigator.vibrate([100,50,100]);
    statusEl.className  = 'staff-scan-status staff-status-found';
    statusEl.textContent = '⏳ Document found — loading...';
    document.getElementById('ss-loader').style.display = 'flex';
    fetchAndShowOverlay(id);
    return;
  }

  // ── /office-action/<slug>-rec  (office receive QR) ───────────────────────
  const mRec = data.match(/\/office-action\/([\w-]+-rec)/i);
  if(mRec){
    const action = mRec[1].toLowerCase();
    const url    = '/office-action/' + action;
    const name   = action.slice(0,-4).replace(/-/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
    scanning = false;
    statusEl.className = 'staff-scan-status staff-status-found';
    statusEl.textContent = '📥 ' + name + ' — redirecting to receive...';
    resultBtn.href = url;
    resultBtn.textContent = '📥 Receive at ' + name;
    resultBtn.style.display = 'flex';
    if(navigator.vibrate) navigator.vibrate([100,50,100]);
    setTimeout(()=>{ window.location.href = url; }, 1200);
    return;
  }

  // ── /office-action/<slug>-rel  (office release QR) ───────────────────────
  const mRel = data.match(/\/office-action\/([\w-]+-rel)/i);
  if(mRel){
    const action = mRel[1].toLowerCase();
    const url    = '/office-action/' + action;
    const name   = action.slice(0,-4).replace(/-/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
    scanning = false;
    statusEl.className = 'staff-scan-status staff-status-found';
    statusEl.textContent = '✅ ' + name + ' — redirecting to release...';
    resultBtn.href = url;
    resultBtn.textContent = '✅ Release from ' + name;
    resultBtn.style.display = 'flex';
    if(navigator.vibrate) navigator.vibrate([100,50,100]);
    setTimeout(()=>{ window.location.href = url; }, 1200);
    return;
  }

  // ── Routing slip token (SLIP_ prefix) ────────────────────────────────────
  const mSlip = data.match(/^SLIP_/i);
  if(mSlip){
    const url = '/routed-documents';
    scanning = false;
    statusEl.className = 'staff-scan-status staff-status-found';
    statusEl.textContent = '📦 Routing slip detected — opening...';
    resultBtn.href = url;
    resultBtn.textContent = '📦 View Routing Slips';
    resultBtn.style.display = 'flex';
    if(navigator.vibrate) navigator.vibrate([100,50,100]);
    setTimeout(()=>{ window.location.href = url; }, 1200);
    return;
  }

  lastDetected = null;
  requestAnimationFrame(tick);
}

// ── Overlay: fetch + show ─────────────────────────────────────────────────────
async function fetchAndShowOverlay(id){
  try {
    const res = await fetch('/api/doc-lookup/' + id, { credentials: 'include' });
    if(!res.ok) throw new Error('not found');
    const doc = await res.json();
    if(!doc.ok) throw new Error(doc.error || 'not found');
    document.getElementById('ss-loader').style.display = 'none';
    showOverlay(id, doc);
  } catch(e){
    console.warn('[staff-scan] lookup failed, falling back to /view/', e);
    document.getElementById('ss-loader').style.display = 'none';
    statusEl.className  = 'staff-scan-status staff-status-error';
    statusEl.textContent = '❌ Could not load document. Redirecting...';
    setTimeout(() => { window.location.href = '/view/' + id; }, 1200);
  }
}

function showOverlay(id, doc){
  // Populate doc info
  document.getElementById('ss-doc-name').textContent = doc.doc_name || 'Untitled Document';
  document.getElementById('ss-doc-ref').textContent  = 'Ref: ' + (doc.doc_id || id);

  const badge     = document.getElementById('ss-doc-status');
  const statusKey = (doc.status || '').toLowerCase().replace(/\s+/g, '-');
  badge.textContent = doc.status || '—';
  badge.className   = 'ss-status-badge ss-status-' + statusKey;

  document.getElementById('ss-doc-category').textContent = doc.category   || '—';
  document.getElementById('ss-doc-sender').textContent   = doc.sender_name || doc.sender_org || '—';
  document.getElementById('ss-doc-referred').textContent = doc.referred_to || '—';
  document.getElementById('ss-doc-date').textContent     = doc.created_at  || '—';

  const intendedRow = document.getElementById('ss-intended-row');
  if(doc.intended_for_name){
    document.getElementById('ss-intended-name').textContent = doc.intended_for_name;
    intendedRow.style.display = 'flex';
  } else {
    intendedRow.style.display = 'none';
  }

  // Determine which action buttons to show
  const me       = (window.CURRENT_USERNAME || '').trim().toLowerCase();
  const myOffice = (window.CURRENT_OFFICE   || '').trim().toLowerCase();

  const isPending     = doc.transfer_status === 'pending';
  const pendingStaff  = (doc.pending_at_staff  || '').trim().toLowerCase();
  const pendingOffice = (doc.pending_at_office || '').trim().toLowerCase();
  const pendingForMe  = (pendingStaff === me) ||
                        (!pendingStaff && pendingOffice && pendingOffice === myOffice);

  const isReleased      = doc.status === 'Released';
  const docOffice       = (doc.logged_by_office || '').trim().toLowerCase();
  const differentOffice = myOffice && docOffice && docOffice !== myOffice;

  const showAccRej     = isPending && pendingForMe;
  const showReceiveCli = isReleased && differentOffice;

  document.getElementById('ss-btn-accept').style.display         = showAccRej     ? '' : 'none';
  document.getElementById('ss-btn-reject').style.display         = showAccRej     ? '' : 'none';
  document.getElementById('ss-btn-receive-client').style.display = showReceiveCli ? '' : 'none';

  // Store doc id and intended recipient for button handlers
  overlay.dataset.docId           = id;
  overlay.dataset.intendedUsername = doc.intended_for_username || '';
  overlay.dataset.intendedName     = doc.intended_for_name     || '';

  // Reset to main step, clear reject textarea
  document.getElementById('ss-main-step').style.display  = '';
  document.getElementById('ss-reject-step').style.display = 'none';
  document.getElementById('ss-reject-reason').value       = '';
  setOverlayLoading(false);

  // Show overlay
  overlay.classList.add('ss-overlay-visible');
}

function dismissOverlay(){
  overlay.classList.remove('ss-overlay-visible');
  setOverlayLoading(false);
  lastDetected = null;
  scanning = true;
  statusEl.className  = 'staff-scan-status staff-status-idle';
  statusEl.textContent = '📷 Scanning — point at a QR code';
  requestAnimationFrame(tick);
}

function setOverlayLoading(on){
  overlay.querySelectorAll('.ss-action-btn, .ss-btn-cancel').forEach(b => {
    b.disabled = on;
  });
}

function showToast(msg, type){
  statusEl.className  = 'staff-scan-status ' +
    (type === 'success' ? 'staff-status-found' : 'staff-status-error');
  statusEl.textContent = msg;
}

// ── Button handlers ───────────────────────────────────────────────────────────
document.getElementById('ss-btn-accept').addEventListener('click', async () => {
  const id = overlay.dataset.docId;
  setOverlayLoading(true);
  try {
    const res  = await fetch('/accept-document/' + id, {
      method: 'POST', credentials: 'include',
      headers: { 'X-CSRF-Token': window.CSRF_TOKEN || '' }
    });
    const data = await res.json();
    if(data.ok){
      showToast('✅ Document accepted!', 'success');
      const intendedUsername = overlay.dataset.intendedUsername || '';
      const intendedName     = overlay.dataset.intendedName     || '';
      if(intendedUsername && intendedUsername !== (window.CURRENT_USERNAME || '')){
        setOverlayLoading(false);
        setTimeout(() => { showForwardStep(intendedUsername, intendedName, id); }, 800);
      } else {
        overlay.classList.remove('ss-overlay-visible');
        setTimeout(dismissOverlay, 1500);
      }
    } else {
      showToast('❌ ' + (data.error || 'Failed to accept'), 'error');
      setOverlayLoading(false);
    }
  } catch(e){
    showToast('❌ Network error', 'error');
    setOverlayLoading(false);
  }
});

document.getElementById('ss-btn-reject').addEventListener('click', () => {
  document.getElementById('ss-main-step').style.display   = 'none';
  document.getElementById('ss-reject-step').style.display = '';
});

document.getElementById('ss-btn-reject-back').addEventListener('click', () => {
  document.getElementById('ss-reject-step').style.display = 'none';
  document.getElementById('ss-main-step').style.display   = '';
});

document.getElementById('ss-btn-reject-submit').addEventListener('click', async () => {
  const id     = overlay.dataset.docId;
  const reason = document.getElementById('ss-reject-reason').value.trim();
  if(!reason){ showToast('Please enter a rejection reason.', 'error'); return; }
  setOverlayLoading(true);
  try {
    const fd = new FormData();
    fd.append('rejection_reason', reason);
    const res  = await fetch('/reject-document/' + id, {
      method: 'POST', credentials: 'include',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRF-Token': window.CSRF_TOKEN || ''
      },
      body: fd
    });
    const data = await res.json();
    if(data.ok){
      overlay.classList.remove('ss-overlay-visible');
      showToast('📤 Document rejected and returned to sender.', 'success');
      setTimeout(dismissOverlay, 1500);
    } else {
      showToast('❌ ' + (data.error || 'Failed to reject'), 'error');
      setOverlayLoading(false);
    }
  } catch(e){
    showToast('❌ Network error', 'error');
    setOverlayLoading(false);
  }
});

document.getElementById('ss-btn-receive-client').addEventListener('click', async () => {
  const id = overlay.dataset.docId;
  setOverlayLoading(true);
  try {
    const res  = await fetch('/web/receive-from-client/' + id, {
      method: 'POST', credentials: 'include',
      headers: { 'X-CSRF-Token': window.CSRF_TOKEN || '' }
    });
    const data = await res.json();
    if(data.ok){
      overlay.classList.remove('ss-overlay-visible');
      showToast('✅ ' + (data.message || 'Document received!'), 'success');
      setTimeout(dismissOverlay, 1500);
    } else {
      showToast('❌ ' + (data.error || 'Failed'), 'error');
      setOverlayLoading(false);
    }
  } catch(e){
    showToast('❌ Network error', 'error');
    setOverlayLoading(false);
  }
});

document.getElementById('ss-btn-transfer').addEventListener('click', () => {
  window.location.href = '/transfer/' + overlay.dataset.docId;
});

document.getElementById('ss-btn-view').addEventListener('click', () => {
  window.location.href = '/view/' + overlay.dataset.docId;
});

document.getElementById('ss-btn-cancel').addEventListener('click', dismissOverlay);

// ── Forward step ──────────────────────────────────────────────────────────────
function showForwardStep(toUsername, toName, docId){
  document.getElementById('ss-main-step').style.display    = 'none';
  document.getElementById('ss-reject-step').style.display  = 'none';
  document.getElementById('ss-forward-step').style.display = '';
  document.getElementById('ss-forward-name').textContent     = toName;
  document.getElementById('ss-forward-name-btn').textContent = toName;

  document.getElementById('ss-btn-forward-confirm').onclick = async () => {
    setOverlayLoading(true);
    const csrfToken = window.CSRF_TOKEN || '';
    const body = new URLSearchParams();
    body.append('new_staff', toUsername);
    body.append('transfer_type', 'inside_office');
    try {
      const res  = await fetch('/transfer/' + docId, {
        method: 'POST', credentials: 'include',
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-Token': csrfToken },
        body
      });
      const data = await res.json();
      if(data.ok){
        showToast('✅ Forwarded to ' + toName, 'success');
        setTimeout(dismissOverlay, 1500);
      } else {
        showToast('❌ ' + (data.error || 'Transfer failed'), 'error');
        setOverlayLoading(false);
      }
    } catch(e){
      showToast('❌ Transfer failed', 'error');
      setOverlayLoading(false);
    }
  };

  document.getElementById('ss-btn-forward-change').onclick = () => {
    _showStaffPickerOverlay(docId);
  };

  document.getElementById('ss-btn-forward-skip').onclick = () => {
    dismissOverlay();
  };
}

function _showStaffPickerOverlay(docId){
  const office = window.CURRENT_OFFICE || '';
  fetch('/api/office-staff' + (office ? '?office=' + encodeURIComponent(office) : ''), { credentials: 'include' })
    .then(r => r.json())
    .then(staffList => {
      const fwd = document.getElementById('ss-forward-step');
      fwd.innerHTML =
        '<div style="font-size:15px;font-weight:800;color:#1E293B;margin-bottom:14px;">Choose Staff</div>' +
        '<div style="max-height:240px;overflow-y:auto;display:flex;flex-direction:column;gap:8px;">' +
        (staffList || []).map(s =>
          '<button class="_spk-btn ss-action-btn ss-btn-view" data-uname="' + s.username + '" data-fname="' + (s.full_name || s.username) + '">' +
            (s.full_name || s.username) +
          '</button>'
        ).join('') +
        '</div>' +
        '<button class="ss-btn-cancel" style="margin-top:10px;" id="_spk-back">← Back</button>';

      document.getElementById('_spk-back').addEventListener('click', () => {
        fwd.innerHTML = '';
        showForwardStep(overlay.dataset.intendedUsername, overlay.dataset.intendedName, docId);
      });

      fwd.querySelectorAll('._spk-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          const uname = btn.dataset.uname;
          const fname = btn.dataset.fname;
          setOverlayLoading(true);
          const csrfToken = window.CSRF_TOKEN || '';
          const body = new URLSearchParams();
          body.append('new_staff', uname);
          body.append('transfer_type', 'inside_office');
          try {
            const res  = await fetch('/transfer/' + docId, {
              method: 'POST', credentials: 'include',
              headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-Token': csrfToken },
              body
            });
            const data = await res.json();
            if(data.ok){
              showToast('✅ Forwarded to ' + fname, 'success');
              setTimeout(dismissOverlay, 1500);
            } else {
              showToast('❌ ' + (data.error || 'Transfer failed'), 'error');
              setOverlayLoading(false);
            }
          } catch(e){
            showToast('❌ Transfer failed', 'error');
            setOverlayLoading(false);
          }
        });
      });
    })
    .catch(() => { showToast('❌ Could not load staff list', 'error'); });
}

startCamera();
