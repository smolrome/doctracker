/* ═══════════════════════════════════════════════════════
   BACKUP & RESTORE PAGE SCRIPTS
   ═══════════════════════════════════════════════════════ */

/* ── Tab switcher ──
   Buttons id="tab-<name>", panels id="panel-<name>". Active state is a
   .active CSS class toggled via classList (no inline styles). */
function switchTab(name) {
  document.querySelectorAll('.backup-panel').forEach(function (p) { p.classList.remove('active'); });
  document.querySelectorAll('.backup-tab').forEach(function (b) { b.classList.remove('active'); });
  var panel = document.getElementById('panel-' + name);
  var tab = document.getElementById('tab-' + name);
  if (panel) panel.classList.add('active');
  if (tab) tab.classList.add('active');
}

function handleFileSelect(input) {
  const file = input.files[0];
  if (!file) return;
  document.getElementById('dz-file-name').textContent = file.name;
  document.getElementById('dz-file-name').style.display = 'block';
  document.getElementById('restore-btn').disabled = false;
}

function selectMode(card, mode) {
  document.querySelectorAll('.mode-card').forEach(c => c.classList.remove('selected'));
  card.classList.add('selected');
  card.querySelector('input[type=radio]').checked = true;
  const btn = document.getElementById('restore-btn');
  if (mode === 'replace') {
    btn.textContent = 'Wipe & Restore';
    btn.className = 'backup-btn backup-btn-red';
  } else {
    btn.textContent = 'Restore Backup';
    btn.className = 'backup-btn backup-btn-blue';
  }
}

// Drag & drop
document.addEventListener('DOMContentLoaded', function () {
  // Auto-open the Restore tab when a restore just completed (server passed
  // `summary`, so the .summary-box is rendered). Mirrors send_invite.js
  // auto-opening its batch tab when batch_results is set. Otherwise the
  // restore confirmation would be hidden in an inactive tab.
  if (document.querySelector('.summary-box')) {
    switchTab('restore');
  }

  const zone = document.getElementById('drop-zone');
  if (!zone) return;

  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('drag-over');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) {
      const input = document.getElementById('backup-file-input');
      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      handleFileSelect(input);
    }
  });

  // Confirm replace mode before submit
  const form = document.getElementById('restore-form');
  if (form) {
    form.addEventListener('submit', function (e) {
      const mode = document.querySelector('input[name=mode]:checked').value;
      if (mode === 'replace') {
        if (!confirm('FULL REPLACE: This will permanently delete ALL current documents and routing slips before restoring.\n\nAre you sure you want to continue?')) {
          e.preventDefault();
        }
      }
    });
  }
});