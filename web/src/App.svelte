<script lang="ts">
  import { APP_NAME } from "./lib/brand";
  import { onMount } from "svelte";
  import { ApiError, clearCache, forget, get, paths, Unauthorized, type League, type Status, type UserLeagues } from "./lib/api";
  import { leagueOptions, type LeagueOption } from "./lib/leagues";
  import { leagueNames } from "./lib/names.svelte";
  import { prefs } from "./lib/prefs";
  import { interceptLinks, navigate, route, setParams } from "./lib/router.svelte";
  import Login from "./components/Login.svelte";
  import ErrorCard from "./components/ErrorCard.svelte"; // ---- IH-1
  import { failureOf, type Failure } from "./lib/remote.svelte"; // ---- IH-1
  import PlayerPane from "./components/PlayerPane.svelte";
  import { withContext } from "./lib/md";
  import { platformOf } from "./lib/providers"; // PO 2026-10-05: Yahoo's attribution line under a Yahoo league's screens
  import TopBar, { sectionOf } from "./components/TopBar.svelte";
  import LeaguesPage from "./routes/Leagues.svelte";
  import MyWeekPage from "./routes/MyWeek.svelte";
  import PlayerPage from "./routes/Player.svelte";
  import RosPage from "./routes/Ros.svelte";
  // ---- IK-4: the account (sign in by email, the saved leagues) loads on first use, like About
  let accountPage: ReturnType<typeof loadAccountPage> | null = null;
  const loadAccountPage = () => import("./routes/Account.svelte");
  const accountChunk = () => (accountPage ??= loadAccountPage());
  // ---- G4 decisions: the four screens, each loaded on first use (src/lib/decisionPages.ts)
  import { decisionPage, isDecision } from "./lib/decisionPages";
  import { countView } from "./lib/usage"; // ---- U-1: usage tracking (one count per screen view)
  import { pause as gaPause, screenView, trackLogin } from "./lib/analytics"; // ---- INF-1: Google Analytics
  import { INVITE_WORDS, isRef, NEEDS_LEAGUE, REF_DEFAULT, refLabel } from "./lib/refleague"; // ---- IM-3: no league
  // the research screens and About load on first use (their own chunks): My Week's first screen stays small
  const LAZY = {
    trends: () => import("./routes/Trends.svelte"),
    matchups: () => import("./routes/Matchups.svelte"),
    players: () => import("./routes/Players.svelte"),
    receivers: () => import("./routes/Receivers.svelte"),
    compare: () => import("./routes/Compare.svelte"),
    about: () => import("./routes/About.svelte"),
    watchlist: () => import("./routes/Watchlist.svelte"), // ---- IL-5: the watchlist, in the league frame (the drawer)
    dfs: () => import("./routes/Dfs.svelte"), // ---- IM-5: DFS (in the frame with a league; alone without one, below)
  } as const;
  type LazyName = keyof typeof LAZY;
  const isLazy = (n: string): n is LazyName => n in LAZY;
  // ---- II-2 (Wave I-I): one promise per screen — a new import() promise on every route change (the drawer's
  // `?pane=`, a filter) re-mounted the screen and lost its state (a "Show all", the pick, the focused name)
  // eslint-disable-next-line svelte/prefer-svelte-reactivity -- a plain cache, never observed
  const lazyLoaded = new Map<LazyName, ReturnType<(typeof LAZY)[LazyName]>>();
  const lazy = (n: LazyName) => lazyLoaded.get(n) ?? lazyLoaded.set(n, LAZY[n]()).get(n)!;
  // ---- end II-2

  let phase = $state<"loading" | "login" | "ready" | "error">("loading");
  let house = $state<League[]>([]);
  // the user's leagues (sign in with a Sleeper username): remembered on this phone, refreshed in the background
  let mine = $state<UserLeagues | null>(prefs.userLeagues());
  let status = $state<Status | null>(null);
  let failure = $state<Failure | null>(null); // ---- IH-1: the boot's failure as a kind (the API down: a card, Try again)
  // ---- IH-1: a 401 after this browser was signed in (the cookie expired, the password changed) says so on the
  // password screen; a first visit sees the plain screen. "Signed in before" = the app was on screen in this tab, or
  // a league was picked on this browser (only possible once signed in).
  const SIGNED_OUT = "Signed out — sign in again.";
  let loginNotice = $state<string | null>(null);
  function toLogin() {
    loginNotice = phase === "ready" || prefs.league() !== null ? SIGNED_OUT : null;
    phase = "login";
  }
  // the status line (the stale banner, the footer) is read again when the app comes back to the screen after 10
  // minutes away, and every 15 minutes while it stays on screen: a phone or a desktop tab that kept the app open
  // overnight must not show yesterday's "fresh"
  let statusAt = 0;
  function loadStatus(force = false) {
    if (!force && Date.now() - statusAt < 10 * 60_000) return;
    statusAt = Date.now();
    if (force) forget(paths.status());
    get<Status>(paths.status())
      .then((s) => (status = s))
      .catch(() => {});
  }
  // ---- end IH-1

  const r = $derived(route.current);

  // ---- IN-5 (Wave I-N): the boundaries below (a render error shows ErrorCard, never a blank screen) start again when
  // the screen changes (another tab, another player): a boundary that failed leaves its reset here
  const resets: Record<"app" | "screen", (() => void) | null> = { app: null, screen: null };
  function crashed(e: unknown, reset: () => void, where: "app" | "screen") {
    console.error(e);
    resets[where] = reset;
  }
  $effect(() => {
    void `${r.name}|${r.gsis ?? ""}`;
    for (const k of ["app", "screen"] as const) {
      const f = resets[k];
      resets[k] = null;
      f?.();
    }
  });
  // ---- end IN-5

  // league: the URL's (a shared link: ANY Sleeper league, the API serves it on demand), else the one picked on this
  // phone. None → the sign-in screen (a Sleeper username → the league picker).
  const league = $derived(r.params.get("league") || prefs.league() || null);
  const options = $derived<LeagueOption[]>(leagueOptions(mine, house, league, leagueNames));
  // team: the URL's (it belongs to the URL's league), else the one picked in this league on this phone, else the
  // user's own team in that league (pre-selected from the username's league list).
  const team = $derived.by(() => {
    if (!league || isRef(league)) return null; // ---- IM-3: a reference key has no teams
    const t = r.params.get("team");
    const urlLeague = r.params.get("league");
    if (t && /^\d+$/.test(t) && (!urlLeague || urlLeague === league)) return Number(t);
    return prefs.team(league) ?? mine?.leagues.find((l) => l.league_id === league)?.roster_id ?? null;
  });

  // ---- the PO's merge (IM-3 + IM-5): /dfs with no league at all → the same screen on the reference league
  $effect(() => {
    if (phase === "ready" && r.name === "dfs" && !league) setParams({ league: REF_DEFAULT });
  });

  // remember the pick and keep the URL shareable (replace: no extra Back step)
  $effect(() => {
    if (phase !== "ready" || !league || r.name === "leagues" || r.name === "player" || r.name === "account") return; // ---- IK-4: account
    if (!isRef(league)) {
      // ---- IM-3: a reference key (`ref:half`) is never a remembered league: it lives in the URL only
      prefs.setLeague(league);
      if (team !== null) prefs.setTeam(league, team);
    }
    const want = { league, team: team === null ? null : String(team) };
    if (r.params.get("league") !== want.league || r.params.get("team") !== want.team) setParams(want);
  });

  // ---- U-1: count the screen on screen (route, league, team) once signed in; never blocks rendering (lib/usage.ts)
  $effect(() => void (phase === "ready" && countView(league ? r.name : "leagues", league, team)));
  // ---- INF-1: Google Analytics beside it (lib/analytics.ts: page_view, screen_view, ids only); silent on the sign-in screen
  $effect(() => {
    gaPause(phase === "login");
    if (phase === "ready") screenView(league ? r.name : "leagues", league, team);
  });

  // ---- II-3: /receivers is the Stats screen's WR / TE preset now (old links and bookmarks land there, league and team
  // kept); the receivers' role cards stay at /receivers?view=cards
  $effect(() => {
    if (r.name !== "receivers" || r.params.get("view") === "cards") return;
    // eslint-disable-next-line svelte/prefer-svelte-reactivity -- a scratch copy for the redirect, never observed
    const qs = new URLSearchParams(r.params);
    qs.set("position", "WRTE");
    for (const k of ["limit", "context", "weeks", "players"]) qs.delete(k);
    navigate(`/players?${qs.toString()}`, { replace: true });
  });

  async function boot() {
    try {
      house = await get<League[]>(paths.leagues());
      phase = "ready";
      loadStatus(true); // ---- IH-1
      refreshMine();
    } catch (e) {
      if (e instanceof Unauthorized) toLogin(); // ---- IH-1
      else {
        phase = "error";
        failure = failureOf(e); // ---- IH-1
      }
    }
  }

  /** Re-read the remembered user's leagues (a new league this season, a renamed team). Quiet on failure. */
  function refreshMine() {
    const u = prefs.user();
    if (!u) return;
    get<UserLeagues>(paths.userLeagues(u))
      .then((v) => {
        mine = v;
        prefs.setUserLeagues(v);
      })
      .catch((e) => {
        if (e instanceof Unauthorized) toLogin(); // ---- IH-1
        else if (e instanceof ApiError && e.status === 404) {
          prefs.forgetUser();
          mine = null;
        }
      });
  }

  function signedInUser(v: UserLeagues | null) {
    mine = v;
  }

  function needLogin() {
    toLogin(); // ---- IH-1: "Signed out — sign in again" when the cookie expired mid-session
  }

  function signedIn() {
    trackLogin(); // ---- INF-1: GA `login` (the password was accepted; nothing about it is sent)
    clearCache();
    phase = "loading";
    boot();
  }

  onMount(() => {
    boot();
    // ---- IH-1: back on screen after a while → the status line again (the stale banner)
    const onVisible = () => document.visibilityState === "visible" && phase === "ready" && loadStatus();
    document.addEventListener("visibilitychange", onVisible);
    const every = setInterval(onVisible, 15 * 60_000); // a tab that stays on screen all day (a desktop)
    const stop = interceptLinks(document.body);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      clearInterval(every);
      stop();
    };
  });
</script>

<!-- ---- IN-5: a render error anywhere shows ErrorCard ("This screen hit a problem" + Reload), never a blank page; the
     screens in the league frame have their own boundary below (the bar stays) -->
<svelte:boundary onerror={(e, reset) => crashed(e, reset, "app")}>
{#snippet failed()}<div class="mx-auto max-w-xl p-4" data-testid="app-crashed"><ErrorCard crashed={r.name} /></div>{/snippet}
<!-- ---- end IN-5 -->
{#if phase === "login"}
  <Login onok={signedIn} notice={loginNotice} />
{:else if phase === "error"}
  <!-- ---- IH-1: the API down at the first screen: a plain card with Try again (ErrorCard) -->
  <div class="mx-auto max-w-xl p-4" data-testid="boot-error">
    <ErrorCard failure={failure ?? { kind: "down", status: null, words: `Cannot reach ${APP_NAME} right now. Try again in a minute.` }} onretry={signedIn} />
  </div>
{:else if phase === "loading" && !league}
  <div class="mx-auto max-w-xl p-4"><div class="ll-skel h-40" aria-label="Loading"></div></div>
{:else if r.name === "account"}
  <!-- ---- IK-4: the account, outside the league frame like the setup screen -->
  {#await accountChunk()}
    <div class="mx-auto max-w-xl p-4"><div class="ll-skel h-40" aria-label="Loading"></div></div>
  {:then m}
    <m.default current={league} onauth={needLogin} />
  {/await}
<!-- ---- IM-5 + IM-3 (the PO's merge): DFS needs no league — without one it opens in the frame on the reference
     league (Half PPR), so the tabs stay and a player's name opens his card; the effect below writes the URL -->
{:else if r.name === "dfs" && !league}
  <div class="mx-auto max-w-xl p-4"><div class="ll-skel h-40" aria-label="Loading"></div></div>
<!-- ---- end IM-5 -->
{:else if r.name === "leagues" || !league}
  <LeaguesPage {mine} current={league} onuser={signedInUser} onauth={needLogin} />
{:else}
  <!-- the league's screens: one bar (picker + tabs + search), then the screen, the research pane beside it (900 px+) or
       over it (a phone). IB-1: a player's page sits in the same frame (the tab bar stays). -->
  <TopBar {options} {league} {team} onauth={needLogin} />
  <div class="wide:flex wide:items-start">
    <div class="ll-under-bar mx-auto w-full max-w-6xl min-w-0 px-4 pt-4 wide:flex-1" data-section={sectionOf(r.name)}>
      <!-- ---- IN-5: each screen behind a boundary (a render error: ErrorCard, the bar stays; a new screen starts again) -->
      <svelte:boundary onerror={(e, reset) => crashed(e, reset, "screen")}>
      {#snippet failed()}<ErrorCard crashed={r.name} />{/snippet}
      <!-- ---- end IN-5 -->
      {#if isRef(league) && NEEDS_LEAGUE.has(r.name)}
        <!-- ---- IM-3: a screen that needs a league and a team, opened without one: the invitation, never an error -->
        <section class="mx-auto max-w-xl space-y-3 rounded-lg border border-line bg-surface p-5" style="box-shadow:var(--ll-shadow)" data-testid="invite-card">
          <h2 class="text-xl font-bold">{INVITE_WORDS}</h2>
          <p class="leading-snug text-ink-2">
            You are browsing without a league, in {refLabel(league)} scoring. Open your league on Sleeper, MyFantasyLeague, ESPN or Yahoo and this
            screen shows your own team.
          </p>
          <div class="flex flex-wrap gap-2">
            <a href="/leagues" class="inline-flex min-h-11 items-center rounded-md bg-accent px-4 font-semibold text-on-accent" data-testid="invite-open">Open your league</a>
            <a href={withContext("/players", { league, team: null })} class="inline-flex min-h-11 items-center rounded-md border border-line px-4 font-semibold" data-testid="invite-browse"
              >Keep browsing players</a
            >
          </div>
        </section>
      {:else if r.name === "player" && r.gsis}
        <PlayerPage gsis={r.gsis} {league} {team} onauth={needLogin} />
      {:else if r.name === "ros"}
        <RosPage {options} {league} {team} onauth={needLogin} />
      {:else if isLazy(r.name)}
        {#await lazy(r.name)}<!-- II-2: one promise per screen -->
          <div class="space-y-3" aria-label="Loading" data-testid="loading"><div class="ll-skel h-8 w-1/2"></div><div class="ll-skel h-40"></div></div>
        {:then m}
          <m.default {options} {league} {team} onauth={needLogin} />
        {/await}
      {:else if isDecision(r.name)}
        <!-- G4 decisions: Waivers, Trades, Team, League -->
        {#await decisionPage(r.name)}
          <div class="ll-skel h-40" aria-label="Loading"></div>
        {:then Page}
          <Page {options} {league} {team} onauth={needLogin} />
        {/await}
      {:else}
        <MyWeekPage {options} {league} {team} {mine} {status} onauth={needLogin} />
      {/if}
      </svelte:boundary><!-- ---- IN-5 -->
      {#if sectionOf(r.name) === "myteam" && !isRef(league)}
        <!-- IB-1: About the numbers left the tab bar: the overflow menu (⋯) and here, at the foot of My Team -->
        <footer class="mt-6 border-t border-line pt-3 text-sm" data-testid="myteam-foot">
          <a class="ll-link" href={withContext("/about", { league, team })} data-testid="foot-about">About the numbers and our record</a>
        </footer>
      {/if}
      {#if platformOf(league) === "yahoo"}
        <!-- PO 2026-10-05: Yahoo's attribution policy (docs/YAHOO_TERMS.md), under every screen of a Yahoo league -->
        <p class="mt-6 border-t border-line pt-3 text-sm text-ink-3" data-testid="yahoo-attribution">
          Fantasy data provided by <a class="ll-link" href="https://football.fantasysports.yahoo.com/" target="_blank" rel="noopener noreferrer">Yahoo Fantasy</a>
        </p>
      {/if}
    </div>
    <PlayerPane {league} {team} onauth={needLogin} />
  </div>
{/if}
</svelte:boundary><!-- ---- IN-5 -->
