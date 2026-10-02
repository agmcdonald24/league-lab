<script lang="ts">
  // The API's metric blocks (label · value · delta · help) as stat tiles; a tile with help opens it on tap.
  import type { Metric } from "../lib/api";

  let { metrics }: { metrics: Metric[] } = $props();
  let open = $state<string | null>(null);
  const cols = $derived(metrics.length >= 4 ? "grid-cols-2 sm:grid-cols-4" : metrics.length === 3 ? "grid-cols-3" : "grid-cols-2");
</script>

<div class="grid {cols} gap-2" data-testid="metrics">
  {#each metrics as m (m.label)}
    <button
      type="button"
      class="min-w-0 rounded-md bg-raised px-3 py-2.5 text-left"
      aria-expanded={m.help ? open === m.label : undefined}
      disabled={!m.help}
      onclick={() => (open = open === m.label ? null : m.label)}
    >
      <div class="ll-label truncate">
        {m.label}{#if m.help}<span class="ml-1 text-ink-3" aria-hidden="true">ⓘ</span>{/if}
      </div>
      <div class="mt-0.5 text-2xl leading-tight font-bold tracking-tight">{m.value ?? "—"}</div>
      {#if m.delta}
        <div class="tabnum text-xs font-semibold {m.trend === 'up' ? 'text-good' : m.trend === 'down' ? 'text-bad' : 'text-ink-3'}">
          {m.trend === "up" ? "▲" : m.trend === "down" ? "▼" : ""}
          {m.delta}
        </div>
      {/if}
      {#if m.help && open === m.label}
        <div class="mt-1 text-xs leading-snug text-ink-2">{m.help}</div>
      {/if}
    </button>
  {/each}
</div>
