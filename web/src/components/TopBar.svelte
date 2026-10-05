<script lang="ts" module>
  import { APP_MARK, APP_NAME } from "../lib/brand";
  import type { RouteName } from "../lib/router.svelte";

  // IB-1 (Wave I-B): the screens grouped by task — four tabs: My Team · Waivers · Trades · Players. Each tab with more
  // than one screen shows them as a second row (sub-tabs). The paths stay (bookmarks, shared links); About the
  // numbers moved to the bar's overflow menu (⋯) and the foot of My Team.
  export type Section = "myteam" | "waivers" | "trades" | "players";
  export const SECTIONS: { key: Section; label: string; screens: { name: RouteName; label: string; path: string }[] }[] = [
    {
      key: "myteam",
      label: "My Team",
      screens: [
        { name: "week", label: "This week", path: "/" },
        { name: "ros", label: "Season", path: "/ros" },
        { name: "team", label: "Team", path: "/team" },
        { name: "league", label: "League", path: "/league" },
      ],
    },
    { key: "waivers", label: "Waivers", screens: [{ name: "waivers", label: "Waivers", path: "/waivers" }] },
    {
      key: "trades",
      label: "Trades",
      screens: [
        { name: "trades", label: "Partners", path: "/trades" },
        { name: "trade-calc", label: "Calculator", path: "/trade-calc" }, // ---- IA-2's calculator
      ],
    },
    {
      key: "players",
      label: "Players",
      // ---- II-3 (the fifth review § 4): the research tabs are Stats · Trends · Matchups · Compare; Receivers is the
      // Stats WR / TE preset (/receivers redirects there; its role cards stay at /receivers?view=cards, lit as Stats)
      screens: [
        { name: "players", label: "Stats", path: "/players" },
        { name: "trends", label: "Trends", path: "/trends" },
        { name: "matchups", label: "Matchups", path: "/matchups" },
        { name: "compare", label: "Compare", path: "/compare" },
      ],
    },
  ];
  export function sectionOf(name: RouteName): Section | null {
    if (name === "receivers") return "players"; // ---- II-3: the role cards sit under Players
    return SECTIONS.find((s) => s.screens.some((x) => x.name === name))?.key ?? null;
  }
  // the player's page and About keep the tab you came from lit (Back goes there)
  let lastSection: Section | null = null;
</script>

<script lang="ts">
  // The app's bar: the wordmark, the four tabs, the search field, the league / team picker, the overflow menu (⋯:
  // About the numbers, other leagues). On a phone the four tabs sit in a bar at the bottom (thumb reach, always one
  // tap away) and the search field opens from the magnifier over the bar; from 900 px the tabs sit in the top bar,
  // and from 1280 px the search field is always open. The screens of the tab on screen are the second row. Picking a
  // league or team rewrites the URL in place (no Back step); a tab is a real link (same tab, one history entry).
  import { get, paths, peek, Unauthorized, type Hit, type Roster } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import { openPane } from "../lib/pane.svelte";
  import { prefs } from "../lib/prefs";
  import { navigate, route, setParams } from "../lib/router.svelte";
  import Picker, { OTHER } from "./Picker.svelte";
  import { account, loadStatus as loadAccount } from "../lib/account.svelte"; // ---- IK-4: the ⋯ menu's Account item

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
  const section = $derived.by(() => {
    const s = sectionOf(here);
    if (s) lastSection = s;
    return s ?? (here === "player" || here === "about" ? lastSection : null);
  });
  const href = (path: string) => withContext(path, ctx);
  // a tab opens its first screen
  const tabs = $derived(SECTIONS.map((s) => ({ key: s.key, label: s.label, href: href(s.screens[0].path) })));
  // the second row: the screens of the tab on screen (not on a player's page or About: no screen of the row is there)
  const sub = $derived(SECTIONS.find((s) => s.key === sectionOf(here) && s.screens.length > 1)?.screens ?? []);

  // ---- the search field: a player's name → the research pane
  let q = $state("");
  let hits = $state<Hit[]>([]);
  let searched = $state("");
  let searchOpen = $state(false); // under 1280 px the field opens from the magnifier
  let input = $state<HTMLInputElement | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;

  function onInput() {
    clearTimeout(timer);
    const text = q.trim();
    if (text.length < 2) {
      hits = [];
      searched = "";
      return;
    }
    const l = league;
    timer = setTimeout(() => {
      get<Hit[]>(paths.search(l, text))
        .then((h) => {
          if (q.trim() !== text) return;
          hits = h;
          searched = text;
        })
        .catch((e) => e instanceof Unauthorized && onauth());
    }, 150);
  }

  function clearSearch() {
    q = "";
    hits = [];
    searched = "";
    searchOpen = false;
  }

  function pick(h: Hit) {
    clearSearch();
    input?.blur();
    openPane(h.gsis_id, { from: "search", context: { name: h.player_name } });
  }

  function openSearch() {
    searchOpen = true;
    requestAnimationFrame(() => input?.focus());
  }

  // ---- the overflow menu (⋯)
  let menuOpen = $state(false);
  $effect(() => void loadAccount()); // ---- IK-4: asked once per page load (lib/account.svelte.ts); quiet when off
  $effect(() => {
    void route.current;
    menuOpen = false;
  });
</script>

<svelte:window
  onkeydown={(e) => {
    if (e.key === "Escape") {
      menuOpen = false;
      if (searchOpen || searched) clearSearch();
    }
  }}
/>

{#snippet icon(key: string)}
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    {#if key === "myteam"}
      <rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" />
    {:else if key === "waivers"}
      <path d="M12 5v14M5 12h14" /><circle cx="12" cy="12" r="9" />
    {:else if key === "trades"}
      <path d="M4 8h13l-3-3M20 16H7l3 3" />
    {:else if key === "players"}
      <circle cx="12" cy="8" r="4" /><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" />
    {:else if key === "search"}
      <circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" />
    {:else}
      <circle cx="5" cy="12" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="19" cy="12" r="1.5" />
    {/if}
  </svg>
{/snippet}

<header class="border-b border-line bg-surface pt-[env(safe-area-inset-top)]" data-testid="top-bar">
  <div class="relative mx-auto flex max-w-6xl items-center gap-2 px-4 py-2 wide:gap-4 wide:py-2.5">
    <!-- the wordmark: from 640 px (on a phone My Team is the way home, and the picker needs the room) -->
    <a href={href("/")} class="order-1 hidden shrink-0 items-center gap-1.5 text-sm font-extrabold tracking-tight uppercase sm:flex" aria-label="{APP_NAME}, my team">
      <span class="grid h-7 w-7 place-items-center rounded-sm bg-accent text-[11px] font-black text-on-accent">{APP_MARK}</span>
      <span class="hidden xl:inline normal-case">{APP_NAME}</span>
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
          <span class="truncate">{t.label}</span>
        </a>
      {/each}
    </nav>

    <!-- the search field: always open from 1280 px; a magnifier under that (the field then covers the bar's row) -->
    <button
      type="button"
      class="order-4 grid h-10 w-9 shrink-0 place-items-center rounded-md text-ink-2 hover:bg-raised hover:text-ink xl:hidden"
      aria-label="Find a player"
      onclick={openSearch}
      data-testid="search-open">{@render icon("search")}</button
    >
    <div
      class="{searchOpen
        ? 'absolute inset-x-0 top-0 z-40 flex h-full items-center gap-2 bg-surface px-4'
        : 'hidden'} xl:relative xl:order-3 xl:z-auto xl:ml-auto xl:flex xl:h-auto xl:w-52 xl:shrink-0 xl:bg-transparent xl:px-0"
      data-testid="search-box"
    >
      <label class="sr-only" for="ll-search">Find a player</label>
      <input
        id="ll-search"
        bind:this={input}
        class="ll-input min-w-0 flex-1 py-1.5 text-sm"
        type="search"
        placeholder="Search players"
        autocomplete="off"
        enterkeyhint="search"
        bind:value={q}
        oninput={onInput}
        onkeydown={(e) => {
          if (e.key === "Enter" && hits[0]) pick(hits[0]);
        }}
        data-testid="search"
      />
      {#if searchOpen}
        <button type="button" class="min-h-10 shrink-0 px-1 text-sm font-semibold text-accent xl:hidden" onclick={clearSearch} data-testid="search-cancel">Cancel</button>
      {/if}
      {#if searched}
        <ul
          class="absolute top-full right-4 left-4 z-40 max-h-[60vh] overflow-y-auto rounded-lg border border-line bg-surface shadow-lg xl:right-auto xl:left-0 xl:w-80"
          data-testid="search-results"
        >
          {#if hits.length === 0}
            <li class="p-3 text-sm text-ink-3">No QB, RB, WR, TE or K named like “{searched}” in this season's pool.</li>
          {/if}
          {#each hits as h (h.gsis_id)}
            <li>
              <a
                class="block min-h-11 px-3 py-2.5 text-base hover:bg-raised"
                href={withContext(`/player/${h.gsis_id}`, ctx)}
                onclick={(e) => {
                  e.preventDefault();
                  pick(h);
                }}
                data-testid="search-hit">{h.label}</a
              >
            </li>
          {/each}
        </ul>
      {/if}
    </div>

    <div class="order-3 min-w-0 flex-1 wide:ml-auto wide:w-[22rem] wide:flex-none xl:order-4 xl:ml-0 xl:w-[20rem]">
      <Picker leagues={options} {league} {rosters} {team} onleague={pickLeague} onteam={pickTeam} />
    </div>

    <!-- the overflow menu: About the numbers (and the record), other leagues -->
    <div class="relative order-5 shrink-0">
      <button
        type="button"
        class="grid h-10 w-9 place-items-center rounded-md text-ink-2 hover:bg-raised hover:text-ink {here === 'about' ? 'text-accent' : ''}"
        aria-label="More"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        onclick={() => (menuOpen = !menuOpen)}
        data-testid="overflow">{@render icon("more")}</button
      >
      <div class="{menuOpen ? '' : 'hidden'} absolute top-full right-0 z-40 mt-1 w-60 overflow-hidden rounded-lg border border-line bg-surface shadow-lg" role="menu" data-testid="overflow-menu">
        <a
          href={href("/about")}
          role="menuitem"
          class="block min-h-11 px-3 py-3 text-base hover:bg-raised {here === 'about' ? 'font-semibold text-accent' : ''}"
          aria-current={here === "about" ? "page" : undefined}
          data-testid="menu-about">About the numbers</a
        >
        <a href="/leagues" role="menuitem" class="block min-h-11 border-t border-line px-3 py-3 text-base hover:bg-raised" data-testid="menu-leagues">Other leagues</a>
        <!-- ---- IK-4: the account (only when the server has accounts on) -->
        {#if account.status?.enabled}
          <a href="/account" role="menuitem" class="block min-h-11 border-t border-line px-3 py-3 text-base hover:bg-raised" data-testid="menu-account"
            >{account.status.signed_in ? "Your account" : "Sign in to save your leagues"}</a
          >
        {/if}
        <!-- ---- end IK-4 -->
      </div>
    </div>
  </div>
  {#if sub.length}
    <div class="mx-auto max-w-6xl px-4 pb-2">
      <!-- a phone: one row that scrolls inside itself when the labels do not fit (the page never does); the picked one
           is scrolled into view -->
      <nav
        class="-mx-4 flex gap-1 overflow-x-auto px-4 [scrollbar-width:none] wide:mx-0 wide:px-0"
        aria-label={SECTIONS.find((s) => s.key === section)?.label ?? "Screens"}
        data-testid="subtabs"
        {@attach (el) => el.querySelector('[aria-current="page"]')?.scrollIntoView({ block: "nearest", inline: "center" })}
      >
        {#each sub as s (s.name)}
          <a
            href={href(s.path)}
            class="inline-flex min-h-9 shrink-0 items-center rounded-full border px-3 text-sm font-semibold {here === s.name || (here === 'receivers' && s.name === 'players')
              ? 'border-accent bg-accent-soft text-ink'
              : 'border-line text-ink-2 hover:text-ink'}"
            aria-current={here === s.name || (here === "receivers" && s.name === "players") ? "page" : undefined}
            data-testid={`sub-${s.name}`}>{s.label}</a
          >
        {/each}
      </nav>
    </div>
  {/if}
</header>
