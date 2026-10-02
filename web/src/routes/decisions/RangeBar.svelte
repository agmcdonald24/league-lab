<script lang="ts">
  // A projection and its range on one track (plan G4): the floor–ceiling (8 weeks in 10) as a thin line, most weeks
  // (half his weeks) as the band, the projection as the tick. One scale for a whole list (`max`), 0 at the left.
  let {
    value,
    p10 = null,
    p25 = null,
    p75 = null,
    p90 = null,
    max,
    testid = "range-bar",
  }: { value: number | null; p10?: number | null; p25?: number | null; p75?: number | null; p90?: number | null; max: number; testid?: string } =
    $props();

  const at = (v: number) => `${Math.max(0, Math.min(100, (v / Math.max(1e-9, max)) * 100))}%`;
  const w = (a: number, b: number) => `${Math.max(0, Math.min(100, ((b - a) / Math.max(1e-9, max)) * 100))}%`;
</script>

<div class="relative h-2.5 w-full rounded-sm bg-sunken" data-testid={testid} role="presentation">
  {#if p10 != null && p90 != null}
    <span class="absolute top-1/2 h-0.5 -translate-y-1/2 rounded" style="left:{at(p10)};width:{w(p10, p90)};background:color-mix(in oklab, var(--ll-series-1) 45%, transparent)"></span>
  {/if}
  {#if p25 != null && p75 != null}
    <span class="absolute inset-y-0.5 rounded-sm" style="left:{at(p25)};width:{w(p25, p75)};background:color-mix(in oklab, var(--ll-series-1) 70%, transparent)"></span>
  {/if}
  {#if value != null}
    <span class="absolute -inset-y-0.5 w-0.5 rounded bg-ink" style="left:calc({at(value)} - 1px)"></span>
  {/if}
</div>
