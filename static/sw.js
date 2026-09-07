// Minimal pass-through service worker — exists only to satisfy PWA installability
// criteria. This app is fundamentally about live sensor/device data over the LAN,
// so it deliberately does not cache responses; every request still goes to the
// network as normal.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => event.respondWith(fetch(event.request)));
