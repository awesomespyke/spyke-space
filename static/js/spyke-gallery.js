(() => {
  'use strict';

  const box = document.getElementById('spyke-lightbox');
  if (!box) return;

  const galleryTiles = Array.from(document.querySelectorAll('.spyke-gallery__tile'));
  const messageImages = Array.from(document.querySelectorAll('.spyke-chat__message .spyke-chat__content img'));

  const items = galleryTiles.length
    ? galleryTiles.map(tile => ({
        opener: tile,
        src: tile.dataset.src,
        alt: tile.querySelector('img')?.alt || 'Gallery photograph',
        caption: tile.dataset.caption || '',
        date: tile.dataset.date || '',
        source: tile.dataset.source || ''
      }))
    : messageImages.map(img => {
        const message = img.closest('.spyke-chat__message');
        return {
          opener: img,
          src: img.getAttribute("src") || img.src,
          alt: img.alt || 'Message photograph',
          caption: img.alt === 'Transmission photograph' ? '' : (img.alt || ''),
          date: message?.querySelector('.spyke-local-time')?.dateTime || '',
          source: message?.querySelector('.spyke-chat__meta a')?.href || ''
        };
      });

  if (!items.length) return;

  const fromMessages = galleryTiles.length === 0 && messageImages.length > 0;

  const image = document.getElementById('spyke-lightbox-image');
  const count = document.getElementById('spyke-lightbox-count');
  const caption = document.getElementById('spyke-lightbox-caption');
  const source = document.getElementById('spyke-lightbox-source');
  const dateLabel = document.getElementById('spyke-lightbox-date');
  const closeButton = document.getElementById('spyke-lightbox-close');
  const prev = document.getElementById('spyke-lightbox-prev');
  const next = document.getElementById('spyke-lightbox-next');

  let index = 0;
  let opener = null;
  let touchStartX = null;

  function show(n) {
    index = (n + items.length) % items.length;
    const item = items[index];

    image.src = item.src;
    image.alt = item.alt;
    count.textContent = `${index + 1} / ${items.length}`;
    caption.textContent = item.caption;

    const date = new Date(item.date);
    dateLabel.textContent = Number.isNaN(date.getTime())
      ? ''
      : new Intl.DateTimeFormat(undefined, {
          dateStyle: 'long',
          timeStyle: 'short'
        }).format(date);
    dateLabel.dateTime = item.date;

    source.href = item.source || '#';
    source.hidden = fromMessages || !item.source;
  }

  function open(n, element) {
    opener = element;
    show(n);
    box.hidden = false;
    document.body.classList.add('spyke-gallery--lightbox-open');
    closeButton.focus();
  }

  function close() {
    box.hidden = true;
    document.body.classList.remove('spyke-gallery--lightbox-open');
    image.removeAttribute('src');
    opener?.focus();
  }

  items.forEach((item, i) => {
    const element = item.opener;

    if (element.tagName === 'IMG') {
      element.tabIndex = 0;
      element.setAttribute('role', 'button');
      element.setAttribute('aria-label', item.alt === 'Message photograph'
        ? 'Open photograph'
        : `Open photograph: ${item.alt}`);

      element.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          open(i, element);
        }
      });
    }

    element.addEventListener('click', () => open(i, element));
  });

  closeButton.addEventListener('click', close);
  box.querySelector('[data-gallery-close]').addEventListener('click', close);
  prev.addEventListener('click', () => show(index - 1));
  next.addEventListener('click', () => show(index + 1));

  document.addEventListener('keydown', event => {
    if (box.hidden) return;

    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      show(index - 1);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      show(index + 1);
    } else if (event.key === 'Tab') {
      const focusables = [closeButton, prev, next, source].filter(el => !el.hidden);
      const current = focusables.indexOf(document.activeElement);

      if (event.shiftKey && current <= 0) {
        event.preventDefault();
        focusables[focusables.length - 1].focus();
      } else if (!event.shiftKey && current === focusables.length - 1) {
        event.preventDefault();
        closeButton.focus();
      }
    }
  });

  let suppressImageClick = false;

  image.addEventListener('click', () => {
    if (!fromMessages) return;
    if (suppressImageClick) {
      suppressImageClick = false;
      return;
    }
    close();
  });

  box.addEventListener('touchstart', event => {
    touchStartX = event.changedTouches[0]?.screenX ?? null;
    suppressImageClick = false;
  }, { passive: true });

  box.addEventListener('touchend', event => {
    if (touchStartX === null) return;

    const dx = (event.changedTouches[0]?.screenX ?? touchStartX) - touchStartX;

    if (Math.abs(dx) > 10) {
      suppressImageClick = true;
    }

    if (Math.abs(dx) > 55) {
      show(index + (dx < 0 ? 1 : -1));
    }

    touchStartX = null;
  }, { passive: true });
})();
