<script lang="ts">
  // One player in a list: headshot (a silhouette without one) · name · position + team badges · one line of context
  // · an optional headline number on the right. "Yours" gets the accent edge. With `onselect` a tap on the row picks
  // him for the detail pane (list + detail); a tap on the name opens his card.
  import type { Snippet } from "svelte";
  import { paneLink, type PaneOptions } from "../lib/pane.svelte";
  import Headshot from "./Headshot.svelte";
  import PosBadge from "./PosBadge.svelte";
  import TeamBadge from "./TeamBadge.svelte";

  export interface RowPlayer {
    gsis_id?: string | null;
    player_name: string;
    position?: string | null;
    team?: string | null;
    headshot_url?: string | null;
  }

  let {
    player,
    href,
    context,
    contextSnippet,
    value,
    valueLabel,
    trailing,
    rank,
    yours = false,
    selected = false,
    onselect,
    pane,
    testid = "player-row",
  }: {
    player: RowPlayer;
    href?: string | null;
    context?: string | null;
    contextSnippet?: Snippet;
    value?: string | number | null;
    valueLabel?: string;
    trailing?: Snippet;
    rank?: number | string | null;
    yours?: boolean;
    selected?: boolean;
    onselect?: () => void;
    pane?: PaneOptions; // IB-1: a tap on the name opens the research pane (lib/pane.svelte.ts) instead of his page
    testid?: string;
  } = $props();
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div
  class="relative flex min-h-14 items-center gap-3 px-3 py-2 {selected ? 'bg-accent-soft' : ''} {onselect ? 'cursor-pointer hover:bg-raised' : ''}"
  onclick={(e) => {
    if (!onselect || (e.target as Element).closest("a")) return; // the name is a link: it opens his card
    onselect();
  }}
  data-testid={testid}
  data-gsis={player.gsis_id ?? undefined}
  data-yours={yours ? "1" : undefined}
>
  {#if yours || selected}<span class="absolute inset-y-1 left-0 w-1 rounded-r bg-accent" aria-hidden="true"></span>{/if}
  {#if rank !== undefined && rank !== null}<span class="tabnum w-6 shrink-0 text-right text-sm font-semibold text-ink-3">{rank}</span>{/if}
  <Headshot url={player.headshot_url} name={player.player_name} team={player.team} size={40} />
  <div class="min-w-0 flex-1">
    <div class="flex min-w-0 items-center gap-1.5">
      {#if href}
        <a class="ll-name truncate text-base font-semibold" {href} {@attach paneLink(pane ? player.gsis_id : null, pane)}>{player.player_name}</a>
      {:else}
        <span class="truncate text-base font-semibold">{player.player_name}</span>
      {/if}
      {#if yours}<span class="shrink-0 rounded-sm bg-accent-soft px-1 text-[10px] font-bold tracking-wide text-accent uppercase">yours</span>{/if}
    </div>
    <div class="mt-0.5 flex min-w-0 items-center gap-1.5 text-sm text-ink-3">
      <PosBadge pos={player.position} />
      {#if player.position !== "DEF"}<TeamBadge team={player.team} />{/if}
      <span class="min-w-0 truncate">{#if contextSnippet}{@render contextSnippet()}{:else}{context ?? ""}{/if}</span>
    </div>
  </div>
  {#if trailing}
    <div class="shrink-0">{@render trailing()}</div>
  {:else if value !== undefined}
    <div class="shrink-0 text-right">
      <div class="text-xl leading-none font-bold text-ink" data-testid="row-value">{value ?? "—"}</div>
      {#if valueLabel}<div class="mt-0.5 text-[10px] font-semibold tracking-wide text-ink-3 uppercase">{valueLabel}</div>{/if}
    </div>
  {/if}
</div>
