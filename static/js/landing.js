const revealEls = document.querySelectorAll('.reveal,.reveal-left,.reveal-right,.reveal-scale');
const revObs = new IntersectionObserver(entries => {
  entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('visible'); });
}, { threshold: 0.1, rootMargin: '0px 0px -36px 0px' });
revealEls.forEach(el => revObs.observe(el));

const bar = document.getElementById('progressBar');
const btn = document.getElementById('backTop');
window.addEventListener('scroll', () => {
  const pct = window.scrollY / (document.documentElement.scrollHeight - window.innerHeight) * 100;
  bar.style.width = pct + '%';
  btn.classList.toggle('visible', window.scrollY > 500);
});

window.addEventListener('load', () => {
  const coverEls = document.querySelectorAll('.cover > *:not(.cover-pattern):not(.cover-particle)');
  coverEls.forEach((el, i) => {
    el.style.opacity = '0'; el.style.transform = 'translateY(30px)';
    el.style.transition = 'opacity .8s ease, transform .8s ease';
    el.style.transitionDelay = (i * 0.11) + 's';
    setTimeout(() => { el.style.opacity = ''; el.style.transform = ''; }, 60);
  });
});

function animateCounter(el, target, duration = 1400) {
  let start = 0; const step = target / (duration / 16);
  const timer = setInterval(() => {
    start += step;
    if (start >= target) { el.textContent = target; clearInterval(timer); }
    else el.textContent = Math.floor(start);
  }, 16);
}
const statNums = document.querySelectorAll('.cover-stat-num');
let countersStarted = false;
const counterObs = new IntersectionObserver(entries => {
  if (!countersStarted && entries.some(e => e.isIntersecting)) {
    countersStarted = true;
    statNums.forEach(el => { const v = parseInt(el.textContent); if (!isNaN(v)) animateCounter(el, v); });
  }
});
if (statNums.length) counterObs.observe(statNums[0]);

document.querySelectorAll('.flow-phase').forEach(p => {
  p.addEventListener('mouseenter', () => { p.style.paddingLeft = '8px'; p.style.transition = 'padding .2s'; });
  p.addEventListener('mouseleave', () => { p.style.paddingLeft = ''; });
});

function filterOffices(q) {
  q = q.trim().toLowerCase();
  document.querySelectorAll('#officesGrid .office-card').forEach(c => {
    c.style.display = (!q || c.dataset.name.includes(q)) ? '' : 'none';
  });
}

function openQR(name, src) {
  document.getElementById('qrLbName').textContent = name;
  document.getElementById('qrLbImg').src = src;
  document.getElementById('qrLb').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeQR() {
  document.getElementById('qrLb').classList.remove('open');
  document.body.style.overflow = '';
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeQR(); });