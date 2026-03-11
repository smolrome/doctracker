const form = document.getElementById('reg-form');
form.addEventListener('submit', function(e) {
  const p1 = document.getElementById('pw1').value;
  const p2 = document.getElementById('pw2').value;
  if (p1 !== p2) {
    e.preventDefault();
    alert('Passwords do not match.');
    return;
  }
  if (p1.length < 8) {
    e.preventDefault();
    alert('Password must be at least 8 characters.');
    return;
  }
  document.getElementById('submit-btn').disabled = true;
  document.getElementById('loading-overlay').classList.add('active');
});
window.addEventListener('pageshow', e => {
  if (e.persisted) {
    document.getElementById('loading-overlay').classList.remove('active');
    document.getElementById('submit-btn').disabled = false;
  }
});