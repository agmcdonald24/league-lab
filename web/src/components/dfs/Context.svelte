<script lang="ts">
  // ---- IN-4 (Wave I-N): a player's context beside his projection — one chip per signal with a tone (favourable /
  // difficult), its sentence in the title; a chip with a dashed border is NOT in the projection (the legend says so).
  // `full`: every signal as its sentence with "In the projection" / "Not in the projection" (the row's detail, a lineup).
  import { chipWords, type Signal } from "./dfs";

  let { signals = [], full = false, testid = "dfs-context" }: { signals?: Signal[]; full?: boolean; testid?: string } = $props();
  // ---- IO-1 fix round: a likely corner call shows as information (its quarter), never by a tone
  const shown = $derived(full ? signals : signals.filter((s) => s.tone === "favorable" || s.tone === "difficult" || s.signal === "weather" || (s.signal === "corner" && !!s.quarter)));
  // ---- IO-1 (Wave I-O): the corner keeps its words and its grade but never a colour (fix round: always neutral)
  const quiet = (s: Signal) => s.signal === "corner";
  const toneClass = (s: Signal) =>
    quiet(s) ? "text-ink-2 border-line-strong" : s.tone === "favorable" ? "text-good border-good" : s.tone === "difficult" ? "text-bad border-bad" : "text-ink-2 border-line-strong";
  const title = (s: Signal) => `${s.words} ${s.projection_words}.${s.graded ? ` ${s.graded}` : ""}`;
</script>

{#if full}
  {#if shown.length}
    <ul class="space-y-1 text-sm" data-testid={testid}>
      {#each shown as s (s.signal)}
        <li data-testid="dfs-signal" data-signal={s.signal}>
          <span class="font-semibold {quiet(s) ? 'text-ink' : s.tone === 'favorable' ? 'text-good' : s.tone === 'difficult' ? 'text-bad' : 'text-ink'}">{s.label}:</span>
          <span class="text-ink-2">{s.words}</span>
          <span class="text-xs whitespace-nowrap text-ink-3"> · {s.projection_words}</span>
          {#if s.graded}<span class="block text-xs text-ink-3" data-testid="dfs-signal-graded">{s.graded}</span>{/if}
        </li>
      {/each}
    </ul>
  {:else}
    <p class="text-sm text-ink-3" data-testid={testid}>No context signal for him this week.</p>
  {/if}
{:else if shown.length}
  <span class="flex flex-wrap gap-1" data-testid={testid}>
    {#each shown as s (s.signal)}
      <span
        class="inline-flex items-center rounded-full border px-1.5 py-px text-xs font-semibold whitespace-nowrap {toneClass(s)} {s.in_projection ? '' : 'border-dashed'}"
        title={title(s)}
        aria-label={`${s.label}: ${title(s)}`}
        data-testid="dfs-chip"
        data-signal={s.signal}
        data-outside={s.in_projection ? "no" : "yes"}
        data-graded={s.graded_effect ?? ""}>{chipWords(s)}</span
      >
    {/each}
  </span>
{:else}
  <span class="text-xs text-ink-3" data-testid={testid}>—</span>
{/if}
