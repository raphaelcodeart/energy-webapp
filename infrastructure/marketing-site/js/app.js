/* ============================================================
   LIAL ENERGY — app.js
============================================================ */

(function () {
  'use strict';

  /* ── Navigation scroll effect ─────────────────────────── */
  const nav = document.getElementById('nav');
  window.addEventListener('scroll', () => {
    nav.classList.toggle('scrolled', window.scrollY > 50);
  }, { passive: true });

  /* ── Mobile menu ───────────────────────────────────────── */
  const mobMenu = document.getElementById('mob-menu');
  window.toggleMenu = function () {
    mobMenu.classList.toggle('open');
    document.body.style.overflow = mobMenu.classList.contains('open') ? 'hidden' : '';
  };

  /* ── Particles (hero) ──────────────────────────────────── */
  const pc = document.getElementById('particles');
  if (pc) {
    for (let i = 0; i < 20; i++) {
      const p = document.createElement('div');
      p.className = 'pt';
      const size = Math.random() * 7 + 2;
      Object.assign(p.style, {
        width:             size + 'px',
        height:            size + 'px',
        left:              Math.random() * 100 + '%',
        animationDuration: (Math.random() * 12 + 8) + 's',
        animationDelay:    (Math.random() * 12) + 's',
      });
      pc.appendChild(p);
    }
  }

  /* ── Intersection Observer — fade-in ───────────────────── */
  const fadeObs = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (!e.isIntersecting) return;
      e.target.classList.add('on');

      /* Animate stat numbers inside revealed element */
      e.target.querySelectorAll('.stat-num[data-target]').forEach(animateNumber);

      /* Animate progress bars inside revealed element */
      e.target.querySelectorAll('.bar-fill[data-w]').forEach(bar => {
        setTimeout(() => { bar.style.width = bar.dataset.w + '%'; }, 300);
      });
    });
  }, { threshold: 0.12 });

  document.querySelectorAll('.fade').forEach(el => fadeObs.observe(el));

  /* ── Number counter ────────────────────────────────────── */
  function animateNumber(el) {
    const target = +el.dataset.target;
    const suffix = el.dataset.suffix || '';
    if (!target && suffix !== '%') return;
    let cur = 0;
    const step = target / (2000 / 16);
    const timer = setInterval(() => {
      cur = Math.min(cur + step, target);
      el.textContent = (target >= 1000
        ? Math.floor(cur).toLocaleString('it-IT')
        : Math.floor(cur)) + suffix;
      if (cur >= target) clearInterval(timer);
    }, 16);
  }

  /* ── Money big counter (consequences section) ──────────── */
  const mSection = document.querySelector('.s-conseq');
  if (mSection) {
    let mDone = false;
    const mObs = new IntersectionObserver(entries => {
      if (!entries[0].isIntersecting || mDone) return;
      mDone = true;
      const el = document.getElementById('mCounter');
      if (!el) return;
      let cur = 0;
      const target = 18000;
      const step = target / (2600 / 16);
      const timer = setInterval(() => {
        cur = Math.min(cur + step, target);
        el.textContent = '€ ' + Math.floor(cur).toLocaleString('it-IT');
        if (cur >= target) clearInterval(timer);
      }, 16);
    }, { threshold: 0.25 });
    mObs.observe(mSection);
  }

  /* ── Card tilt/glow on hover ───────────────────────────── */
  document.querySelectorAll('.p-card, .ben-card, .stat-card').forEach(card => {
    card.addEventListener('mousemove', e => {
      const r = card.getBoundingClientRect();
      const x = ((e.clientX - r.left) / r.width)  * 100;
      const y = ((e.clientY - r.top)  / r.height) * 100;
      const isFeat = card.classList.contains('feat');
      card.style.background = isFeat
        ? `radial-gradient(circle at ${x}% ${y}%, rgba(255,107,0,.15), rgba(255,179,0,.07))`
        : `radial-gradient(circle at ${x}% ${y}%, rgba(255,107,0,.05), transparent 70%), #ffffff`;
    });
    card.addEventListener('mouseleave', () => {
      card.style.background = card.classList.contains('feat')
        ? 'linear-gradient(135deg, var(--orange-pale), rgba(255,179,0,.07))'
        : 'var(--bg-card)';
    });
  });

  /* ── Smooth close mobile menu on link click ────────────── */
  document.querySelectorAll('#mob-menu a').forEach(a => {
    a.addEventListener('click', () => {
      mobMenu.classList.remove('open');
      document.body.style.overflow = '';
    });
  });

})();
