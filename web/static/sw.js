// Service Worker fuer Move2Notion PWA
// Minimal - ermoeglicht Installation, kein Offline-Cache

self.addEventListener('install', function(event) {
    self.skipWaiting();
});

self.addEventListener('activate', function(event) {
    event.waitUntil(clients.claim());
});

self.addEventListener('fetch', function(event) {
    event.respondWith(fetch(event.request));
});
