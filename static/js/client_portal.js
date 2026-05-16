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

// ── Document search + filter ───────────────────────────────────────────────

function applyFilters() {
  var q       = (document.getElementById('doc-search')     ? document.getElementById('doc-search').value     : '').toLowerCase().trim();
  var cat     = (document.getElementById('doc-filter-cat') ? document.getElementById('doc-filter-cat').value : '').toLowerCase();
  var date    =  document.getElementById('doc-filter-date') ? document.getElementById('doc-filter-date').value : '';
  var cards   = document.querySelectorAll('#doc-list .doc-card');
  var clearBtn       = document.getElementById('search-clear');
  var filterClearBtn = document.getElementById('filter-clear');
  var countEl        = document.getElementById('doc-count');
  var emptyMsg       = document.getElementById('doc-empty-filtered');

  if (clearBtn)       clearBtn.style.display       = q             ? 'block' : 'none';
  if (filterClearBtn) filterClearBtn.style.display = (cat || date) ? 'block' : 'none';

  var visible = 0;
  cards.forEach(function(card) {
    var name     = card.dataset.name     || '';
    var ref      = card.dataset.ref      || '';
    var status   = card.dataset.status   || '';
    var referred = card.dataset.referred || '';
    var org      = card.dataset.org      || '';
    var cardCat  = card.dataset.category || '';
    var cardDate = card.dataset.date     || '';

    var matchQ    = !q    || name.includes(q) || ref.includes(q) || status.includes(q) || referred.includes(q) || org.includes(q);
    var matchCat  = !cat  || cardCat === cat;
    var matchDate = !date || cardDate === date;

    var show = matchQ && matchCat && matchDate;
    card.style.display = show ? '' : 'none';
    if (show) visible++;
  });

  var total = cards.length;
  if (countEl) {
    if (q || cat || date) {
      countEl.textContent = 'Showing ' + visible + ' of ' + total + ' document' + (total !== 1 ? 's' : '');
    } else {
      countEl.textContent = total > 0 ? total + ' document' + (total !== 1 ? 's' : '') : '';
    }
  }
  if (emptyMsg) emptyMsg.style.display = (visible === 0 && total > 0) ? 'block' : 'none';
}

function clearSearch() {
  var inp = document.getElementById('doc-search');
  if (inp) inp.value = '';
  applyFilters();
}

function clearFilters() {
  var cat  = document.getElementById('doc-filter-cat');
  var date = document.getElementById('doc-filter-date');
  if (cat)  cat.value  = '';
  if (date) date.value = '';
  applyFilters();
}

function _initCategoryFilter() {
  var sel   = document.getElementById('doc-filter-cat');
  var cards = document.querySelectorAll('#doc-list .doc-card');
  if (!sel) return;
  var cats = {};
  cards.forEach(function(c) {
    var cat = c.dataset.category;
    if (cat) cats[cat] = true;
  });
  Object.keys(cats).sort().forEach(function(cat) {
    var opt = document.createElement('option');
    opt.value = cat;
    opt.textContent = cat.charAt(0).toUpperCase() + cat.slice(1);
    sel.appendChild(opt);
  });
  if (Object.keys(cats).length === 0) {
    sel.style.display = 'none';
  }
}

document.addEventListener('DOMContentLoaded', function() {
  _initCategoryFilter();
  applyFilters();
});