(() => {
  const body = document.body;
  const toggle = document.querySelector('#sidebarToggle');
  const mobile = document.querySelector('#mobileMenuButton');
  const overlay = document.querySelector('#sidebarOverlay');
  const navSections = document.querySelectorAll('[data-nav-section]');
  const saved = localStorage.getItem('sidebar-collapsed-v2');
  let savedSections = {};
  try {
    savedSections = JSON.parse(localStorage.getItem('sidebar-sections-v306') || '{}');
  } catch {
    savedSections = {};
  }
  if (saved === '1' || (saved === null && body.dataset.endpoint === 'pos.index')) body.classList.add('sidebar-collapsed');
  navSections.forEach((section) => {
    const name = section.dataset.navSection;
    const button = section.querySelector('.nav-group');
    const arrow = section.querySelector('.nav-group-arrow');
    const defaultExpanded = section.dataset.defaultExpanded === 'true';
    let expanded = Object.prototype.hasOwnProperty.call(savedSections, name)
      ? savedSections[name] === true
      : defaultExpanded;
    const syncSection = () => {
      section.classList.toggle('is-collapsed', !expanded);
      if (button) button.setAttribute('aria-expanded', String(expanded));
      if (arrow) arrow.textContent = '^';
    };
    if (button) {
      button.addEventListener('click', () => {
        expanded = !expanded;
        savedSections[name] = expanded;
        try {
          localStorage.setItem('sidebar-sections-v306', JSON.stringify(savedSections));
        } catch {
          // The section still works when browser storage is unavailable.
        }
        syncSection();
      });
    }
    syncSection();
  });
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
