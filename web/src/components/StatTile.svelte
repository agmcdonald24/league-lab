<script lang="ts">
  // A number with its label (the dataviz stat tile): label (small uppercase) · value (big, proportional figures) ·
  // an optional delta (signed; ▲ / ▼ and the good / bad color by whether up is good) · an optional caption.
  let {
    label,
    value,
    unit,
    delta = null,
    upIsGood = true,
    caption,
    size = "md",
    accent,
    testid,
  }: {
    label: string;
    value: string | number | null | undefined;
    unit?: string;
    delta?: number | null;
    upIsGood?: boolean;
    caption?: string | null;
    size?: "sm" | "md" | "lg";
    accent?: string | null;
    testid?: string;
  } = $props();

  const shown = $derived(value === null || value === undefined || value === "" ? "—" : String(value));
  const good = $derived(delta === null || delta === 0 ? null : delta > 0 === upIsGood);
  const deltaText = $derived(delta === null ? "" : `${delta > 0 ? "+" : delta < 0 ? "−" : ""}${Math.abs(delta).toFixed(1)}`);
</script>

<div class="relative min-w-0 rounded-md bg-raised px-3 py-2.5" data-testid={testid ?? "stat-tile"}>
  {#if accent}<span class="absolute inset-x-3 top-0 h-0.5 rounded-b" style="background:{accent}" aria-hidden="true"></span>{/if}
  <div class="ll-label truncate">{label}</div>
  <div class="mt-0.5 flex items-baseline gap-1">
    <span class="font-bold tracking-tight text-ink {size === 'lg' ? 'text-num' : size === 'sm' ? 'text-lg' : 'text-2xl'} leading-none" data-testid="stat-value"
      >{shown}</span
    >
    {#if unit && shown !== "—"}<span class="text-sm text-ink-3">{unit}</span>{/if}
  </div>
  {#if delta !== null && delta !== undefined}
    <div class="tabnum mt-1 text-xs font-semibold {good === null ? 'text-ink-3' : good ? 'text-good' : 'text-bad'}">
      {delta > 0 ? "▲" : delta < 0 ? "▼" : "■"}
      {deltaText}
    </div>
  {/if}
  {#if caption}<div class="mt-1 text-xs leading-snug text-ink-3">{caption}</div>{/if}
</div>
