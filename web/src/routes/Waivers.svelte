<script lang="ts">
  import { competing, horizonOf, topIntro } from "../lib/feed"; // ---- II-4: when each claim helps; competing claims
  // Waivers (plan G4; app/pages/2_Waiver_Wire.py on GET /api/waivers). IB-2 (Wave I-B): short — the answer first, the
  // three strongest moves (one card each: the move, the lineup gain, one reason, the claim's cost; a drop who starts
  // for you carries the best claim that keeps him), then ONE view at a time behind chips: Help now (this week's lineup
  // gain) · Bye coverage (the next bye the roster cannot cover) · Stashes (the upside stash) · All available (the free
  // agents by position — list on the left, the picked one on the right on desktop). The view and the position are the
  // URL (?view=, ?position=; rewritten in place, no Back step); one answer carries every view, so a chip switches at
  // once. ?add=<sleeper id>[&drop=] (the research pane's "Evaluate add / drop") shows the claim for him first.
  import { get, peek, Unauthorized, decisionPaths, type FreeAgent, type WaiverCard, type Waivers } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { md, withContext } from "../lib/md";
  import { errorWords, f1, rangeWords, s1, slotLabel, waiverAnswer, waiverHeadline } from "../lib/decisions";
  import { openPlayer, VIEW_TABS, viewOf } from "../lib/decisions";
  import { restoreScroll, route, setParams } from "../lib/router.svelte";
  import { fmt } from "../lib/theme";
  import Card from "../components/Card.svelte";
  import ProvenanceLine from "../components/provenance/ProvenanceLine.svelte"; // ---- IT-3
  import type { DecisionCaveat, Provenance } from "../lib/api"; // ---- IT-3
  import Chips from "../components/Chips.svelte";
  import Expander from "../components/Expander.svelte";
  import ListDetail from "../components/ListDetail.svelte";
  import Md from "../components/Md.svelte";
  import Meter from "../components/Meter.svelte";
  import PlayerCard from "../components/PlayerCard.svelte";
  import PlayerRow from "../components/PlayerRow.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import StatTile from "../components/StatTile.svelte";
  import Tabs from "../components/Tabs.svelte";
  import ClaimCard from "./decisions/ClaimCard.svelte";
  import RangeBar from "./decisions/RangeBar.svelte";

  let { options, league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  let data = $state<Waivers | null>(null);
  // ---- IT-3: provenance and the starter caveats the answer carries since IS-2
  const prov = (d: Waivers | null) => d as (Waivers & { provenance?: Provenance | null; caveats?: DecisionCaveat[] | null }) | null;
  let error = $state<string | null>(null);
  let picked = $state<string | null>(null);

  const ctx = $derived({ league, team });
  const position = $derived((route.current.params.get("position") ?? "ALL").toUpperCase());
  // "in League of Scrubs scoring" (WORDS.md: name the league's scoring); a league the picker does not know: "your league's"
  const scoring = $derived.by(() => {
    const n = options.find((o) => o.league_id === league)?.name;
    return n && n !== "This league" ? `${n} scoring` : "your league's scoring";
  });

  $effect(() => {
    const l = league;
    const t = team;
    const p = position;
    error = null;
    if (t === null) {
      data = null;
      return;
    }
    const path = decisionPaths.waivers(l, t, p);
    const hit = peek<Waivers>(path);
    if (hit) {
      data = hit;
      restoreScroll();
      return;
    }
    if (data && (data.league_id !== l || data.roster_id !== t)) data = null; // another team: no stale answer
    get<Waivers>(path)
      .then((d) => {
        if (league !== l || team !== t || position !== p) return;
        data = d;
        restoreScroll();
      })
      .catch((e) => {
        if (league !== l || team !== t || position !== p) return;
        if (e instanceof Unauthorized) onauth();
        else error = errorWords(e);
      });
  });

  // ---- IB-2: the three strongest moves, the views
  const top3 = $derived(data?.top3 ?? []);
  const views = $derived(data?.views ?? null);
  const view = $derived(viewOf(route.current.params.get("view"), data?.default_view ?? "help"));
  // ---- IE-1: the answer is not the first card's move again (the API's `answer`: "The three strongest claims are below …")
  const lead = $derived(
    data ? (top3.length ? `**${topIntro(top3, data.week ?? 0, data.horizon_last_week ?? data.week ?? 0)}**` /* ---- II-4: the horizon, honest */ : data.answer ? `**${data.answer}**` : waiverAnswer(data)) : "",
  );
  void waiverHeadline; // ---- II-4: IE-1's first-card headline gave way to topIntro
  const rivals = $derived(competing(top3)); // ---- II-4
  const chips = $derived(
    VIEW_TABS.map((t) => ({ key: t.key, label: t.key === "stash" && views?.stash.count ? `${t.label} (${views.stash.count})` : t.label })),
  );
  // the research pane's "Evaluate add / drop" (?add=, ?drop=): the claim for him (any view's card, else the paged
  // moves), else the free agent picked in All available
  const focusAdd = $derived(route.current.params.get("add"));
  const focusDrop = $derived(route.current.params.get("drop"));
  const focus = $derived.by<WaiverCard | null>(() => {
    if (!focusAdd || !data) return null;
    const pool = [...top3, ...(views?.help.moves ?? []), ...(views?.bye.moves ?? [])];
    const hit =
      pool.find((c) => c.move.add.sleeper_id === focusAdd && (!focusDrop || c.move.drop?.sleeper_id === focusDrop)) ?? pool.find((c) => c.move.add.sleeper_id === focusAdd);
    if (hit) return hit;
    const m = data.moves.find((x) => x.add.sleeper_id === focusAdd);
    if (!m) return null;
    const cost = m.drop ? `Drop ${m.drop.player_name}.` : "No drop: you have an open roster spot.";
    return { move: m, reason: m.words?.why ?? "", cost, gain: m.horizon_gain, gain_label: span > 1 ? `weeks ${wk}–${last}` : `week ${wk}`, this_week: m.weekly_gain };
  });
  const focusFa = $derived(focusAdd && !focus ? ((data?.free_agents ?? []).find((f) => f.sleeper_id === focusAdd) ?? null) : null);
  $effect(() => {
    if (focusFa) picked = focusFa.gsis_id ?? focusFa.sleeper_id ?? null;
  });
  // a free agent's row: the detail on the right (desktop); on a phone (no room for it) the research pane, when in the build
  function pickFa(f: FreeAgent) {
    picked = f.gsis_id ?? f.sleeper_id ?? null;
    if (typeof matchMedia === "function" && !matchMedia("(min-width: 56.25rem)").matches)
      openPlayer(f.gsis_id, { from: "waiver", context: { add: f.sleeper_id, name: f.player_name } }, () => {});
  }
  const one = (c: WaiverCard) => `${c.move.add.sleeper_id ?? ""}|${c.move.drop?.sleeper_id ?? ""}`;
  // the lineup line under the answer (it replaces Wave G's four tiles: the screen is short)
  const closest = $derived.by(() => {
    const w = data?.weakest;
    if (!w?.slot) return "";
    const who = w.player?.player_name;
    if (!who) return ` · closest call ${slotLabel(w.slot)}`;
    return w.replacement_name
      ? ` · closest call ${slotLabel(w.slot)}, ${who} over ${w.replacement_name} by ${f1(w.margin)}`
      : ` · closest call ${slotLabel(w.slot)}, ${who} (nobody on the bench can fill in)`;
  });
  // ---- end IB-2
  const fas = $derived(data?.free_agents ?? []);
  const fa = $derived<FreeAgent | null>(fas.find((f) => (f.gsis_id ?? f.sleeper_id) === picked) ?? fas[0] ?? null);
  const scale = $derived(Math.max(10, ...fas.map((f) => f.p90 ?? f.projection ?? 0)));
  // the free-agent tabs: the positions the league starts (requested of G2: `positions`); else the four, plus K / DEF
  // when the list has them
  const tabs = $derived.by(() => {
    const extra = ["K", "DEF"].filter((p) => fas.some((f) => f.position === p) || position === p);
    const ps = data?.positions?.length ? data.positions : ["QB", "RB", "WR", "TE", ...extra];
    return ["ALL", ...ps].map((p) => ({ key: p, label: p === "ALL" ? "All" : p }));
  });
  const wk = $derived(data?.week ?? 0);
  const last = $derived(data?.horizon_last_week ?? wk);
  const span = $derived(last - wk + 1);

  // 2_Waiver_Wire.py's "How to read this", the screen's own words
  const HOWTO =
    "- **What a claim is worth**: we try every free agent against every player you could drop, rebuild your best lineup each time, and show how many points it adds. Same projections and same lineup as the rest of the app.\n" +
    "- **This week** (the big number on a card) is what the claim adds to this week's starters; **in total** adds up this week and the next three, so covering a bye counts, and so do the games the dropped player would have started. It is a total over the weeks, not a number per week.\n" +
    "- **Each claim is weighed on its own** against your roster as it is: two claims do not simply add up (each may need its own drop, and two claims for the same spot help only once). **Instead of …** marks a claim for the same spot as one above.\n" +
    // ---- IG-3: the drop is the cheapest by its cost (IF-1), for the claims and the stashes alike
    "- **Who to drop**: the cheapest drop — the most of what dropping him costs your lineup over those four weeks, his worth as a backup, his later starts and his season points above the best free agent at his position. We never suggest dropping someone we have no projection for yet: unknown is not zero.\n" +
    "- **When claims run** (the line under the title): from your league's own settings on Sleeper, or MFL's waiver type (MFL does not share the time: see MFL). Players lock at their own kickoff.\n" +
    "- **Only the next four weeks count.** In a dynasty league, a young player's future is not in these numbers: look twice before dropping one.\n" +
    "- **Free agents** are ranked by this week's projection in your league's scoring. **Typical range** (the middle 50% of outcomes) is the band half his weeks land in; the thin line runs from the low-end to the high-end outcome (8 weeks in 10); the tick is the projection. **Rest of season** adds up every week left to your league's final.\n" +
    "- **The moves first** are the claims that add the most to your lineup over the next 4 weeks, one per position (two defenses compete for one spot). **Help now** lists the claims that raise this week's lineup; **Bye coverage** the next week a bye leaves a starting spot empty that your bench cannot fill; **Stashes** the upside stash; **All available** every free agent.\n" +
    "- **Before you drop a starter**: when the drop starts for you this week or next, the card says so and shows the best claim that keeps him (its drop sits), or says none does.\n" +
    "- **Upside stash**: a free agent whose role grew in his last one to three games (more snaps, targets or carries: a teammate out, a new starter) before his points caught up. **If it holds** is his projection with the bigger role: a what-if, not a forecast. **Lineup gain if it holds** adds up this week and the next three; most stashes add nothing yet, which is why they are stashes, not starters. A stash says **claim** only when, if the role holds, he is worth the roster spot after what the cheapest drop costs; otherwise **watch**.\n" +
    "- **Players scoring below or above their work** are on the Trades screen, next to the trades to ask about."; // ---- IP-3 fix round

  // ---- IS-2: the status block the API sends beside each free agent (null: no word)
  type GateNote = { status: string | null; why: string; sits: boolean; out_indefinitely: boolean; words: string | null };
  const gateNote = (f: FreeAgent): GateNote | null => (f as FreeAgent & { availability?: GateNote | null }).availability ?? null;
  function faContext(f: FreeAgent): string {
    const bits = [rangeWords(f.p25, f.p75, f.p10, f.p90), f.ros_points != null ? `rest of season ${fmt.whole(f.ros_points)}` : null];
    // ---- IS-2: the one definition's status with its source and date ("Out (ankle) · Sleeper, Oct 7"), and why his week is 0
    const gate = gateNote(f);
    if (gate) bits.unshift(gate.sits && gate.words ? `${gate.why}. ${gate.words}` : gate.why);
    else if (f.injury_status) bits.unshift(f.injury_status);
    return bits.filter(Boolean).join(" · ");
  }
</script>

<main class="space-y-4" data-testid="waivers">
  {#if team === null}
    <p class="ll-empty" data-testid="pick-team-first">Pick your team above: this screen then opens with the claims that improve that roster's lineup, each with the player to drop.</p>
  {:else if error}
    <p class="ll-error" data-testid="error">{error}</p>
  {:else if !data}
    <div class="space-y-3" aria-label="Loading" data-testid="loading">
      <div class="ll-skel h-24"></div>
      <div class="ll-skel h-48"></div>
    </div>
  {:else}
    <ScreenHead eyebrow={`Waivers · week ${data.week}`} title={`Best claims for ${data.team_name ?? "your team"}`}>
      {#snippet answer()}
        <p data-testid="waiver-answer"><Md text={lead} {ctx} /></p>
      {/snippet}
      <p class="text-sm text-ink-3" data-testid="waiver-lineup">
        Your lineup this week: <strong class="tabnum text-ink">{f1(data.lineup_value)}</strong> in {scoring}{closest}.
      </p>
      <!-- ---- IG-3: when claims run (the league's own settings) and when the next game starts -->
      {#if data.deadline?.words}
        <p class="text-sm leading-snug text-ink-3" data-testid="waiver-deadline">
          {#if data.deadline.runs_at}<time datetime={data.deadline.runs_at}>{data.deadline.words}</time>{:else}{data.deadline.words}{/if}
        </p>
      {/if}
      <!-- ---- end IG-3 -->
    </ScreenHead>

    {#if data.inputs_current === false || data.on_current_lineup === false}
      <p class="rounded-lg bg-warn-soft p-3 text-sm text-ink" data-testid="stale">
        These claims were computed before the latest {data.inputs_current === false ? "rosters or injury reports" : "lineup"}: a player may already be gone. They refresh with the nightly update.
      </p>
    {/if}

    {#if focus}
      <!-- the research pane's "Evaluate add / drop" (?add=): the claim for him, first -->
      <section class="space-y-2" data-testid="claim-focus">
        <h2 class="ll-label">The claim you asked about</h2>
        <ClaimCard card={focus} {ctx} focus testid="claim-focused" />
      </section>
    {:else if focusFa}
      <p class="rounded-lg bg-raised p-3 text-sm text-ink" data-testid="claim-focus">
        Claiming <strong>{focusFa.player_name}</strong> does not raise your lineup over {span > 1 ? `weeks ${wk}–${last}` : `week ${wk}`}: every player you could drop is worth more to it. He is picked in All available.
      </p>
    {/if}

    {#if top3.length}
      <section class="space-y-2" data-testid="top3">
        <h2 class="text-xl font-bold">{top3.length === 1 ? "The strongest move" : `The ${top3.length === 2 ? "two" : "three"} strongest moves`}</h2>
        <div class="grid grid-cols-1 gap-3 wide:grid-cols-3">
          {#each top3 as c, i (`${one(c)}#${i}`)}
            <!-- ---- II-4: the horizon on each claim (helps this week / covers a bye / helps later / upside stash) -->
            {@const h = horizonOf(c, data.week ?? 0)}
            <div class="space-y-1" data-testid="top-move-wrap">
              <span class="inline-block rounded-sm px-2 py-0.5 text-xs font-bold {h.key === 'now' ? 'bg-accent-soft text-accent' : 'bg-raised text-ink-2'}" data-testid="top-move-horizon" data-horizon={h.key}>{h.label}</span>
              <ClaimCard card={c} {ctx} rank={i + 1} testid="top-move" />
            </div>
          {/each}
        </div>
        {#each rivals as r, i (i)}<p class="text-sm leading-snug font-semibold text-ink" data-testid="top-compete">{r}</p>{/each}<!-- II-4 -->
        {#if data.not_additive}<p class="text-sm leading-snug text-ink-2" data-testid="not-additive">{data.not_additive}</p>{/if}<!-- IE-1 -->
        <!-- ---- IT-3: what the numbers are and what has been checked; a claim on a quarterback whose starter is unclear or set by hand says so -->
        <ProvenanceLine p={prov(data)?.provenance} caveats={prov(data)?.caveats} testid="waivers-provenance" />
      </section>
    {/if}

    <!-- one view at a time (default: Help now, or Bye coverage when nothing helps this week) -->
    <Chips items={chips} current={view} onpick={(v) => setParams({ view: v === (data?.default_view ?? "help") ? null : v })} label="View" testid="views" />

    {#if view === "help" || view === "bye"}
      {@const v = view === "help" ? views?.help : views?.bye}
      <section class="space-y-2" data-testid={`view-${view}`}>
        {#if v?.line}<p class="text-base leading-snug text-ink-2" data-testid="view-line"><Md text={v.line} {ctx} /></p>{/if}
        {#if v?.moves.length}
          <Card pad={false}>
            <ul class="divide-y divide-line" data-testid="view-list">
              {#each v.moves as c, ix (`${one(c)}#${ix}`)}<li><ClaimCard card={c} {ctx} compact testid="view-move" /></li>{/each}
            </ul>
          </Card>
        {:else if !views}
          <p class="ll-empty"><Md text={waiverAnswer(data)} {ctx} /></p>
        {/if}
      </section>
    {:else if view === "stash"}
      <!-- H1 (Wave H): the upside stash (2_Waiver_Wire.py's third card region) -->
      <section class="space-y-3" data-testid="upside">
        {#if data.upside}
          <p class="text-sm text-ink-3">{data.upside.title}.</p>
          {#if data.upside.stashes.length}
            <div class="grid grid-cols-1 gap-3 wide:grid-cols-3">
              {#each data.upside.stashes.slice(0, 3) as u, ix (`${u.add.sleeper_id ?? u.add.gsis_id}#${ix}`)}
                <Card testid="stash">
                  <PlayerRow
                    player={{ ...u.add, player_name: u.add.player_name ?? "" }}
                    href={u.add.gsis_id ? withContext(`/player/${u.add.gsis_id}`, ctx) : null}
                    pane={{ from: "waiver", context: { add: u.add.sleeper_id, name: u.add.player_name } }} /* II-2: the drawer, with Evaluate add / drop */
                    context={u.change_text ? `${u.change_text} since week ${u.since_week}` : null}
                    value={f1(u.scenario_value)}
                    valueLabel="If it holds"
                    testid="stash-player"
                  />
                  <p class="mt-2 text-base font-semibold leading-snug" data-testid="stash-headline"><Md text={u.headline} {ctx} /></p>
                  <ul class="mt-1 space-y-1 text-sm leading-snug text-ink-2" data-testid="stash-lines">
                    {#each u.lines as line, i (i)}<li><Md text={line} {ctx} /></li>{/each}
                  </ul>
                  <!-- ---- IF-1: a stash is a watchlist — no drop when the drop costs more than the scenario adds -->
                  {#if u.stash_action === "watch" && u.watch_words}
                    <p class="mt-2 rounded-md bg-accent-soft px-3 py-2 text-sm leading-snug text-ink" data-testid="stash-watch">{u.watch_words}</p>
                  {/if}
                  <!-- ---- end IF-1 -->
                  {#if u.holds_horizon_gain != null}
                    <div class="mt-2 grid grid-cols-2 gap-2">
                      <StatTile label="As he is" value={f1(u.base_value)} caption={`week ${wk}`} size="sm" />
                      <StatTile label="Lineup gain if it holds" value={s1(u.holds_horizon_gain)} caption={span > 1 ? `weeks ${wk}–${last}` : `week ${wk}`} size="sm" />
                    </div>
                  {/if}
                </Card>
              {/each}
            </div>
            {#if data.upside.stashes.length > 3}
              <p class="text-sm text-ink-3" data-testid="stash-more">{data.upside.stashes.length - 3} more stashes: {data.upside.stashes.slice(3).map((u) => u.add.player_name).join(", ")}.</p>
            {/if}
          {/if}
          {#if data.upside.why}<p class="text-sm leading-snug text-ink-3" data-testid="stash-why">{data.upside.why}</p>{/if}
        {:else}
          <p class="ll-empty">No upside stash this week.</p>
        {/if}
      </section>
    {:else}
      <section class="space-y-3" data-testid="free-agents">
        <p class="text-sm text-ink-3">Week {wk} projection in {scoring}, with its range</p>
        <Tabs items={tabs} current={position} onpick={(p) => setParams({ position: p === "ALL" ? null : p })} size="sm" label="Position" testid="fa-pos" />
        {#if !fas.length}
          <p class="ll-empty">No free agent at this position has a projection this week.</p>
        {:else}
          <ListDetail>
            {#snippet list()}
              <Card pad={false} testid="fa-list">
                <ul class="divide-y divide-line">
                  {#each fas as f, i (`${f.gsis_id ?? f.sleeper_id ?? ""}#${i}`)}
                    <li>
                      <PlayerRow
                        player={{ ...f, player_name: f.player_name ?? "" }}
                        href={f.gsis_id ? withContext(`/player/${f.gsis_id}`, ctx) : null}
                        pane={{ from: "waiver", context: { add: f.sleeper_id, name: f.player_name } }} /* II-2: the drawer, with Evaluate add / drop */
                        rank={i + 1}
                        context={faContext(f)}
                        value={f1(f.projection)}
                        valueLabel={`Wk ${wk}`}
                        selected={fa === f}
                        onselect={() => pickFa(f)}
                        testid="fa-row"
                      />
                      <div class="px-3 pb-2 pl-[4.75rem]"><RangeBar value={f.projection} p10={f.p10} p25={f.p25} p75={f.p75} p90={f.p90} max={scale} /></div>
                    </li>
                  {/each}
                </ul>
              </Card>
            {/snippet}
          {#snippet detail()}
            {#if fa}
              <div class="hidden wide:block">
                <PlayerCard
                  player={{ ...fa, player_name: fa.player_name ?? "" }}
                  number={f1(fa.projection)}
                  numberLabel={`Week ${wk}`}
                  context={gateNote(fa)?.why ?? fa.injury_status}
                  line={[
                    fa.p25 != null && fa.p75 != null ? `Typical range ${Math.round(fa.p25)}–${Math.round(fa.p75)} (the middle 50% of outcomes).` : null,
                    fa.p10 != null && fa.p90 != null ? `A bad week to a good week: ${Math.round(fa.p10)}–${Math.round(fa.p90)} (8 weeks in 10).` : null,
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  href={fa.gsis_id ? withContext(`/player/${fa.gsis_id}`, ctx) : null}
                  pane={{ from: "waiver", context: { add: fa.sleeper_id, name: fa.player_name } }} /* II-2: the drawer, with Evaluate add / drop */
                  testid="fa-detail"
                >
                  {#snippet extra()}
                    <RangeBar value={fa!.projection} p10={fa!.p10} p25={fa!.p25} p75={fa!.p75} p90={fa!.p90} max={scale} />
                    <div class="mt-3 grid grid-cols-3 gap-2">
                      <StatTile label="Rest of season" value={fmt.whole(fa!.ros_points)} caption={fa!.ros_rank_pos ? `${fa!.position}${fa!.ros_rank_pos} in this league` : null} size="sm" />
                      <StatTile label="Points per game" value={f1(fa!.ppg_std)} caption={fa!.games_played != null ? `${fa!.games_played} games` : null} size="sm" />
                      <StatTile
                        label="Expected per game"
                        value={f1(fa!.expected_per_game)}
                        caption={fa!.diff_per_game != null ? `${s1(fa!.diff_per_game)} scored vs his work` : "what his work is worth"}
                        size="sm"
                      />
                    </div>
                    {#if fa!.position !== "QB" && fa!.position !== "K" && fa!.position !== "DEF"}
                      <div class="mt-3 grid grid-cols-2 gap-4">
                        <Meter label="Target share, last 3" value={fa!.target_share_l3} />
                        <Meter label="Snaps, last 3" value={fa!.snap_pct_l3} />
                      </div>
                    {/if}
                  {/snippet}
                </PlayerCard>
              </div>
            {/if}
          {/snippet}
        </ListDetail>
        {/if}
      </section>
    {/if}

    <!-- ---- IL-2 (Wave I-L): every team's adds of this week and last, from the league's moves (MFL's export too) -->
    {#if data.recent_adds}
      {@const ra = data.recent_adds}
      {@const span = ra.weeks.length > 1 ? `weeks ${ra.weeks[0]}–${ra.weeks[ra.weeks.length - 1]}` : `week ${ra.weeks[0]}`}
      <Card title="Recently added in this league" pad={false} testid="recent-adds">
        {#if ra.unavailable}
          <p class="px-4 pb-4 text-base text-ink-2" data-testid="recent-adds-unavailable">{ra.unavailable}.</p>
        {:else if !ra.rows.length}
          <p class="px-4 pb-4 text-base text-ink-2" data-testid="recent-adds-none">No adds in {span}.</p>
        {:else}
          <ul class="divide-y divide-line">
            {#each ra.rows as r, i (i)}
              <li class="flex items-center gap-2 px-3 py-2 {r.mine ? 'bg-accent-soft' : ''}" data-testid="recent-add">
                <span class="min-w-0 flex-1 truncate text-base">
                  {#if r.gsis_id}<a class="ll-name" href={withContext(`/player/${r.gsis_id}`, ctx)}>{r.player_name}</a>{:else}{r.player_name ?? "—"}{/if}
                  <span class="text-sm text-ink-3"> · {r.position ?? "—"}</span>
                </span>
                <span class="shrink-0 text-right text-sm text-ink-2">{r.team_name ?? "—"}{r.mine ? " (you)" : ""} · week {r.week}{r.waiver_bid != null ? ` · $${r.waiver_bid}` : ""}</span>
              </li>
            {/each}
          </ul>
          <p class="px-3 pt-1 pb-2 text-xs text-ink-3" data-testid="recent-adds-note">{ra.total} add{ra.total === 1 ? "" : "s"} in {span}{ra.total > ra.rows.length ? `, the latest ${ra.rows.length} shown` : ""} · {ra.source}</p>
        {/if}
      </Card>
    {/if}
    <!-- ---- end IL-2 -->

    <!-- IA-2: buy low / sell high moved to Trades (they are trades to ask about, not claims) -->
    <p class="text-sm text-ink-3" data-testid="buy-sell-moved">
      Players scoring below or above their work are on <a class="ll-name font-semibold" href={withContext("/trades", ctx)}>Trades ›</a><!-- ---- IP-3 fix round -->
    </p>

    <Expander title="How to read this" testid="howto">
      <div class="text-base leading-snug">{@html md(HOWTO)}</div>
    </Expander>
  {/if}
</main>
