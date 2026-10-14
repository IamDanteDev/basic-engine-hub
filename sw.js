"use strict";

const CACHE_NAME = "basic-engine-hub-shell-v1";
const SHELL_PATHS = [
  "./",
  "./index.html",
  "./web/index.html",
  "./web/app.js",
  "./web/style.css",
  "./web/player.html",
  "./app.js",
  "./style.css",
  "./player.html",
];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await Promise.all(SHELL_PATHS.map(async (path) => {
      const url = new URL(path, self.registration.scope).href;
      try {
        const response = await fetch(url, { cache: "reload" });
        if (response.ok) await cache.put(url, response);
      } catch {
        // Cache whichever entry points exist on this hosting layout.
      }
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((key) => key.startsWith("basic-engine-hub-") && key !== CACHE_NAME)
      .map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.includes("/api/")) return;

  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    try {
      const response = await fetch(request);
      if (response.ok) await cache.put(request, response.clone());
      return response;
    } catch {
      const cached = await cache.match(request);
      if (cached) return cached;
      if (request.mode === "navigate") {
        const root = new URL("index.html", self.registration.scope);
        const cachedRoot = await cache.match(root.href) || await cache.match(self.registration.scope);
        if (cachedRoot) return cachedRoot;
      }
      return Response.error();
    }
  })());
});
