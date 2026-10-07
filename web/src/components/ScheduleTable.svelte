<script lang="ts">
  // ---- IF-4 (Wave I-F; the I-E review's leftover): the compact schedule — week · opponent · projected — from the
  // player card's `schedule` (the rest-of-season board's number for each week; "—" = no projection, never 0). The matchup
  // rank in words, one direction everywhere ("5th-fewest WR points allowed": lib/words.ts).
  import type { ScheduleRow } from "../lib/api";
  import { pts1 } from "../lib/card"; // ---- IP-4 fix round: the API's rounding (the Projection section's "Week by week" line)
  import { teamLabel } from "../lib/theme";
  import { rankWords } from "../lib/words";

  let { rows, position, testid = "schedule-table" }: { rows: ScheduleRow[]; position: string; testid?: string } = $props();
</script>

<table class="tabnum w-full table-fixed text-sm" data-testid={testid}>
  <thead>
    <tr class="ll-label border-b border-line text-left">
      <th class="w-[3.25rem] py-1 font-semibold">Week</th>
      <th class="py-1 font-semibold">Opponent</th>
      <th class="w-[4.5rem] py-1 text-right font-semibold">Projected</th>
    </tr>
  </thead>
  <tbody>
    {#each rows as r, ix (`${r.week}#${ix}`)}
      <tr class="border-b border-line align-top last:border-0" data-testid="schedule-row">
        <td class="py-1.5 font-semibold text-ink-2">{r.week}</td>
        <td class="py-1.5 leading-snug">
          {#if r.opponent}
            {r.is_home ? "vs" : "at"} {teamLabel(r.opponent)}
            {#if r.opp_rank !== null}<span class="block text-xs text-ink-3">{rankWords(r.opp_rank, position)}</span>{/if}
          {:else}
            <span class="text-ink-3">Bye</span>
          {/if}
        </td>
        <td class="py-1.5 text-right font-semibold">{pts1(r.proj)}</td>
      </tr>
    {/each}
  </tbody>
</table>
