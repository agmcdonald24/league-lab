<script lang="ts">
  // Points by week, with the expected points beside them (the player card's game log; Trends' detail). Two series:
  // the actual in series 1 (2 px line, a 10 % wash, dots with a surface ring), the expected in the muted ink, dashed
  // (it is a model's line, not a score). A legend for the two, the last value labelled, a hairline grid; tap or hover a
  // week to read it; "Show as a table" is the chart's twin (every value reachable without the picture).
  import { areaPath, extent, linear, linePath, niceTicks } from "../lib/chart";
  import { SERIES } from "../lib/theme";

  export interface WeekPoint {
    week: number;
    label?: string; // "W3 vs DAL"
    actual: number | null;
    expected?: number | null;
  }

  let {
    points,
    actualLabel = "Points",
    expectedLabel = "Expected points",
    height = 200,
    unit = "pts",
    testid = "line-chart",
  }: { points: WeekPoint[]; actualLabel?: string; expectedLabel?: string; height?: number; unit?: string; testid?: string } = $props();

  let width = $state(340);
  let focus = $state<number | null>(null);

  const M = { l: 30, r: 14, t: 10, b: 22 };
  const hasExpected = $derived(points.some((p) => p.expected !== null && p.expected !== undefined));
  const weeks = $derived(points.map((p) => p.week));
  const yMax = $derived(Math.max(10, extent(points.flatMap((p) => [p.actual, p.expected ?? null]))[1]));
  const ticks = $derived(niceTicks(0, yMax, 4));
  const top = $derived(ticks[ticks.length - 1]);
  const x = $derived(linear(Math.min(...weeks), Math.max(...weeks), M.l + 6, width - M.r - 6));
  const y = $derived(linear(0, top, height - M.b, M.t));
  const actualPts = $derived(points.map((p) => ({ x: x(p.week), y: p.actual === null ? null : y(p.actual) })));
  const expectedPts = $derived(points.map((p) => ({ x: x(p.week), y: p.expected === null || p.expected === undefined ? null : y(p.expected) })));
  const last = $derived([...points].reverse().find((p) => p.actual !== null) ?? null);
  const step = $derived(points.length > 12 && width < 500 ? 2 : 1);
  const f = (v: number | null | undefined) => (v === null || v === undefined ? "—" : v.toFixed(1));
  const shown = $derived(focus === null ? null : (points.find((p) => p.week === focus) ?? null));

  function onmove(e: PointerEvent) {
    const r = (e.currentTarget as SVGElement).getBoundingClientRect();
    const px = e.clientX - r.left;
    let best: number | null = null;
    let d = Infinity;
    for (const p of points) {
      const dd = Math.abs(x(p.week) - px);
      if (dd < d) {
        d = dd;
        best = p.week;
      }
    }
    focus = best;
  }
</script>

<figure class="min-w-0" data-testid={testid}>
  <div class="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2" data-testid="legend">
    <span class="inline-flex items-center gap-1.5"
      ><svg width="16" height="8" aria-hidden="true"><line x1="0" y1="4" x2="16" y2="4" stroke={SERIES.actual} stroke-width="2" stroke-linecap="round" /></svg
      >{actualLabel}</span
    >
    {#if hasExpected}
      <span class="inline-flex items-center gap-1.5"
        ><svg width="16" height="8" aria-hidden="true"
          ><line x1="0" y1="4" x2="16" y2="4" stroke={SERIES.expected} stroke-width="2" stroke-dasharray="4 3" stroke-linecap="round" /></svg
        >{expectedLabel}</span
      >
    {/if}
    <span class="ml-auto min-h-4 text-ink" data-testid="chart-readout" aria-live="polite">
      {#if shown}<strong>{shown.label ?? `Week ${shown.week}`}</strong>: {f(shown.actual)}{hasExpected ? ` · expected ${f(shown.expected)}` : ""}{/if}
    </span>
  </div>
  <div bind:clientWidth={width} class="w-full">
    <svg
      {width}
      {height}
      role="img"
      aria-label="{actualLabel} by week{hasExpected ? `, with ${expectedLabel.toLowerCase()}` : ''}"
      class="block touch-pan-y overflow-visible"
      onpointermove={onmove}
      onpointerdown={onmove}
      onpointerleave={() => (focus = null)}
    >
      {#each ticks as t (t)}
        <line x1={M.l} x2={width - M.r} y1={y(t)} y2={y(t)} stroke={t === 0 ? SERIES.axis : SERIES.grid} stroke-width="1" />
        <text x={M.l - 6} y={y(t)} dy="0.32em" text-anchor="end" class="tabnum fill-ink-3 text-[10px]">{t}</text>
      {/each}
      {#each points as p, i (p.week)}
        {#if i % step === 0 || i === points.length - 1}
          <text x={x(p.week)} y={height - 6} text-anchor="middle" class="tabnum fill-ink-3 text-[10px]">{p.week}</text>
        {/if}
      {/each}
      {#if focus !== null}
        <line x1={x(focus)} x2={x(focus)} y1={M.t} y2={height - M.b} stroke={SERIES.axis} stroke-width="1" />
      {/if}
      <path d={areaPath(actualPts, height - M.b)} fill={SERIES.actual} opacity="0.1" />
      {#if hasExpected}
        <path d={linePath(expectedPts)} fill="none" stroke={SERIES.expected} stroke-width="2" stroke-dasharray="4 3" stroke-linecap="round" stroke-linejoin="round" />
      {/if}
      <path d={linePath(actualPts)} fill="none" stroke={SERIES.actual} stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
      {#each actualPts as p, i (i)}
        {#if p.y !== null}
          <circle cx={p.x} cy={p.y} r={points[i].week === focus ? 5.5 : 4} fill={SERIES.actual} stroke="var(--ll-surface)" stroke-width="2" />
        {/if}
      {/each}
      {#if last && last.actual !== null}
        <text x={x(last.week)} y={y(last.actual) - 10} text-anchor="end" class="tabnum fill-ink text-[11px] font-semibold">{f(last.actual)}</text>
      {/if}
    </svg>
  </div>
  <div class="mt-1 text-xs text-ink-3">Week</div>
  <details class="mt-2 text-sm" data-testid="chart-table">
    <summary class="inline-flex min-h-8 items-center gap-1 text-ink-2"><span class="chev" aria-hidden="true">›</span>Show as a table</summary>
    <table class="tabnum mt-1 w-full text-sm">
      <thead
        ><tr class="ll-label text-left"
          ><th class="py-1 font-semibold">Week</th><th class="py-1 text-right font-semibold">{actualLabel}</th>{#if hasExpected}<th
              class="py-1 text-right font-semibold">{expectedLabel}</th
            >{/if}</tr
        ></thead
      >
      <tbody>
        {#each points as p (p.week)}
          <tr class="border-t border-line"
            ><td class="py-1">{p.label ?? p.week}</td><td class="py-1 text-right">{f(p.actual)}</td>{#if hasExpected}<td class="py-1 text-right text-ink-2"
                >{f(p.expected)}</td
              >{/if}</tr
          >
        {/each}
      </tbody>
    </table>
  </details>
  <span class="sr-only">{unit}</span>
</figure>
