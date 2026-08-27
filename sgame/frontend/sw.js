const CACHE_NAME = "sgame-shell-v0.1.2";
const APP_SHELL = [
  "/",
  "/static/style.css?v=0.1.1",
  "/static/pwa.js?v=0.1.1",
  "/static/manifest.webmanifest",
  "/static/icon.svg",
  "/schulte",
  "/static/schulte/schulte.css?v=0.1.1",
  "/static/schulte/schulte.js?v=0.1.1",
  "/minesweeper",
  "/static/minesweeper/minesweeper.css?v=0.1.1",
  "/static/minesweeper/minesweeper.js?v=0.1.1",
  "/pacman",
  "/static/pacman/pacman.css?v=0.1.2",
  "/static/pacman/pacman.js?v=0.1.1",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) => Promise.all(
      names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name)),
    )),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const requestUrl = new URL(event.request.url);
  if (event.request.method !== "GET" || requestUrl.origin !== self.location.origin || requestUrl.pathname.startsWith("/api/")) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, response.clone()));
        }
        return response;
      })
      .catch(() => caches.match(event.request).then((cached) => cached || Response.error())),
  );
});
