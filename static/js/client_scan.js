const video     = document.getElementById('qr-video');
const statusEl  = document.getElementById('scan-status');
const resultBtn = document.getElementById('result-btn');
const cameraBox = document.getElementById('camera-box');
let scanning = true, lastDetected = null;
const c = document.createElement('canvas');
const ctx = c.getContext('2d');

async function startCamera(){
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:720}}
    });
    video.srcObject = stream;
    await video.play();
    statusEl.textContent = '📷 Scanning — point at a QR code';
    statusEl.className = 'scan-status status-idle';
    requestAnimationFrame(tick);
  } catch(err) {
    statusEl.className = 'scan-status status-error';
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
    if(code) console.log('[scan] detected:', code.data);
    else if(Math.random() < 0.01) console.log('[scan] scanning... no code yet');
    if(code && code.data !== lastDetected){
      lastDetected = code.data;
      onDetected(code.data);
      return;
    }
  }
  requestAnimationFrame(tick);
}

function onDetected(data){
  // ── /receive/<doc_id> ────────────────────────────────────────────────────
  const mReceive = data.match(/\/receive\/([A-Z0-9]{8})/i);
  if(mReceive){
    const url = '/receive/'+mReceive[1].toUpperCase();
    scanning = false;
    statusEl.className = 'scan-status status-found';
    statusEl.textContent = '✅ Document found! Opening...';
    resultBtn.href = url;
    resultBtn.textContent = '⚡ Open Document '+mReceive[1].toUpperCase();
    resultBtn.style.display = 'flex';
    if(navigator.vibrate) navigator.vibrate([100,50,100]);
    setTimeout(()=>{ window.location.href = url; }, 1200);
    return;
  }

  // ── /office-action/<slug>-sub  (office submission QR) ────────────────────
  const mSub = data.match(/\/office-action\/([\w-]+-sub)/i);
  if(mSub){
    const action     = mSub[1].toLowerCase();
    const url        = '/office-action/' + action;
    const officeName = action.slice(0, -4).replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    scanning = false;
    statusEl.className = 'scan-status status-found';
    statusEl.textContent = '🏢 ' + officeName + ' — redirecting to submission...';
    resultBtn.href = url;
    resultBtn.textContent = '✓ Submit to ' + officeName;
    resultBtn.style.display = 'flex';
    if(navigator.vibrate) navigator.vibrate([100,50,100]);
    setTimeout(()=>{ window.location.href = url; }, 1200);
    return;
  }

  // ── /office-action/<slug>-reg  (office registration QR) ──────────────────
  const mReg = data.match(/\/office-action\/([\w-]+-reg)/i);
  if(mReg){
    const action     = mReg[1].toLowerCase();
    const url        = '/office-action/' + action;
    const officeName = action.slice(0, -4).replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    scanning = false;
    statusEl.className = 'scan-status status-found';
    statusEl.textContent = '📝 ' + officeName + ' — redirecting to registration...';
    resultBtn.href = url;
    resultBtn.textContent = '📝 Register / Login for ' + officeName;
    resultBtn.style.display = 'flex';
    if(navigator.vibrate) navigator.vibrate([100,50,100]);
    setTimeout(()=>{ window.location.href = url; }, 1200);
    return;
  }

  lastDetected = null;
  requestAnimationFrame(tick);
}

startCamera();