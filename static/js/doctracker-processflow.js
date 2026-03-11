const revealEls = document.querySelectorAll('.reveal, .reveal-left, .reveal-right, .reveal-scale');
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => { if (entry.isIntersecting) entry.target.classList.add('visible'); });
}, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
revealEls.forEach(el => revealObserver.observe(el));
const progressBar = document.getElementById('progressBar');
const backTop = document.getElementById('backTop');
window.addEventListener('scroll', () => {
  const scrollTop = window.scrollY;
  const docHeight = document.documentElement.scrollHeight - window.innerHeight;
  progressBar.style.width = (scrollTop / docHeight * 100) + '%';
  backTop.classList.toggle('visible', scrollTop > 400);
});
window.addEventListener('load', () => {
  const coverEls = document.querySelectorAll('.cover > *:not(.cover-pattern):not(.cover-particle)');
  coverEls.forEach((el, i) => {
    el.style.opacity = '0'; el.style.transform = 'translateY(30px)';
    el.style.transition = 'opacity .8s ease, transform .8s ease';
    el.style.transitionDelay = (i * 0.12) + 's';
    setTimeout(() => { el.style.opacity = ''; el.style.transform = ''; }, 50);
  });
});
function animateCounter(el, target, duration = 1500) {
  let start = 0; const step = target / (duration / 16);
  const timer = setInterval(() => {
    start += step;
    if (start >= target) { el.textContent = target; clearInterval(timer); }
    else el.textContent = Math.floor(start);
  }, 16);
}
const statNums = document.querySelectorAll('.cover-stat-num');
let countersStarted = false;
const counterObserver = new IntersectionObserver((entries) => {
  if (!countersStarted && entries.some(e => e.isIntersecting)) {
    countersStarted = true;
    statNums.forEach(el => animateCounter(el, parseInt(el.textContent), 1200));
  }
});
if (statNums.length) counterObserver.observe(statNums[0]);
document.querySelectorAll('.flow-phase').forEach(phase => {
  phase.addEventListener('mouseenter', () => { phase.style.paddingLeft = '8px'; phase.style.transition = 'padding .2s'; });
  phase.addEventListener('mouseleave', () => { phase.style.paddingLeft = ''; });
});