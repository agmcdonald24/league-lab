<script lang="ts">
  // IR-4 (Wave I-R): what the numbers are and what has been checked — one quiet line (api provenance.py; WORDS.md
  // § "IR-4"); the starter caveats under it, each a sentence (a withheld or softened verdict says why). No colour, no
  // warning: what it is and what has been checked.
  import type { DecisionCaveat, Provenance } from "../../lib/api";

  let { p, caveats = [], testid = "provenance" }: { p?: Provenance | null; caveats?: DecisionCaveat[] | null; testid?: string } = $props();
</script>

{#if p?.words || caveats?.length}
  <div class="space-y-1 text-xs leading-snug text-ink-3" data-testid={testid}>
    {#each caveats ?? [] as c, ix (`${c.kind}#${c.team}#${ix}`)}
      <p class="text-sm text-ink-2" data-testid={`${testid}-caveat`} data-effect={c.effect}>{c.words}</p>
    {/each}
    {#if p?.words}<p data-testid={`${testid}-line`} data-status={p.status}>{p.words}</p>{/if}
  </div>
{/if}
