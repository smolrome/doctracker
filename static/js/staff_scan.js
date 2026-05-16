const video     = document.getElementById('staff-qr-video');
const statusEl  = document.getElementById('staff-scan-status');
const resultBtn = document.getElementById('staff-result-btn');
const cameraBox = document.getElementById('staff-camera-box');
let scanning = true, lastDetected = null;
const c = document.createElement('canvas');
const ctx = c.getContext('2d', { willReadFrequently: true });

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

function onDetected(data){
  // ── /receive/<doc_id>  or full URL containing it ─────────────────────────
  const mReceive = data.match(/\/receive\/([A-Z0-9]{8})/i);
  if(mReceive){
    const id  = mReceive[1].toUpperCase();
    const url = '/view/' + id;
    scanning = false;
    statusEl.className = 'staff-scan-status staff-status-found';
    statusEl.textContent = '✅ Document found! Opening...';
    resultBtn.href = url;
    resultBtn.textContent = '⚡ View Document ' + id;
    resultBtn.style.display = 'flex';
    if(navigator.vibrate) navigator.vibrate([100,50,100]);
    setTimeout(()=>{ window.location.href = url; }, 1200);
    return;
  }

  // ── bare doc ID (legacy / mobile-generated QR) ───────────────────────────
  const mBare = data.match(/^([A-Z0-9]{8})$/i);
  if(mBare){
    const id  = mBare[1].toUpperCase();
    const url = '/view/' + id;
    scanning = false;
    statusEl.className = 'staff-scan-status staff-status-found';
    statusEl.textContent = '✅ Document found! Opening...';
    resultBtn.href = url;
    resultBtn.textContent = '⚡ View Document ' + id;
    resultBtn.style.display = 'flex';
    if(navigator.vibrate) navigator.vibrate([100,50,100]);
    setTimeout(()=>{ window.location.href = url; }, 1200);
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

startCamera();
