<script lang="ts">
  // ---- IZ-2 (Wave I-Z, the review of 10 October § "The trade decision that could distinguish the product"): the
  // trade's answer as five questions, in the review's order, each one sentence first and the detail under it:
  // (1) what changes in your starters — the lineup panel (the slots that change, before → after, the displaced player
  // named; the weekly effect under it); (2) what they get — their panel and why they might say no, in words (never a
  // chance that they accept); (3) what it costs beyond the package — cuts, bench depth, bye cover, slots; (4) could you
  // get there another way — keep / claim / trade on one basis, one row; (5) what could change the answer — the caveats
  // on the players involved, the trust line's verdicts for their positions, what is missing. Nothing is re-priced:
  // every number is the answer's (lib/tradefive.ts says which).
  import type { ChangedLine, TeamRosterRow, TradeEval } from "../../lib/api";
  import DecisionNews from "../../components/news/DecisionNews.svelte"; // ---- IZ-4
  import { f1, s1, slotLabel } from "../../lib/decisions";
  import { involved, panelRows, threeWays, weekly, type PanelRow } from "../../lib/tradefive";
  import Expander from "../../components/Expander.svelte";
  import Md from "../../components/Md.svelte";
  import WeekStrip from "./WeekStrip.svelte";

  let { r, ctx, mineRows = [], theirRows = [] }: { r: TradeEval; ctx: { league: string; team: number | null }; mineRows?: TeamRosterRow[]; theirRows?: TeamRosterRow[] } = $props();

  const d = $derived(r.decision!);
  const them = $derived(r.partner_team);
  const mineRowsP = $derived(panelRows(d.changes.mine));
  const theirRowsP = $derived(panelRows(d.changes.theirs));
  const ways = $derived(threeWays(r));
  const people = $derived(involved(r, mineRows, theirRows));
  const flagged = $derived(people.filter((p) => p.words));
  const card = $derived(r.card ?? null);
  const refuse = $derived(card?.why_refuse ?? []);
  const consider = $derived(card?.why_consider ?? []);
  const theirAlt = $derived((d.alternative as unknown as { mine?: unknown; theirs?: { player?: { player_name: string } | null; gain_window?: number; words?: string } | null }).theirs ?? null);
  const checks = $derived((r.provenance?.checks ?? []).filter((c) => c.position || c.span === "trade_gap"));
  const missing = $derived([
    ...(r.market?.unknown ?? []).map((n) => `${n}: no season value (no rest-of-season projection)`),
    ...(d.out_indefinitely ? [d.out_indefinitely.words] : []),
  ]);
  // the one sentence of section 3 and of section 5
  const costLead = $derived(
    (r.cut ?? []).length
      ? (r.cut ?? []).map((c) => c.words).join(" ")
      : card?.depth_cost.roster_spots && card.depth_cost.roster_spots < 0
        ? `Nobody is cut: you open ${-card.depth_cost.roster_spots} roster spot${card.depth_cost.roster_spots === -1 ? "" : "s"}.`
        : "Nobody is cut: the trade fits your roster as it is.",
  );
  const changeLead = $derived(
    r.caveats?.length
      ? r.caveats[0].words
      : flagged.length
        ? `${flagged[0].name}: ${flagged[0].words}.`
        : "Nothing is flagged on the players in this trade: the projections' checks for their positions are below.",
  );
  // ---- IZ-2 → IZ-4: a news line per player in section 5 — the feed's newest item about him (the answer's `news`, by
  // Sleeper id; the same line as on My Week's decisions: the words, the source, how long ago, what the projection does
  // with it). Nothing is read from it.
  const newsFor = (key: string): ChangedLine[] | null => {
    const l = r.news?.[key];
    return l && l.length ? l : null;
  };
</script>

{#snippet panel(rows: PanelRow[], who: string, testid: string, total: { before: number; after: number; change: number } | null)}
  <div class="rounded-md border border-line" data-testid={testid}>
    <div class="grid grid-cols-[2.75rem_minmax(0,1fr)_minmax(0,1fr)_2.75rem] gap-x-2 border-b border-line px-2 py-1 text-xs font-semibold tracking-wide text-ink-3 uppercase">
      <span>Slot</span><span>Before</span><span>After</span><span class="text-right">Pts</span>
    </div>
    {#if rows.length}
      <ul class="divide-y divide-line">
        {#each rows as x, i (`${x.slot}-${i}`)}
          <li class="grid grid-cols-[2.75rem_minmax(0,1fr)_minmax(0,1fr)_2.75rem] items-start gap-x-2 px-2 py-1.5 text-sm" data-testid="panel-row">
            <span class="font-semibold text-ink-2">{slotLabel(x.slot)}</span>
            <span class="min-w-0 break-words" data-testid="panel-out"
              >{#if x.out}<span class="text-ink">{x.out}</span>{#if x.outWhy}<span class="block text-xs text-ink-3">{x.outWhy}</span>{/if}{:else}<span class="text-ink-3">empty</span>{/if}</span
            >
            <span class="min-w-0 break-words" data-testid="panel-in"
              >{#if x.in}<strong class="text-ink">{x.in}</strong>{#if x.inHow}<span class="block text-xs text-ink-3">{x.inHow}</span>{/if}{:else}<span class="text-ink-3">empty</span>{/if}</span
            >
            <span class="tabnum text-right {x.change == null ? 'text-ink-3' : x.change >= 0.05 ? 'text-good' : x.change <= -0.05 ? 'text-bad' : 'text-ink-3'}">{x.change == null ? "—" : s1(x.change)}</span>
          </li>
        {/each}
      </ul>
    {:else}
      <p class="px-2 py-2 text-sm text-ink-2" data-testid="panel-same">The same players start for {who} this week.</p>
    {/if}
    {#if total}<p class="border-t border-line px-2 py-1.5 text-sm text-ink-2" data-testid="panel-total">Starting lineup, week {d.this_week ?? r.week}: {f1(total.before)} → <strong class="text-ink">{f1(total.after)}</strong> ({s1(total.change)} projected points)</p>{/if}
  </div>
{/snippet}

{#snippet weeksLine(gains: number[], testid: string)}
  {#if d.strip.weeks.length > 1}
    <p class="text-sm text-ink-2" data-testid={testid}>
      Week by week:
      {#each weekly(d.strip.weeks, gains) as w, i (w.week)}{i ? " · " : ""}<span class="whitespace-nowrap">week {w.week} <span class="tabnum">{s1(w.gain)}</span></span>{/each}
    </p>
  {/if}
{/snippet}

<div class="space-y-5" data-testid="trade-five">
  <!-- 1. What changes in your starters -->
  <section class="space-y-2" data-testid="five-1">
    <h3 class="ll-label">1 · What changes in your starters</h3>
    <p class="text-lg leading-snug font-semibold text-ink" data-testid="trade-effect">{d.effect_words}</p>
    {@render panel(mineRowsP, "you", "panel-mine", d.this_week != null ? { before: d.mine.before.this_week, after: d.mine.after.this_week, change: d.mine.gain_week } : null)}
    {#if d.strip.weeks.length > 1}
      <div data-testid="trade-strip-block">
        <h4 class="ll-label mb-1">Starter points gained, week by week ({d.span})</h4>
        <WeekStrip strip={d.strip} {them} testid="trade-strip" />
      </div>
    {/if}
    <Expander title="Your starters, slot by slot, in words" testid="trade-starters">
      <ul class="space-y-1 text-base">
        {#each d.changes.mine as x, i (`${x.slot}-${i}`)}<li data-testid="starter-change">{x.words}.</li>{/each}
        {#if !d.changes.mine.length}<li class="text-ink-2">The same players start this week.</li>{/if}
      </ul>
      <p class="mt-1 text-sm text-ink-2" data-testid="trade-total">Starting lineup this week: {f1(d.mine.before.this_week)} → <strong class="text-ink">{f1(d.mine.after.this_week)}</strong> ({s1(d.mine.gain_week)} projected points)</p>
      <p class="mt-1 text-sm text-ink-3">A starter who only moves from one numbered slot to another (WR/TE 2 to WR/TE 3) is not a change. Every slot is under "Lineups" below.</p>
    </Expander>
  </section>

  <!-- 2. What they get -->
  <section class="space-y-2" data-testid="five-2">
    <h3 class="ll-label">2 · What {them} gets</h3>
    <p class="text-base leading-snug font-semibold text-ink" data-testid="trade-their-side">{d.their_effect_words}</p>
    {@render panel(theirRowsP, them, "panel-theirs", d.this_week != null ? { before: d.theirs.before.this_week, after: d.theirs.after.this_week, change: d.theirs.gain_week } : null)}
    {@render weeksLine(d.strip.theirs, "panel-theirs-weeks")}
    {#if refuse.length}
      <p class="text-base leading-snug text-ink" data-testid="five-refuse-lead"><span class="font-semibold">Why they might say no:</span> {refuse[0]}</p>
    {/if}
    <Expander title="Why they might say yes or no" testid="five-reasons">
      <div class="space-y-2 text-base">
        {#if consider.length}<div><h4 class="ll-label">Why they might say yes</h4><ul class="mt-1 list-disc space-y-1 pl-5" data-testid="five-consider">{#each consider as w, i (i)}<li>{w}</li>{/each}</ul></div>{/if}
        {#if refuse.length}<div><h4 class="ll-label">Why they might say no</h4><ul class="mt-1 list-disc space-y-1 pl-5" data-testid="five-refuse">{#each refuse as w, i (i)}<li>{w}</li>{/each}</ul></div>{/if}
        {#if d.changes.theirs.length}<ul class="space-y-1 text-ink-2">{#each d.changes.theirs as x, i (`t-${x.slot}-${i}`)}<li data-testid="their-change">{x.words}.</li>{/each}</ul>{/if}
        <p class="text-sm text-ink-3">Reasons from the numbers, not a guess at his answer: we cannot know how another manager rates his players.</p>
      </div>
    </Expander>
  </section>

  <!-- 3. What it costs beyond the package -->
  <section class="space-y-2" data-testid="five-3">
    <h3 class="ll-label">3 · What it costs beyond the players named</h3>
    <p class="text-base leading-snug font-semibold text-ink" data-testid="trade-cut">{costLead}</p>
    {#if d.depth.mine.words}<p class="text-base text-ink" data-testid="trade-backup">Backup coverage: {d.depth.mine.words}.</p>{/if}
    <Expander title="Bench depth, bye cover and roster slots" testid="five-costs">
      <div class="space-y-2 text-base text-ink-2">
        {#if d.depth.theirs.words}<p data-testid="their-backup">{them}'s backup coverage: {d.depth.theirs.words}.</p>{/if}
        {#if d.fills.mine.words || d.fills.theirs.words}
          <div data-testid="trade-fills">
            {#if d.fills.mine.words}<p>{d.fills.mine.words}</p>{/if}
            {#if d.fills.theirs.words}<p class="mt-1">{d.fills.theirs.words}</p>{/if}
          </div>
        {/if}
        {#each card?.legal.notes ?? [] as n, i (i)}<p data-testid="five-legal">{n}</p>{/each}
        {#if r.size_words}<p data-testid="five-size"><Md text={r.size_words} {ctx} /></p>{/if}
      </div>
    </Expander>
  </section>

  <!-- 4. Could you get there another way: keep / claim / trade on one basis -->
  <section class="space-y-2" data-testid="five-4">
    <h3 class="ll-label">4 · Could you get there another way</h3>
    <p class="text-base leading-snug {d.alternative.beats ? 'text-ink' : 'text-warn'}" data-testid="trade-alternative"><span class="font-semibold">Against your best waiver move:</span> {d.alternative.words}</p>
    {#if ways}
      <div class="grid grid-cols-3 gap-2" data-testid="three-ways">
        {#each [{ k: "keep", label: "Keep your roster", total: ways.keep, gain: 0 }, { k: "claim", label: "Best claim", total: ways.claim, gain: ways.claimGain }, { k: "trade", label: "This trade", total: ways.trade, gain: ways.tradeGain }] as w (w.k)}
          <div class="rounded-md border px-2 py-2 {ways.best === w.k ? 'border-accent bg-accent-soft' : 'border-line'}" data-testid={`way-${w.k}`} data-best={ways.best === w.k}>
            <div class="text-xs font-semibold tracking-wide text-ink-3 uppercase">{w.label}</div>
            <div class="tabnum text-xl leading-tight font-bold text-ink">{w.total == null ? "—" : f1(w.total)}</div>
            <div class="tabnum text-sm text-ink-2">{w.total == null ? "no claim found" : w.k === "keep" ? "as it is" : s1(w.gain ?? 0)}</div>
          </div>
        {/each}
      </div>
      <p class="text-sm text-ink-2" data-testid="three-ways-basis">Your starters' projected points over {d.span}, the best lineup each week: the same scoring, the same weeks and the same roster for all three, an empty starting slot filled from the free pool.</p>
      {#if ways.claimName}<p class="text-sm text-ink" data-testid="three-ways-claim"><span class="font-semibold">The claim:</span> {ways.claimName}. {ways.assumption}</p>{/if}
      {#if theirAlt?.player && theirAlt.gain_window != null}<p class="text-sm text-ink-2" data-testid="three-ways-theirs">{them}'s own best claim (add {theirAlt.player.player_name}) gives them {s1(theirAlt.gain_window)} over {d.span}; this trade gives them {s1(d.theirs.gain_window)}.</p>{/if}
    {/if}
  </section>

  <!-- 5. What could change the answer -->
  <section class="space-y-2" data-testid="five-5">
    <h3 class="ll-label">5 · What could change the answer</h3>
    <p class="text-base leading-snug font-semibold text-ink" data-testid="five-change-lead">{changeLead}</p>
    <ul class="space-y-1 text-base text-ink" data-testid="five-players">
      {#each people as p (`${p.side}-${p.key}`)}
        <li data-testid="five-player" data-key={p.key}>
          <span class="font-semibold">{p.name}</span> <span class="text-sm text-ink-3">({p.side === "give" ? "you give" : p.side === "get" ? "you get" : "cut"})</span>: {p.words ?? "nothing flagged on his report"}.
          <!-- ---- IZ-2 → IZ-4: the news line for this player (source, how long ago, "context only: not in the projection") -->
          {#if newsFor(p.key)}<div class="mt-1" data-testid="trade-news"><DecisionNews lines={newsFor(p.key)!} names={false} testid="trade-news-lines" /></div>{/if}
        </li>
      {/each}
      {#each r.caveats ?? [] as c, i (i)}<li class="text-warn" data-testid="five-caveat">{c.words}</li>{/each}
    </ul>
    <Expander title="How sure the numbers are, and what is missing" testid="five-checks">
      <div class="space-y-2 text-base text-ink-2">
        {#if checks.length}<ul class="list-disc space-y-1 pl-5" data-testid="five-check-list">{#each checks as c, i (i)}<li>{c.words}.</li>{/each}</ul>{/if}
        {#if missing.length}<ul class="list-disc space-y-1 pl-5" data-testid="five-missing">{#each missing as m, i (i)}<li>{m}</li>{/each}</ul>{/if}
        <p class="text-sm text-ink-3">A role is read from his games: a change of role (more snaps, targets or carries) after his latest game is not in these numbers.</p>
      </div>
    </Expander>
  </section>
</div>
