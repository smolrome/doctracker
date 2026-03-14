function changeRdPerPage(val) {
  window.location.href = '/routed-documents?page=1&per_page=' + val;
}

/* Delete Routing Slip */
function deleteRoutingSlip(slipId, slipNo) {
  if (!confirm('Are you sure you want to delete routing slip ' + slipNo + '? This action cannot be undone.')) {
    return;
  }
  
  fetch('/routing-slip/' + slipId + '/delete', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    }
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      alert('Routing slip ' + slipNo + ' has been deleted.');
      window.location.reload();
    } else {
      alert('Error: ' + (data.message || 'Failed to delete routing slip.'));
    }
  })
  .catch(error => {
    alert('Error: ' + error.message);
  });
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