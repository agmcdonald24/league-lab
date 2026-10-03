<script lang="ts">
  // IB-1 (Wave I-B): the research pane — the player card unit, the actions for where it was opened from, then the
  // card's sections and his game log. From 900 px a panel beside the screen (sticky, the list stays usable: another
  // name swaps the player); on a phone a sheet over the screen (Back, the backdrop, × or Escape close it). The API
  // other screens call: lib/pane.svelte.ts (openPane / paneLink); App.svelte mounts this once.
  import { ApiError, get, paths, peek, Unauthorized, type PlayerCard } from "../lib/api";
  import { cardHeadLine, cardSections } from "../lib/card";
  import { learnLeagueName } from "../lib/names.svelte";
  import { closePane, openFullPage, pane, paneActions } from "../lib/pane.svelte";
  import { navigate } from "../lib/router.svelte";
  import { fmt } from "../lib/theme";
  import GameLog from "./GameLog.svelte";
  import PlayerCardView from "./PlayerCard.svelte";
  import SectionBox from "./Section.svelte";

  let { league, team, onauth }: { league: string; team: number | null; onauth: () => void } = $props();

  let data = $state<PlayerCard | null>(null);
  let error = $state<string | null>(null);
  let box = $state<HTMLElement | null>(null);

  const ctx = $derived({ league, team });
  const gsis = $derived(pane.gsis);
  const from = $derived(pane.from);
  const context = $derived(pane.context);
  const actions = $derived(gsis ? paneActions(gsis, from, context, ctx) : []);
  const sections = $derived(data ? cardSections(data) : []);
  const headLine = $derived(data ? cardHeadLine(data) : "");
  const title = $derived(data?.player_name ?? context.name ?? "Player");

  $effect(() => {
    const id = gsis;
    const l = league;
    const t = team;
    error = null;
    if (!id) {
      data = null;
      return;
    }
    box?.scrollTo?.(0, 0);
    const path = paths.player(id, l, t);
    const hit = peek<PlayerCard>(path);
    if (hit) {
      data = hit;
      return;
    }
    data = null;
    get<PlayerCard>(path)
      .then((d) => {
        if (gsis !== id || league !== l) return;
        data = d;
        learnLeagueName(d.league_id, d.league_name);
      })
      .catch((e) => {
        if (gsis !== id) return;
        if (e instanceof Unauthorized) onauth();
        else if (e instanceof ApiError && e.status === 404) error = "No card for this player in this league yet.";
        else if (e instanceof ApiError && e.status === 502) error = "Sleeper did not answer. Try again in a minute.";
        else error = e instanceof Error ? e.message : String(e);
      });
  });

  function onKey(e: KeyboardEvent) {
    if (e.key === "Escape" && gsis) closePane();
  }
</script>

<svelte:window onkeydown={onKey} />

{#if gsis}
  <!-- a phone: the screen dims under the sheet; a tap on it closes the sheet -->
  <button type="button" class="fixed inset-0 z-40 bg-black/45 wide:hidden" aria-label="Close" tabindex="-1" onclick={closePane} data-testid="pane-backdrop"></button>
  <aside
    bind:this={box}
    class="fixed inset-x-0 bottom-0 z-50 max-h-[88dvh] overflow-y-auto overscroll-contain rounded-t-xl border-t border-line bg-page pb-[env(safe-area-inset-bottom)] shadow-2xl
           wide:sticky wide:top-0 wide:bottom-auto wide:z-auto wide:h-[100dvh] wide:max-h-none wide:w-[25rem] wide:shrink-0 wide:rounded-none wide:border-t-0 wide:border-l wide:pb-0 wide:shadow-none"
    aria-label={`${title}: his card`}
    data-testid="pane"
    data-gsis={gsis}
    data-from={from}
  >
    <header class="sticky top-0 z-10 border-b border-line bg-page/95 px-4 pt-2 pb-2 backdrop-blur">
      <span class="mx-auto mb-1.5 block h-1 w-10 rounded-full bg-line-strong wide:hidden" aria-hidden="true"></span>
      <div class="flex items-center gap-2">
        <p class="ll-label min-w-0 flex-1 truncate" data-testid="pane-title">{title}</p>
        <button
          type="button"
          class="grid h-9 w-9 shrink-0 place-items-center rounded-md text-xl leading-none text-ink-2 hover:bg-raised hover:text-ink"
          aria-label="Close"
          onclick={closePane}
          data-testid="pane-close">×</button
        >
      </div>
    </header>

    <div class="space-y-3 px-4 pt-3 pb-6">
      {#if error}
        <p class="ll-error">{error}</p>
      {:else if !data}
        <div class="space-y-3" aria-label="Loading" data-testid="pane-loading">
          <div class="ll-skel h-28"></div>
          <div class="ll-skel h-10"></div>
          <div class="ll-skel h-24"></div>
        </div>
      {:else}
        <PlayerCardView
          player={{ gsis_id: data.gsis_id, player_name: data.player_name, position: data.position, team: data.team, headshot_url: data.headshot_url ?? null }}
          number={fmt.pts(data.proj_points)}
          numberLabel={data.week ? `Week ${data.week}` : "Projection"}
          line={headLine}
          context={data.injury_status ?? null}
          compact
          testid="pane-card"
        />
      {/if}

      <!-- what to do with him, for where he was opened from; always his full page -->
      <div class="flex flex-wrap gap-2" data-testid="pane-actions">
        {#each actions as a (a.key)}
          <a
            href={a.href}
            class="inline-flex min-h-11 items-center rounded-md bg-accent px-3.5 text-sm font-semibold text-on-accent"
            onclick={(e) => {
              e.preventDefault();
              navigate(a.href);
            }}
            data-testid={`pane-action-${a.key}`}>{a.label}</a
          >
        {/each}
        <a
          href={`/player/${gsis}`}
          class="inline-flex min-h-11 items-center rounded-md border border-line-strong px-3.5 text-sm font-semibold text-ink"
          onclick={(e) => {
            e.preventDefault();
            openFullPage(gsis, ctx);
          }}
          data-testid="pane-full">Full page <span class="ml-1 text-accent" aria-hidden="true">›</span></a
        >
      </div>
      {#if actions[0]?.key === "compare" && context.starterName}
        <p class="-mt-1 text-sm text-ink-3" data-testid="pane-compare-with">With {context.starterName}{context.slot && context.slot !== "bench" ? `, the next best for ${context.slot}` : ""}.</p>
      {/if}

      {#if data}
        {#if data.why}
          <p class="text-sm leading-snug font-semibold text-ink-2" data-testid="pane-why">{data.why.sentence}</p>
        {/if}
        {#each sections as x (x.key)}
          <SectionBox section={x.sec} {ctx} testid={`pane-section-${x.key}`} />
        {/each}
        <GameLog gsis={data.gsis_id} {league} season={data.season} {onauth} leagueName={data.league_name} />
      {/if}
    </div>
  </aside>
{/if}

<style>
  /* the pane is a phone's width at every size: the card's tiles two to a row (Metrics goes four across from 640 px) */
  aside :global([data-testid="metrics"]) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
</style>
