(() => {
  'use strict';
  const formatter = new Intl.DateTimeFormat(undefined, {dateStyle:'long',timeStyle:'short'});
  document.querySelectorAll('.spyke-media__time').forEach(el => {
    const date = new Date(el.dateTime);
    if (!Number.isNaN(date.getTime())) el.textContent = formatter.format(date);
  });
  document.querySelectorAll('.spyke-single-time, .spyke-single-date').forEach(el => {
    const date = new Date(el.dateTime);
    if (Number.isNaN(date.getTime())) return;
    el.textContent = el.classList.contains('spyke-single-date')
      ? new Intl.DateTimeFormat(undefined, {dateStyle:'long'}).format(date)
      : new Intl.DateTimeFormat(undefined, {timeStyle:'short'}).format(date);
  });
  const players = document.querySelectorAll('.spyke-media audio, .spyke-media video');
  players.forEach(player => player.addEventListener('play', () => {
    players.forEach(other => { if (other !== player) other.pause(); });
  }));
})();
