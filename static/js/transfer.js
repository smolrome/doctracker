const officesData   = JSON.parse(document.getElementById('offices-data').textContent || '{}');
const sortedOffices = JSON.parse(document.getElementById('sorted-offices').textContent || '[]');
const currentOffice = JSON.parse(document.getElementById('current-office-data').textContent);
// {office_name: recipient_username} — primary_recipient is a username, omitted when unset
const primaryRecipients = JSON.parse((document.getElementById('primary-recipients') || {}).textContent || '{}');

// Resolve a username to a display name using any office's staff list in officesData.
function _lookupStaffName(username) {
  for (const office in officesData) {
    for (const s of officesData[office]) {
      if (s.username === username) return s.full_name || s.username;
    }
  }
  return username;
}

// Get user name and role from server session data
var currentUserName = null;
var currentUserRole = null;
if (typeof serverSessionData !== 'undefined') {
  currentUserName = serverSessionData.full_name || serverSessionData.username || null;
  currentUserRole = serverSessionData.role || null;
}

// Log user info and staff in logged in user's office
console.log('=== Transfer Page - User Info ===');
console.log('Name:', currentUserName);
console.log('Role:', currentUserRole);
console.log('Office:', currentOffice);
console.log('Staff in office:', officesData[currentOffice] || []);
console.log('=================================');

function show(id)  { document.getElementById(id).classList.add('visible'); }
function hide(id)  { document.getElementById(id).classList.remove('visible'); }

function resetFrom(step) {
  // step: 'office' | 'staff' | 'submit'
  const order = ['step-office-block','step-staff-block','step-submit-block'];
  const from  = order.indexOf('step-' + step + '-block');
  for (let i = from; i < order.length; i++) hide(order[i]);
}
function onTransferTypeChange() {
const type = document.getElementById('transfer_type').value;

resetFrom('office');
document.getElementById('new_office').value = '';
document.getElementById('new_staff').innerHTML = '<option value="">-- Select Staff --</option>';

if (!type) return;

if (type === 'inside_office') {
  document.getElementById('staff-step-label').textContent = 'Step 3: Select Staff';
  document.getElementById('office-step-label').textContent = 'Step 2: Your Office';

  // Populate and lock to current office
  const officeSelect = document.getElementById('new_office');
  officeSelect.innerHTML = `<option value="${currentOffice}">${currentOffice}</option>`;
  officeSelect.value = currentOffice;
  officeSelect.disabled = true;
  document.getElementById('office-info').textContent = '📍 Auto-selected: your office';

  show('step-office-block');
  populateStaff(currentOffice);
  show('step-staff-block');
  // Internal: reveal submit only if a primary-recipient default was
  // pre-selected. Never auto-reveal office-level for your own office.
  if (document.getElementById('new_staff').value) show('step-submit-block');

} else {
  document.getElementById('staff-step-label').textContent = 'Step 3: Select Staff';
  document.getElementById('office-step-label').textContent = 'Step 2: Select Office';

  const officeSelect = document.getElementById('new_office');
  officeSelect.disabled = false;
  document.getElementById('office-info').textContent = '';
  populateOffices();
  show('step-office-block');
}
}
function populateOffices() {
  const officeSelect = document.getElementById('new_office');
  let options = '<option value="">-- Select Office --</option>';
  for (const office of sortedOffices) {
    if (office === 'No Office' || office === currentOffice) continue; // exclude own office for external
    options += `<option value="${office}">${office}</option>`;
  }
  officeSelect.innerHTML = options;
}

function updateStaff() {
  const office = document.getElementById('new_office').value;
  hide('step-staff-block');
  hide('step-submit-block');

  if (!office) return;

  const reveal = populateStaff(office);
  show('step-staff-block');

  // Reveal submit when a default/target is set (case 1 pre-select, case 2
  // recipient) or for an office-level transfer (case 3, staffless + no
  // recipient). Case 1 with no default returns false → user must pick first.
  if (reveal) show('step-submit-block');
}

// Populate the staff dropdown for an office. Returns true when the submit
// block should be revealed immediately (a default/target is set, or it's an
// office-level transfer); false when the user still needs to pick someone.
function populateStaff(office) {
  const staffSelect = document.getElementById('new_staff');
  const staffList = (office && officesData[office]) ? officesData[office] : [];
  const recipient = primaryRecipients[office] || '';

  if (staffList.length > 0) {
    // ── Case 1: office has staff. Pre-select the primary recipient if it
    //    matches one of them; otherwise the user must choose. ──
    staffSelect.disabled = false;
    let html = '<option value="">-- Select Staff --</option>';
    let matched = false;
    for (const s of staffList) {
      const name = s.full_name || s.username;
      const isSel = (s.username === recipient);
      if (isSel) matched = true;
      html += `<option value="${s.username}"${isSel ? ' selected' : ''}>${name} (@${s.username})</option>`;
    }
    staffSelect.innerHTML = html;
    staffSelect.value = matched ? recipient : '';
    return matched;   // reveal submit only when a default was pre-selected
  }

  if (recipient) {
    // ── Case 2: no staff, but a primary recipient is configured. Route to
    //    that specific username (submits as a normal staff transfer). ──
    staffSelect.disabled = false;
    const name = _lookupStaffName(recipient);
    staffSelect.innerHTML =
      `<option value="${recipient}" selected>📌 Primary recipient — ${name} (@${recipient})</option>`;
    staffSelect.value = recipient;
    return true;
  }

  // ── Case 3: no staff and no primary recipient — office-level general queue.
  //    Keep the select empty/disabled so new_staff submits blank. ──
  staffSelect.innerHTML =
    '<option value="">— No primary recipient — document will be sent to this office\'s general queue —</option>';
  staffSelect.disabled = true;
  return true;
}

function onStaffChange() {
  const val = document.getElementById('new_staff').value;
  if (val) show('step-submit-block');
  else hide('step-submit-block');
}

// ── Pre-fill from ?preset=<username> ─────────────────────────────────────────
(function presetFromUrl() {
  var preset = new URLSearchParams(window.location.search).get('preset');
  if (!preset) return;

  // Locate which office the preset staff member belongs to
  var presetOffice = null;
  for (var office in officesData) {
    for (var i = 0; i < officesData[office].length; i++) {
      if (officesData[office][i].username === preset) {
        presetOffice = office;
        break;
      }
    }
    if (presetOffice) break;
  }
  if (!presetOffice) return;

  var isInternal   = (presetOffice === currentOffice);
  var typeSelect   = document.getElementById('transfer_type');
  var officeSelect = document.getElementById('new_office');
  var staffSelect  = document.getElementById('new_staff');

  typeSelect.value = isInternal ? 'inside_office' : 'outside_office';
  onTransferTypeChange();   // populates office block and (for internal) staff block

  if (!isInternal) {
    officeSelect.value = presetOffice;
    updateStaff();          // populates staff block for the chosen external office
  }

  staffSelect.value = preset;
  onStaffChange();          // shows the submit button
})();
