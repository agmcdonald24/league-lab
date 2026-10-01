# League Lab web app (plan D7 spike)

My Week and the player card as a phone-first web app: Svelte 5 + TypeScript + Tailwind 4, built by Vite into
static files that the API (`api/`) serves — one deploy. It reads only the API; the API reads the same marts as
the Streamlit app. `docs/FRONTEND_DECISION.md` says why it exists and what it measured.

* **Two routes.** `/` is My Week: the league / team picker (remembered on the phone in `localStorage`; a
  shared `?league=&team=` link wins and is then remembered), the record and league line, the three closest
  calls as cards (the cards' text is `app/lib/cards.py`'s own), the lineup (four columns; the flag column only
  when a player has a flag), the full lineup, "How to read this" and the movers behind expanders.
  `/player/<gsis>?league=&team=` is the player card: Projection, Value, Availability, Usage, Signals (the
  answer first; the Streamlit page leads with Usage), search, "How to read this".
* **One tap, one tab.** Every name is a real link (`<a href="/player/…">`, so long-press / share work) that the
  app handles in place: no reload, no new tab, no new session. Back (the button or the browser's) returns to the
  same scroll position; picking a league or team rewrites the URL without adding a Back step.
* **Phone first.** 390 px is the design width; one column up to 576 px (centred on a desktop); no table wider
  than the screen; light / dark from the system; system fonts (nothing to download).
* **Installable.** `public/manifest.webmanifest` (standalone, icons 192 / 512 / maskable, `apple-touch-icon`)
  and a small service worker (`public/sw.js`: hashed files cache-first, the shell network-first, `/api` never
  cached). On an iPhone: Safari → Share → *Add to Home Screen*.
* **Fast first screen.** An inline script in `index.html` starts the first screen's API call before the app's
  JavaScript arrives (≈27 KB gzipped JS + 5 KB CSS); answers are kept in memory for five minutes, so Back and a
  second visit to a player render at once.
* **Password gate.** When the API has `LEAGUE_LAB_APP_PASSWORD`, the app shows the password screen; a right
  password sets an HttpOnly cookie for 180 days (a new tab, or the home-screen icon tomorrow, stays signed in).

## Run

```bash
cd api && uv run uvicorn league_lab_api.main:app --port 8581      # the API (reads the repository's .env)
cd web && npm ci && npm run build                                 # → web/dist, served by the API at http://localhost:8581/
npm run dev                                                       # or: dev server on :8582 with hot reload, /api proxied to :8581
```

## Check

```bash
npm run lint             # eslint + svelte-check (types, a11y) + tsc on the e2e / config files
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers npm run e2e      # Playwright, phone (iPhone UA, 390 × 844) and desktop (1300 × 900)
E2E_GATED_URL=http://localhost:8583 E2E_GATED_PASSWORD=… npm run e2e    # + the password screen (an API started with that password)
node e2e/gzip-proxy.mjs http://localhost:8577 8578       # Streamlit compressed, as a host serves it (streamlit run does not gzip)
MEASURE_ST_URL=http://localhost:8578 MEASURE_ST_RAW_URL=http://localhost:8577 npm run measure
                                                          # side by side: first content, taps, page weight → e2e/.out/measure.md
node e2e/streamlit-probe.mjs                              # Streamlit's Back after a page hop, and the password per new tab (PROBE_GATED_URL)
```

`e2e/app.spec.ts` asserts, at both sizes: no sideways scroll, the first decision card ends inside the first
screen, tables of at most five columns, a name opens the player card on ONE tap in the SAME tab (no popup, one
history entry), Back (in-app and browser) returns to My Week at the same scroll position, the pick is
remembered, search, dark mode, the manifest and service worker, the password screen. Screenshots go to
`SHOTS_DIR` (default `e2e/.out`).

## Deploy

With the API: `api/Dockerfile` builds this app and serves it (see `api/README.md`). No environment variables
of its own; it talks to the API on the same origin.

## Files

| Path | What |
|---|---|
| `src/App.svelte` | boot (leagues, the gate), the league / team rule, the route switch |
| `src/routes/MyWeek.svelte`, `src/routes/Player.svelte` | the two pages |
| `src/components/*` | picker, lineup table, section card, metric tiles, expander, markdown, login |
| `src/lib/api.ts` | the API's types, fetch + five-minute memory cache, the prefetch hand-off |
| `src/lib/router.svelte.ts` | History-API router: same-tab links, Back with scroll restore, URL rewrites without history |
| `src/lib/md.ts` | the pages' markdown subset (bold, links, line breaks, bullets), escaped before rendering |
| `src/lib/prefs.ts` | the remembered pick (`localStorage`, guarded) |
| `public/` | manifest, icons (`scripts/make-icons.py`), service worker |
| `e2e/` | Playwright checks and the side-by-side measurement |
