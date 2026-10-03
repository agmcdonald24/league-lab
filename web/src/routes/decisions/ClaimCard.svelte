<script lang="ts">
  // IB-2 (Wave I-B): one claim, short — the unit Waivers leads with (the three strongest moves) and lists in its views.
  // The free agent (headshot, name, position, team, this week's projection) with the lineup gain as the number, ONE
  // reason (a fact: the role, the bye, the slot), the claim's cost ("Drop Croskey-Merritt: he sits anyway" — the drop is
  // named once); when the drop starts for you this week or next, the warning and the best claim that keeps him
  // (`keep_alternative`) — never one without the other.
  // `compact`: a list row (the views), no card frame. The name opens the research pane (IB-1) when it is in the build.
  import type { WaiverCard } from "../../lib/api";
  import { withContext, type LinkContext } from "../../lib/md";
  import { f1, paneAt, s1 } from "../../lib/decisions";
  import { team as teamColors } from "../../lib/theme";
  import Card from "../../components/Card.svelte";
  import Headshot from "../../components/Headshot.svelte";
  import PosBadge from "../../components/PosBadge.svelte";
  import TeamBadge from "../../components/TeamBadge.svelte";

  let {
    card: c,
    ctx,
    rank = null,
    compact = false,
    focus = false,
    testid = "claim",
  }: { card: WaiverCard; ctx: LinkContext; rank?: number | null; compact?: boolean; focus?: boolean; testid?: string } = $props();

  const m = $derived(c.move);
  // the number: the bye week's gain in Bye coverage, else the horizon's; this week's beside it when it differs
  const big = $derived(c.week_gain ?? c.gain ?? m.horizon_gain);
  const bigLabel = $derived(c.week_gain_label ?? c.gain_label);
  const href = (g: string | null | undefined) => (g ? withContext(`/player/${g}`, ctx) : null);
  const paneOpts = $derived({ from: "waiver" as const, context: { add: m.add.sleeper_id, drop: m.drop?.sleeper_id ?? null, name: m.add.player_name } });
</script>

{#snippet body()}
  <div class="flex items-center gap-3">
    {#if rank !== null}<span class="tabnum w-4 shrink-0 text-sm font-bold text-ink-3">{rank}</span>{/if}
    <Headshot url={m.add.headshot_url} name={m.add.player_name ?? ""} team={m.add.team} size={compact ? 40 : 48} />
    <div class="min-w-0 flex-1">
      {#if href(m.add.gsis_id)}
        <a class="ll-name block truncate text-base leading-tight font-bold wide:text-lg" href={href(m.add.gsis_id)} {@attach paneAt(m.add.gsis_id, paneOpts)} data-testid="claim-add">{m.add.player_name}</a>
      {:else}
        <span class="block truncate text-base leading-tight font-bold wide:text-lg" data-testid="claim-add">{m.add.player_name}</span>
      {/if}
      <div class="mt-0.5 flex min-w-0 items-center gap-1.5 text-sm text-ink-3">
        <PosBadge pos={m.add.position} />
        {#if m.add.position !== "DEF"}<TeamBadge team={m.add.team} />{/if}
        <span class="min-w-0 truncate">{m.add.projection != null ? `projects ${f1(m.add.projection)}` : "no projection yet"}</span>
      </div>
    </div>
    <div class="shrink-0 text-right">
      <div class="tabnum text-2xl leading-none font-extrabold {big != null && big >= 0.05 ? 'text-good' : 'text-ink'}" data-testid="claim-gain">{s1(big)}</div>
      <div class="ll-label mt-1">{bigLabel}</div>
    </div>
  </div>
  <p class="mt-2 text-base leading-snug text-ink" data-testid="claim-reason">{c.reason}</p>
  <p class="mt-1 text-sm leading-snug text-ink-3" data-testid="claim-cost">
    {c.cost}{#if c.this_week != null && c.this_week >= 0.05 && Math.abs(c.this_week - (big ?? 0)) >= 0.05}<span class="ml-1">{`· this week ${s1(c.this_week)}`}</span>{/if}
  </p>
  {#if m.drop_starts}
    <div class="mt-2 rounded-md bg-warn-soft px-3 py-2 text-sm leading-snug text-ink" data-testid="keep-alt">
      <strong>{m.drop_starts.text}.</strong>
      {m.keep_alternative?.line ?? ""}
    </div>
  {/if}
{/snippet}

{#if compact}
  <div class="px-3 py-3" data-testid={testid} data-add={m.add.sleeper_id}>{@render body()}</div>
{:else}
  <Card accent={teamColors(m.add.team).accent} tone={focus ? "accent" : "plain"} testid={testid}>{@render body()}</Card>
{/if}
