<script lang="ts">
  // The top of My Week, Rest of season and Our record: the league / team picker and the three screens as tabs.
  // Picking rewrites the URL in place (no Back step); a tab is a real link (same tab, one history entry).
  import { get, paths, peek, Unauthorized, type Roster } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import { prefs } from "../lib/prefs";
  import { navigate, route, setParams } from "../lib/router.svelte";
  import Picker, { OTHER } from "./Picker.svelte";

  let {
    options,
    league,
    team,
    onauth,
    rosters = $bindable([]),
  }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void; rosters?: Roster[] } = $props();

  $effect(() => {
    const l = league;
    rosters = peek<Roster[]>(paths.rosters(l)) ?? [];
    get<Roster[]>(paths.rosters(l))
      .then((r) => {
        if (league === l) rosters = r;
      })
      .catch((e) => e instanceof Unauthorized && onauth());
  });

  function pickLeague(l: string) {
    if (l === OTHER) return navigate("/leagues");
    prefs.setLeague(l);
    const t = prefs.team(l) ?? options.find((o) => o.league_id === l)?.roster_id ?? null;
    setParams({ league: l, team: t === null ? null : String(t) }); // other parameters (the position) stay
  }

  function pickTeam(t: number | null) {
    prefs.setTeam(league, t);
    setParams({ league, team: t === null ? null : String(t) });
  }

  const ctx = $derived({ league, team });
  const tabs = $derived([
    { name: "week", label: "My week", href: withContext("/", ctx) },
    { name: "ros", label: "Rest of season", href: withContext("/ros", ctx) },
    { name: "record", label: "Our record", href: withContext("/record", { league }) },
  ]);
</script>

<header class="space-y-2 px-4 pt-[max(0.75rem,env(safe-area-inset-top))] pb-2">
  <Picker leagues={options} {league} {rosters} {team} onleague={pickLeague} onteam={pickTeam} />
  <nav class="flex gap-1 rounded-full bg-zinc-100 p-1 text-[14px] dark:bg-zinc-900" aria-label="Screens" data-testid="tabs">
    {#each tabs as t (t.name)}
      <a
        href={t.href}
        class="flex min-h-9 flex-1 items-center justify-center rounded-full px-2 font-medium whitespace-nowrap {route.current.name === t.name
          ? 'bg-green-700 text-white dark:bg-green-600'
          : 'text-zinc-700 dark:text-zinc-300'}"
        aria-current={route.current.name === t.name ? "page" : undefined}
        data-testid={`tab-${t.name}`}>{t.label}</a
      >
    {/each}
  </nav>
</header>
