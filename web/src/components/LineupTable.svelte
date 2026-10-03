<script lang="ts">
  import type { LineupRow } from "../lib/api";
  import { withContext, type LinkContext } from "../lib/md";
  import { shortName } from "../lib/names.svelte";
  import { paneLink, type PaneOptions } from "../lib/pane.svelte";
  import { AVAILABILITY_CHIPS } from "../lib/shapes";
  import Headshot from "./Headshot.svelte";

  // IB-1 (Wave I-B): `pane` — a tap on a name opens the research pane (lib/pane.svelte.ts) with these options
  let {
    rows,
    full = false,
    ctx,
    testid,
    pane,
  }: { rows: LineupRow[]; full?: boolean; ctx: LinkContext; testid: string; pane?: (r: LineupRow) => PaneOptions } = $props();
  // injury / lock / empty-slot flags: under the name (IA-1; was a column only when some row had one)
  const num = (v: number | null) => (v === null || v === undefined ? "—" : v.toFixed(2));
  // I0-A: the availability overlay's reason for an OUT / DOUBTFUL / IR chip ("Out (ankle) · ESPN, Oct 2 2:35 PM ET")
  const reason = (r: LineupRow) => (r as LineupRow & { reason?: string | null }).reason ?? "";
  // IA-1: "J. Jefferson" under 640 px (unique initials within this list; a defense keeps its name), the whole name above
  const names = $derived(rows.map((r) => r.player_name));
</script>

<table class="w-full table-fixed border-collapse text-base" data-testid={testid}>
  <thead>
    <tr class="ll-label border-b border-line text-left">
      <th class="w-[4.25rem] py-1.5 pr-1 font-medium sm:w-[4.75rem]">Slot</th>
      <th class="py-1.5 pr-1 font-medium">Player</th>
      <th class="w-[3.25rem] py-1.5 text-right font-medium">Proj</th>
      {#if full}<th class="hidden w-[3.75rem] py-1.5 text-right font-medium sm:table-cell">Margin</th>{/if}
    </tr>
  </thead>
  <tbody>
    {#each rows as r, i (i)}
      <tr class="border-b border-line align-middle last:border-0">
        <td class="py-1.5 pr-1 text-sm font-semibold text-ink-3">{r.slot}</td>
        <td class="py-1.5 pr-1 leading-snug">
          <div class="flex min-w-0 items-center gap-2">
            {#if r.player_name}<Headshot url={r.headshot_url ?? null} team={r.team ?? null} size={32} />{/if}
            <div class="min-w-0 break-words">
              {#if r.gsis_id && r.player_name}
                <a
                  class="ll-link"
                  href={withContext(`/player/${r.gsis_id}`, ctx)}
                  aria-label={r.player_name}
                  data-testid="lineup-name"
                  {@attach paneLink(pane ? r.gsis_id : null, pane?.(r))}
                  ><span class="sm:hidden" data-testid="short-name">{shortName(r.player_name, r.position, names)}</span><span class="hidden sm:inline"
                    >{r.player_name}</span
                  ></a
                >
              {:else}
                {r.player_name ?? "—"}
              {/if}
              <!-- IA-1: the flag (OUT / IR chip, locked, an injury tag) under the name: the name keeps the row's width on a phone -->
              {#if r.flag}<div class="text-xs leading-snug text-warn" data-testid="lineup-flag"
                  >{#if AVAILABILITY_CHIPS.has(r.flag)}<span
                      class="inline-block rounded border border-current px-1 py-px text-[0.7rem] font-bold tracking-wide"
                      title={reason(r)}
                      data-testid="avail-chip">{r.flag}</span
                    >{:else}{r.flag}{/if}</div
                >{/if}
              {#if full && r.margin !== null}<div class="tabnum text-xs text-ink-3 sm:hidden" data-testid="margin-line">margin {r.margin.toFixed(2)}</div>{/if}
              {#if full && reason(r)}<div class="text-xs leading-snug text-ink-3" data-testid="avail-reason">{reason(r)}</div>{/if}
            </div>
          </div>
        </td>
        <td class="tabnum py-1.5 text-right font-semibold">{num(r.value)}</td>
        {#if full}<td class="tabnum hidden py-1.5 text-right text-ink-2 sm:table-cell">{r.margin === null ? "" : r.margin.toFixed(2)}</td>{/if}
      </tr>
    {/each}
  </tbody>
</table>
