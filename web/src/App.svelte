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
  // the research screens and About load on first use (their own chunks): My Week's first screen stays small
  const LAZY = {
    trends: () => import("./routes/Trends.svelte"),
    matchups: () => import("./routes/Matchups.svelte"),
    players: () => import("./routes/Players.svelte"),
    receivers: () => import("./routes/Receivers.svelte"),
    compare: () => import("./routes/Compare.svelte"),
    about: () => import("./routes/About.svelte"),
    watchlist: () => import("./routes/Watchlist.svelte"), // ---- IL-5: the watchlist, in the league frame (the drawer)
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

  // league: the URL's (a shared link: ANY Sleeper league, the API serves it on demand), else the one picked on this
  // phone. None → the sign-in screen (a Sleeper username → the league picker).
  const league = $derived(r.params.get("league") || prefs.league() || null);
  const options = $derived<LeagueOption[]>(leagueOptions(mine, house, league, leagueNames));
  // team: the URL's (it belongs to the URL's league), else the one picked in this league on this phone, else the
  // user's own team in that league (pre-selected from the username's league list).
  const team = $derived.by(() => {
    if (!league) return null;
    const t = r.params.get("team");
    const urlLeague = r.params.get("league");
    if (t && /^\d+$/.test(t) && (!urlLeague || urlLeague === league)) return Number(t);
    return prefs.team(league) ?? mine?.leagues.find((l) => l.league_id === league)?.roster_id ?? null;
  });

  // remember the pick and keep the URL shareable (replace: no extra Back step)
  $effect(() => {
    if (phase !== "ready" || !league || r.name === "leagues" || r.name === "player" || r.name === "account") return; // ---- IK-4: account
    prefs.setLeague(league);
    if (team !== null) prefs.setTeam(league, team);
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
{:else if r.name === "leagues" || !league}
  <LeaguesPage {mine} current={league} onuser={signedInUser} onauth={needLogin} />
{:else}
  <!-- the league's screens: one bar (picker + tabs + search), then the screen, the research pane beside it (900 px+) or
       over it (a phone). IB-1: a player's page sits in the same frame (the tab bar stays). -->
  <TopBar {options} {league} {team} onauth={needLogin} />
  <div class="wide:flex wide:items-start">
    <div class="ll-under-bar mx-auto w-full max-w-6xl min-w-0 px-4 pt-4 wide:flex-1" data-section={sectionOf(r.name)}>
      {#if r.name === "player" && r.gsis}
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
      {#if sectionOf(r.name) === "myteam"}
        <!-- IB-1: About the numbers left the tab bar: the overflow menu (⋯) and here, at the foot of My Team -->
        <footer class="mt-6 border-t border-line pt-3 text-sm" data-testid="myteam-foot">
          <a class="ll-link" href={withContext("/about", { league, team })} data-testid="foot-about">About the numbers and our record</a>
        </footer>
      {/if}
    </div>
    <PlayerPane {league} {team} onauth={needLogin} />
  </div>
{/if}
