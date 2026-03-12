async function regenRef() {
  const res = await fetch('/api/gen-ref');
  const data = await res.json();
  document.getElementById('doc-ref-input').value = data.ref;
}

function setAction(val, el) {
  document.getElementById('action-input').value = val;
  document.querySelectorAll('.action-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
}
document.addEventListener('DOMContentLoaded', () => {
  const btns = document.querySelectorAll('.action-btn');
  if (btns.length) btns[0].classList.add('active');

  // Drag and drop
  const zone = document.getElementById('drop-zone');
  if (zone) {
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
      e.preventDefault(); zone.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file) {
        document.getElementById('qr-file').files = e.dataTransfer.files;
        previewFile(document.getElementById('qr-file'));
      }
    });
  }

  // Loading on form submit
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', () => {
      const hasImage = document.getElementById('qr-file') && document.getElementById('qr-file').files.length > 0;
      if (hasImage) {
        showLoading('Reading QR Code...', 'Scanning and finding document');
      } else {
        showLoading('Saving Log Entry...', 'Updating travel log');
      }
    });
  });

  window.addEventListener('pageshow', e => { if (e.persisted) hideLoading(); });
});

function previewFile(input) {
  const file = input.files[0];
  if (!file) return;
  document.getElementById('file-name-display').style.display = 'block';
  document.getElementById('file-name-display').textContent = file.name;
  const reader = new FileReader();
  reader.onload = e => {
    document.getElementById('qr-preview').src = e.target.result;
    document.getElementById('qr-preview-wrap').style.display = 'block';
  };
  reader.readAsDataURL(file);
}
