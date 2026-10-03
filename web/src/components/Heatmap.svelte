<script lang="ts">
  // A grid of values (the defense-vs-position matrix: team × position). One hue, more = stronger (sequential; each
  // column on its own scale, since a QB gives up more points than a TE); the number in the cell (ink chosen by the
  // fill); marked cells (your starters' matchups) carry an accent ring and a dot. A scale legend under it; the cells
  // are the table (every value is printed).
  // IB-3: `tones` — a cell's `tone` (favorable / neutral / difficult) is its fill instead (the state color's wash; the
  // cell prints a glyph with the number, so color never carries it alone) and the legend names the three tones.
  import { seqFill, seqInk } from "../lib/theme";
  import { TONE_COLOR, TONE_GLYPH, TONE_WORD, toneWash, type Tone } from "../lib/research";

  export interface HeatCol {
    key: string;
    label: string;
  }
  export interface HeatRow {
    key: string;
    label: string;
  }
  export interface HeatCell {
    v: number | null;
    display?: string;
    title?: string;
    tone?: Tone | null; // IB-3
  }

  let {
    rows,
    cols,
    cell,
    marked = {},
    lowLabel = "fewer",
    highLabel = "more",
    testid = "heatmap",
    tones = false,
  }: {
    rows: HeatRow[];
    cols: HeatCol[];
    cell: (row: string, col: string) => HeatCell;
    marked?: Record<string, string>; // "row|col" → who (the title on the ring)
    lowLabel?: string;
    highLabel?: string;
    testid?: string;
    tones?: boolean; // IB-3: fill by the cell's tone, a tone legend
  } = $props();

  const ranges = $derived(
    Object.fromEntries(
      cols.map((c) => {
        const vs = rows.map((r) => cell(r.key, c.key).v).filter((v): v is number => v !== null);
        return [c.key, vs.length ? [Math.min(...vs), Math.max(...vs)] : [0, 1]];
      }),
    ) as Record<string, [number, number]>,
  );
  const t = (col: string, v: number | null) => {
    if (v === null) return 0;
    const [lo, hi] = ranges[col];
    return hi === lo ? 0.5 : (v - lo) / (hi - lo);
  };
</script>

<div class="min-w-0" data-testid={testid}>
  <table class="w-full table-fixed border-separate text-sm" style="border-spacing:2px">
    <thead>
      <tr>
        <th class="ll-label w-[3.25rem] text-left font-semibold"></th>
        {#each cols as c (c.key)}<th class="ll-label pb-1 text-center font-semibold">{c.label}</th>{/each}
      </tr>
    </thead>
    <tbody>
      {#each rows as r (r.key)}
        <tr data-testid="heat-row" data-row={r.key}>
          <th class="pr-1 text-left text-xs font-bold text-ink-2" scope="row">{r.label}</th>
          {#each cols as c (c.key)}
            {@const x = cell(r.key, c.key)}
            {@const tt = t(c.key, x.v)}
            {@const who = marked[`${r.key}|${c.key}`]}
            <td
              class="tabnum relative h-8 rounded-sm text-center text-xs font-semibold {who ? 'ring-2 ring-accent ring-inset' : ''}"
              style={tones
                ? `background:${toneWash(x.tone ?? null, 30)};color:${x.tone && x.tone !== "neutral" ? TONE_COLOR[x.tone] : x.v === null ? "var(--ll-ink-3)" : "var(--ll-ink)"}`
                : `background:${x.v === null ? "var(--ll-sunken)" : seqFill(0.08 + tt * 0.92)};color:${x.v === null ? "var(--ll-ink-3)" : seqInk(0.08 + tt * 0.92)}`}
              title={[x.title, who].filter(Boolean).join(" · ") || undefined}
              data-testid={who ? "heat-marked" : undefined}
              data-tone={tones ? (x.tone ?? "none") : undefined}
            >
              {x.display ?? (x.v === null ? "—" : x.v.toFixed(1))}
              {#if who}<span class="absolute top-0.5 right-0.5 h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true"></span>{/if}
            </td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>
  {#if tones}
    <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-3" data-testid="heat-legend">
      {#each ["favorable", "neutral", "difficult"] as Tone[] as t (t)}
        <span class="inline-flex items-center gap-1"
          ><span class="inline-block h-3 w-5 rounded-sm text-center text-[9px] leading-3" style="background:{toneWash(t, 30)};color:{TONE_COLOR[t]}">{TONE_GLYPH[t]}</span>{TONE_WORD[t]}</span
        >
      {/each}
    </div>
  {:else}
    <div class="mt-2 flex items-center gap-2 text-xs text-ink-3" data-testid="heat-legend">
      <span>{lowLabel}</span>
      <span class="h-2 flex-1 rounded-sm" style="background:linear-gradient(90deg, {seqFill(0.08)}, {seqFill(1)})"></span>
      <span>{highLabel}</span>
    </div>
  {/if}
</div>
