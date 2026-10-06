<script lang="ts">
  // ---- IF-2 (Wave I-F, the decision-quality review § Priority 3): the starter points a trade gains, week by week, for
  // both sides (this week · next · …), so "a four-week win hides a loss this week" is visible. Compact: one row per
  // side; a long window scrolls inside the strip, never the page.
  import type { WeekStrip } from "../../lib/api";
  import { s1 } from "../../lib/decisions";

  let { strip, them = "Them", testid = "week-strip" }: { strip: WeekStrip; them?: string; testid?: string } = $props();
  const tone = (x: number) => (x >= 0.05 ? "text-good" : x <= -0.05 ? "text-bad" : "text-ink-3");
</script>

{#if strip.weeks.length}
  <div class="max-w-full overflow-x-auto" data-testid={testid}>
    <table class="text-sm tabnum">
      <caption class="sr-only">Starter points gained each week</caption>
      <thead>
        <tr class="text-left text-ink-3">
          <th class="py-0.5 pr-2 font-normal">Week</th>
          {#each strip.weeks as w, ix (`${w}#${ix}`)}<th class="px-1.5 py-0.5 text-right font-normal">{w}</th>{/each}
        </tr>
      </thead>
      <tbody>
        <tr data-testid="strip-mine">
          <th class="py-0.5 pr-2 text-left font-semibold">You</th>
          {#each strip.mine as x, i (i)}<td class="px-1.5 py-0.5 text-right font-semibold {tone(x)}">{s1(x)}</td>{/each}
        </tr>
        <tr data-testid="strip-theirs">
          <th class="max-w-[7rem] truncate py-0.5 pr-2 text-left font-normal text-ink-2">{them}</th>
          {#each strip.theirs as x, i (i)}<td class="px-1.5 py-0.5 text-right {tone(x)}">{s1(x)}</td>{/each}
        </tr>
      </tbody>
    </table>
  </div>
{/if}
