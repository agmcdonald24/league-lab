<script lang="ts">
  // ---- JA-1 (Wave J-A): the weeks you choose — one track of the season's played weeks with two handles for the stretch
  // (A) and, with "Compare with", a second pair for another stretch (B) on a lane of the same track (a hatched fill and
  // square handles: colour is never the only carrier). Each handle is a labelled <input type="range"> (drag, arrow keys,
  // a screen reader); the week numbers under the track are buttons (a tap moves the nearer handle); one handle on the
  // other = a single week; the choice is said in words. Quick picks one tap away. URL keys (lib/stretch.ts): `window`,
  // `weeks` (A), `vs` (B) — the parent writes them with what `onchange` hands it. Shared by Stats, Compare, Matchups.
  import Chips from "../Chips.svelte";
  import { rangeName, rangeWords, restOfSeason, stretchParams, weeksBefore, weeksOf, words, type Range, type Stretch, type Win } from "../../lib/stretch";

  let {
    first,
    last,
    stretch,
    onchange,
    compare = true,
    games = true,
    collapse = "phone",
    testid = "slider",
  }: {
    first: number;
    last: number;
    stretch: Stretch;
    onchange: (keys: Record<string, string | null>) => void;
    compare?: boolean; // offer "Compare with" (a second stretch)
    games?: boolean; // offer "his last 3 / 5 games played"
    // ---- JA-5: "always" = from 900 px too it opens closed, one line ("Season · weeks 1–4 ▾"), the full control in place
    collapse?: "phone" | "always";
    testid?: string;
  } = $props();

  const span = $derived(Math.max(0, last - first));
  const weeks = $derived(Array.from({ length: span + 1 }, (_, i) => first + i));
  const fromUrl = $derived(weeksOf(stretch, first, last));
  const vsUrl = $derived(stretch.vs ? ([Math.max(first, Math.min(stretch.vs[0], last)), Math.max(first, Math.min(stretch.vs[1], last))] as Range) : null);
  // the handles' live values while dragging (the URL is written on release / each key press)
  let a = $state<Range>([1, 1]);
  let b = $state<Range | null>(null);
  $effect(() => {
    a = fromUrl ?? [first, last];
    b = vsUrl;
  });
  const isGames = $derived(stretch.win === "last3" || stretch.win === "last5");
  const quick = $derived(
    stretch.win === "weeks" && fromUrl && fromUrl[0] === last && fromUrl[1] === last ? "this" : stretch.win === "weeks" ? "" : stretch.win,
  );
  const QUICK = $derived([
    { key: "season", label: "Season" },
    { key: "last3w", label: "Last 3 weeks" },
    { key: "last5w", label: "Last 5 weeks" },
    { key: "this", label: "This week" },
    ...(games
      ? [
          { key: "last3", label: "Last 3 games" },
          { key: "last5", label: "Last 5 games" },
        ]
      : []),
  ]);
  // ---- JA-2: below 900 px a chosen stretch closes to one line that names it ("Weeks 3–4 against weeks 1–2 ▾") and opens
  // in place on a tap; it stays open while the visitor works it (a quick pick, a handle, the switch)
  const inForce = $derived(stretch.win !== "season" || !!stretch.vs);
  let open = $state(false);
  let touched = $state(false);
  // ---- JA-5: on a desktop (900 px and wider) with collapse="always" it opens closed whatever is chosen
  const wide = typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(min-width: 900px)").matches;
  const wideClosed = $derived(collapse === "always" && wide);
  $effect(() => {
    if (!inForce && !touched && !wideClosed) open = true; // the season: nothing to fold (the parent's Filters fold holds it)
  });
  const summary = $derived.by(() => {
    const a0 = weeksOf(stretch, first, last);
    const head = isGames ? words(stretch, first, last) : stretch.win === "season" ? (vsUrl ? "Season" : words(stretch, first, last)) : a0 ? rangeName(a0).replace(/^w/, "W") : "Season";
    return vsUrl ? `${head} against ${rangeName(vsUrl)}` : head;
  });
  const said = $derived(isGames ? words(stretch, first, last) : stretch.win === "season" && !b ? words(stretch, first, last) : rangeWords(a));

  function emit(win: Win, nextA: Range | null, nextB: Range | null) {
    touched = true;
    open = true; // ---- JA-2: working it keeps it open
    onchange(stretchParams(win, nextA, nextB, first, last));
  }
  const otherFor = (r: Range): Range | null => weeksBefore(r, first) ?? restOfSeason(r, first, last);
  function pick(k: string) {
    if (k === "this") {
      const r: Range = [last, last];
      return emit("weeks", r, b ? otherFor(r) : null);
    }
    const win = k as Win;
    const r = weeksOf({ win, weeks: null, vs: null }, first, last);
    emit(win, r, b && r && win !== "season" ? otherFor(r) : null);
  }
  function commit() {
    emit("weeks", a, b);
  }
  function setA(i: 0 | 1, v: number) {
    a = i === 0 ? [Math.min(v, a[1]), a[1]] : [a[0], Math.max(v, a[0])];
  }
  function setB(i: 0 | 1, v: number) {
    if (!b) return;
    b = i === 0 ? [Math.min(v, b[1]), b[1]] : [b[0], Math.max(v, b[0])];
  }
  function tapWeek(w: number) {
    // a tap moves the nearer handle of A (outside A: the end on that side)
    if (w < a[0]) a = [w, a[1]];
    else if (w > a[1]) a = [a[0], w];
    else if (w - a[0] <= a[1] - w) a = [w, a[1]];
    else a = [a[0], w];
    commit();
  }
  const canCompare = $derived(!isGames && span >= 1);
  function toggleCompare() {
    if (b) return emit(stretch.win, a, null);
    if (!canCompare) return;
    if (a[0] === first && a[1] === last) {
      const mid = first + Math.floor((last - first + 1) / 2) - 1;
      return emit("weeks", [mid + 1, last], [first, mid]);
    }
    emit("weeks", a, otherFor(a));
  }
  // where a week sits on the track (the thumb is 22 px wide: its centre runs from 11 px to 100% − 11 px)
  const at = (w: number) => (span ? (w - first) / span : 0.5);
  const pos = (w: number) => `calc(${at(w) * 100}% + ${(0.5 - at(w)) * 22}px)`;
  const AGAINST = " against "; // its spaces survive the template
</script>

<div class="space-y-2" data-testid={testid}>
  {#if inForce || wideClosed}
    <!-- ---- JA-2: the compact closed form on a phone (a real button; hidden from 900 px, where the control is always open)
         ---- JA-5: with collapse="always" it is there from 900 px too -->
    <button
      type="button"
      class="ll-stoggle {wideClosed ? 'll-stoggle-wide' : ''} flex min-h-10 w-full items-center gap-2 text-left text-sm font-semibold text-ink"
      aria-expanded={open}
      aria-controls={`${testid}-body`}
      onclick={() => (open = !open)}
      data-testid={`${testid}-toggle`}><span class="min-w-0 flex-1 truncate">{summary}</span><span aria-hidden="true" class="text-ink-2">{open ? "▴" : "▾"}</span></button
    >
  {/if}
  <div id={`${testid}-body`} class="ll-sbody space-y-2 {inForce ? 'll-can-close' : ''} {wideClosed ? 'll-can-close-wide' : ''} {open ? 'll-open' : ''}">
  <div class="ll-chiprow">
    <Chips label="Weeks" testid={`${testid}-quick`} current={quick} onpick={pick} items={QUICK} />
  </div>
  <p class="text-sm" aria-live="polite" data-testid={`${testid}-words`}>
    <span class="font-semibold text-ink">{#if b}<span class="ll-key ll-key-a" aria-hidden="true"></span>{/if}{b ? `A: ${said}` : said}</span>{#if b}<span class="text-ink-2">{AGAINST}</span><span class="font-semibold text-ink"
        ><span class="ll-key ll-key-b" aria-hidden="true"></span>{`B: ${rangeWords(b)}`}</span
      >{/if}
  </p>
  {#if span >= 1}
    <div class="ll-track {b ? 'll-two' : ''} {isGames ? 'opacity-60' : ''}" data-testid={`${testid}-track`}>
      <div class="ll-rail ll-rail-a"></div>
      <div class="ll-fill ll-fill-a" style="left:{pos(a[0])};right:calc(100% - {pos(a[1])})"></div>
      <input
        type="range"
        class="ll-range ll-range-a"
        min={first}
        max={last}
        step="1"
        value={a[0]}
        aria-label={b ? "A, first week" : "First week"}
        aria-valuetext={`Week ${a[0]}`}
        style="z-index:{a[0] === last ? 4 : 3}"
        oninput={(e) => setA(0, Number(e.currentTarget.value))}
        onchange={commit}
        data-testid={`${testid}-a-lo`}
      />
      <input
        type="range"
        class="ll-range ll-range-a"
        min={first}
        max={last}
        step="1"
        value={a[1]}
        aria-label={b ? "A, last week" : "Last week"}
        aria-valuetext={`Week ${a[1]}`}
        style="z-index:3"
        oninput={(e) => setA(1, Number(e.currentTarget.value))}
        onchange={commit}
        data-testid={`${testid}-a-hi`}
      />
      {#if b}
        <div class="ll-rail ll-rail-b"></div>
        <div class="ll-fill ll-fill-b" style="left:{pos(b[0])};right:calc(100% - {pos(b[1])})"></div>
        <input
          type="range"
          class="ll-range ll-range-b"
          min={first}
          max={last}
          step="1"
          value={b[0]}
          aria-label="B, first week"
          aria-valuetext={`Week ${b[0]}`}
          style="z-index:{b[0] === last ? 4 : 3}"
          oninput={(e) => setB(0, Number(e.currentTarget.value))}
          onchange={commit}
          data-testid={`${testid}-b-lo`}
        />
        <input
          type="range"
          class="ll-range ll-range-b"
          min={first}
          max={last}
          step="1"
          value={b[1]}
          aria-label="B, last week"
          aria-valuetext={`Week ${b[1]}`}
          style="z-index:3"
          oninput={(e) => setB(1, Number(e.currentTarget.value))}
          onchange={commit}
          data-testid={`${testid}-b-hi`}
        />
      {/if}
    </div>
    <div class="ll-ticks" aria-label="Weeks" role="group">
      {#each weeks as w (w)}
        <button
          type="button"
          class="ll-tick {w >= a[0] && w <= a[1] ? 'll-in' : ''}"
          style="left:{pos(w)}"
          aria-label={`Week ${w}`}
          aria-pressed={w >= a[0] && w <= a[1]}
          onclick={() => tapWeek(w)}
          data-testid={`${testid}-week-${w}`}>{w}</button
        >
      {/each}
    </div>
  {/if}
  {#if compare}
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <label class="inline-flex min-h-9 items-center gap-2 text-sm font-semibold {canCompare ? '' : 'text-ink-3'}">
        <input type="checkbox" checked={!!b} disabled={!canCompare && !b} onchange={toggleCompare} data-testid={`${testid}-compare`} />
        Compare with other weeks
      </label>
      {#if b}
        {@const before = weeksBefore(a, first)}
        {@const rest = restOfSeason(a, first, last)}
        <Chips
          label="Compare with"
          testid={`${testid}-preset`}
          current={before && b[0] === before[0] && b[1] === before[1] ? "before" : rest && b[0] === rest[0] && b[1] === rest[1] ? "rest" : ""}
          onpick={(k) => {
            const r = k === "before" ? before : rest;
            if (r) emit("weeks", a, r);
          }}
          items={[
            ...(before ? [{ key: "before", label: `The weeks before (${rangeName(before)})` }] : []),
            // ---- JA-2: one preset when the two are the same weeks (A ends the season): "The weeks before"
            ...(rest && !(before && before[0] === rest[0] && before[1] === rest[1]) ? [{ key: "rest", label: `The rest of the season (${rangeName(rest)})` }] : []),
          ]}
        />
      {:else if !canCompare}
        <span class="text-sm text-ink-2">{isGames ? "Pick weeks to compare (his last games are not a fixed stretch)." : "One week played: nothing to compare yet."}</span>
      {/if}
    </div>
  {/if}
  </div>
</div>

<style>
  /* ---- JA-2: closed to one line below 900 px once a stretch is chosen; always open from 900 px */
  @media (max-width: 899px) {
    .ll-can-close:not(.ll-open) {
      display: none;
    }
  }
  @media (min-width: 900px) {
    .ll-stoggle:not(.ll-stoggle-wide) {
      display: none;
    }
    .ll-can-close-wide:not(.ll-open) {
      display: none;
    }
  }
  /* on a phone the quick picks keep one row, scrolling inside themselves (the page never does) */
  @media (max-width: 639px) {
    .ll-chiprow :global([role="group"]) {
      flex-wrap: nowrap;
      overflow-x: auto;
      scrollbar-width: none;
    }
    .ll-chiprow :global([role="group"] > button) {
      flex-shrink: 0;
    }
  }
  .ll-track {
    position: relative;
    height: 2rem;
    margin: 0 0.25rem;
  }
  .ll-track.ll-two {
    height: 3.5rem;
  }
  .ll-rail,
  .ll-fill {
    position: absolute;
    height: 0.375rem;
    border-radius: 9999px;
  }
  .ll-rail {
    left: 11px;
    right: 11px;
    background: var(--color-line);
  }
  .ll-rail-a,
  .ll-fill-a {
    top: calc(1rem - 0.1875rem);
  }
  .ll-rail-b,
  .ll-fill-b {
    top: calc(2.75rem - 0.1875rem);
  }
  .ll-fill-a {
    background: var(--color-accent);
  }
  /* B: another colour AND a hatch (colour is never the only carrier) */
  .ll-fill-b {
    height: 0.5rem;
    background: repeating-linear-gradient(135deg, var(--color-warn) 0 4px, transparent 4px 7px);
    border: 1px solid var(--color-warn);
  }
  .ll-range {
    position: absolute;
    left: 0;
    width: 100%;
    height: 2rem;
    margin: 0;
    background: transparent;
    appearance: none;
    -webkit-appearance: none;
    pointer-events: none;
  }
  .ll-range-a {
    top: 0;
  }
  .ll-range-b {
    top: 1.75rem;
  }
  .ll-range::-webkit-slider-runnable-track {
    background: transparent;
  }
  .ll-range::-webkit-slider-thumb {
    -webkit-appearance: none;
    pointer-events: auto;
    width: 22px;
    height: 22px;
    border-radius: 9999px;
    background: var(--color-accent);
    border: 2px solid var(--color-surface);
    box-shadow: 0 0 0 1px var(--color-line-strong);
    cursor: grab;
  }
  .ll-range::-moz-range-thumb {
    pointer-events: auto;
    width: 22px;
    height: 22px;
    border-radius: 9999px;
    background: var(--color-accent);
    border: 2px solid var(--color-surface);
    cursor: grab;
  }
  .ll-range-b::-webkit-slider-thumb {
    border-radius: 3px;
    background: var(--color-warn);
  }
  .ll-range-b::-moz-range-thumb {
    border-radius: 3px;
    background: var(--color-warn);
  }
  .ll-range:focus-visible::-webkit-slider-thumb {
    outline: 3px solid var(--color-accent);
    outline-offset: 2px;
  }
  .ll-range:focus-visible::-moz-range-thumb {
    outline: 3px solid var(--color-accent);
    outline-offset: 2px;
  }
  .ll-ticks {
    position: relative;
    height: 2rem;
    margin: 0 0.25rem;
  }
  .ll-tick {
    position: absolute;
    top: 0;
    min-width: 1.75rem;
    height: 1.75rem;
    transform: translateX(-50%);
    border-radius: 0.375rem;
    font-size: 0.8125rem;
    color: var(--color-ink-2);
    font-variant-numeric: tabular-nums;
  }
  .ll-tick.ll-in {
    color: var(--color-ink);
    font-weight: 700;
  }
  .ll-key {
    display: inline-block;
    width: 0.75rem;
    height: 0.75rem;
    margin-right: 0.25rem;
    vertical-align: -1px;
  }
  .ll-key-a {
    border-radius: 9999px;
    background: var(--color-accent);
  }
  .ll-key-b {
    border-radius: 2px;
    border: 1px solid var(--color-warn);
    background: repeating-linear-gradient(135deg, var(--color-warn) 0 3px, transparent 3px 5px);
  }
</style>
