<script lang="ts">
  import { onMount } from "svelte";
  import { ApiError, clearCache, get, paths, Unauthorized, type League, type Status, type UserLeagues } from "./lib/api";
  import { leagueOptions, type LeagueOption } from "./lib/leagues";
  import { leagueNames } from "./lib/names.svelte";
  import { prefs } from "./lib/prefs";
  import { interceptLinks, route, setParams } from "./lib/router.svelte";
  import Coming from "./components/Coming.svelte";
  import Login from "./components/Login.svelte";
  import TopBar, { sectionOf } from "./components/TopBar.svelte";
  import AboutPage from "./routes/About.svelte";
  import LeaguesPage from "./routes/Leagues.svelte";
  import MyWeekPage from "./routes/MyWeek.svelte";
  import PlayerPage from "./routes/Player.svelte";
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

{#if phase === "login"}
  <Login onok={signedIn} />
{:else if phase === "error"}
  <div class="mx-auto max-w-xl p-4">
    <div class="ll-error">
      Cannot reach League Lab right now ({failure}). Try again in a minute.
      <button class="mt-3 block rounded-md bg-accent px-4 py-2 font-semibold text-on-accent" onclick={signedIn}>Try again</button>
    </div>
  </div>
{:else if phase === "loading" && !league}
  <div class="mx-auto max-w-xl p-4"><div class="ll-skel h-40" aria-label="Loading"></div></div>
{:else if r.name === "leagues" || !league}
  <LeaguesPage {mine} current={league} onuser={signedInUser} onauth={needLogin} />
{:else if r.name === "player" && r.gsis}
  <PlayerPage gsis={r.gsis} {league} {team} onauth={needLogin} />
{:else}
  <!-- the league's screens: one bar (picker + tabs), then the screen -->
  <TopBar {options} {league} {team} onauth={needLogin} />
  <div class="ll-under-bar mx-auto max-w-6xl px-4 pt-4" data-section={sectionOf(r.name)}>
    {#if r.name === "ros"}
      <RosPage {options} {league} {team} onauth={needLogin} />
    {:else if r.name === "about"}
      <AboutPage {options} {league} {team} onauth={needLogin} />
    {:else if r.name === "waivers"}
      <Coming title="Waivers" what="Who to claim this week, who to drop for him, and what he adds to your lineup now and over the next four weeks." />
    {:else if r.name === "trades"}
      <Coming title="Trades" what="Build a trade and see what it does to both lineups, this week and for the rest of the season." />
    {:else if r.name === "team"}
      <Coming title="Your team" what="Where your roster ranks in the league, slot by slot, and how it holds up over the season." />
    {:else if r.name === "league"}
      <Coming title="The league" what="Standings, the record against everyone, luck, the managers and the latest moves." />
    {:else if r.name === "trends" || r.name === "matchups" || r.name === "players" || r.name === "receivers" || r.name === "compare"}
      <Coming title={r.name[0].toUpperCase() + r.name.slice(1)} what="On its way in this release." />
    {:else}
      <MyWeekPage {options} {league} {team} {mine} {status} onauth={needLogin} />
    {/if}
  </div>
{/if}
