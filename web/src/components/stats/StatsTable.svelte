<script lang="ts">
  // ---- IM-2 (Wave I-M): the Stats table built for width (Players · Stats; docs/DESIGN.md § "The Stats table").
  // A real <table>: the player column sticky on the left (a row header), the header rows sticky on top (the group row
  // over the column row in the Full table, each group a <colgroup> + a header cell), the numbers right-aligned in
  // tabular figures, a sort on any column (aria-sort, ▲ / ▼), a row highlighted on hover / tap, the dash's reason on
  // hover (title) and on tap (a note), a small sample greyed. Scrolls inside its own box both ways (the page never
  // scrolls sideways); the focus never lands under the sticky column (scroll-padding). Rows render in chunks after the
  // first screenful, so 400 rows x 40 columns never block a phone's frame for long.
  import type { StatsColumn, StatsRow } from "../../lib/api";
  import { paneLink } from "../../lib/pane.svelte"; // a name opens the drawer (lib/player-drawer.svelte.ts)
  import { shortName } from "../../lib/names.svelte";
  import Headshot from "../Headshot.svelte";
  import PosBadge from "../PosBadge.svelte";
  import TeamBadge from "../TeamBadge.svelte";
  import { head, runs, show, small, title, why, type Mode } from "./columns";

  let {
    rows,
    cols,
    grouped = false,
    mode,
    limit,
    sortId,
    dir,
    onsort,
    href,
    mine,
    sel = [],
    onselect,
    owner = null,
    caption,
    dim = false,
  }: {
    rows: StatsRow[]; // the whole filtered, sorted set
    cols: StatsColumn[];
    grouped?: boolean; // the Full table: the group header row
    mode: Mode;
    limit: number; // how many rows to show (Infinity: all)
    sortId: string | null;
    dir: "asc" | "desc";
    onsort: (c: StatsColumn) => void;
    href: (p: StatsRow) => string;
    mine: (p: StatsRow) => boolean;
    sel?: string[];
    onselect?: (id: string) => void;
    owner?: ((p: StatsRow) => string) | null;
    caption: string;
    dim?: boolean;
  } = $props();

  // ---- every row, without a long frame: up to WINDOW_FROM rows render as they are; past that ("Show all": 450 rows x
  // 45 columns = 20,000 cells, each name cell a sticky layer the browser re-places on every scroll frame) only the rows
  // in and near the box's visible part are in the page (OVERSCAN rows each side), spacer rows keep the scroll height,
  // and the table says how many rows it has (aria-rowcount / aria-rowindex). Measured in docs/handbacks/IM-2.md.
  const WINDOW_FROM = 100;
  const OVERSCAN = 8;
  const target = $derived(Math.min(rows.length, limit));
  const windowed = $derived(target > WINDOW_FROM);
  let rowH = $state(48); // measured from the first row on screen
  let headH = $state(40);
  let viewH = $state(600);
  let top = $state(0); // the box's scrollTop, a frame at a time
  const count = $derived(Math.ceil(viewH / rowH) + 2 * OVERSCAN);
  const start = $derived(windowed ? Math.max(0, Math.min(Math.floor(Math.max(0, top - headH) / rowH) - OVERSCAN, target - count)) : 0);
  const end = $derived(windowed ? Math.min(target, start + count) : target);
  const visible = $derived(rows.slice(start, end));
  const headRows = $derived(grouped ? 2 : 1);
  // windowed, the column widths are measured once from the first rows (auto layout) and then fixed: a column never
  // jumps wider or narrower as other rows scroll in, and a fixed layout is cheaper to lay out on every frame
  let widths = $state<{ key: string; player: number; cols: number[]; owner: number } | null>(null);
  const widthKey = $derived(`${cols.map((c) => c.id).join(",")}|${mode}|${grouped}|${sortId}`);
  const locked = $derived(windowed && widths !== null && widths.key === widthKey ? widths : null);
  $effect(() => {
    const key = widthKey;
    if (!windowed || !scroller || (widths && widths.key === key)) return;
    const id = requestAnimationFrame(() => {
      const ths = [...(scroller?.querySelectorAll<HTMLElement>("thead th[data-c]") ?? [])];
      const corner = scroller?.querySelector<HTMLElement>("thead .ll-corner");
      const own = scroller?.querySelector<HTMLElement>("thead th[data-owner]");
      if (ths.length !== cols.length || !corner) return;
      widths = { key, player: corner.getBoundingClientRect().width, cols: ths.map((th) => Math.ceil(th.getBoundingClientRect().width) + 6), owner: own ? own.getBoundingClientRect().width : 0 };
    });
    return () => cancelAnimationFrame(id);
  });
  $effect(() => {
    void visible;
    if (!scroller || !windowed) return;
    const tr = scroller.querySelector<HTMLElement>("tbody tr[data-id]");
    const th = scroller.querySelector<HTMLElement>("thead");
    if (tr) rowH = Math.max(24, tr.getBoundingClientRect().height);
    if (th) headH = th.getBoundingClientRect().height;
    viewH = scroller.clientHeight;
  });

  // ---- short names on a phone ("J. Jefferson"; the first name grows when two would read the same): the visible
  // first name is swapped for its short form by CSS, so the link's text (and its name) stays the whole name
  const shorts = $derived.by(() => {
    const byLast: Record<string, string[]> = {};
    for (const p of rows) {
      const parts = (p.player_name ?? "").trim().split(/\s+/);
      (byLast[parts.slice(1).join(" ")] ??= []).push(p.player_name);
    }
    const out: Record<string, { first: string; rest: string; s: string } | null> = {};
    for (const p of rows) {
      const name = (p.player_name ?? "").trim();
      const parts = name.split(/\s+/);
      const rest = parts.slice(1).join(" ");
      const s = shortName(name, p.position, byLast[rest] ?? []);
      out[p.gsis_id] = s !== name && s.endsWith(rest) ? { first: parts[0], rest, s: s.slice(0, s.length - rest.length).trim() } : null;
    }
    return out;
  });

  // a phone shows no headshot in the name column (≤ 120 px): not rendered at all there (one component a row fewer)
  const faces = typeof window === "undefined" || typeof window.matchMedia !== "function" || window.matchMedia("(min-width: 640px)").matches;
  const groups = $derived(grouped ? runs(cols) : []);
  // a group of one or two columns is narrow: its name in a short form (the whole name on hover, and to a screen reader
  // through the header cell's title)
  const NARROW: Record<string, string> = { "Games and points": "Games", "Expected points": "Expected", "Snaps and routes": "Snaps", "Next Gen Stats": "Next Gen", "Advanced (PFR)": "PFR" };
  const starts = $derived(new Set(groups.slice(1).map((g) => g.cols[0].id)));
  // a column's cell class, worked out once per column (20,000 cells at 450 rows x 45 columns)
  const colClass = $derived(cols.map((c) => `px-1.5 py-1.5 text-right whitespace-nowrap sm:px-2${sortId === c.id ? " ll-sorted" : ""}${starts.has(c.id) ? " ll-gstart" : ""}`));

  // ---- the row a tap picked (highlighted until another tap); the note that reads a dash's reason on a tap
  let hl = $state<string | null>(null);
  let tip = $state<{ text: string; x: number; y: number } | null>(null);
  let scroller: HTMLDivElement | undefined = $state();
  let swiped = $state(false);
  let overflowX = $state(false);
  let scrolledX = $state(false);

  function onclick(e: MouseEvent) {
    const t = e.target as HTMLElement;
    const w = t.closest<HTMLElement>("td[data-why]");
    if (w) {
      const r = w.getBoundingClientRect();
      const text = w.getAttribute("title") ?? "";
      tip = tip && tip.text === text ? null : { text, x: Math.min(r.left, window.innerWidth - 272), y: r.bottom + 6 };
      return;
    }
    tip = null;
    if (t.closest("a, button, input, label, select")) return;
    const tr = t.closest<HTMLElement>("tr[data-id]");
    if (tr) hl = hl === tr.dataset.id ? null : (tr.dataset.id ?? null);
  }
  let pendingTop = false;
  function onscroll() {
    tip = null;
    if (windowed && !pendingTop) {
      pendingTop = true;
      requestAnimationFrame(() => {
        pendingTop = false;
        top = scroller?.scrollTop ?? 0;
      });
    }
    const x = scroller?.scrollLeft ?? 0;
    scrolledX = x > 2;
    if (x > 8) swiped = true;
  }
  function measure() {
    if (scroller) overflowX = scroller.scrollWidth > scroller.clientWidth + 4;
  }
  $effect(() => {
    void cols.length;
    void visible.length;
    const id = requestAnimationFrame(measure); // after the frame's layout, never a forced one per chunk
    return () => cancelAnimationFrame(id);
  });
  $effect(() => {
    if (!scroller || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(scroller);
    return () => ro.disconnect();
  });
  function onkeydown(e: KeyboardEvent) {
    if (e.key === "Escape" && tip) tip = null;
  }
</script>

<svelte:window {onkeydown} onscroll={() => (tip = null)} />

{#if overflowX && !swiped}
  <p class="ll-swipe flex justify-end text-sm font-semibold text-accent sm:hidden" aria-hidden="true" data-testid="stats-swipe">Swipe for more →</p>
{/if}
<!-- a tap: a row's highlight, or a dash's / a small sample's note (the same words as the cell's title on hover) -->
<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div
  class="ll-stats overflow-auto rounded-lg border border-line bg-surface {dim ? 'opacity-60' : ''} {grouped ? 'll-grouped' : ''} {scrolledX ? 'll-scrolled' : ''}"
  style="box-shadow:var(--ll-shadow)"
  data-testid="stats-scroll"
  bind:this={scroller}
  {onscroll}
  {onclick}
>
  <table
    class="ll-table tabnum {grouped ? 'text-sm' : 'text-base'} {windowed ? 'll-windowed' : ''}"
    data-testid="players-table"
    data-view={grouped ? "full" : "key"}
    aria-rowcount={windowed ? target + headRows : undefined}
    data-rows={target}
    style={locked ? `table-layout:fixed;width:${locked.player + locked.cols.reduce((a, b) => a + b, 0) + locked.owner}px` : undefined}
  >
    <caption class="sr-only">{caption}</caption>
    <colgroup><col class="ll-col-player" style={locked ? `width:${locked.player}px` : undefined} /></colgroup>
    {#if grouped}
      {#each groups as g (g.name)}<colgroup data-group={g.name}
          >{#each g.cols as c (c.id)}<col style={locked ? `width:${locked.cols[cols.indexOf(c)]}px` : undefined} />{/each}</colgroup
        >{/each}
    {:else}
      <colgroup>{#each cols as c, j (c.id)}<col style={locked ? `width:${locked.cols[j]}px` : undefined} />{/each}</colgroup>
    {/if}
    {#if owner}<colgroup><col style={locked && locked.owner ? `width:${locked.owner}px` : undefined} /></colgroup>{/if}
    <thead>
      {#if grouped}
        <tr class="ll-ghead" data-testid="stats-group-row">
          <th scope="col" rowspan="2" class="ll-stick ll-corner ll-label bg-raised px-2 py-2 pl-3 text-left align-bottom">Player</th>
          {#each groups as g, i (g.name)}
            <th scope="colgroup" colspan={g.cols.length} class="ll-g bg-raised px-2 text-left whitespace-nowrap {i > 0 ? 'll-gstart' : ''}" title={g.name} data-testid="stats-group-head" data-group={g.name}
              >{#if g.cols.length <= 2 && NARROW[g.name]}<span class="ll-gbox" aria-hidden="true"><span class="ll-gname">{NARROW[g.name]}</span></span><span class="sr-only">{g.name}</span
                >{:else}<span class="ll-gbox"><span class="ll-gname">{g.name}</span></span>{/if}</th
            >
          {/each}
          {#if owner}<th scope="col" rowspan="2" data-owner class="ll-label hidden bg-raised px-2 py-2 pr-3 text-left align-bottom sm:table-cell">Team in league</th>{/if}
        </tr>
      {/if}
      <tr class="ll-chead">
        {#if !grouped}<th scope="col" class="ll-stick ll-corner ll-label bg-raised px-2 py-2 pl-3 text-left">Player</th>{/if}
        {#each cols as c (c.id)}
          <th
            scope="col"
            data-c={c.id}
            class="ll-label bg-raised px-0.5 py-1 text-right whitespace-nowrap {starts.has(c.id) ? 'll-gstart' : ''} {sortId === c.id ? 'll-sorted' : ''}"
            aria-sort={sortId === c.id ? (dir === "asc" ? "ascending" : "descending") : undefined}
            title={`${title(c, mode)} — ${c.definition}${c.denominator ? ` Denominator: ${c.denominator}.` : ""}`}
          >
            <button type="button" class="ll-sortbtn inline-flex min-h-8 items-center gap-0.5 rounded-sm px-1 uppercase {sortId === c.id ? 'text-ink' : ''}" onclick={() => onsort(c)} data-testid={`sort-${c.id}`}
              >{head(c, mode)}<span class="ll-arrow" aria-hidden="true">{sortId === c.id ? (dir === "asc" ? "▲" : "▼") : ""}</span><span class="sr-only"> {title(c, mode)}</span></button
            >
          </th>
        {/each}
        {#if owner && !grouped}<th scope="col" data-owner class="ll-label hidden bg-raised px-2 py-2 pr-3 text-left sm:table-cell">Team in league</th>{/if}
      </tr>
    </thead>
    <tbody>
      {#if windowed && start > 0}<tr class="ll-spacer" aria-hidden="true" style="height:{start * rowH}px"><td colspan={cols.length + 1 + (owner ? 1 : 0)}></td></tr>{/if}
      {#each visible as p, i (p.gsis_id)}
        {@const short = shorts[p.gsis_id]}
        <tr class="{mine(p) ? 'll-mine' : ''} {hl === p.gsis_id ? 'll-hl' : ''}" data-id={p.gsis_id} data-testid="players-table-row" aria-rowindex={windowed ? start + i + headRows + 1 : undefined}>
          <th scope="row" class="ll-stick bg-surface py-1.5 pr-2 pl-2 text-left font-normal sm:pl-3">
            <div class="flex min-w-0 items-center gap-1.5 sm:gap-2">
              {#if onselect}
                <input
                  type="checkbox"
                  class="shrink-0"
                  aria-label={`Select ${p.player_name} to compare`}
                  checked={sel.includes(p.gsis_id)}
                  disabled={!sel.includes(p.gsis_id) && sel.length >= 4}
                  onchange={() => onselect(p.gsis_id)}
                  data-testid="stats-select"
                />
              {/if}
              {#if faces}<span class="hidden sm:inline-flex"><Headshot url={p.headshot_url} name={p.player_name} team={p.team} size={28} /></span>{/if}
              <div class="min-w-0">
                <a class="ll-name block truncate font-semibold" href={href(p)} aria-label={p.player_name} {@attach paneLink(p.gsis_id, { from: "list", context: { name: p.player_name } })}
                  >{#if short}<span class="ll-first" data-short={short.s}>{short.first}</span> {short.rest}{:else}{p.player_name}{/if}</a
                >
                <div class="mt-0.5 flex items-center gap-1"><PosBadge pos={p.position} /><TeamBadge team={p.team} /></div>
              </div>
            </div>
          </th>
          {#each cols as c, j (j)}
            {@const t = show(c, p, mode)}
            {@const sm = t === "—" ? null : small(c, p, mode)}
            {#if t === "—" || sm}
              <td class="{colClass[j]} ll-why text-ink-3" title={sm ? `${why(c, p, mode)}. ${sm}` : why(c, p, mode)} data-col={c.id} data-why="">{t}</td>
            {:else}
              <td class={colClass[j]} title={why(c, p, mode)} data-col={c.id}>{t}</td>
            {/if}
          {/each}
          {#if owner}<td class="hidden px-2 py-1.5 pr-3 text-left text-sm text-ink-2 sm:table-cell"><span class="block max-w-[10rem] truncate">{owner(p)}</span></td>{/if}
        </tr>
      {/each}
      {#if windowed && end < target}<tr class="ll-spacer" aria-hidden="true" style="height:{(target - end) * rowH}px"><td colspan={cols.length + 1 + (owner ? 1 : 0)}></td></tr>{/if}
    </tbody>
  </table>
</div>
{#if tip}
  <div class="ll-tip fixed z-50 max-w-[17rem] rounded-md border border-line-strong bg-raised px-3 py-2 text-sm text-ink shadow-lg" style="left:{Math.max(8, tip.x)}px;top:{tip.y}px" role="status" data-testid="stats-tip">
    {tip.text}
  </div>
{/if}

<style>
  /* the box scrolls both ways (never the page); the header rows and the player column stay put */
  .ll-stats {
    --ll-stick: 7.5rem; /* ≤ 120 px at 375: the short name + the badges */
    --ll-gh: 1.75rem; /* the group row's height: the column row sticks under it */
    max-height: 75vh;
    max-width: 100%;
    overscroll-behavior-x: contain;
    /* a focused cell scrolled to never lands under the sticky column or the sticky header */
    scroll-padding-left: var(--ll-stick);
    scroll-padding-top: 2.75rem;
  }
  .ll-stats.ll-grouped {
    scroll-padding-top: calc(2.75rem + var(--ll-gh));
  }
  @media (min-width: 640px) {
    .ll-stats {
      --ll-stick: 14rem;
    }
  }
  .ll-table {
    border-collapse: separate;
    border-spacing: 0;
    min-width: 100%;
  }
  .ll-table thead th {
    position: sticky;
    top: 0;
    z-index: 2;
    border-bottom: 1px solid var(--color-line-strong);
  }
  .ll-grouped .ll-chead th {
    top: var(--ll-gh);
  }
  .ll-ghead .ll-g {
    height: var(--ll-gh);
    border-bottom: 1px solid var(--color-line);
  }
  /* a group's name never widens its columns (width 0, then the cell's width; clipped when the group is narrow, the
     whole name on hover) and stays in view while a wide group scrolls under it (sticky; clip keeps it working) */
  .ll-gbox {
    display: block;
    width: 0;
    min-width: 100%;
    overflow: clip;
  }
  .ll-gname {
    display: inline-block;
    position: sticky;
    left: calc(var(--ll-stick) + 0.5rem);
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    color: var(--color-ink-2);
  }
  /* the column labels: the label style, tracked a little tighter (31 columns want the width) */
  .ll-chead .ll-sortbtn {
    letter-spacing: 0.03em;
  }
  .ll-table tbody td,
  .ll-table tbody th {
    border-bottom: 1px solid var(--color-line);
  }
  .ll-table tbody tr:last-child > * {
    border-bottom: 0;
  }
  /* windowed: every row the same height (the spacers are counted in rows) */
  .ll-windowed tbody tr[data-id] {
    height: 3.25rem;
  }
  .ll-windowed tbody tr[data-id] > * {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .ll-spacer > td {
    padding: 0;
    border: 0 !important;
  }
  .ll-stick {
    position: sticky;
    left: 0;
    z-index: 1;
    width: var(--ll-stick);
    min-width: var(--ll-stick);
    max-width: var(--ll-stick);
  }
  .ll-table thead .ll-corner {
    z-index: 3;
  }
  /* the sticky column's edge: a hairline, stronger once the numbers slide under it (borders: cheap to scroll) */
  .ll-stick {
    border-right: 1px solid var(--color-line);
  }
  .ll-scrolled .ll-corner,
  .ll-scrolled tbody .ll-stick {
    border-right-color: var(--color-ink-3);
  }
  .ll-gstart {
    border-left: 1px solid var(--color-line-strong);
  }
  /* the sorted column: a faint wash down the column, the arrow in accent */
  .ll-table td.ll-sorted {
    background: color-mix(in oklab, var(--color-accent) 7%, transparent);
  }
  .ll-arrow {
    font-size: 9px;
    color: var(--color-accent);
    min-width: 0.5rem;
  }
  .ll-sortbtn:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: -2px;
  }
  /* a row: hover (a pointer) and the row a tap picked; yours keeps its green wash */
  .ll-table tbody tr:hover > * {
    background: var(--color-raised);
  }
  /* opaque washes (a sticky cell must hide what slides under it): yours green, the tapped row blue */
  .ll-table tbody tr.ll-mine > * {
    background: color-mix(in oklab, var(--color-accent) 14%, var(--color-surface));
  }
  .ll-table tbody tr.ll-hl > * {
    background: color-mix(in oklab, var(--color-series-1) 20%, var(--color-surface));
  }
  .ll-table tbody tr.ll-hl > .ll-stick {
    border-left: 3px solid var(--color-series-1);
  }
  /* a dash or a small sample: the note on a tap (the same words as the title on hover) */
  .ll-why {
    cursor: help;
  }
  /* a phone: the first name's short form ("J."), the link's text stays the whole name */
  @media (max-width: 639px) {
    .ll-first[data-short] {
      font-size: 0;
    }
    .ll-first[data-short]::before {
      content: attr(data-short);
      font-size: 0.8125rem;
    }
    .ll-name {
      font-size: 0.8125rem;
    }
  }
  .ll-swipe {
    margin-bottom: -0.25rem;
  }
</style>
