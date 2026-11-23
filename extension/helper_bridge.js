(() => {
  'use strict';

  document.documentElement.dataset.talontermoInstalled = '1';

  const params = new URLSearchParams(window.location.search);
  if (params.get('target') === 'extensions') {
    chrome.runtime.sendMessage({ action: 'open_extensions' });
  }

  document.addEventListener('click', (e) => {
    const trigger = e.target.closest?.('[data-open-extensions]');
    if (!trigger) return;
    e.preventDefault();
    chrome.runtime.sendMessage({ action: 'open_extensions' });
  });
})();
