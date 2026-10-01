// Side by side: the web app (API + static, MEASURE_WEB_URL) and the Streamlit app (MEASURE_ST_URL) on the same
// database, phone (iPhone 13 UA, 390 × 844, touch) and desktop (1300 × 900), Chromium.
//   * first content: navigation start → the first decision card on screen (a MutationObserver stamps
//     performance.now() when it appears), cold (new browser profile) and warm (second visit), median of N;
//   * page weight: bytes over the wire until first content + 2 s (HTTP bodies + WebSocket frames), by type;
//   * taps (10 each): a name in a card → the player card; back to My Week; change team → the new team's cards;
//   * one tap? does a name open on the first tap, in the same tab?
//   * the same on a throttled phone network ("slow 4G": 150 ms round trip, 1.6 Mbit/s down, 0.75 up).
// Servers are warmed first (one pass), so both apps answer from their 10-minute query caches, as in normal use.
// Output: e2e/.out/measure.json and measure.md (a table for docs/FRONTEND_DECISION.md); screenshots st_* (SHOTS_DIR).
import { devices, test, type BrowserContext, type CDPSession, type Page } from "@playwright/test";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { cpus, loadavg } from "node:os";
import { join } from "node:path";
import { performance } from "node:perf_hooks";

const WEB = process.env.MEASURE_WEB_URL ?? "http://localhost:8581";
// Streamlit behind e2e/gzip-proxy.mjs (compressed, as a host serves it) and, optionally, direct (`streamlit run`
// sends its JavaScript uncompressed): first-visit numbers for both
const ST = process.env.MEASURE_ST_URL ?? "http://localhost:8577";
const ST_RAW = process.env.MEASURE_ST_RAW_URL;
const LOADS = Number(process.env.MEASURE_LOADS ?? 5);
const TAPS = Number(process.env.MEASURE_TAPS ?? 10);
const OUT = join(import.meta.dirname, ".out");
const SHOTS = process.env.SHOTS_DIR ?? OUT;
mkdirSync(OUT, { recursive: true });
mkdirSync(SHOTS, { recursive: true });

const DYNASTY = "1321941740235550720";
const TEAM = 12;
const OTHER_TEAM = 11; // "2 da Moon wit Love": the team switch alternates 12 ↔ 11
const SLOW4G = { offline: false, latency: 150, downloadThroughput: (1.6e6 / 8) | 0, uploadThroughput: (0.75e6 / 8) | 0 };

type Profile = { name: "phone" | "desktop"; options: Parameters<import("@playwright/test").Browser["newContext"]>[0]; mobile: boolean };
const { defaultBrowserType: _ignored, ...IPHONE } = devices["iPhone 13"];
void _ignored;
const MEMBERS: Record<number, string> = { 12: "Shake & Bake", 11: "2 da Moon wit Love" };
const PROFILES: Profile[] = [
  { name: "phone", options: { ...IPHONE, viewport: { width: 390, height: 844 } }, mobile: true },
  { name: "desktop", options: { viewport: { width: 1300, height: 900 } }, mobile: false },
];

// ---- first-content stamp: set window.__ll_first when the answer (a decision card) is in the DOM
const STAMP = `(() => {
  const re = /apart, (a coin flip|a lean|clear)/;
  const check = () => {
    if (window.__ll_first) return;
    if (document.querySelector('[data-testid="decision-card"]')) { window.__ll_first = performance.now(); return; }
    for (const el of document.querySelectorAll('[data-testid="stMarkdownContainer"]')) {
      if (re.test(el.textContent || "")) { window.__ll_first = performance.now(); return; }
    }
  };
  new MutationObserver(check).observe(document, { childList: true, subtree: true, characterData: true });
})();`;

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : NaN;
};
const r0 = (x: number) => Math.round(x);
const log = (...a: unknown[]) =>
  appendFileSync(join(OUT, "measure.log"), [new Date().toISOString().slice(11, 19), ...a.map(String)].join(" ") + "\n");

interface Weight {
  total: number;
  byType: Record<string, number>;
  requests: number;
  wsFrames: number;
}

async function meter(page: Page, throttle = false): Promise<{ cdp: CDPSession; weight: Weight }> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: false });
  if (throttle) await cdp.send("Network.emulateNetworkConditions", SLOW4G);
  const weight: Weight = { total: 0, byType: {}, requests: 0, wsFrames: 0 };
  const types = new Map<string, string>();
  cdp.on("Network.responseReceived", (e) => types.set(e.requestId, e.type));
  cdp.on("Network.loadingFinished", (e) => {
    const t = types.get(e.requestId) ?? "Other";
    weight.total += e.encodedDataLength;
    weight.byType[t] = (weight.byType[t] ?? 0) + e.encodedDataLength;
    weight.requests++;
  });
  cdp.on("Network.webSocketFrameReceived", (e) => {
    const n = e.response.opcode === 1 ? e.response.payloadData.length : Math.floor((e.response.payloadData.length * 3) / 4);
    weight.total += n;
    weight.byType.WebSocket = (weight.byType.WebSocket ?? 0) + n;
    weight.wsFrames++;
  });
  return { cdp, weight };
}

type App = {
  name: "web" | "streamlit";
  base: string;
  week: (team?: number) => string;
  player: (gsis: string) => string;
  cards: (page: Page) => Promise<void>;
  playerShown: (page: Page, name: string) => Promise<void>;
};

const web: App = {
  name: "web",
  base: WEB,
  week: (team = TEAM) => `${WEB}/?league=${DYNASTY}&team=${team}`,
  player: (gsis) => `${WEB}/player/${gsis}?league=${DYNASTY}&team=${TEAM}`,
  cards: async (page) => {
    await page.getByTestId("decision-card").first().waitFor({ timeout: 60_000 });
  },
  playerShown: async (page, name) => {
    await page.getByTestId("player-name").filter({ hasText: name }).waitFor({ timeout: 60_000 });
    await page.getByTestId("section-value").waitFor({ timeout: 60_000 });
  },
};

async function stIdle(page: Page) {
  await page.waitForTimeout(50);
  await page.locator('[data-testid="stStatusWidget"]').waitFor({ state: "detached", timeout: 120_000 }).catch(() => {});
}

const streamlit: App = {
  name: "streamlit",
  base: ST,
  week: (team = TEAM) => `${ST}/?league=${DYNASTY}&team=${team}`,
  player: (gsis) => `${ST}/Player?id=${gsis}&league=${DYNASTY}&team=${TEAM}`,
  cards: async (page) => {
    await page.getByText(/apart, (a coin flip|a lean|clear)/).first().waitFor({ timeout: 120_000 });
  },
  playerShown: async (page, name) => {
    await page.locator("h3", { hasText: name }).first().waitFor({ timeout: 120_000 });
    await page.getByText(/^Value — /).first().waitFor({ timeout: 120_000 });
  },
};

const streamlitRaw: App | null = ST_RAW
  ? { ...streamlit, base: ST_RAW, week: (team = TEAM) => `${ST_RAW}/?league=${DYNASTY}&team=${team}`, player: (g) => `${ST_RAW}/Player?id=${g}&league=${DYNASTY}&team=${TEAM}` }
  : null;

interface LoadResult {
  firstContent: number;
  responseStart: number;
  domContentLoaded: number;
  load: number;
  weight?: Weight;
}

async function loadOnce(ctx: BrowserContext, app: App, throttle: boolean, withWeight: boolean): Promise<LoadResult> {
  const page = await ctx.newPage();
  await page.addInitScript(STAMP);
  const { weight } = await meter(page, throttle);
  await page.goto(app.week(), { waitUntil: "commit" });
  await app.cards(page);
  await page.waitForFunction(() => (window as unknown as { __ll_first?: number }).__ll_first, null, { timeout: 60_000 });
  const t = await page.evaluate(() => {
    const nav = window.performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
    return {
      firstContent: (window as unknown as { __ll_first: number }).__ll_first,
      responseStart: nav.responseStart,
      domContentLoaded: nav.domContentLoadedEventEnd,
      load: nav.loadEventEnd,
    };
  });
  if (withWeight) await page.waitForTimeout(2000);
  if (app.name === "streamlit") await stIdle(page);
  await page.close();
  return { ...t, weight: withWeight ? { ...weight, byType: { ...weight.byType } } : undefined };
}

async function firstContent(browser: import("@playwright/test").Browser, app: App, p: Profile, throttle: boolean, n: number) {
  const cold: LoadResult[] = [];
  const warm: LoadResult[] = [];
  for (let i = 0; i < n; i++) {
    const ctx = await browser.newContext(p.options);
    cold.push(await loadOnce(ctx, app, throttle, true));
    warm.push(await loadOnce(ctx, app, throttle, false));
    await ctx.close();
  }
  return {
    cold_first_content_ms: r0(median(cold.map((x) => x.firstContent))),
    cold_runs_ms: cold.map((x) => r0(x.firstContent)),
    warm_first_content_ms: r0(median(warm.map((x) => x.firstContent))),
    warm_runs_ms: warm.map((x) => r0(x.firstContent)),
    cold_dom_content_loaded_ms: r0(median(cold.map((x) => x.domContentLoaded))),
    cold_load_event_ms: r0(median(cold.map((x) => x.load))),
    weight_kb: Math.round(median(cold.map((x) => x.weight!.total)) / 102.4) / 10,
    weight_by_type_kb: Object.fromEntries(
      Object.entries(cold[0].weight!.byType).map(([k, v]) => [k, Math.round(v / 102.4) / 10]),
    ),
    requests: cold[0].weight!.requests,
    ws_frames: cold[0].weight!.wsFrames,
  };
}

// ------------------------------------------------------------------ taps
async function tap(page: Page, loc: ReturnType<Page["locator"]>, mobile: boolean) {
  if (mobile) await loc.tap();
  else await loc.click();
}

/** The players named in the cards and the lineup table, in page order, distinct (each tap opens a player not seen yet). */
async function names(page: Page, app: App): Promise<{ name: string; locator: (p: Page) => ReturnType<Page["locator"]> }[]> {
  const seen = new Set<string>();
  const out: { name: string; locator: (p: Page) => ReturnType<Page["locator"]> }[] = [];
  const scope = app.name === "web" ? '[data-testid="decision-card"] a, [data-testid="lineup"] a' : '[data-testid="stMarkdownContainer"] a[href^="Player?"]';
  for (const text of await page.locator(scope).allTextContents()) {
    const n = text.trim();
    if (n && !seen.has(n)) {
      seen.add(n);
      out.push({ name: n, locator: (p) => p.locator(scope).filter({ hasText: n }).first() });
    }
  }
  return out;
}

async function webTaps(browser: import("@playwright/test").Browser, p: Profile, n: number, throttle: boolean) {
  const ctx = await browser.newContext(p.options);
  const page = await ctx.newPage();
  await meter(page, throttle);
  await page.goto(web.week());
  await web.cards(page);
  const people = (await names(page, web)).slice(0, n);
  const toCard: number[] = [];
  const back: number[] = [];
  const oneTap = true;
  let sameTab = true;
  for (const who of people) {
    const pagesBefore = ctx.pages().length;
    const t0 = performance.now();
    await tap(page, who.locator(page), p.mobile);
    await web.playerShown(page, who.name);
    toCard.push(performance.now() - t0);
    sameTab &&= ctx.pages().length === pagesBefore && page.url().includes("/player/");
    const t1 = performance.now();
    await tap(page, page.getByTestId("back"), p.mobile);
    await web.cards(page);
    back.push(performance.now() - t1);
  }
  // team switch: alternate 12 ↔ 11 in the picker (the first two are fetched, later ones come from memory)
  const teams: number[] = [];
  for (let i = 0; i < n; i++) {
    const to = i % 2 === 0 ? OTHER_TEAM : TEAM;
    const t0 = performance.now();
    await page.getByTestId("pick-team").selectOption(String(to));
    await page.getByTestId("team-name").filter({ hasText: MEMBERS[to] }).waitFor({ timeout: 60_000 });
    await web.cards(page);
    teams.push(performance.now() - t0);
  }
  await ctx.close();
  return { toCard, back, teams, oneTap, sameTab, popups: 0 };
}

async function streamlitTaps(browser: import("@playwright/test").Browser, p: Profile, n: number) {
  const ctx = await browser.newContext(p.options);
  const page = await ctx.newPage();
  await page.goto(streamlit.week());
  await streamlit.cards(page);
  await stIdle(page);
  const distinct = await names(page, streamlit); // the cards' names (the lineup table is a canvas: no links to tap in the DOM)
  const people = Array.from({ length: n }, (_, i) => distinct[i % distinct.length]);
  const toCard: number[] = [];
  let oneTap = true;
  let sameTab = true;
  let tapsNeeded = 0;
  for (const who of people) {
    const loc = who.locator(page);
    await loc.scrollIntoViewIfNeeded();
    let popup: Page | null = null;
    let t0 = 0;
    for (let k = 1; k <= 3 && !popup; k++) {
      const wait = ctx.waitForEvent("page", { timeout: 2500 }).catch(() => null);
      t0 = performance.now();
      await tap(page, loc, p.mobile);
      popup = await wait;
      if (popup) {
        tapsNeeded = Math.max(tapsNeeded, k);
        if (k > 1) oneTap = false;
      }
    }
    if (!popup) {
      // the tap navigated in place (not expected)
      sameTab = sameTab && true;
      await streamlit.playerShown(page, who.name);
      toCard.push(performance.now() - t0);
      await page.goBack();
      await streamlit.cards(page);
      continue;
    }
    sameTab = false;
    await streamlit.playerShown(popup, who.name);
    // from the tap that opened it (an extra dead tap before it is counted in tapsNeeded, not in the time)
    toCard.push(performance.now() - t0);
    await popup.close();
  }
  log("streamlit name taps", JSON.stringify(toCard.map(r0)));
  // back to My Week: Streamlit's cards open a NEW tab, so "back" is the old tab; inside one tab the way back is the
  // sidebar's Home link (the browser's Back is not reliable: one page hop adds three history entries). Timed from
  // the Home tap: Home → (sidebar) Player, then (sidebar) Home → the cards.
  const back: number[] = [];
  const nav = (label: string) => page.locator('[data-testid="stSidebarNavLink"]').filter({ hasText: new RegExp(`^${label}$`) }).first();
  const openSidebar = async () => {
    if (p.mobile && (await page.locator('[data-testid="stExpandSidebarButton"]').isVisible())) {
      await tap(page, page.locator('[data-testid="stExpandSidebarButton"]'), true);
      await page.waitForTimeout(400); // the slide-in
    }
  };
  let historyPerHop = 0;
  let browserBackWorks = true;
  for (let i = 0; i < n; i++) {
    await openSidebar();
    const h0 = await page.evaluate(() => history.length);
    await tap(page, nav("Player"), p.mobile);
    await page.getByText("Pick a player above").first().waitFor({ timeout: 60_000 });
    await stIdle(page);
    if (i === 0) {
      historyPerHop = (await page.evaluate(() => history.length)) - h0;
      await page.goBack();
      browserBackWorks = await page
        .getByText(/apart, (a coin flip|a lean|clear)/)
        .first()
        .waitFor({ timeout: 8000 })
        .then(() => true)
        .catch(() => false);
      if (!browserBackWorks) await page.goto(streamlit.week()).then(() => streamlit.cards(page)).then(() => stIdle(page));
      {
        await stIdle(page);
        await openSidebar();
        await tap(page, nav("Player"), p.mobile);
        await page.getByText("Pick a player above").first().waitFor({ timeout: 60_000 });
        await stIdle(page);
      }
    }
    await openSidebar();
    const t1 = performance.now();
    await tap(page, nav("Home"), p.mobile);
    await streamlit.cards(page);
    back.push(performance.now() - t1);
    await stIdle(page);
  }
  log("streamlit back", JSON.stringify(back.map(r0)), "history entries per hop", historyPerHop, "browser back works", browserBackWorks);
  // team switch: the sidebar's "Team perspective" selectbox, 12 ↔ 11
  const teams: number[] = [];
  const members = MEMBERS;
  for (let i = 0; i < n; i++) {
    const to = i % 2 === 0 ? OTHER_TEAM : TEAM;
    await openSidebar();
    const box = page.locator('[data-testid="stSidebar"] [data-testid="stSelectbox"]').nth(1);
    await box.locator('input[role="combobox"]').click();
    await box.locator('input[role="combobox"]').fill(members[to]);
    const option = page.locator('[role="option"]').filter({ hasText: members[to] }).first();
    const t0 = performance.now();
    await option.click();
    await page.locator('[data-testid="stMain"] [data-testid="stMarkdownContainer"] strong', { hasText: members[to] }).first().waitFor({ timeout: 60_000 });
    await streamlit.cards(page);
    await stIdle(page);
    teams.push(performance.now() - t0);
    if (p.mobile && (await page.locator('[data-testid="stSidebarCollapseButton"]').isVisible())) {
      await page.locator('[data-testid="stSidebarCollapseButton"]').click().catch(() => {});
    }
  }
  await ctx.close();
  return { toCard, back, teams, oneTap, sameTab, tapsNeeded, historyPerHop, browserBackWorks };
}

/** Streamlit's name tap on a throttled network = a new tab loading the Player page with a warm cache. */
async function streamlitNewTabThrottled(browser: import("@playwright/test").Browser, p: Profile, n: number) {
  const ctx = await browser.newContext(p.options);
  const first = await ctx.newPage();
  await first.goto(streamlit.week());
  await streamlit.cards(first);
  const people = (await names(first, streamlit)).slice(0, n);
  const out: number[] = [];
  for (const who of people) {
    const href = await who.locator(first).getAttribute("href");
    const tab = await ctx.newPage();
    await meter(tab, true);
    const t0 = performance.now();
    await tab.goto(`${ST}/${href}`, { waitUntil: "commit" });
    await streamlit.playerShown(tab, who.name);
    out.push(performance.now() - t0);
    await tab.close();
  }
  await ctx.close();
  return out;
}

async function webTapsThrottledToCard(browser: import("@playwright/test").Browser, p: Profile, n: number) {
  const r = await webTaps(browser, p, n, true);
  return r.toCard;
}

const stat = (xs: number[]) => ({ median_ms: r0(median(xs)), max_ms: r0(Math.max(...xs)), n: xs.length, runs_ms: xs.map(r0) });

test("measure web vs streamlit", async ({ browser }) => {
  const results: Record<string, unknown> = {
    when: new Date().toISOString(),
    web: WEB,
    streamlit: ST,
    streamlit_raw: ST_RAW ?? null,
    loads: LOADS,
    taps: TAPS,
    cpus: cpus().length,
    loadavg_start: loadavg().map((x) => Math.round(x * 10) / 10),
  };
  // warm both servers' query caches (one pass of everything measured)
  log("start", JSON.stringify({ WEB, ST, LOADS, TAPS }));
  for (const app of [web, streamlit]) {
    log("warming", app.name);
    const ctx = await browser.newContext(PROFILES[1].options);
    const page = await ctx.newPage();
    await page.goto(app.week());
    await app.cards(page);
    await page.goto(app.week(OTHER_TEAM));
    await app.cards(page);
    await page.goto(app.week());
    await app.cards(page);
    for (const who of (await names(page, app)).slice(0, TAPS)) {
      const href = await who.locator(page).getAttribute("href");
      const tab = await ctx.newPage();
      await tab.goto(app.name === "web" ? `${WEB}${href}` : `${ST}/${href}`);
      await app.playerShown(tab, who.name);
      await tab.close();
    }
    await ctx.close();
  }
  log("warmed");
  for (const p of PROFILES) {
    const row: Record<string, unknown> = {};
    for (const app of [web, streamlit]) {
      row[`${app.name}_load`] = await firstContent(browser, app, p, false, LOADS);
      log(p.name, app.name, "loads", JSON.stringify(row[`${app.name}_load`]));
    }
    if (streamlitRaw) {
      row.streamlit_raw_load = await firstContent(browser, streamlitRaw, p, false, LOADS);
      log(p.name, "streamlit raw loads", JSON.stringify(row.streamlit_raw_load));
    }
    const wt = await webTaps(browser, p, TAPS, false);
    log(p.name, "web taps", JSON.stringify(wt));
    const st = await streamlitTaps(browser, p, TAPS);
    log(p.name, "streamlit taps", JSON.stringify(st));
    row.web_taps = { name_to_card: stat(wt.toCard), back_to_week: stat(wt.back), change_team: stat(wt.teams), one_tap: wt.oneTap, same_tab: wt.sameTab };
    row.streamlit_taps = {
      name_to_card: stat(st.toCard),
      back_to_week: stat(st.back),
      change_team: stat(st.teams),
      one_tap: st.oneTap,
      same_tab: st.sameTab,
      taps_needed: st.tapsNeeded,
      history_entries_per_page_hop: st.historyPerHop,
      browser_back_returns_to_my_week: st.browserBackWorks,
    };
    results[p.name] = row;
  }
  log("throttled");
  // throttled phone network, phone profile only
  const phone = PROFILES[0];
  const n = Math.max(3, Math.min(LOADS, 3));
  results.phone_slow4g = {
    web_load: await firstContent(browser, web, phone, true, n),
    streamlit_load: await firstContent(browser, streamlit, phone, true, n),
    streamlit_raw_load: streamlitRaw ? await firstContent(browser, streamlitRaw, phone, true, n) : null,
    web_name_to_card: stat(await webTapsThrottledToCard(browser, phone, 5)),
    streamlit_name_to_card_new_tab: stat(await streamlitNewTabThrottled(browser, phone, 5)),
  };
  results.loadavg_end = loadavg().map((x) => Math.round(x * 10) / 10);
  writeFileSync(join(OUT, "measure.json"), JSON.stringify(results, null, 2));
  writeFileSync(join(OUT, "measure.md"), table(results));
  console.log(table(results));

  // Streamlit twins of the web screenshots
  for (const prof of PROFILES) {
    const ctx = await browser.newContext(prof.options);
    const page = await ctx.newPage();
    await page.goto(streamlit.week());
    await streamlit.cards(page);
    await stIdle(page);
    await page.screenshot({ path: join(SHOTS, `st_week_dyn12_${prof.name}_fold.png`) });
    await page.screenshot({ path: join(SHOTS, `st_week_dyn12_${prof.name}_full.png`), fullPage: true });
    await page.goto(streamlit.player("00-0036963"));
    await streamlit.playerShown(page, "Amon-Ra St. Brown");
    await stIdle(page);
    await page.screenshot({ path: join(SHOTS, `st_player_stbrown_${prof.name}_fold.png`) });
    await page.screenshot({ path: join(SHOTS, `st_player_stbrown_${prof.name}_full.png`), fullPage: true });
    await ctx.close();
  }
});

/* eslint-disable @typescript-eslint/no-explicit-any -- a report over the JSON written above */
function table(r: Record<string, any>): string {
  const lines: string[] = [];
  lines.push("| Measure | Phone · web | Phone · Streamlit | Desktop · web | Desktop · Streamlit |", "|---|---|---|---|---|");
  const ph = r.phone,
    dt = r.desktop;
  const row = (label: string, f: (x: any, app: "web" | "streamlit") => string) =>
    lines.push(`| ${label} | ${f(ph, "web")} | ${f(ph, "streamlit")} | ${f(dt, "web")} | ${f(dt, "streamlit")} |`);
  row("First content, first visit (median ms)", (x, a) => `${x[`${a}_load`].cold_first_content_ms}`);
  row("First content, repeat visit (median ms)", (x, a) => `${x[`${a}_load`].warm_first_content_ms}`);
  row("Page weight, first visit (KB over the wire)", (x, a) => `${x[`${a}_load`].weight_kb}`);
  if (ph.streamlit_raw_load) {
    row("…Streamlit as `streamlit run` sends it, uncompressed: first content / KB", (x, a) =>
      a === "web" ? "" : `${x.streamlit_raw_load.cold_first_content_ms} / ${x.streamlit_raw_load.weight_kb}`,
    );
  }
  row("Name → player card (median / max ms)", (x, a) => `${x[`${a}_taps`].name_to_card.median_ms} / ${x[`${a}_taps`].name_to_card.max_ms}`);
  row("Back to My Week (median / max ms)", (x, a) => `${x[`${a}_taps`].back_to_week.median_ms} / ${x[`${a}_taps`].back_to_week.max_ms}`);
  row("Change team (median / max ms)", (x, a) => `${x[`${a}_taps`].change_team.median_ms} / ${x[`${a}_taps`].change_team.max_ms}`);
  row("A name opens on the first tap", (x, a) => (x[`${a}_taps`].one_tap ? "yes" : `no (${x[`${a}_taps`].taps_needed} taps)`));
  row("…and stays in the same tab / session", (x, a) => (x[`${a}_taps`].same_tab ? "yes" : "no: new tab, new session"));
  const s = r.phone_slow4g;
  lines.push(
    "",
    `Machine: ${r.cpus} CPUs, load average ${r.loadavg_start.join(" / ")} at the start, ${r.loadavg_end.join(" / ")} at the end (other work was running). ${r.loads} loads, ${r.taps} taps each.`,
    "",
    "Phone on a slow 4G network (150 ms round trip, 1.6 Mbit/s):",
    "",
    "| Measure | web | Streamlit |",
    "|---|---|---|",
    `| First content, first visit (median ms) | ${s.web_load.cold_first_content_ms} | ${s.streamlit_load.cold_first_content_ms} |`,
    `| First content, repeat visit (median ms) | ${s.web_load.warm_first_content_ms} | ${s.streamlit_load.warm_first_content_ms} |`,
    `| Name → player card (median / max ms) | ${s.web_name_to_card.median_ms} / ${s.web_name_to_card.max_ms} | ${s.streamlit_name_to_card_new_tab.median_ms} / ${s.streamlit_name_to_card_new_tab.max_ms} (new tab) |`,
  );
  if (s.streamlit_raw_load) {
    lines.push(`| First content, first visit, Streamlit uncompressed (median ms) | | ${s.streamlit_raw_load.cold_first_content_ms} |`);
  }
  return lines.join("\n") + "\n";
}
/* eslint-enable @typescript-eslint/no-explicit-any */
