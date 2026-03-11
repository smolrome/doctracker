const officesData   = JSON.parse(document.getElementById('offices-data').textContent || '{}');
const sortedOffices = JSON.parse(document.getElementById('sorted-offices').textContent || '[]');
const currentOffice = JSON.parse(document.getElementById('current-office-data').textContent);
const currentUserName = JSON.parse(document.getElementById('current-user-data').textContent || '""');
const currentUserRole = JSON.parse(document.getElementById('current-role-data').textContent || '""');

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

  populateStaff(office);
  show('step-staff-block');
}

function populateStaff(office) {
  const staffSelect = document.getElementById('new_staff');
  staffSelect.innerHTML = '<option value="">-- Select Staff --</option>';

  if (!office || !officesData[office]) return;

  for (const s of officesData[office]) {
    const name = s.full_name || s.username;
    staffSelect.innerHTML += `<option value="${s.username}">${name} (@${s.username})</option>`;
  }
}

function onStaffChange() {
  const val = document.getElementById('new_staff').value;
  if (val) show('step-submit-block');
  else hide('step-submit-block');
}
