<script lang="ts">
  // A tiny trend (a stat tile's last games): the de-emphasis ink, the last point in the accent.
  import { extent, linear, linePath } from "../lib/chart";

  let { values, width = 72, height = 22 }: { values: (number | null)[]; width?: number; height?: number } = $props();
  const [lo, hi] = $derived(extent(values));
  const x = $derived(linear(0, Math.max(1, values.length - 1), 2, width - 4));
  const y = $derived(linear(lo, hi === lo ? lo + 1 : hi, height - 3, 3));
  const pts = $derived(values.map((v, i) => ({ x: x(i), y: v === null ? null : y(v) })));
  const lastI = $derived(values.map((v, i) => (v === null ? -1 : i)).reduce((a, b) => Math.max(a, b), -1));
</script>

<svg {width} {height} aria-hidden="true" class="block overflow-visible">
  <path d={linePath(pts)} fill="none" stroke="var(--ll-ink-3)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
  {#if lastI >= 0 && pts[lastI].y !== null}<circle cx={pts[lastI].x} cy={pts[lastI].y} r="2.5" fill="var(--ll-series-1)" />{/if}
</svg>
