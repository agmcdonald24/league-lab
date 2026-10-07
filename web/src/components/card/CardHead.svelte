<script lang="ts">
  // IP-4 (Wave I-P): the player card's head — a card, not a header. His picture on his team's colour (the card's edge
  // and the photo's field), the name (first name small, LAST NAME big), position, team and status, this week's game
  // and kickoff; then ONE headline number — this week's projection — with its range, and his value in the scoring on
  // screen. Every number is the card's own (lib/card.ts headRange / nextGame / headValue): the head adds no new one.
  import type { PlayerCard } from "../../lib/api";
  import { headRange, headValue, nextGame, projLabel, statusTone } from "../../lib/card";
  import { fmt, onColor, splitName, team as teamColors, teamLabel } from "../../lib/theme";
  import Headshot from "../Headshot.svelte";
  import PosBadge from "../PosBadge.svelte";
  import TeamBadge from "../TeamBadge.svelte";
  import RangeBar from "./RangeBar.svelte";

  let {
    d,
    line = null,
    scoring,
    compact = false,
    testid = "player-header",
  }: { d: PlayerCard; line?: string | null; scoring: string; compact?: boolean; testid?: string } = $props();

  const c = $derived(teamColors(d.team));
  const name = $derived(splitName(d.player_name));
  const range = $derived(headRange(d));
  const game = $derived(nextGame(d));
  const value = $derived(headValue(d));
  const tone = $derived(statusTone(d.injury_status));
  const shade = $derived(`color-mix(in oklab, ${c.primary} 62%, #05070b)`);
  const vs = $derived(game?.opponent ? `${game.home ? "vs" : "at"} ${teamLabel(game.opponent)}` : game ? "Bye" : null);
  let valueOpen = $state(false);
</script>

<article
  class="relative overflow-hidden rounded-xl border border-line bg-surface"
  style="box-shadow:var(--ll-shadow)"
  data-testid={testid}
  data-team={teamLabel(d.team) ?? ""}
>
  <!-- the card's edge: his team's colour -->
  <span class="absolute inset-y-0 left-0 z-10 w-1.5" style="background:{c.accent}" aria-hidden="true"></span>
  <div class="grid {compact ? 'grid-cols-[6.5rem_minmax(0,1fr)]' : 'grid-cols-[7.5rem_minmax(0,1fr)] sm:grid-cols-[10rem_minmax(0,1fr)] xl:grid-cols-[12rem_minmax(0,1fr)_minmax(0,27rem)]'}">
    <!-- the photo on his team's field (no text sits on it) -->
    <div
      class="relative flex items-end justify-center overflow-hidden pt-4"
      style="background:linear-gradient(165deg, {c.primary} 0%, {shade} 100%)"
      aria-hidden="true"
    >
      <span class="absolute inset-0" style="background:radial-gradient(120% 70% at 50% 105%, color-mix(in oklab, {c.accent} 70%, transparent) 0%, transparent 60%)"></span>
      <span class="absolute -top-6 -right-10 h-28 w-28 rotate-45" style="background:color-mix(in oklab, {onColor(c.primary)} 7%, transparent)"></span>
      <span class="relative mb-[-2px]">
        <Headshot url={d.headshot_url ?? null} name={d.player_name} team={d.team} size={compact ? 84 : 104} eager />
      </span>
    </div>

    <!-- who he is and this week's game -->
    <div class="min-w-0 py-3 pr-3 pl-4 {compact ? '' : 'sm:py-4 sm:pl-5'}">
      {#if name[0]}<div class="truncate text-sm leading-tight font-medium text-ink-2">{name[0]}</div>{/if}
      <h2
        class="{compact ? 'text-2xl' : 'text-3xl sm:text-4xl'} leading-[1.02] font-black tracking-tight break-words uppercase"
        data-testid="card-name"
      >
        {name[1]}
      </h2>
      <div class="mt-2 flex flex-wrap items-center gap-1.5">
        <PosBadge pos={d.position} size="md" />
        {#if d.position !== "DEF"}<TeamBadge team={d.team} size="md" />{/if}
        {#if d.injury_status}
          <span
            class="inline-flex items-center rounded-sm px-2 py-0.5 text-sm font-bold {tone === 'bad' ? 'bg-bad-soft text-bad' : 'bg-warn-soft text-warn'}"
            data-testid="card-status">{d.injury_status}</span
          >
        {/if}
        {#if d.locked}<span class="inline-flex items-center rounded-sm bg-raised px-2 py-0.5 text-sm font-semibold text-ink-2">Game started</span>{/if}
      </div>
      {#if game}
        <p class="mt-2 text-sm leading-snug text-ink-2" data-testid="card-game">
          <span class="font-semibold text-ink">Week {game.week} {vs}</span>{#if game.kickoff}<span class="block text-ink-2 sm:inline"><span class="hidden sm:inline">&nbsp;·&nbsp;</span>{game.kickoff}</span>{/if}
          {#if game.rank}<span class="block text-xs text-ink-3">{teamLabel(game.opponent)}: #{game.rank} of 32 vs {d.position} (1 = gives up the most)</span>{/if}
        </p>
      {/if}
      {#if line}<p class="mt-1 text-xs leading-snug text-ink-3" data-testid="card-line">{line}</p>{/if}
    </div>

    <!-- the one number: this week's projection, its range, his value -->
    <div
      class="col-span-2 border-t border-line px-4 py-3 pl-5 {compact ? '' : 'sm:px-5 xl:col-span-1 xl:border-t-0 xl:border-l xl:py-4'}"
      data-testid="card-headline"
    >
      <div class="flex items-end justify-between gap-3">
        <div class="min-w-0">
          <div class="text-xs leading-tight font-semibold text-ink-3">{projLabel(d.week, d.proj_points)}{d.proj_points === null ? "" : " projection"}</div>
          <div
            class="{compact ? 'text-[2.75rem]' : 'text-hero xl:text-[4rem]'} mt-0.5 leading-none font-black tracking-tight text-ink"
            title={d.proj_points === null ? "No projection for him this week: unknown, not 0" : `A forecast in ${scoring} scoring, not a guarantee`}
            data-testid="card-number"
          >
            {fmt.pts(d.proj_points)}
          </div>
          <div class="mt-1 text-xs leading-tight text-ink-3">{scoring} points · not a guarantee</div>
        </div>
        {#if value}
          <button
            type="button"
            class="shrink-0 rounded-md bg-raised px-3 py-2 text-right"
            aria-expanded={valueOpen}
            onclick={() => (valueOpen = !valueOpen)}
            data-testid="card-value"
          >
            <span class="block text-xs leading-tight text-ink-3">{value.label} <span aria-hidden="true">ⓘ</span></span>
            <span class="block text-xl leading-tight font-extrabold tracking-tight text-ink">{value.big}</span>
            <span class="tabnum block text-xs leading-tight text-ink-2">{value.small}</span>
          </button>
        {/if}
      </div>
      {#if value && valueOpen}<p class="mt-2 text-xs leading-snug text-ink-2" data-testid="card-value-help">{value.help}</p>{/if}
      <div class="mt-3">
        <RangeBar proj={d.proj_points} p10={range.p10} p25={range.p25} p75={range.p75} p90={range.p90} color={c.accent} />
      </div>
    </div>
  </div>
</article>
