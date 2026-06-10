document.addEventListener('DOMContentLoaded', () => {
  // Set footer year
  const year = document.getElementById('year');
  if (year) year.textContent = new Date().getFullYear();

  // Smooth scroll
  function smoothScroll(target) {
    const el = document.querySelector(target);
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  }

  // Get Started button scrolls to features
  document.getElementById('getStarted')?.addEventListener('click', () => {
    smoothScroll('#features');
  });

  // Navbar smooth links
  document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', e => {
      const href = link.getAttribute('href');
      if (href && href.startsWith('#')) {
        e.preventDefault();
        smoothScroll(href);
      }
    });
  });

  // Contact button opens email
  document.getElementById('contactBtn')?.addEventListener('click', () => {
    window.location.href = 'mailto:email@gmail.com?subject=Automation%20Dashboard%20Inquiry';
  });
});
