function changeRdPerPage(val) {
  window.location.href = '/routed-documents?page=1&per_page=' + val;
}

/* Re-route Modal */
var rerouteModal = null;
var currentSlipId = null;

function openRerouteModal(slipId, currentDest) {
  currentSlipId = slipId;
  document.getElementById('reroute-dest').value = currentDest;
  document.getElementById('reroute-slip-id').value = slipId;
  document.getElementById('reroute-modal').style.display = 'flex';
}

function closeRerouteModal() {
  document.getElementById('reroute-modal').style.display = 'none';
  currentSlipId = null;
}

function submitReroute() {
  const dest = document.getElementById('reroute-dest').value.trim();
  if (!dest) {
    alert('Please enter a destination office.');
    return;
  }
  document.getElementById('reroute-form').submit();
}