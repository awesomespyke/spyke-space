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
})();

// Responsive SpykeSpace navigation.
(function () {
  const container = document.querySelector(".spyke-floating-nav");
  const toggle = document.getElementById("spyke-nav-toggle");
  const panel = document.getElementById("spyke-nav-panel");

  if (!container || !toggle || !panel) return;

  const desktop = window.matchMedia("(min-width: 1024px)");

  function setOpen(open) {
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute(
      "aria-label",
      open ? "Close navigation" : "Open navigation"
    );
    container.classList.remove("is-hidden");
  }

  function synchronize() {
    setOpen(desktop.matches);
  }

  toggle.addEventListener("click", () => {
    if (!desktop.matches) setOpen(panel.hidden);
  });

  document.addEventListener("pointerdown", (event) => {
    if (!desktop.matches && !container.contains(event.target)) {
      setOpen(false);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (!desktop.matches && event.key === "Escape" && !panel.hidden) {
      setOpen(false);
      toggle.focus();
    }
  });

  let previousY = window.scrollY;

  window.addEventListener("scroll", () => {
    const currentY = window.scrollY;
    const difference = currentY - previousY;

    if (!desktop.matches && panel.hidden && Math.abs(difference) > 4) {
      container.classList.toggle(
        "is-hidden",
        difference > 0 && currentY > 100
      );
    }

    previousY = currentY;
  }, { passive: true });

  synchronize();
  desktop.addEventListener("change", synchronize);
})();
