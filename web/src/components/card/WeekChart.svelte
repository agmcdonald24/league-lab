<script lang="ts">
  // IP-4 (Wave I-P): the player card's week-by-week chart — the chart kit's (lib/chart.ts) bars, a band and lines on
  // one categorical week axis. Bars are what happened (his points); a line is a model's or a share's; the band is a
  // range. A week is read by tap / hover (a line under the chart says its numbers), by the arrow keys once the chart
  // has focus, and in "Show the numbers" (the chart's twin: every value without the picture).
  import { bandPath, bands, linePath, niceTicks } from "../../lib/chart";
  import { SERIES } from "../../lib/theme";

  export interface ChartLine {
    key: string;
    label: string;
    color: string;
    values: (number | null)[];
    dashed?: boolean;
  }
  export interface ChartBars {
    label: string;
    color: string;
    values: (number | null)[];
  }
  export interface ChartBand {
    label: string;
    color: string;
    lo: (number | null)[];
    hi: (number | null)[];
  }
  export interface ChartColumn {
    label: string;
    cell: (i: number) => string;
  }

  let {
    weeks,
    bars = null,
    lines = [],
    band = null,
    tick = (v: number) => String(v),
    describe,
    columns,
    ariaLabel,
    height = 180,
    floor = 10,
    testid = "week-chart",
  }: {
    weeks: number[];
    bars?: ChartBars | null;
    lines?: ChartLine[];
    band?: ChartBand | null;
    tick?: (v: number) => string;
    describe: (i: number) => string;
    columns: ChartColumn[];
    ariaLabel: string;
    height?: number;
    floor?: number; // the y axis reaches at least this high (a quiet week does not look like a big one)
    testid?: string;
  } = $props();

  let width = $state(340);
  let focus = $state<number | null>(null);

  const M = { l: 30, r: 8, t: 10, b: 22 };
  const all = $derived([...(bars?.values ?? []), ...lines.flatMap((l) => l.values), ...(band?.hi ?? [])].filter((v): v is number => typeof v === "number"));
  // the top tick at or above the largest value (niceTicks can stop half a step short of it)
  const ticks = $derived.by(() => {
    const hi = Math.max(floor, ...all);
    const t = niceTicks(0, hi, 4);
    const stepT = t.length > 1 ? t[1] - t[0] : hi || 1;
    while (t[t.length - 1] < hi) t.push(Math.round((t[t.length - 1] + stepT) * 1e6) / 1e6);
    return t;
  });
  const top = $derived(ticks[ticks.length - 1] || 1);
  const xs = $derived(bands(weeks.length, M.l, width - M.r));
  const y = (v: number) => height - M.b - (v / top) * (height - M.b - M.t);
  const barW = $derived(Math.max(6, Math.min(28, xs.step * 0.56)));
  const lastBar = $derived.by(() => {
    for (let i = weeks.length - 1; i >= 0; i--) if (bars?.values[i] !== null && bars?.values[i] !== undefined) return i;
    return weeks.length - 1;
  });
  const shown = $derived(focus ?? lastBar);
  const step = $derived(weeks.length > 12 && width < 480 ? 2 : 1);

  function barPath(x: number, v: number): string {
    const y0 = height - M.b;
    const y1 = y(v);
    const r = Math.min(3, (y0 - y1) / 2, barW / 2);
    const l = x - barW / 2;
    const rr = x + barW / 2;
    return `M${l},${y0}L${l},${y1 + r}Q${l},${y1} ${l + r},${y1}L${rr - r},${y1}Q${rr},${y1} ${rr},${y1 + r}L${rr},${y0}Z`;
  }

  function onpointer(e: PointerEvent) {
    const r = (e.currentTarget as SVGElement).getBoundingClientRect();
    const px = e.clientX - r.left;
    const i = Math.floor((px - M.l) / xs.step);
    focus = Math.max(0, Math.min(weeks.length - 1, i));
  }

  function onkey(e: KeyboardEvent) {
    const n = weeks.length;
    if (!n) return;
    const cur = focus ?? lastBar;
    const to = e.key === "ArrowRight" ? Math.min(n - 1, cur + 1) : e.key === "ArrowLeft" ? Math.max(0, cur - 1) : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : -1;
    if (to < 0) return;
    e.preventDefault();
    focus = to;
  }
</script>

<figure class="min-w-0" data-testid={testid}>
  <div class="mb-1.5 flex flex-wrap items-center gap-x-3.5 gap-y-1 text-xs text-ink-2" data-testid="chart-legend">
    {#if bars}
      <span class="inline-flex items-center gap-1.5"><span class="inline-block h-2.5 w-2.5 rounded-[2px]" style="background:{bars.color}" aria-hidden="true"></span>{bars.label}</span>
    {/if}
    {#each lines as l (l.key)}
      <span class="inline-flex items-center gap-1.5"
        ><svg width="16" height="8" aria-hidden="true"
          ><line x1="0" y1="4" x2="16" y2="4" stroke={l.color} stroke-width="2" stroke-dasharray={l.dashed ? "4 3" : undefined} stroke-linecap="round" /></svg
        >{l.label}</span
      >
    {/each}
    {#if band}
      <span class="inline-flex items-center gap-1.5"
        ><span class="inline-block h-2.5 w-4 rounded-[2px]" style="background:color-mix(in oklab, {band.color} 22%, transparent)" aria-hidden="true"></span>{band.label}</span
      >
    {/if}
  </div>
  <div
    bind:clientWidth={width}
    class="w-full rounded-md outline-none focus-visible:ring-2 focus-visible:ring-accent"
    role="slider"
    tabindex="0"
    aria-label="{ariaLabel}: the week shown. Left and right arrows move between weeks."
    aria-valuemin={weeks[0] ?? 0}
    aria-valuemax={weeks[weeks.length - 1] ?? 0}
    aria-valuenow={weeks[shown] ?? 0}
    aria-valuetext={weeks.length ? describe(shown) : ""}
    onkeydown={onkey}
  >
    <svg {width} {height} aria-hidden="true" class="block touch-pan-y overflow-visible" onpointermove={onpointer} onpointerdown={onpointer}>
      {#each ticks as t (t)}
        <line x1={M.l} x2={width - M.r} y1={y(t)} y2={y(t)} stroke={t === 0 ? SERIES.axis : SERIES.grid} stroke-width="1" />
        <text x={M.l - 6} y={y(t)} dy="0.32em" text-anchor="end" class="tabnum fill-ink-3 text-[10px]">{tick(t)}</text>
      {/each}
      {#if focus !== null || shown !== null}
        <rect x={xs.at(shown) - xs.step / 2} y={M.t} width={xs.step} height={height - M.b - M.t} fill="var(--ll-ink)" opacity="0.05" rx="3" />
      {/if}
      {#each weeks as w, i (`${w}#${i}`)}
        {#if i % step === 0 || i === weeks.length - 1}
          <text x={xs.at(i)} y={height - 6} text-anchor="middle" class="tabnum text-[10px] {i === shown ? 'fill-ink font-semibold' : 'fill-ink-3'}">{w}</text>
        {/if}
      {/each}
      {#if band}
        <path d={bandPath(weeks.map((_, i) => ({ x: xs.at(i), lo: band.lo[i] == null ? null : y(band.lo[i]!), hi: band.hi[i] == null ? null : y(band.hi[i]!) })))} fill={band.color} opacity="0.16" />
      {/if}
      {#if bars}
        {#each bars.values as v, i (i)}
          {#if v !== null && v !== undefined && v > 0}
            <path d={barPath(xs.at(i), v)} fill={bars.color} opacity={i === shown ? 1 : 0.82} />
          {:else if v === 0}
            <line x1={xs.at(i) - barW / 2} x2={xs.at(i) + barW / 2} y1={height - M.b - 1} y2={height - M.b - 1} stroke={bars.color} stroke-width="2" />
          {/if}
        {/each}
      {/if}
      {#each lines as l (l.key)}
        {@const pts = l.values.map((v, i) => ({ x: xs.at(i), y: v === null || v === undefined ? null : y(v) }))}
        <path d={linePath(pts)} fill="none" stroke={l.color} stroke-width="2" stroke-dasharray={l.dashed ? "4 3" : undefined} stroke-linecap="round" stroke-linejoin="round" />
        {#each pts as p, i (i)}
          {#if p.y !== null}
            {@const hollow = !!bars && (bars.values[i] === null || bars.values[i] === undefined)}
            <circle cx={p.x} cy={p.y} r={i === shown ? 4.5 : 3.5} fill={hollow ? "var(--ll-surface)" : l.color} stroke={hollow ? l.color : "var(--ll-surface)"} stroke-width={hollow ? 2 : 1.5} />
          {/if}
        {/each}
      {/each}
    </svg>
  </div>
  <p class="tabnum mt-1.5 min-h-5 text-sm leading-snug text-ink" aria-live="polite" data-testid="chart-readout">{weeks.length ? describe(shown) : ""}</p>
  <details class="mt-1 text-sm" data-testid="chart-numbers">
    <summary class="inline-flex min-h-9 items-center gap-1 text-ink-2"><span class="chev" aria-hidden="true">›</span>Show the numbers</summary>
    <div class="mt-1 overflow-x-auto">
      <table class="tabnum w-full text-sm">
        <thead><tr class="text-left text-xs text-ink-3"><th class="py-1 pr-2 font-semibold">Week</th>{#each columns as c (c.label)}<th class="py-1 pl-2 text-right font-semibold">{c.label}</th>{/each}</tr></thead>
        <tbody>
          {#each weeks as w, i (`${w}#${i}`)}
            <tr class="border-t border-line"><td class="py-1 pr-2">{w}</td>{#each columns as c (c.label)}<td class="py-1 pl-2 text-right">{c.cell(i)}</td>{/each}</tr>
          {/each}
        </tbody>
      </table>
    </div>
  </details>
</figure>
