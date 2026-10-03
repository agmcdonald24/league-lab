<script lang="ts">
  // The unit (the references' player card): the headshot on his team's color, a big headline number with its label,
  // the name (first name small, LAST NAME big), position + team badges, one stat line. `compact` for a grid of cards.
  import type { Snippet } from "svelte";
  import { paneLink, type PaneOptions } from "../lib/pane.svelte";
  import { splitName, team as teamColors } from "../lib/theme";
  import Headshot from "./Headshot.svelte";
  import PosBadge from "./PosBadge.svelte";
  import TeamBadge from "./TeamBadge.svelte";
  import type { RowPlayer } from "./PlayerRow.svelte";

  let {
    player,
    number,
    numberLabel,
    line,
    context,
    href,
    compact = false,
    stacked = false,
    extra,
    pane,
    testid = "player-card",
  }: {
    player: RowPlayer;
    number?: string | number | null;
    numberLabel?: string;
    line?: string | null;
    context?: string | null;
    href?: string | null;
    compact?: boolean;
    stacked?: boolean; // a narrow column (Compare on a phone): the face on top, then the number, then the name
    extra?: Snippet;
    pane?: PaneOptions; // IB-1: a tap on the name opens the research pane (lib/pane.svelte.ts) instead of his page
    testid?: string;
  } = $props();

  const c = $derived(teamColors(player.team));
  const name = $derived(splitName(player.player_name));
</script>

<article
  class="relative overflow-hidden rounded-lg border border-line bg-surface"
  style="box-shadow:var(--ll-shadow);background-image:linear-gradient(135deg, color-mix(in oklab, {c.accent} 26%, transparent) 0%, transparent 55%)"
  data-testid={testid}
>
  <span class="absolute inset-x-0 top-0 h-1" style="background:{c.accent}" aria-hidden="true"></span>
  {#if stacked}
    <div class="flex flex-col items-center p-3 text-center">
      <Headshot url={player.headshot_url} name={player.player_name} team={player.team} size={64} eager />
      {#if number !== undefined}
        {#if numberLabel}<div class="ll-label mt-2">{numberLabel}</div>{/if}
        <div class="text-3xl font-extrabold tracking-tight text-ink" data-testid="card-number">{number ?? "—"}</div>
      {/if}
      {#if name[0]}<div class="mt-1 w-full truncate text-xs leading-tight font-medium text-ink-2">{name[0]}</div>{/if}
      <h2 class="w-full truncate text-lg leading-tight font-extrabold tracking-tight uppercase" data-testid="card-name">
        {#if href}<a class="ll-name" {href} {@attach paneLink(pane ? player.gsis_id : null, pane)}>{name[1]}</a>{:else}{name[1]}{/if}
      </h2>
      <div class="mt-1 flex flex-wrap items-center justify-center gap-1">
        <PosBadge pos={player.position} />
        {#if player.position !== "DEF"}<TeamBadge team={player.team} />{/if}
      </div>
      {#if context}<div class="mt-1 w-full truncate text-xs text-ink-3">{context}</div>{/if}
    </div>
  {:else}
  <div class="flex items-start gap-3 {compact ? 'p-3' : 'p-4'}">
    {#if number !== undefined}
      <div class="shrink-0 text-center">
        {#if numberLabel}<div class="ll-label">{numberLabel}</div>{/if}
        <div class="{compact ? 'text-3xl' : 'text-num'} mt-0.5 font-extrabold tracking-tight text-ink" data-testid="card-number">{number ?? "—"}</div>
      </div>
    {/if}
    <div class="min-w-0 flex-1">
      {#if name[0]}<div class="truncate text-sm leading-tight font-medium text-ink-2">{name[0]}</div>{/if}
      <h2 class="{compact ? 'text-xl' : 'text-2xl'} leading-tight font-extrabold tracking-tight break-words uppercase" data-testid="card-name">
        {#if href}<a class="ll-name" {href} {@attach paneLink(pane ? player.gsis_id : null, pane)}>{name[1]}</a>{:else}{name[1]}{/if}
      </h2>
      <div class="mt-1 flex flex-wrap items-center gap-1.5">
        <PosBadge pos={player.position} size="md" />
        {#if player.position !== "DEF"}<TeamBadge team={player.team} size="md" />{/if}
        {#if context}<span class="text-sm text-ink-3">{context}</span>{/if}
      </div>
    </div>
    <Headshot url={player.headshot_url} name={player.player_name} team={player.team} size={compact ? 56 : 76} eager />
  </div>
  {/if}
  {#if line}
    <p class="border-t border-line px-4 py-2 text-sm leading-snug text-ink-2" data-testid="card-line">{line}</p>
  {/if}
  {#if extra}<div class="border-t border-line px-4 py-3">{@render extra()}</div>{/if}
</article>
