// Minimal service worker for kino-barn-innherred.
//
// Dette er ikke en cache-først offline-app -- Shiny-innholdet er dynamisk og
// skal alltid hentes ferskt. Service workeren finnes utelukkende for å gjøre
// siden "installerbar" som PWA: nettlesere som Chrome på Android krever en
// registrert service worker med en fetch-handler før de tilbyr
// "Legg til på startskjerm" / installer-appen.
//
// Den lar derfor alle forespørsler gå rett til nettverket, uendret.

self.addEventListener("install", function (event) {
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", function (event) {
  event.respondWith(fetch(event.request));
});
