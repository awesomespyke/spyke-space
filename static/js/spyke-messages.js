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

// Display transmission dates and times in each visitor's timezone.
function localizeTransmissionTimes() {
  const timeFormatter = new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit"
  });

  const dateFormatter = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric"
  });

  const thread = document.querySelector(".spyke-chat__thread");
  if (!thread) return;

  let previousDate = "";

  Array.from(thread.children).forEach((element) => {
    if (element.classList.contains("spyke-chat__date")) {
      element.remove();
      return;
    }

    if (!element.classList.contains("spyke-chat__message")) return;

    const timestamp = element.querySelector(".spyke-local-time");
    if (!timestamp) return;

    const date = new Date(timestamp.dateTime);
    if (Number.isNaN(date.getTime())) return;

    timestamp.textContent = timeFormatter.format(date);

    const localDate = [
      date.getFullYear(),
      String(date.getMonth() + 1).padStart(2, "0"),
      String(date.getDate()).padStart(2, "0")
    ].join("-");

    if (localDate !== previousDate) {
      const separator = document.createElement("div");
      separator.className = "spyke-chat__date";

      const label = document.createElement("time");
      label.dateTime = localDate;
      label.textContent = dateFormatter.format(date);

      separator.appendChild(label);
      thread.insertBefore(separator, element);
      previousDate = localDate;
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", localizeTransmissionTimes);
} else {
  localizeTransmissionTimes();
}

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

/* SpykeSpace YouTube presentation */
document.querySelectorAll('.spyke-chat__content:has(.spyke-youtube)').forEach(content => {
    const player = content.querySelector('.spyke-youtube');
    if (!player) return;

    const iframe = player.querySelector('iframe');
    const videoId = iframe?.src.match(/\/embed\/([A-Za-z0-9_-]{11})(?:[?#]|$)/)?.[1];
    if (!videoId) return;

    for (const paragraph of content.querySelectorAll('p')) {
        const link = paragraph.querySelector('a[href]');
        if (!link || paragraph.textContent.trim() !== link.textContent.trim()) continue;
        if (paragraph.querySelectorAll('a').length !== 1) continue;

        try {
            const url = new URL(link.href);
            const host = url.hostname.toLowerCase();
            const id = host === 'youtu.be'
                ? url.pathname.slice(1)
                : ['youtube.com', 'www.youtube.com', 'm.youtube.com'].includes(host)
                    ? url.searchParams.get('v')
                    : null;

            if (id === videoId) {
                paragraph.classList.add('spyke-youtube__source');
                break;
            }
        } catch {}
    }

    content.prepend(player);
});
