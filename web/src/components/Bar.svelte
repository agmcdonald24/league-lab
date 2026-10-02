<script lang="ts">
  // A comparison bar (the free-agent screens' meters): label on the left, the value on the right, the bar under
  // them. One baseline: 0 at the left, or — when `min` < 0 — 0 in the middle and the bar grows either way
  // (over / under). `mark` draws a thin tick (a yardstick: the league average, the top-12 average).
  // Marks per docs/DESIGN.md § Charts: ≤ 8 px thick here, square at the baseline, rounded at the data end.
  import type { Snippet } from "svelte";

  let {
    label,
    labelSnippet,
    value,
    max,
    min = 0,
    display,
    color = "var(--ll-series-1)",
    negColor,
    mark = null,
    markLabel,
    thick = 8,
    testid,
  }: {
    label?: string;
    labelSnippet?: Snippet;
    value: number | null | undefined;
    max: number;
    min?: number;
    display?: string;
    color?: string;
    negColor?: string;
    mark?: number | null;
    markLabel?: string;
    thick?: number;
    testid?: string;
  } = $props();

  const span = $derived(Math.max(1e-9, max - min));
  const zero = $derived(min < 0 ? (-min / span) * 100 : 0);
  const v = $derived(value === null || value === undefined || Number.isNaN(value) ? null : Math.max(min, Math.min(max, value)));
  const left = $derived(v === null ? zero : v >= 0 ? zero : zero - (-v / span) * 100);
  const width = $derived(v === null ? 0 : (Math.abs(v) / span) * 100);
  const fill = $derived(v !== null && v < 0 && negColor ? negColor : color);
  const markAt = $derived(mark === null ? null : ((Math.max(min, Math.min(max, mark)) - min) / span) * 100);
  const radius = $derived(v !== null && v < 0 ? "4px 0 0 4px" : "0 4px 4px 0");
</script>

<div class="min-w-0" data-testid={testid ?? "bar"}>
  <div class="flex items-baseline justify-between gap-2 text-sm">
    <span class="min-w-0 truncate text-ink-2">{#if labelSnippet}{@render labelSnippet()}{:else}{label}{/if}</span>
    <span class="tabnum shrink-0 font-semibold text-ink" data-testid="bar-value">{display ?? (value === null || value === undefined ? "—" : value)}</span>
  </div>
  <div class="relative mt-1 rounded-sm bg-sunken" style="height:{thick}px" role="presentation">
    {#if min < 0}<span class="absolute inset-y-[-2px] w-px bg-line-strong" style="left:{zero}%" aria-hidden="true"></span>{/if}
    {#if v !== null}
      <span class="absolute inset-y-0" style="left:{left}%;width:{width}%;background:{fill};border-radius:{radius}" aria-hidden="true"></span>
    {/if}
    {#if markAt !== null}
      <span class="absolute inset-y-[-3px] w-0.5 rounded bg-ink" style="left:calc({markAt}% - 1px)" title={markLabel} aria-hidden="true"></span>
    {/if}
  </div>
</div>
