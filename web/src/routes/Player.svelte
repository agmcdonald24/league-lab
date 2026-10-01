<script lang="ts">
  import { ApiError, get, paths, peek, Unauthorized, type Hit, type PlayerCard } from "../lib/api";
  import { withContext } from "../lib/md";
  import { back, navigate, restoreScroll, route } from "../lib/router.svelte";
  import Expander from "../components/Expander.svelte";
  import Md from "../components/Md.svelte";
  import SectionBox from "../components/Section.svelte";

  let { gsis, league, team, onauth }: { gsis: string; league: string | null; team: number | null; onauth: () => void } = $props();

  let data = $state<PlayerCard | null>(null);
  let error = $state<string | null>(null);
  let q = $state("");
  let hits = $state<Hit[]>([]);
  let searched = $state("");

  const ctx = $derived({ league, team });
  const home = $derived(withContext("/", ctx));
  // The card's answer first: this week's projection and where he sits in the lineup, then the rest.
  const order = ["projection", "value", "availability", "usage", "signals"] as const;

  $effect(() => {
    const id = gsis;
    const l = league;
    const t = team;
    error = null;
    if (!l) return;
    const path = paths.player(id, l, t);
    const hit = peek<PlayerCard>(path);
    if (hit) {
      data = hit;
      restoreScroll();
      return;
    }
    data = null;
    get<PlayerCard>(path)
      .then((d) => {
        if (gsis !== id || league !== l) return;
        data = d;
        restoreScroll();
      })
      .catch((e) => {
        if (gsis !== id) return;
        if (e instanceof Unauthorized) onauth();
        else error = e instanceof ApiError && e.status === 404 ? `No player with id ${id}. Search for him above.` : String(e);
      });
  });

  let timer: ReturnType<typeof setTimeout> | undefined;
  function onInput() {
    clearTimeout(timer);
    const text = q.trim();
    if (text.length < 2 || !league) {
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

  function pick(id: string) {
    q = "";
    hits = [];
    searched = "";
    navigate(withContext(`/player/${id}`, ctx));
  }
</script>

<header class="relative flex items-center gap-2 px-4 pt-[max(0.75rem,env(safe-area-inset-top))] pb-2">
  <button
    type="button"
    class="flex min-h-11 shrink-0 items-center gap-1 rounded-xl px-2 text-[15px] font-medium text-green-700 dark:text-green-400"
    onclick={() => back(home)}
    data-testid="back"
  >
    <span aria-hidden="true" class="text-xl leading-none">‹</span>{route.current.depth > 0 ? "Back" : "My week"}
  </button>
  <label class="sr-only" for="ll-search">Find a player</label>
  <input
    id="ll-search"
    class="min-w-0 flex-1 rounded-xl border border-zinc-300 bg-white px-3 py-2 text-base dark:border-zinc-700 dark:bg-zinc-900"
    type="search"
    placeholder="Find another player"
    autocomplete="off"
    bind:value={q}
    oninput={onInput}
    data-testid="search"
  />
  {#if searched}
    <ul
      class="absolute top-full right-4 left-4 z-10 max-h-[60vh] overflow-y-auto rounded-2xl border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
      data-testid="search-results"
    >
      {#if hits.length === 0}
        <li class="p-3 text-sm text-zinc-500">No QB, RB, WR, TE or K named like “{searched}” in this season's pool.</li>
      {/if}
      {#each hits as h (h.gsis_id)}
        <li>
          <a
            class="block min-h-11 px-3 py-2.5 text-[15px]"
            href={withContext(`/player/${h.gsis_id}`, ctx)}
            onclick={(e) => {
              e.preventDefault();
              pick(h.gsis_id);
            }}>{h.label}</a
          >
        </li>
      {/each}
    </ul>
  {/if}
</header>

<main class="space-y-3 px-4 pb-10" data-testid="player">
  {#if error}
    <p class="rounded-2xl border border-red-200 p-4 text-[15px] text-red-800 dark:border-red-900 dark:text-red-300">{error}</p>
  {:else if !data}
    <div class="animate-pulse space-y-3" aria-label="Loading" data-testid="loading">
      <div class="h-7 w-2/3 rounded bg-zinc-200 dark:bg-zinc-800"></div>
      <div class="h-4 w-5/6 rounded bg-zinc-200 dark:bg-zinc-800"></div>
      {#each [0, 1, 2] as i (i)}<div class="h-28 rounded-2xl bg-zinc-100 dark:bg-zinc-900"></div>{/each}
    </div>
  {:else}
    <section class="space-y-1">
      <h1 class="text-2xl leading-tight font-bold" data-testid="player-name">{data.player_name}</h1>
      <p class="text-[14px] leading-snug text-zinc-600 dark:text-zinc-300"><Md text={data.header} {ctx} /></p>
    </section>
    {#each order as key (key)}
      <SectionBox section={data.sections[key]} {ctx} testid={`section-${key}`} />
    {/each}
    <Expander title="How to read this" testid="howto"><Md text={data.howto} {ctx} block class="text-[14px] leading-snug" /></Expander>
  {/if}
</main>
