<script lang="ts">
  // One waiver move as a card (plan G4; app/pages/2_Waiver_Wire.py `_card`): the free agent as the unit (headshot,
  // name, badges, the gain this week as the big number), the card's answer in one sentence, what each week of the
  // next four gains (small bars, one scale for the screen), the drop, then the card's lines.
  import type { WaiverMove } from "../../lib/api";
  import { withContext, type LinkContext } from "../../lib/md";
  import { f1, rangeWords, s1, waiverHeadline } from "../../lib/decisions";
  import { team as teamColors } from "../../lib/theme";
  import Card from "../../components/Card.svelte";
  import Headshot from "../../components/Headshot.svelte";
  import Md from "../../components/Md.svelte";
  import PosBadge from "../../components/PosBadge.svelte";
  import TeamBadge from "../../components/TeamBadge.svelte";

  let {
    move: m,
    ctx,
    gainMax,
    compact = false,
    headline = true,
  }: { move: WaiverMove; ctx: LinkContext; gainMax: number; compact?: boolean; headline?: boolean } = $props();

  const weeks = $derived((m.week_gains ?? []).map((g, i) => ({ week: m.week + i, gain: g ?? 0 })));
  const range = $derived(rangeWords(m.add_p25, m.add_p75, m.add_p10, m.add_p90));
  const big = $derived(m.weekly_gain > 0.005 ? m.weekly_gain : m.horizon_gain);
  const bigLabel = $derived(m.weekly_gain > 0.005 ? "this week" : `over ${m.horizon_last_week - m.week + 1} weeks`);
  const href = (g: string | null) => (g ? withContext(`/player/${g}`, ctx) : null);
</script>

<Card title={m.card_title ?? "Also helps"} accent={teamColors(m.add_team).accent} testid="waiver-move">
  <div class="flex items-center gap-3">
    <Headshot url={m.add_headshot_url} name={m.add_name ?? ""} team={m.add_team} size={compact ? 44 : 60} />
    <div class="min-w-0 flex-1">
      {#if href(m.add_gsis_id)}
        <a class="ll-name line-clamp-2 block text-lg leading-tight font-bold break-words" href={href(m.add_gsis_id)} data-testid="move-add">{m.add_name}</a>
      {:else}
        <span class="line-clamp-2 block text-lg leading-tight font-bold break-words" data-testid="move-add">{m.add_name}</span>
      {/if}
      <div class="mt-1 flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-sm text-ink-3">
        <PosBadge pos={m.add_position} />
        {#if m.add_position !== "DEF"}<TeamBadge team={m.add_team} />{/if}
        <span>{m.add_value != null ? `projects ${f1(m.add_value)}` : "no projection yet"}</span>
        {#if range}<span>· {range}</span>{/if}
      </div>
    </div>
    <div class="shrink-0 text-right">
      <div class="tabnum text-3xl font-extrabold tracking-tight wide:text-num {big > 0 ? 'text-good' : 'text-ink'}" data-testid="move-gain">{s1(big)}</div>
      <div class="ll-label mt-1">{bigLabel}</div>
    </div>
  </div>

  {#if headline}<p class="mt-3 text-base leading-snug font-semibold" data-testid="move-headline">{waiverHeadline(m)}</p>{/if}

  {#if weeks.length > 1}
    <div class="mt-3" data-testid="move-weeks">
      <div class="ll-label mb-1">What it adds, week by week</div>
      <div class="flex items-end gap-2">
        {#each weeks as w (w.week)}
          {@const h = Math.max(0, Math.min(1, w.gain / Math.max(gainMax, 1e-9)))}
          <div class="flex min-w-0 flex-1 flex-col items-center gap-1">
            <span class="tabnum text-xs font-semibold {w.gain > 0.005 ? 'text-ink' : 'text-ink-3'}">{w.gain > 0.005 ? s1(w.gain) : "0"}</span>
            <div class="flex h-10 w-full items-end rounded-sm bg-sunken">
              <div class="w-full rounded-t-sm" style="height:{Math.round(h * 100)}%;background:var(--ll-series-1)"></div>
            </div>
            <span class="text-xs text-ink-3">Wk {w.week}</span>
          </div>
        {/each}
      </div>
    </div>
  {/if}

  <div class="mt-3 flex items-center gap-2 rounded-md bg-raised px-3 py-2" data-testid="move-drop">
    <span class="ll-label w-10 shrink-0">Drop</span>
    {#if m.drop_name}
      <Headshot url={m.drop_headshot_url} name={m.drop_name} team={m.drop_team} size={28} />
      <span class="min-w-0 flex-1 truncate text-base">
        {#if href(m.drop_gsis_id)}<a class="ll-name font-semibold" href={href(m.drop_gsis_id)}>{m.drop_name}</a>{:else}<span class="font-semibold">{m.drop_name}</span>{/if}
        <span class="text-sm text-ink-3"> {m.drop_position}</span>
      </span>
      <span class="tabnum shrink-0 text-sm text-ink-2">{(m.drop_horizon_loss ?? 0) > 0.05 ? `costs ${f1(m.drop_horizon_loss)}` : "sits anyway"}</span>
    {:else}
      <span class="text-base text-ink-2">Nobody: you have an open roster spot.</span>
    {/if}
  </div>

  {#if !compact && m.lines?.length}
    <ul class="mt-3 space-y-1 text-sm leading-snug text-ink-2" data-testid="move-lines">
      {#each m.lines as line, i (i)}<li><Md text={line} {ctx} /></li>{/each}
    </ul>
  {/if}
</Card>
