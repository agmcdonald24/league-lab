<script lang="ts">
  // IP-4: this week's projection as a range — the low-end to high-end outcome (one week in ten below / above) as the
  // track's band, the typical range (the middle half) thicker inside it, the projection a tick in ink. The numbers are
  // printed under it (the bar never carries a value alone).
  import { pts1 } from "../../lib/card";
  import { fmt } from "../../lib/theme";

  let {
    proj,
    p10,
    p25 = null,
    p75 = null,
    p90,
    color = "var(--ll-series-1)",
    testid = "range-bar",
  }: { proj: number | null; p10: number | null; p25?: number | null; p75?: number | null; p90: number | null; color?: string; testid?: string } = $props();

  const max = $derived(Math.max(10, Math.ceil(((p90 ?? proj ?? 10) * 1.12) / 5) * 5));
  const at = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  const has = $derived(p10 !== null && p90 !== null);
</script>

{#if has || proj !== null}
  <div class="min-w-0" data-testid={testid}>
    <div class="relative h-3 rounded-sm bg-sunken" role="presentation">
      {#if has}
        <span class="absolute inset-y-0 rounded-sm" style="left:{at(p10!)};width:calc({at(p90!)} - {at(p10!)});background:color-mix(in oklab, {color} 34%, transparent)" aria-hidden="true"></span>
      {/if}
      {#if p25 !== null && p75 !== null}
        <span class="absolute inset-y-0 rounded-sm" style="left:{at(p25)};width:calc({at(p75)} - {at(p25)});background:{color}" aria-hidden="true"></span>
      {/if}
      {#if proj !== null}
        <span class="absolute -inset-y-1 w-[3px] rounded-full bg-ink" style="left:calc({at(proj)} - 1.5px)" aria-hidden="true"></span>
      {/if}
    </div>
    {#if has}
      <div class="tabnum mt-1.5 flex items-baseline justify-between gap-2 text-xs text-ink-3">
        <span><strong class="font-semibold text-ink-2">{pts1(p10)}</strong> low-end</span>
        {#if p25 !== null && p75 !== null}<span>typical <strong class="font-semibold text-ink-2">{fmt.whole(p25)}–{fmt.whole(p75)}</strong></span>{/if}
        <span><strong class="font-semibold text-ink-2">{pts1(p90)}</strong> high-end</span>
      </div>
    {/if}
  </div>
{/if}
