<script lang="ts">
  import { onMount } from "svelte";
  import { ApiError, clearCache, get, paths, Unauthorized, type League, type Status, type UserLeagues } from "./lib/api";
  import { leagueOptions, type LeagueOption } from "./lib/leagues";
  import { leagueNames } from "./lib/names.svelte";
  import { prefs } from "./lib/prefs";
  import { interceptLinks, route, setParams } from "./lib/router.svelte";
  import Login from "./components/Login.svelte";
  import LeaguesPage from "./routes/Leagues.svelte";
  import MyWeekPage from "./routes/MyWeek.svelte";
  import PlayerPage from "./routes/Player.svelte";
  import RecordPage from "./routes/Record.svelte";
  import RosPage from "./routes/Ros.svelte";

  let phase = $state<"loading" | "login" | "ready" | "error">("loading");
  let house = $state<League[]>([]);
  // the user's leagues (sign in with a Sleeper username): remembered on this phone, refreshed in the background
  let mine = $state<UserLeagues | null>(prefs.userLeagues());
  let status = $state<Status | null>(null);
  let failure = $state("");

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
    if (phase !== "ready" || !league || r.name === "leagues" || r.name === "player") return;
    prefs.setLeague(league);
    if (team !== null) prefs.setTeam(league, team);
    const want = { league, team: team === null ? null : String(team) };
    if (r.params.get("league") !== want.league || r.params.get("team") !== want.team) setParams(want);
  });

  async function boot() {
    try {
      house = await get<League[]>(paths.leagues());
      phase = "ready";
      get<Status>(paths.status())
        .then((s) => (status = s))
        .catch(() => {});
      refreshMine();
    } catch (e) {
      if (e instanceof Unauthorized) phase = "login";
      else {
        phase = "error";
        failure = e instanceof Error ? e.message : String(e);
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
        if (e instanceof Unauthorized) phase = "login";
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
    phase = "login";
  }

  function signedIn() {
    clearCache();
    phase = "loading";
    boot();
  }

  onMount(() => {
    boot();
    return interceptLinks(document.body);
  });
</script>

<div class="mx-auto max-w-xl">
  {#if phase === "login"}
    <Login onok={signedIn} />
  {:else if phase === "error"}
    <div class="m-4 rounded-2xl border border-red-200 p-4 text-[15px] text-red-800 dark:border-red-900 dark:text-red-300">
      Cannot reach League Lab right now ({failure}). Try again in a minute.
      <button class="mt-3 block rounded-xl bg-green-700 px-4 py-2 font-semibold text-white" onclick={signedIn}>Try again</button>
    </div>
  {:else if phase === "loading" && !league}
    <div class="m-4 h-40 animate-pulse rounded-2xl bg-zinc-100 dark:bg-zinc-900" aria-label="Loading"></div>
  {:else if r.name === "leagues" || !league}
    <LeaguesPage {mine} current={league} onuser={signedInUser} onauth={needLogin} />
  {:else if r.name === "player" && r.gsis}
    <PlayerPage gsis={r.gsis} {league} {team} onauth={needLogin} />
  {:else if r.name === "ros"}
    <RosPage {options} {league} {team} onauth={needLogin} />
  {:else if r.name === "record"}
    <RecordPage {options} {league} {team} onauth={needLogin} />
  {:else}
    <MyWeekPage {options} {league} {team} {mine} {status} onauth={needLogin} />
  {/if}
</div>
