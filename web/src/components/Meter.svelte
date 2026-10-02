<script lang="ts">
  // A share against a whole (target share, snap share, a chance): the fill in one hue on a lighter step of the same
  // hue, so the whole bar reads as one thing. `value` is 0–1.
  let {
    label,
    value,
    display,
    color = "var(--ll-series-1)",
    testid,
  }: { label: string; value: number | null | undefined; display?: string; color?: string; testid?: string } = $props();

  const pct = $derived(value === null || value === undefined || Number.isNaN(value) ? null : Math.max(0, Math.min(1, value)) * 100);
</script>

<div class="min-w-0" data-testid={testid ?? "meter"}>
  <div class="flex items-baseline justify-between gap-2 text-sm">
    <span class="min-w-0 truncate text-ink-2">{label}</span>
    <span class="tabnum shrink-0 font-semibold text-ink">{display ?? (pct === null ? "—" : `${Math.round(pct)}%`)}</span>
  </div>
  <div class="mt-1 h-2 overflow-hidden rounded-sm" style="background:color-mix(in oklab, {color} 20%, transparent)">
    {#if pct !== null}<div class="h-full rounded-r-sm" style="width:{pct}%;background:{color}"></div>{/if}
  </div>
</div>
