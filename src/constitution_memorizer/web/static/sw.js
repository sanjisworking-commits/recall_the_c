/* Kill-switch service worker.

   This app has never registered a service worker — there is no registration
   call, no manifest, and no worker source anywhere in the repo. The /sw.js
   requests in production therefore come from outside it: most likely a worker
   registered by something else and still alive in a browser, re-fetching its
   script to check for an update.

   That fetch is the only lever we have. Serving this makes an orphaned worker
   remove itself permanently.

   It deliberately does NOT touch Cache Storage. We do not know which cache
   names such a worker owns, and enumerating them to delete would wipe every
   cache on the origin, including ones we did not create. Unregistering is
   enough: the browser discards a departed worker's caches on its own. */
self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.registration.unregister());
});
