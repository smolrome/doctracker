function copyGenLink() {
  const link = document.getElementById('gen-link-text').textContent.trim();
  navigator.clipboard.writeText(link).then(() => {
    event.target.textContent = '✅ Copied!';
    setTimeout(() => event.target.textContent = '📋 Copy Invite Link', 2000);
  });
}

function copyText(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = '✅ Copied!';
    setTimeout(() => btn.textContent = orig, 2000);
  });
}

function copyAllLinks() {
  const links = [];
  document.querySelectorAll('[data-batch-link]').forEach(el => links.push(el.textContent.trim()));
  // fallback: grab all monospace link lines from batch results
  document.querySelectorAll('#batch-results-box .link-line').forEach(el => links.push(el.textContent.trim()));
  if (!links.length) {
    // grab from visible monospace divs inside batch results
    document.querySelectorAll('#batch-results-box div[style*="monospace"]').forEach(el => links.push(el.textContent.trim()));
  }
  if (links.length) {
    navigator.clipboard.writeText(links.join('\n')).then(() => {
      event.target.textContent = '✅ All Copied!';
      setTimeout(() => event.target.textContent = '📋 Copy All Links', 2000);
    });
  }
}

/* ── Tab switcher ── */
function switchTab(tab) {
  console.log('switchTab called with:', tab);
  const isSingle = tab === 'single';
  var panelSingle = document.getElementById('panel-single');
  var panelBatch = document.getElementById('panel-batch');
  var tabSingle = document.getElementById('tab-single');
  var tabBatch = document.getElementById('tab-batch');
  
  if (panelSingle) panelSingle.style.display = isSingle ? '' : 'none';
  if (panelBatch) panelBatch.style.display  = isSingle ? 'none' : '';
  if (tabSingle) {
    tabSingle.style.background = isSingle ? 'var(--teal)' : 'var(--surface)';
    tabSingle.style.color      = isSingle ? '#fff' : 'var(--muted)';
  }
  if (tabBatch) {
    tabBatch.style.background  = isSingle ? 'var(--surface)' : 'var(--teal)';
    tabBatch.style.color       = isSingle ? 'var(--muted)' : '#fff';
  }
}

/* ── Live email counter ── */
function updateBatchCount(textarea) {
  const lines = textarea.value
    .split(/[\n,]+/)
    .map(e => e.trim())
    .filter(e => e.length > 0);
  document.getElementById('batch-count').textContent = lines.length;
}

/* Auto-switch to batch tab if batch_results present */
document.addEventListener('DOMContentLoaded', function() {
  {% if batch_results %}switchTab('batch');{% endif %}
});