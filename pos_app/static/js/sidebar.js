(() => {
  const body = document.body;
  const toggle = document.querySelector('#sidebarToggle');
  const mobile = document.querySelector('#mobileMenuButton');
  const overlay = document.querySelector('#sidebarOverlay');
  const saved = localStorage.getItem('sidebar-collapsed-v2');
  if (saved === '1' || (saved === null && body.dataset.endpoint === 'pos.index')) body.classList.add('sidebar-collapsed');
  const sync = () => {
    if (toggle) toggle.setAttribute('aria-expanded', String(!body.classList.contains('sidebar-collapsed')));
    if (mobile) mobile.setAttribute('aria-expanded', String(body.classList.contains('sidebar-open')));
  };
  const closeMobile = () => { body.classList.remove('sidebar-open'); sync(); };
  if (toggle) toggle.onclick = () => { body.classList.toggle('sidebar-collapsed'); localStorage.setItem('sidebar-collapsed-v2', body.classList.contains('sidebar-collapsed') ? '1' : '0'); sync(); };
  if (mobile) mobile.onclick = () => { body.classList.toggle('sidebar-open'); sync(); };
  if (overlay) overlay.onclick = closeMobile;
  document.querySelectorAll('.sidebar-nav a').forEach((link) => {
    link.addEventListener('pointerdown', () => {
      const path = new URL(link.href, window.location.origin).pathname;
      if (path === '/pos' || path === '/online-orders') {
        sessionStorage.setItem('onlineOrderAlertNavigationGesture', String(Date.now()));
      }
    }, { passive: true });
    link.addEventListener('click', closeMobile);
  });
  sync();
})();
