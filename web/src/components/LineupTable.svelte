<script lang="ts">
  import type { LineupRow } from "../lib/api";
  import { withContext, type LinkContext } from "../lib/md";
  import { AVAILABILITY_CHIPS } from "../lib/shapes";

  let { rows, full = false, ctx, testid }: { rows: LineupRow[]; full?: boolean; ctx: LinkContext; testid: string } = $props();
  // injury / lock / empty-slot flags: a column only when some row has one (round-2 convention 5)
  const showFlag = $derived(rows.some((r) => r.flag));
  const num = (v: number | null) => (v === null || v === undefined ? "—" : v.toFixed(2));
  // I0-A: the availability overlay's reason for an OUT / DOUBTFUL / IR chip ("Out (ankle) · ESPN, Oct 2 2:35 PM ET")
  const reason = (r: LineupRow) => (r as LineupRow & { reason?: string | null }).reason ?? "";
</script>

<table class="w-full table-fixed border-collapse text-base" data-testid={testid}>
  <thead>
    <tr class="ll-label border-b border-line text-left">
      <th class="w-[4.75rem] py-1.5 pr-1 font-medium">Slot</th>
      <th class="py-1.5 pr-1 font-medium">Player</th>
      <th class="w-[3.5rem] py-1.5 text-right font-medium">Proj</th>
      {#if full}<th class="w-[3.75rem] py-1.5 text-right font-medium">Margin</th>{/if}
      {#if showFlag}<th class="w-[5.5rem] py-1.5 pl-2 font-medium">Flag</th>{/if}
    </tr>
  </thead>
  <tbody>
    {#each rows as r, i (i)}
      <tr class="border-b border-line align-top last:border-0">
        <td class="py-2 pr-1 text-sm font-semibold text-ink-3">{r.slot}</td>
        <td class="py-2 pr-1 leading-snug break-words">
          {#if r.gsis_id && r.player_name}
            <a class="ll-link" href={withContext(`/player/${r.gsis_id}`, ctx)}>{r.player_name}</a>
          {:else}
            {r.player_name ?? "—"}
          {/if}
          {#if full && reason(r)}<div class="text-xs leading-snug text-ink-3" data-testid="avail-reason">{reason(r)}</div>{/if}
        </td>
        <td class="tabnum py-2 text-right font-semibold">{num(r.value)}</td>
        {#if full}<td class="tabnum py-2 text-right text-ink-2">{r.margin === null ? "" : r.margin.toFixed(2)}</td>{/if}
        {#if showFlag}<td class="py-2 pl-2 text-xs leading-snug text-warn"
            >{#if AVAILABILITY_CHIPS.has(r.flag)}<span
                class="inline-block rounded border border-current px-1 py-px text-[0.7rem] font-bold tracking-wide"
                title={reason(r)}
                data-testid="avail-chip">{r.flag}</span
              >{:else}{r.flag}{/if}</td
          >{/if}
      </tr>
    {/each}
  </tbody>
</table>
