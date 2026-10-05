<script lang="ts">
  // IB-1 (Wave I-B): the research pane. II-2 (Wave I-I, the fifth review § 3): THE player drawer — every player link
  // on a league screen opens it (lib/player-drawer.svelte.ts: openPlayer / playerLink, the router's link hook for any
  // `<a href="/player/…">`); App.svelte mounts it once. From 900 px a panel beside the screen (sticky; the list stays
  // usable: another name swaps the player); on a phone a full-height sheet. A compact first view in four sections —
  // Overview (the projection and its range, where he stands, the one-line reason, the actions) · Usage · Game log ·
  // News — an Expand control (a modal lightbox with every section open), Add to compare and Full player page. The
  // league and its scoring stay in the head. × / Escape / Back close it; focus returns to the control that opened it.
  import { onMount, tick } from "svelte";
  import { ApiError, Unauthorized, type NewsItem, type PlayerCard } from "../lib/api";
  import { ago, cardHeadLine, cardSections, paneSplit, projLabel } from "../lib/card"; // IG-1: projLabel
  import { learnLeagueName } from "../lib/names.svelte";
  import { paneActions } from "../lib/pane.svelte";
  import {
    addToCompare,
    cachedCard,
    closePlayer,
    compareTray,
    drawer,
    drawerMounted,
    DRAWER_SECTIONS,
    loadCard,
    openFullPage,
    removeFromCompare,
    restoreFocus,
    setExpanded,
    setSection,
    type DrawerSection,
  } from "../lib/player-drawer.svelte";
  import { navigate } from "../lib/router.svelte";
  import { canWatch, isWatched, unwatch, watch } from "../lib/watchlist.svelte"; // ---- IL-5: Watch / Watching
  import { fmt } from "../lib/theme";
  import GameLog from "./GameLog.svelte";
  import NewsLine from "./NewsLine.svelte"; // ---- N1
  import PlayerCardView from "./PlayerCard.svelte";
  import SectionBox from "./Section.svelte";
  import Expander from "./Expander.svelte"; // ---- IF-4
  import Md from "./Md.svelte"; // ---- IF-4
  import ScheduleTable from "./ScheduleTable.svelte"; // ---- IF-4

  let { league, team, onauth }: { league: string; team: number | null; onauth: () => void } = $props();

  let data = $state<PlayerCard | null>(null);
  let error = $state<string | null>(null);
  let box = $state<HTMLElement | null>(null);
  let titleEl = $state<HTMLElement | null>(null);
  let dlg = $state<HTMLDialogElement | null>(null);
  let expandBtn = $state<HTMLButtonElement | null>(null);
  let note = $state<string | null>(null); // "Added …" under Add to compare

  const ctx = $derived({ league, team });
  const gsis = $derived(drawer.key);
  const from = $derived(drawer.from);
  const context = $derived(drawer.context);
  const section = $derived(drawer.section);
  const expanded = $derived(drawer.expanded);
  const actions = $derived(gsis ? paneActions(gsis, from, context, ctx) : []);
  const sections = $derived(data ? cardSections(data) : []);
  // ---- IF-4 (the decision-quality review: "Keep the drawer focused on the decision"): the drawer leads with what the
  // call needs — the projection and its range, where he stands, the news, his role — and puts the week-by-week line,
  // the next four, the season tiles and the schedule behind expanders (the full page shows everything open).
  // II-2: Usage and the game log are sections of their own.
  const PANE_ORDER = ["projection", "availability", "value", "signals"];
  const focused = $derived(
    sections
      .filter((x) => PANE_ORDER.includes(x.key))
      .sort((x, y) => PANE_ORDER.indexOf(x.key) - PANE_ORDER.indexOf(y.key))
      .map((x) => ({ key: x.key, ...paneSplit(x.key, x.sec) }))
      .map((x) => (x.key === "projection" && data?.why ? statLineToMore(x) : x)),
  );
  // II-2: the "Stat line:" paragraph says what the one-line reason above already says (his projected stat line): in
  // the drawer it goes behind "Week by week and season numbers" (the full page keeps it)
  type Split = { key: string; main: { blocks: { text?: string | null }[] }; more: unknown[] };
  function statLineToMore<T extends Split>(x: T): T {
    const isStat = (b: { text?: string | null }) => (b.text ?? "").startsWith("Stat line:");
    return { ...x, main: { ...x.main, blocks: x.main.blocks.filter((b) => !isStat(b)) }, more: [...x.main.blocks.filter(isStat), ...x.more] };
  }
  const usage = $derived(sections.find((x) => x.key === "usage")?.sec ?? null);
  const moreBlocks = $derived(focused.flatMap((x) => x.more));
  // ---- end IF-4
  const headLine = $derived(data ? cardHeadLine(data) : "");
  const title = $derived(data?.player_name ?? context.name ?? "Player");
  const tray = $derived(compareTray(league));
  const waiting = $derived(tray.find((x) => x.key !== gsis) ?? null);
  const isWaiting = $derived(tray.some((x) => x.key === gsis));
  const news = $derived((data?.news ?? []).filter((n) => n.headline && n.url?.startsWith("https://")));

  onMount(() => {
    drawerMounted(true);
    return () => drawerMounted(false);
  });

  // the card: cached by player + league + team + data version; an older, slower answer never replaces a newer pick
  $effect(() => {
    const id = gsis;
    const l = league;
    const t = team;
    error = null;
    note = null;
    if (!id) {
      data = null;
      return;
    }
    box?.scrollTo?.(0, 0);
    data = cachedCard(id, l, t) ?? null;
    loadCard(id, l, t)
      .then((d) => {
        if (!d || drawer.key !== id || league !== l || team !== t) return;
        data = d;
        learnLeagueName(d.league_id, d.league_name);
      })
      .catch((e) => {
        if (drawer.key !== id) return;
        if (e instanceof Unauthorized) onauth();
        else if (e instanceof ApiError && e.status === 404) error = "No card for this player in this league yet.";
        else if (e instanceof ApiError && e.status === 502) error = "Sleeper did not answer. Try again in a minute.";
        else error = e instanceof Error ? e.message : String(e);
      });
  });

  // focus: into the drawer when a player opens (or is swapped in); back to what opened it when it closes
  let wasOpen = false;
  $effect(() => {
    const id = gsis;
    if (id) {
      wasOpen = true;
      tick().then(() => {
        if (!drawer.expanded) titleEl?.focus({ preventScroll: true });
      });
    } else if (wasOpen) {
      wasOpen = false;
      tick().then(restoreFocus);
    }
  });

  // the lightbox: a modal <dialog>; closing it returns focus to Expand
  $effect(() => {
    const d = dlg;
    if (!d) return;
    if (expanded && !d.open) d.showModal();
    else if (!expanded && d.open) {
      d.close();
      tick().then(() => expandBtn?.focus({ preventScroll: true }));
    }
  });

  function onKey(e: KeyboardEvent) {
    if (e.key !== "Escape" || !gsis) return;
    if (drawer.expanded) {
      e.preventDefault(); // the dialog's own cancel would close it without telling us
      setExpanded(false);
      return;
    }
    closePlayer();
  }

  // the tabs: arrows move between them (the ARIA tabs pattern), Home / End to the ends
  function tabKeys(e: KeyboardEvent, i: number) {
    const n = DRAWER_SECTIONS.length;
    const to = e.key === "ArrowRight" ? (i + 1) % n : e.key === "ArrowLeft" ? (i - 1 + n) % n : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : -1;
    if (to < 0) return;
    e.preventDefault();
    const k = DRAWER_SECTIONS[to].key;
    setSection(k);
    tick().then(() => document.getElementById(`drawer-tab-${k}`)?.focus());
  }

  function compare() {
    if (!gsis) return;
    if (isWaiting) {
      removeFromCompare(gsis);
      note = null;
      return;
    }
    const r = addToCompare(gsis, title, ctx);
    if (r === "waiting") note = `${title} is waiting to be compared: open another player and tap “Compare with ${title}”.`;
  }

  // ---- IL-5 (Wave I-L): Watch / Watching — signed in only; the watchlist is the account's (lib/watchlist.svelte.ts)
  let watchNote = $state<string | null>(null);
  const watching = $derived(isWatched(gsis));
  async function toggleWatch() {
    if (!gsis) return;
    watchNote = null;
    try {
      if (watching) await unwatch(gsis, drawer.origin ?? null);
      else await watch(gsis, drawer.origin ?? null);
    } catch {
      watchNote = "Not saved: try again in a minute.";
    }
  }
  // ---- end IL-5

  const SEP = " · ";
  const newsLabel = (n: NewsItem) => (n.about === "league" ? "League news" : "News");
</script>

<svelte:window onkeydown={onKey} />

{#snippet actionsRow()}
  <!-- what to do with him, for where he was opened from; always Add to compare and his full page -->
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
    <button
      type="button"
      class="inline-flex min-h-11 items-center rounded-md border border-line-strong px-3.5 text-sm font-semibold {isWaiting ? 'text-ink-2' : 'text-ink'}"
      aria-pressed={isWaiting}
      onclick={compare}
      data-testid="drawer-compare">{isWaiting ? "Remove from compare" : waiting ? `Compare with ${waiting.name}` : "Add to compare"}</button
    >
    {#if canWatch() && gsis}
      <!-- ---- IL-5: the account's watchlist -->
      <button
        type="button"
        class="inline-flex min-h-11 items-center rounded-md border px-3.5 text-sm font-semibold {watching ? 'border-accent bg-accent-soft text-ink' : 'border-line-strong text-ink'}"
        aria-pressed={watching}
        onclick={toggleWatch}
        data-testid="drawer-watch">{watching ? "★ Watching" : "☆ Watch"}</button
      >
    {/if}
    <a
      href={`/player/${encodeURIComponent(gsis ?? "")}`}
      class="inline-flex min-h-11 items-center rounded-md border border-line-strong px-3.5 text-sm font-semibold text-ink"
      onclick={(e) => {
        e.preventDefault();
        if (gsis) openFullPage(gsis, ctx);
      }}
      data-full-page
      data-testid="pane-full">Full player page <span class="ml-1 text-accent" aria-hidden="true">›</span></a
    >
  </div>
  {#if note}<p class="-mt-1 text-sm text-ink-3" role="status" data-testid="drawer-compare-note">{note}</p>{/if}
  {#if watchNote}<p class="-mt-1 text-sm text-bad" role="status" data-testid="drawer-watch-note">{watchNote}</p>{/if}<!-- IL-5 -->
  {#if actions[0]?.key === "compare" && context.starterName}
    <p class="-mt-1 text-sm text-ink-3" data-testid="pane-compare-with">With {context.starterName}{context.slot && context.slot !== "bench" ? `, the next best for ${context.slot}` : ""}.</p>
  {/if}
{/snippet}

{#snippet overview(d: PlayerCard)}
  <div class="space-y-3" data-testid="drawer-overview">
    <PlayerCardView
      player={{ gsis_id: d.gsis_id, player_name: d.player_name, position: d.position, team: d.team, headshot_url: d.headshot_url ?? null }}
      number={fmt.pts(d.proj_points)}
      numberLabel={projLabel(d.week, d.proj_points)}
      line={headLine}
      context={d.injury_status ?? null}
      compact
      testid="pane-card"
    />
    {#if d.why}
      <p class="text-sm leading-snug font-semibold text-ink-2" data-testid="pane-why">{d.why.sentence}</p>
    {/if}
    {@render actionsRow()}
    {#each focused as x (x.key)}
      <SectionBox section={x.main} {ctx} testid={`pane-section-${x.key}`}>
        <!-- ---- N1 (Wave I-D): the news line under the availability lines -->
        {#if x.key === "availability"}<NewsLine card={d} testid="pane-news" />{/if}
        <!-- ---- end N1 -->
        <!-- PO (I-F): the matchup evidence's two sentences ride in the projection section's blocks (lib/card.ts
             matchupBlocks, under the "Next:" line), so they are here without a component of their own -->
      </SectionBox>
    {/each}
    <!-- ---- IF-4: the ledger and the schedule behind expanders -->
    {#if moreBlocks.length}
      <Expander title="Week by week and season numbers" testid="pane-more">
        <div class="space-y-2" data-testid="pane-more-body">
          {#each moreBlocks as b, i (i)}
            {#if b.metrics}
              <ul class="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
                {#each b.metrics as m (m.label)}<li><span class="text-ink-3">{m.label}</span> <strong class="tabnum">{m.value ?? "—"}</strong></li>{/each}
              </ul>
            {:else if b.text}
              <p class="text-sm leading-snug text-ink-2"><Md text={b.text} {ctx} /></p>
            {/if}
          {/each}
        </div>
      </Expander>
    {/if}
    {#if d.schedule?.length}
      <Expander title="Schedule" testid="pane-schedule"><ScheduleTable rows={d.schedule} position={d.position} testid="pane-schedule-table" /></Expander>
    {/if}
    <!-- ---- end IF-4 -->
  </div>
{/snippet}

{#snippet usagePanel()}
  <div class="space-y-3" data-testid="drawer-usage">
    {#if usage}
      <SectionBox section={usage} {ctx} testid="pane-section-usage" />
    {:else}
      <p class="ll-empty" data-testid="drawer-usage-empty">No usage numbers for him in this league yet.</p>
    {/if}
  </div>
{/snippet}

{#snippet gamelogPanel(d: PlayerCard)}
  <div data-testid="drawer-gamelog">
    <GameLog gsis={d.gsis_id} {league} season={d.season} {onauth} leagueName={d.league_name} />
  </div>
{/snippet}

{#snippet newsPanel(d: PlayerCard)}
  <div class="space-y-3" data-testid="drawer-news">
    <p class="text-sm leading-snug text-ink-2" data-testid="drawer-news-status">
      <span class="font-semibold text-ink">Status:</span>
      {d.injury_status ? d.injury_status : "no injury designation"}{d.locked ? " · his game has started" : ""}.
    </p>
    {#if news.length}
      <ul class="divide-y divide-line rounded-lg border border-line bg-surface" data-testid="drawer-news-list">
        {#each news as n, i (`${n.url}|${i}`)}
          <li class="space-y-1 px-4 py-3 text-sm leading-snug" data-testid="drawer-news-item">
            <p class="text-ink-3">
              <span class="font-semibold text-ink">{newsLabel(n)}</span>{#if ago(n.date)}{SEP}{ago(n.date)}{/if}{SEP}{n.source || "ESPN"}{#if n.verification}<span
                  class="ml-1.5 inline-block rounded-sm px-1 align-[1px] text-[10px] leading-[16px] font-bold tracking-wide uppercase {n.verification === 'disputed'
                    ? 'bg-warn-soft text-warn'
                    : 'bg-accent-soft text-accent'}"
                  title={`PlayerWire marks this brief ${n.verification}`}>{n.verification}</span
                >{/if}
            </p>
            <a class="ll-link block font-semibold" href={n.url} target="_blank" rel="noopener noreferrer" data-testid="drawer-news-link"
              >{n.headline}<span class="sr-only"> (opens in a new tab)</span></a
            >
            {#if n.summary}<p class="text-ink-2">{n.summary}</p>{/if}
          </li>
        {/each}
      </ul>
    {:else}
      <p class="ll-empty" data-testid="drawer-news-empty">No news about him in the last 14 days.</p>
    {/if}
  </div>
{/snippet}

{#snippet body(which: DrawerSection | "all")}
  {#if error}
    <p class="ll-error">{error}</p>
  {:else if !data}
    <div class="space-y-3" aria-label="Loading" data-testid="pane-loading">
      <div class="ll-skel h-28"></div>
      <div class="ll-skel h-10"></div>
      <div class="ll-skel h-24"></div>
    </div>
    {#if which === "overview"}{@render actionsRow()}{/if}
  {:else if which === "all"}
    <div class="grid grid-cols-1 gap-4 wide:grid-cols-2 wide:items-start" data-testid="drawer-expanded-body">
      <div class="space-y-4">
        {@render overview(data)}
      </div>
      <div class="space-y-4">
        <h3 class="ll-label">Usage</h3>
        {@render usagePanel()}
        <h3 class="ll-label">Game log</h3>
        {@render gamelogPanel(data)}
        <h3 class="ll-label">News</h3>
        {@render newsPanel(data)}
      </div>
    </div>
  {:else if which === "overview"}
    {@render overview(data)}
  {:else if which === "usage"}
    {@render usagePanel()}
  {:else if which === "gamelog"}
    {@render gamelogPanel(data)}
  {:else}
    {@render newsPanel(data)}
  {/if}
{/snippet}

{#if gsis}
  <aside
    bind:this={box}
    class="fixed inset-0 z-50 h-[100dvh] overflow-y-auto overscroll-contain bg-page pb-[env(safe-area-inset-bottom)]
           wide:sticky wide:inset-auto wide:top-0 wide:z-auto wide:w-[25rem] wide:shrink-0 wide:border-l wide:border-line wide:pb-0"
    aria-labelledby="drawer-title"
    data-drawer
    data-testid="pane"
    data-gsis={gsis}
    data-from={from}
    data-section={section}
  >
    <header class="sticky top-0 z-10 border-b border-line bg-page/95 px-4 pt-[max(0.5rem,env(safe-area-inset-top))] backdrop-blur">
      <div class="flex items-center gap-1">
        <div class="min-w-0 flex-1">
          <h2 bind:this={titleEl} id="drawer-title" tabindex="-1" class="ll-label truncate outline-none" data-testid="pane-title">{title}</h2>
          {#if data}
            <p class="truncate text-xs text-ink-3" data-testid="drawer-league">{data.league_name} scoring{data.week ? ` · week ${data.week}` : ""}</p>
          {/if}
        </div>
        <button
          bind:this={expandBtn}
          type="button"
          class="grid h-11 w-11 shrink-0 place-items-center rounded-md text-lg leading-none text-ink-2 hover:bg-raised hover:text-ink"
          aria-label="Expand: every section in a larger view"
          aria-haspopup="dialog"
          title="Expand"
          onclick={() => setExpanded(true)}
          data-testid="drawer-expand"><span aria-hidden="true">⤢</span></button
        >
        <button
          type="button"
          class="grid h-11 w-11 shrink-0 place-items-center rounded-md text-xl leading-none text-ink-2 hover:bg-raised hover:text-ink"
          aria-label="Close"
          onclick={closePlayer}
          data-testid="pane-close">×</button
        >
      </div>
      <div class="-mx-1 mt-1 flex gap-1 overflow-x-auto" role="tablist" aria-label="His sections" data-testid="drawer-tabs">
        {#each DRAWER_SECTIONS as s, i (s.key)}
          <button
            type="button"
            role="tab"
            id={`drawer-tab-${s.key}`}
            aria-selected={section === s.key}
            aria-controls="drawer-panel"
            tabindex={section === s.key ? 0 : -1}
            class="min-h-11 shrink-0 border-b-2 px-2.5 text-sm font-semibold {section === s.key ? 'border-accent text-ink' : 'border-transparent text-ink-3 hover:text-ink'}"
            onclick={() => setSection(s.key)}
            onkeydown={(e) => tabKeys(e, i)}
            data-testid={`drawer-tab-${s.key}`}>{s.label}</button
          >
        {/each}
      </div>
    </header>

    <div class="space-y-3 px-4 pt-3 pb-6" role="tabpanel" id="drawer-panel" aria-labelledby={`drawer-tab-${section}`} tabindex="-1" data-testid="drawer-panel">
      {#if expanded}
        <p class="text-sm text-ink-3">Open in the larger view.</p>
      {:else}
        {@render body(section)}
      {/if}
    </div>
  </aside>

  <!-- Expand: a modal lightbox with every section open (dialog semantics: focus inside, Escape collapses it) -->
  <dialog
    bind:this={dlg}
    class="m-0 h-[100dvh] max-h-none w-screen max-w-none overflow-y-auto overscroll-contain bg-page p-0 text-ink backdrop:bg-black/60
           wide:m-auto wide:h-[min(92dvh,64rem)] wide:w-[min(94vw,72rem)] wide:rounded-xl wide:border wide:border-line"
    aria-labelledby="drawer-expanded-title"
    oncancel={(e) => {
      e.preventDefault();
      setExpanded(false);
    }}
    data-drawer
    data-testid="drawer-expanded"
  >
    {#if expanded}
      <header class="sticky top-0 z-10 flex items-center gap-1 border-b border-line bg-page/95 px-4 py-2 backdrop-blur">
        <div class="min-w-0 flex-1">
          <h2 id="drawer-expanded-title" class="ll-label truncate">{title}</h2>
          {#if data}<p class="truncate text-xs text-ink-3">{data.league_name} scoring{data.week ? ` · week ${data.week}` : ""}</p>{/if}
        </div>
        <button
          type="button"
          class="inline-flex min-h-11 items-center rounded-md px-3 text-sm font-semibold text-accent hover:bg-raised"
          onclick={() => setExpanded(false)}
          data-testid="drawer-collapse">Back to the panel</button
        >
        <button
          type="button"
          class="grid h-11 w-11 shrink-0 place-items-center rounded-md text-xl leading-none text-ink-2 hover:bg-raised hover:text-ink"
          aria-label="Close"
          onclick={closePlayer}
          data-testid="drawer-expanded-close">×</button
        >
      </header>
      <div class="px-4 pt-3 pb-6">{@render body("all")}</div>
    {/if}
  </dialog>
{/if}

<style>
  /* the drawer is a phone's width at every size: the card's tiles two to a row (Metrics goes four across from 640 px) */
  aside :global([data-testid="metrics"]) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
</style>
