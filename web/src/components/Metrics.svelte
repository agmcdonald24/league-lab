<script lang="ts">
  import type { Metric } from "../lib/api";

  let { metrics }: { metrics: Metric[] } = $props();
  let open = $state<string | null>(null);
  const cols = $derived(metrics.length >= 4 ? "grid-cols-2" : metrics.length === 3 ? "grid-cols-3" : "grid-cols-2");
</script>

<div class="grid {cols} gap-2" data-testid="metrics">
  {#each metrics as m (m.label)}
    <button
      type="button"
      class="rounded-xl bg-zinc-100/80 px-3 py-2 text-left dark:bg-zinc-800/60"
      aria-expanded={m.help ? open === m.label : undefined}
      disabled={!m.help}
      onclick={() => (open = open === m.label ? null : m.label)}
    >
      <div class="text-[11px] font-medium tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
        {m.label}{#if m.help}<span class="ml-1 text-zinc-400" aria-hidden="true">ⓘ</span>{/if}
      </div>
      <div class="tabnum text-xl leading-tight font-semibold">{m.value ?? "—"}</div>
      {#if m.delta}
        <div
          class="tabnum text-xs font-medium {m.trend === 'up'
            ? 'text-green-700 dark:text-green-400'
            : m.trend === 'down'
              ? 'text-red-700 dark:text-red-400'
              : 'text-zinc-500'}"
        >
          {m.trend === "up" ? "▲" : m.trend === "down" ? "▼" : ""}
          {m.delta}
        </div>
      {/if}
      {#if m.help && open === m.label}
        <div class="mt-1 text-xs leading-snug text-zinc-600 dark:text-zinc-300">{m.help}</div>
      {/if}
    </button>
  {/each}
</div>
