<script lang="ts">
  // IA-2: the weeks a trade is priced over — This week · Next 4 · Rest of season · Playoffs — as one segmented row of
  // four equal cells (at 375 px "Rest of season" wraps inside its cell; the row never scrolls sideways), and one line
  // under it saying why those weeks (with the span once the answer names it: "Weeks 4–16: every week left …").
  import type { TradeWindow } from "../../lib/api";
  import { WINDOW_TABS, windowWhy } from "../../lib/decisions";

  let { current, span = null, onpick }: { current: TradeWindow; span?: string | null; onpick: (w: TradeWindow) => void } = $props();
</script>

<section class="space-y-1.5" data-testid="window-control">
  <div class="grid grid-cols-4 gap-1 rounded-md border border-line bg-surface p-1" role="group" aria-label="Weeks to count" data-testid="window">
    {#each WINDOW_TABS as t (t.key)}
      <button
        type="button"
        class="min-h-10 rounded-sm px-1.5 text-sm leading-tight font-semibold transition-colors {current === t.key ? 'bg-accent text-on-accent' : 'text-ink-2 hover:bg-raised hover:text-ink'}"
        aria-pressed={current === t.key}
        onclick={() => onpick(t.key)}
        data-testid={`window-${t.key}`}>{t.label}</button
      >
    {/each}
  </div>
  <p class="text-sm text-ink-2" data-testid="window-caption">{windowWhy(current, span)}</p>
</section>
