<script lang="ts">
  import { onMount } from "svelte";
  import { clearCache, get, paths, Unauthorized, type League, type Status } from "./lib/api";
  import { prefs } from "./lib/prefs";
  import { interceptLinks, route, setParams } from "./lib/router.svelte";
  import Login from "./components/Login.svelte";
  import MyWeekPage from "./routes/MyWeek.svelte";
  import PlayerPage from "./routes/Player.svelte";

  let phase = $state<"loading" | "login" | "ready" | "error">("loading");
  let leagues = $state<League[]>([]);
  let status = $state<Status | null>(null);
  let failure = $state("");

  const r = $derived(route.current);

  // league: the URL's (a shared link), else the one picked on this phone, else the reference league.
  // Before the league list arrives the URL / remembered value is used as is, so the page's data can load
  // in parallel with the list.
  const league = $derived.by(() => {
    const ids = leagues.map((l) => l.league_id);
    const candidates = [r.params.get("league"), prefs.league()].filter((x): x is string => !!x);
    if (!ids.length) return candidates[0] ?? null;
    return candidates.find((c) => ids.includes(c)) ?? ids[0];
  });
  // team: the URL's (it belongs to the URL's league), else the one picked in this league on this phone.
  const team = $derived.by(() => {
    if (!league) return null;
    const t = r.params.get("team");
    const urlLeague = r.params.get("league");
    if (t && /^\d+$/.test(t) && (!urlLeague || urlLeague === league)) return Number(t);
    return prefs.team(league);
  });

  // remember the pick and keep the URL shareable (replace: no extra Back step)
  $effect(() => {
    if (phase !== "ready" || !league) return;
    prefs.setLeague(league);
    if (team !== null) prefs.setTeam(league, team);
    const want = { league, team: team === null ? null : String(team) };
    if (r.params.get("league") !== want.league || r.params.get("team") !== want.team) setParams(want);
  });

  async function boot() {
    try {
      leagues = await get<League[]>(paths.leagues());
      phase = "ready";
      get<Status>(paths.status())
        .then((s) => (status = s))
        .catch(() => {});
    } catch (e) {
      if (e instanceof Unauthorized) phase = "login";
      else {
        phase = "error";
        failure = e instanceof Error ? e.message : String(e);
      }
    }
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
  {:else if r.name === "player" && r.gsis}
    <PlayerPage gsis={r.gsis} {league} {team} onauth={needLogin} />
  {:else}
    <MyWeekPage {leagues} {league} {team} {status} onauth={needLogin} />
  {/if}
</div>
