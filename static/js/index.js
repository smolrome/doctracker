// Stats filter
function statFilter(status) {
  const params = new URLSearchParams(window.location.search);
  params.set('status', status); params.delete('page');
  window.location.href = '/?' + params.toString();
}

// Office QR Modal
function openOqsModal()  { document.getElementById('oqs-modal-overlay').classList.add('open'); document.getElementById('oqs-search').focus(); }
function closeOqsModal() { document.getElementById('oqs-modal-overlay').classList.remove('open'); }
function filterOffices(query) {
  const q = query.toLowerCase().trim();
  const cards = document.querySelectorAll('.oqs-card');
  let visible = 0;
  cards.forEach(card => {
    const show = !q || (card.dataset.name||'').includes(q);
    card.classList.toggle('hidden', !show);
    if (show) visible++;
  });
  document.getElementById('oqs-count').textContent = visible + ' office' + (visible !== 1 ? 's' : '') + (q ? ' found' : ' registered');
  document.getElementById('oqs-none').classList.toggle('visible', visible === 0);
}
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeOqsModal();
  if (e.key === '/' && document.activeElement.tagName !== 'INPUT') { e.preventDefault(); openOqsModal(); document.getElementById('oqs-search').focus(); }
});

// Filter functions
function toggleTimeRange(on) {
  document.getElementById('time-range-row').style.display = on ? 'flex' : 'none';
  if (!on) { document.querySelector('[name="time_from"]').value=''; document.querySelector('[name="time_to"]').value=''; document.getElementById('filter-form').submit(); }
}
function setToday() { document.querySelector('[name="date"]').value = new Date().toISOString().slice(0,10); document.getElementById('filter-form').submit(); }
function setType(val) { document.getElementById('type-hidden').value = val; document.getElementById('filter-form').submit(); }
function clearField(name, val='') { const el = document.querySelector('[name="'+name+'"]'); if(el) el.value=val; document.getElementById('filter-form').submit(); }

// Modal data - Initialize when DOM is ready
var modalCurrentOffice = null;
var currentUserName = null;
var currentUserRole = null;
var officesData = {};
var sortedOffices = [];
var transferSingleDocId = null;

function initModalData() {
  try {
    var officesDataEl = document.getElementById('offices-data');
    console.log('offices-data textContent:', officesDataEl?.textContent);
    officesData   = JSON.parse(officesDataEl?.textContent   || '{}');
    sortedOffices = JSON.parse(document.getElementById('sorted-offices')?.textContent || '[]');
    var currentOfficeEl = document.getElementById('current-office-data');
    modalCurrentOffice = currentOfficeEl ? JSON.parse(currentOfficeEl.textContent || 'null') : null;
    
    // Get user name and role from server session data (more reliable)
    if (typeof serverSessionData !== 'undefined') {
      currentUserName = serverSessionData.full_name || serverSessionData.username || null;
      currentUserRole = serverSessionData.role || null;
    }

    // Fallback: use server session data for office
    if (!modalCurrentOffice || modalCurrentOffice === 'null' || modalCurrentOffice === null) {
      if (typeof serverSessionData !== 'undefined' && serverSessionData.office) {
        modalCurrentOffice = serverSessionData.office;
      }
    }
    
    // Log user info and staff in logged in user's office (Console log)
    console.log('=== Transfer Modal - User Info ===');
    console.log('Name:', currentUserName);
    console.log('Role:', currentUserRole);
    console.log('Office:', modalCurrentOffice);
    console.log('Staff in office:', officesData[modalCurrentOffice] || []);
    console.log('===================================');

    console.log('Current office:', modalCurrentOffice);
    console.log('Offices data:', officesData);
  } catch(e) {
    console.error('Error initializing modal data:', e);
    officesData   = {};
    sortedOffices = [];
    // Fallback: use server session data
    if (typeof serverSessionData !== 'undefined' && serverSessionData.office) {
      modalCurrentOffice = serverSessionData.office;
    } else {
      modalCurrentOffice = null;
    }
  }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initModalData);
} else {
  initModalData();
}

// Page load initialization
(function(){ const sd=document.getElementById('slip-date'); if(sd) sd.value=new Date().toISOString().slice(0,10); })();

function changePerPage(val) { const url=new URL(window.location.href); url.searchParams.set('per_page',val); url.searchParams.set('page',1); window.location=url.toString(); }
function rowClick(e,docId) { if(e.target.type==='checkbox') return; window.location='/view/'+docId; }

// ROUTING MODAL
function openRoutingModal() { document.getElementById('routing-modal').style.display='flex'; updateSelectedPreview(); const sd=document.getElementById('slip-date'); if(sd&&!sd.value) sd.value=new Date().toISOString().slice(0,10); }
function closeRoutingModal() { document.getElementById('routing-modal').style.display='none'; }
if (document.getElementById('routing-modal')) {
  document.getElementById('routing-modal').addEventListener('click',function(e){ if(e.target===this) closeRoutingModal(); });
}

// TRANSFER MODAL
function openTransferModal() {
  console.log('=== openTransferModal() — bulk mode, transferSingleDocId reset to null ===');
  const checked=document.querySelectorAll('.doc-checkbox:checked');
  if(checked.length===0){ alert('Please select at least one document to transfer.'); return; }
  document.getElementById('transfer-sel-count').textContent=checked.length+' selected';
  // Reset
  document.getElementById('transfer-type').value='';
  document.getElementById('transfer-office').innerHTML='<option value="">-- Select Office --</option>';
  document.getElementById('transfer-office').disabled=true;
  document.getElementById('transfer-office-info').textContent='';
  document.getElementById('transfer-staff').innerHTML='<option value="">-- Select Staff --</option>';
  document.getElementById('transfer-staff').disabled=true;
  document.getElementById('btn-do-transfer').disabled=true;
  // Hide step blocks
  hideTransferBlock('transfer-office-block');
  hideTransferBlock('transfer-staff-block');
  hideTransferBlock('transfer-submit-block');
  document.getElementById('transfer-modal').style.display='flex';
}
function closeTransferModal() { document.getElementById('transfer-modal').style.display='none'; }
if (document.getElementById('transfer-modal')) {
  document.getElementById('transfer-modal').addEventListener('click',function(e){ if(e.target===this) closeTransferModal(); });
}

function updateTransferOffices() {
  const transferType=document.getElementById('transfer-type').value;
  const officeSelect=document.getElementById('transfer-office');
  const staffSelect=document.getElementById('transfer-staff');
  staffSelect.innerHTML='<option value="">-- Select Staff --</option>';
  staffSelect.disabled=true;
  document.getElementById('btn-do-transfer').disabled=true;
  if(!transferType){ officeSelect.innerHTML='<option value="">-- Select Office --</option>'; officeSelect.disabled=true; document.getElementById('transfer-office-info').textContent=''; return; }
  let options='<option value="">-- Select Office --</option>';
  for(const office of sortedOffices){ if(office==='No Office') continue; options+=`<option value="${office}">${office}</option>`; }
  officeSelect.innerHTML=options;
  if(transferType==='inside_office' && modalCurrentOffice && modalCurrentOffice!=='None' && modalCurrentOffice!==''){
    officeSelect.value=modalCurrentOffice;
    officeSelect.disabled=true;
    document.getElementById('transfer-office-info').textContent='📍 Locked to your office: '+modalCurrentOffice;
    updateTransferStaff();
  } else {
    officeSelect.disabled=false;
    document.getElementById('transfer-office-info').textContent='';
  }
}

// Step-by-step transfer functions (matching transfer.html logic)
function showTransferBlock(id) { 
  const el = document.getElementById(id);
  if (el) el.style.display = 'block';
}
function hideTransferBlock(id) { 
  const el = document.getElementById(id);
  if (el) el.style.display = 'none';
}

function resetTransferFrom(step) {
  const order = ['transfer-office-block','transfer-staff-block','transfer-submit-block'];
  const from = order.indexOf(step);
  for (let i = from; i < order.length; i++) hideTransferBlock(order[i]);
}

function onTransferTypeChangeIndex() {
  try {
    const type = document.getElementById('transfer-type').value;
    const officeSelect = document.getElementById('transfer-office');
    const staffSelect = document.getElementById('transfer-staff');
    
    if (!officeSelect || !staffSelect) {
      console.error('Transfer modal elements not found');
      return;
    }
    
    // Reset staff and submit
    staffSelect.innerHTML = '<option value="">-- Select Staff --</option>';
    staffSelect.disabled = true;
    const btn = document.getElementById('btn-do-transfer');
    if (btn) btn.disabled = true;
    
    if (!type) {
      hideTransferBlock('transfer-office-block');
      hideTransferBlock('transfer-staff-block');
      hideTransferBlock('transfer-submit-block');
      return;
    }
    
    if (type === 'inside_office') {
      const label = document.getElementById('transfer-office-label');
      if (label) label.textContent = 'Step 2: Your Office';
      
      // Populate and lock to current office
      officeSelect.innerHTML = `<option value="${modalCurrentOffice}">${modalCurrentOffice}</option>`;
      officeSelect.value = modalCurrentOffice;
      officeSelect.disabled = true;
      const info = document.getElementById('transfer-office-info');
      if (info) info.textContent = '📍 Auto-selected: your office';
      
      showTransferBlock('transfer-office-block');
      populateTransferStaff(modalCurrentOffice);
      showTransferBlock('transfer-staff-block');
    } else {
      const label = document.getElementById('transfer-office-label');
      if (label) label.textContent = 'Step 2: Select Office';
      
      // Populate all offices (excluding own office for external)
      let options = '<option value="">-- Select Office --</option>';
      for (const office of sortedOffices) {
        if (office === 'No Office' || office === modalCurrentOffice) continue;
        options += `<option value="${office}">${office}</option>`;
      }
      officeSelect.innerHTML = options;
      officeSelect.disabled = false;
      const info = document.getElementById('transfer-office-info');
      if (info) info.textContent = '';
      
      showTransferBlock('transfer-office-block');
    }
  } catch(e) {
    console.error('Error in onTransferTypeChangeIndex:', e);
  }
}

function updateTransferStaffIndex() {
  const office = document.getElementById('transfer-office').value;
  hideTransferBlock('transfer-staff-block');
  hideTransferBlock('transfer-submit-block');
  
  if (!office) return;
  
  populateTransferStaff(office);
  showTransferBlock('transfer-staff-block');
}

function populateTransferStaff(office) {
  console.log('populateTransferStaff called with office:', office);
  console.log('Offices data:', officesData);
  console.log('officesData[office]:', officesData[office]);
  
  const staffSelect = document.getElementById('transfer-staff');
  staffSelect.innerHTML = '<option value="">-- Select Staff --</option>';
  
  if (!office || !officesData[office]) {
    console.log('Returning early - office not found in officesData');
    return;
  }
  
  const staff = officesData[office];
  console.log('Found staff for office:', staff);
  for (const s of staff) {
    const name = s.full_name || s.username;
    staffSelect.innerHTML += `<option value="${s.username}">${name} (@${s.username})</option>`;
  }
  staffSelect.disabled = false;
}

function onTransferStaffChangeIndex() {
  const val = document.getElementById('transfer-staff').value;
  if (val) {
    showTransferBlock('transfer-submit-block');
    document.getElementById('btn-do-transfer').disabled = false;
  } else {
    hideTransferBlock('transfer-submit-block');
  }
}

function updateTransferStaff() {
  const office=document.getElementById('transfer-office').value;
  const staffSelect=document.getElementById('transfer-staff');
  if(!office||!officesData[office]){ staffSelect.innerHTML='<option value="">-- Select Staff --</option>'; staffSelect.disabled=true; document.getElementById('btn-do-transfer').disabled=true; return; }
  const staff=officesData[office];
  let options='<option value="">-- Select Staff --</option>';
  for(const s of staff){ const name=s.full_name||s.username; options+=`<option value="${s.username}">${name} (@${s.username})</option>`; }
  staffSelect.innerHTML=options;
  staffSelect.disabled=false;
  document.getElementById('btn-do-transfer').disabled=true; // wait for selection
}

function onTransferStaffChange() {
  document.getElementById('btn-do-transfer').disabled=!document.getElementById('transfer-staff').value;
}

function submitTransfer() {
  console.log('=== submitTransfer() called ===');
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  console.log('csrf token:', csrfToken ? 'present' : 'MISSING — will be blocked!');

  const transferType = document.getElementById('transfer-type').value;
  const office = document.getElementById('transfer-office').value || modalCurrentOffice;
  const staff = document.getElementById('transfer-staff').value;
  const selectedIds = [...document.querySelectorAll('.doc-checkbox:checked')].map(c => c.value);

  console.log('transfer_type:', transferType);
  console.log('office:', office);
  console.log('staff:', staff);
  console.log('selectedIds:', selectedIds);
  console.log('transferSingleDocId:', transferSingleDocId);
  console.log('modalCurrentOffice:', modalCurrentOffice);

  if (!transferType || !staff) {
    console.warn('BLOCKED: missing transferType or staff');
    alert('Please complete all steps before transferring.');
    return;
  }

  if (!transferSingleDocId && !selectedIds.length) {
    console.warn('BLOCKED: no docs selected and no single doc id');
    alert('Please select at least one document to transfer.');
    return;
  }

  const form = document.createElement('form');
  form.method = 'POST';

  if (transferSingleDocId) {
    // Single doc mode — same endpoint as transfer page
    form.action = '/transfer/' + transferSingleDocId;
    console.log('MODE: single doc → POST to', form.action);
    [['transfer_type', transferType],
     ['new_office', office],
     ['new_staff', staff],
     ['_csrf_token', csrfToken]
    ].forEach(([name, value]) => {
      const input = document.createElement('input');
      input.type = 'hidden'; input.name = name; input.value = value;
      form.appendChild(input);
      console.log('  field:', name, '=', value);
    });

  } else {
    // Bulk mode — batch endpoint
    form.action = '/transfer-batch';
    console.log('MODE: bulk → POST to', form.action);
    [['doc_ids', selectedIds.join(',')],
     ['transfer_type', transferType],
     ['new_office', office],
     ['new_staff', staff],
     ['_csrf_token', csrfToken]
    ].forEach(([name, value]) => {
      const input = document.createElement('input');
      input.type = 'hidden'; input.name = name; input.value = value;
      form.appendChild(input);
      console.log('  field:', name, '=', value);
    });
  }

  console.log('Submitting form to:', form.action);
  document.body.appendChild(form);
  form.submit();
}

// SELECTION
function updateSelectedPreview() {
  const checked=document.querySelectorAll('.doc-checkbox:checked'); const n=checked.length;
  const countEl=document.getElementById('sel-count'); if(countEl) countEl.textContent=n+' selected';
  const preview=document.getElementById('selected-preview'); const list=document.getElementById('selected-list');
  if(!preview||!list) return;
  if(n===0){ preview.style.display='none'; list.innerHTML=''; }
  else { preview.style.display='block'; list.innerHTML=Array.from(checked).map(function(cb,i){ const row=cb.closest('tr'); const name=row?row.querySelector('.doc-name'):null; return '<div style="padding:3px 0;border-bottom:1px solid rgba(255,255,255,.1)">'+(i+1)+'. '+(name?name.textContent.trim():cb.value)+'</div>'; }).join(''); }
}

function updateSelection() {
  const checked=document.querySelectorAll('.doc-checkbox:checked'); const n=checked.length;
  document.querySelectorAll('.doc-checkbox').forEach(cb=>{ cb.closest('tr').classList.toggle('row-selected',cb.checked); });
  const slipBtn=document.getElementById('btn-create-slip');
  if(slipBtn){ slipBtn.style.display=n>0?'inline-flex':'none'; const b=document.getElementById('slip-sel-badge'); if(b) b.textContent=n>0?n+' doc'+(n>1?'s':''):''; }
  const transferBtn=document.getElementById('btn-transfer');
  if(transferBtn){ transferBtn.style.display=n>0?'inline-flex':'none'; const tb=document.getElementById('transfer-sel-badge'); if(tb) tb.textContent=n>0?n+' doc'+(n>1?'s':''):''; }
  updateSelectedPreview();
}

const selAll=document.getElementById('select-all');
if(selAll){ selAll.addEventListener('change',function(){ document.querySelectorAll('.doc-checkbox').forEach(cb=>{ cb.checked=this.checked; cb.closest('tr').classList.toggle('row-selected',this.checked); }); updateSelection(); }); }

// TIME RANGE
function toggleModalTimeRange(on) {
  document.getElementById('time-from-field').style.display=on?'':'none';
  document.getElementById('time-to-field').style.display=on?'':'none';
  document.getElementById('btn-auto-select').style.display=on?'':'none';
  if(!on){ document.getElementById('time-from').value=''; document.getElementById('time-to').value=''; }
}

function autoSelectByTime() {
  const useTime=document.getElementById('use-time-range').checked;
  const tf=document.getElementById('time-from').value; const tt=document.getElementById('time-to').value; const sd=document.getElementById('slip-date').value;
  if(useTime&&(!tf||!tt)){ alert('Please set both a Time From and Time To, or uncheck Include Time Range.'); return; }
  let count=0;
  document.querySelectorAll('.doc-checkbox').forEach(cb=>{
    const row=cb.closest('tr'); const ts=row.dataset.createdAt||'';
    let inRange=false;
    if(ts){ const dateOk=!sd||ts.slice(0,10)===sd; const timeOk=ts.slice(11,16)>=tf&&ts.slice(11,16)<=tt; inRange=dateOk&&timeOk; }
    cb.checked=inRange; row.classList.toggle('row-selected',inRange); if(inRange) count++;
  });
  updateSelection();
  if(count===0){ alert('No documents found in that date/time range.'); }
  else{ const btn=document.querySelector('.btn-time-filter'); const orig=btn.textContent; btn.textContent='✅ '+count+' selected'; setTimeout(()=>btn.textContent=orig,2000); }
}

function submitRouting() {
  const dest=document.getElementById('route-dest').value.trim();
  if(!dest){ const el=document.getElementById('route-dest'); el.focus(); el.style.borderColor='#FCA5A5'; el.style.background='rgba(220,38,38,.15)'; setTimeout(()=>{ el.style.borderColor=''; el.style.background=''; },2500); return; }
  const ids=Array.from(document.querySelectorAll('.doc-checkbox:checked')).map(cb=>cb.value);
  if(!ids.length){ alert('No documents selected.'); return; }
  document.getElementById('routing-doc-ids').value=ids.join(',');
  document.getElementById('routing-dest-field').value=dest;
  document.getElementById('routing-notes').value=document.getElementById('route-notes').value;
  document.getElementById('routing-slip-date').value=document.getElementById('slip-date').value;
  document.getElementById('routing-time-from').value=document.getElementById('time-from').value;
  document.getElementById('routing-time-to').value=document.getElementById('time-to').value;
  document.getElementById('routing-form').submit();
}
