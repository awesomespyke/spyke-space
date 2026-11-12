(function () {
  'use strict';
  var root = document.documentElement;
  var toggle = document.querySelector('.spyke-chat__theme');
  if (toggle) {
    toggle.addEventListener('click', function () {
      var current = root.getAttribute('data-scheme');
      var effective = current || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      var next = effective === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-scheme', next);
      try { localStorage.setItem('StackColorScheme', next); } catch (_) {}
    });
  }
  // Only jump on initial arrival. Respect deep links and browser scroll restoration.
  if (document.getElementById('message-history') && !window.location.hash) {
    if (history.scrollRestoration !== 'manual') {
      window.addEventListener('load', function () {
        if (window.scrollY < 80) window.scrollTo(0, document.documentElement.scrollHeight);
      }, { once: true });
    }
  }
})();
