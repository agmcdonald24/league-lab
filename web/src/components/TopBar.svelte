<script lang="ts" module>
  import type { RouteName } from "../lib/router.svelte";

  // The app's screens. Top level: My week · Rest of season · Research · Decisions · About. Research and Decisions
  // hold several screens each, shown as a second row of tabs.
  export const RESEARCH: { name: RouteName; label: string }[] = [
    { name: "trends", label: "Trends" },
    { name: "matchups", label: "Matchups" },
    { name: "players", label: "Players" },
    { name: "receivers", label: "Receivers" },
    { name: "compare", label: "Compare" },
  ];
  export const DECISIONS: { name: RouteName; label: string }[] = [
    { name: "waivers", label: "Waivers" },
    { name: "trades", label: "Trades" },
    { name: "team", label: "Team" },
    { name: "league", label: "League" },
  ];
  export type Section = "week" | "ros" | "research" | "decisions" | "about" | null;
  export function sectionOf(name: RouteName): Section {
    if (name === "week" || name === "ros" || name === "about") return name;
    if (RESEARCH.some((r) => r.name === name)) return "research";
    if (DECISIONS.some((r) => r.name === name)) return "decisions";
    return null;
  }
</script>

<script lang="ts">
  // The app's bar: the wordmark, the league / team picker, the screens as tabs. On a phone the five top-level tabs
  // sit in a bar at the bottom (thumb reach, always one tap away); from 900 px they sit in the top bar. Picking a
  // league or team rewrites the URL in place (no Back step); a tab is a real link (same tab, one history entry).
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
  const here = $derived(route.current.name);
  const section = $derived(sectionOf(here));
  const href = (path: string) => withContext(path, ctx);
  // a section's tab opens its first screen
  const tabs = $derived([
    { key: "week", label: "My week", short: "My week", href: href("/") },
    { key: "ros", label: "Rest of season", short: "Season", href: href("/ros") },
    { key: "research", label: "Research", short: "Research", href: href("/trends") },
    { key: "decisions", label: "Decisions", short: "Decisions", href: href("/waivers") },
    { key: "about", label: "About", short: "About", href: href("/about") },
  ]);
  const sub = $derived(section === "research" ? RESEARCH : section === "decisions" ? DECISIONS : []);
</script>

{#snippet icon(key: string)}
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    {#if key === "week"}
      <rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" />
    {:else if key === "ros"}
      <path d="M3 17l6-6 4 4 8-8" /><path d="M15 7h6v6" />
    {:else if key === "research"}
      <circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" />
    {:else if key === "decisions"}
      <path d="M7 7h10M7 12h10M7 17h6" /><rect x="3" y="3" width="18" height="18" rx="2" />
    {:else}
      <circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7.5v.5" />
    {/if}
  </svg>
{/snippet}

<header class="border-b border-line bg-surface pt-[env(safe-area-inset-top)]" data-testid="top-bar">
  <div class="mx-auto flex max-w-6xl items-center gap-3 px-4 py-2 wide:gap-6 wide:py-2.5">
    <a href={href("/")} class="order-1 flex shrink-0 items-center gap-1.5 text-sm font-extrabold tracking-tight uppercase" aria-label="League Lab, my week">
      <span class="grid h-7 w-7 place-items-center rounded-sm bg-accent text-[11px] font-black text-on-accent">LL</span>
      <span class="hidden sm:inline">League Lab</span>
    </a>

    <!-- one nav: the bottom bar on a phone, inline in the top bar from 900 px -->
    <nav
      class="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] wide:static wide:z-auto wide:order-2 wide:gap-1 wide:border-0 wide:bg-transparent wide:p-0"
      aria-label="Screens"
      data-testid="tabs"
    >
      {#each tabs as t (t.key)}
        {@const on = section === t.key}
        <a
          href={t.href}
          class="flex h-[var(--ll-bar-h)] min-w-0 flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold wide:h-9 wide:flex-none wide:flex-row wide:gap-0 wide:rounded-sm wide:px-3 wide:text-sm {on
            ? 'text-accent wide:bg-accent wide:text-on-accent'
            : 'text-ink-3 hover:text-ink wide:text-ink-2'}"
          aria-current={on ? "page" : undefined}
          data-testid={`tab-${t.key}`}
        >
          <span class="wide:hidden">{@render icon(t.key)}</span>
          <span class="truncate wide:hidden">{t.short}</span>
          <span class="hidden wide:inline">{t.label}</span>
        </a>
      {/each}
    </nav>

    <div class="order-3 min-w-0 flex-1 wide:ml-auto wide:w-[24rem] wide:flex-none">
      <Picker leagues={options} {league} {rosters} {team} onleague={pickLeague} onteam={pickTeam} />
    </div>
  </div>
  {#if sub.length}
    <div class="mx-auto max-w-6xl px-4 pb-2">
      <!-- a phone: one row that scrolls inside itself when the labels do not fit (the page never does); the picked one
           is scrolled into view -->
      <nav
        class="-mx-4 flex gap-1 overflow-x-auto px-4 [scrollbar-width:none] wide:mx-0 wide:px-0"
        aria-label={section === "research" ? "Research" : "Decisions"}
        data-testid="subtabs"
        {@attach (el) => el.querySelector('[aria-current="page"]')?.scrollIntoView({ block: "nearest", inline: "center" })}
      >
        {#each sub as s (s.name)}
          <a
            href={href(`/${s.name}`)}
            class="inline-flex min-h-9 shrink-0 items-center rounded-full border px-3 text-sm font-semibold {here === s.name
              ? 'border-accent bg-accent-soft text-ink'
              : 'border-line text-ink-2 hover:text-ink'}"
            aria-current={here === s.name ? "page" : undefined}
            data-testid={`sub-${s.name}`}>{s.label}</a
          >
        {/each}
      </nav>
    </div>
  {/if}
</header>
