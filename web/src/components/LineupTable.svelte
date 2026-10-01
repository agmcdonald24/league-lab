<script lang="ts">
  import type { LineupRow } from "../lib/api";
  import { withContext, type LinkContext } from "../lib/md";

  let { rows, full = false, ctx, testid }: { rows: LineupRow[]; full?: boolean; ctx: LinkContext; testid: string } = $props();
  // injury / lock / empty-slot flags: a column only when some row has one (round-2 convention 5)
  const showFlag = $derived(rows.some((r) => r.flag));
  const num = (v: number | null) => (v === null || v === undefined ? "—" : v.toFixed(2));
</script>

<table class="w-full table-fixed border-collapse text-[15px]" data-testid={testid}>
  <thead>
    <tr class="border-b border-zinc-200 text-left text-[11px] tracking-wide text-zinc-500 uppercase dark:border-zinc-800 dark:text-zinc-400">
      <th class="w-[4.75rem] py-1.5 pr-1 font-medium">Slot</th>
      <th class="py-1.5 pr-1 font-medium">Player</th>
      <th class="w-[3.5rem] py-1.5 text-right font-medium">Proj</th>
      {#if full}<th class="w-[3.75rem] py-1.5 text-right font-medium">Margin</th>{/if}
      {#if showFlag}<th class="w-[5.5rem] py-1.5 pl-2 font-medium">Flag</th>{/if}
    </tr>
  </thead>
  <tbody>
    {#each rows as r, i (i)}
      <tr class="border-b border-zinc-100 align-top last:border-0 dark:border-zinc-800/70">
        <td class="py-2 pr-1 text-[13px] text-zinc-500 dark:text-zinc-400">{r.slot}</td>
        <td class="py-2 pr-1 leading-snug break-words">
          {#if r.gsis_id && r.player_name}
            <a class="ll-link" href={withContext(`/player/${r.gsis_id}`, ctx)}>{r.player_name}</a>
          {:else}
            {r.player_name ?? "—"}
          {/if}
        </td>
        <td class="tabnum py-2 text-right">{num(r.value)}</td>
        {#if full}<td class="tabnum py-2 text-right text-zinc-600 dark:text-zinc-300">{r.margin === null ? "" : r.margin.toFixed(2)}</td>{/if}
        {#if showFlag}<td class="py-2 pl-2 text-[12px] leading-snug text-amber-700 dark:text-amber-400">{r.flag}</td>{/if}
      </tr>
    {/each}
  </tbody>
</table>
