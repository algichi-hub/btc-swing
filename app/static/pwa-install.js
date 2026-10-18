/* F5-E0: install shell; push intentionally unavailable until G3/G4 GO. */
'use strict';
if ('serviceWorker' in navigator && window.isSecureContext) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/static/sw.js', {scope:'/'})
      .catch(() => { /* PWA remains usable without background worker */ });
  });
}
