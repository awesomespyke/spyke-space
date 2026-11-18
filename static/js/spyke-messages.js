(function () {
  'use strict';
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
