(() => {
  'use strict';
  const tiles = Array.from(document.querySelectorAll('.spyke-gallery__tile'));
  const box = document.getElementById('spyke-lightbox');
  if (!tiles.length || !box) return;
  const image = document.getElementById('spyke-lightbox-image');
  const count = document.getElementById('spyke-lightbox-count');
  const caption = document.getElementById('spyke-lightbox-caption');
  const source = document.getElementById('spyke-lightbox-source');
  const closeButton = document.getElementById('spyke-lightbox-close');
  const prev = document.getElementById('spyke-lightbox-prev');
  const next = document.getElementById('spyke-lightbox-next');
  let index = 0, opener = null, touchStartX = null;
  function show(n) {
    index = (n + tiles.length) % tiles.length;
    const tile = tiles[index];
    image.src = tile.dataset.src;
    image.alt = tile.querySelector('img')?.alt || 'Gallery photograph';
    count.textContent = `${index + 1} / ${tiles.length}`;
    caption.textContent = tile.dataset.caption || '';
    source.href = tile.dataset.source;
  }
  function open(n, button) {
    opener = button;
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
  tiles.forEach((tile, i) => tile.addEventListener('click', () => open(i, tile)));
  closeButton.addEventListener('click', close);
  box.querySelector('[data-gallery-close]').addEventListener('click', close);
  prev.addEventListener('click', () => show(index - 1));
  next.addEventListener('click', () => show(index + 1));
  document.addEventListener('keydown', (event) => {
    if (box.hidden) return;
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    else if (event.key === 'ArrowLeft') { event.preventDefault(); show(index - 1); }
    else if (event.key === 'ArrowRight') { event.preventDefault(); show(index + 1); }
    else if (event.key === 'Tab') {
      const focusables = [closeButton, prev, next, source];
      const current = focusables.indexOf(document.activeElement);
      if (event.shiftKey && current <= 0) { event.preventDefault(); source.focus(); }
      else if (!event.shiftKey && current === focusables.length - 1) { event.preventDefault(); closeButton.focus(); }
    }
  });
  box.addEventListener('touchstart', (event) => { touchStartX = event.changedTouches[0]?.screenX ?? null; }, {passive:true});
  box.addEventListener('touchend', (event) => {
    if (touchStartX === null) return;
    const dx = (event.changedTouches[0]?.screenX ?? touchStartX) - touchStartX;
    if (Math.abs(dx) > 55) show(index + (dx < 0 ? 1 : -1));
    touchStartX = null;
  }, {passive:true});
})();
