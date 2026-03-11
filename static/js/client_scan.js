const video     = document.getElementById('qr-video');
const statusEl  = document.getElementById('scan-status');
const resultBtn = document.getElementById('result-btn');
const cameraBox = document.getElementById('camera-box');
let scanning = true, lastDetected = null;

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
    const c = document.createElement('canvas');
    c.width = video.videoWidth; c.height = video.videoHeight;
    const ctx = c.getContext('2d');
    ctx.drawImage(video,0,0,c.width,c.height);
    const img = ctx.getImageData(0,0,c.width,c.height);
    const code = jsQR(img.data,img.width,img.height,{inversionAttempts:'dontInvert'});
    if(code && code.data !== lastDetected){
      lastDetected = code.data;
      onDetected(code.data);
      return;
    }
  }
  requestAnimationFrame(tick);
}

function onDetected(data){
  const m = data.match(/\/receive\/([A-Z0-9]{8})/i);
  if(m){
    const url = '/receive/'+m[1].toUpperCase();
    scanning = false;
    statusEl.className = 'scan-status status-found';
    statusEl.textContent = '✅ Document found! Opening...';
    resultBtn.href = url;
    resultBtn.textContent = '⚡ Open Document '+m[1].toUpperCase();
    resultBtn.style.display = 'flex';
    if(navigator.vibrate) navigator.vibrate([100,50,100]);
    setTimeout(()=>{ window.location.href = url; }, 1200);
  } else {
    lastDetected = null;
    requestAnimationFrame(tick);
  }
}

startCamera();