function filterOfficesC(query) {
  const q = query.toLowerCase().trim();
  const cards = document.querySelectorAll('.oqs-card-c');
  let visible = 0;
  cards.forEach(card => {
    const show = !q || (card.dataset.name||'').includes(q);
    card.classList.toggle('hidden', !show);
    if (show) visible++;
  });
  document.getElementById('oqs-count-c').textContent =
    visible + ' office' + (visible !== 1 ? 's' : '') + (q ? ' found' : ' available');
  document.getElementById('oqs-none-c').classList.toggle('visible', visible === 0);
}

function toggleOfficeModal() {
    const m = document.getElementById('office-modal');
    if(m){m.style.display=m.style.display==='none'?'flex':'none';}
  }
  function filterOfficeModal(q) {
    const cards=document.querySelectorAll('.office-modal-card');
    const none=document.getElementById('office-modal-none');
    let v=0;q=q.toLowerCase().trim();
    cards.forEach(c=>{
      const name=c.getAttribute('data-name')||'';
      if(q===''||name.includes(q)){c.style.display='block';v++;}else{c.style.display='none';}
    });
    if(none)none.style.display=v===0?'block':'none';
  }