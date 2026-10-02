<script lang="ts">
  // Waivers (plan G4; app/pages/2_Waiver_Wire.py on GET /api/waivers): the answer first ("Claim A, drop B: +3.4 this
  // week at TE, +9.0 over the next 4 weeks"), the moves as cards, then the free agents by position — each with his
  // headshot, this week's projection and its range, rest of season — list on the left, the picked one on the right
  // (desktop), then "How to read this". The position switch rewrites the URL in place (no Back step).
  import { get, peek, Unauthorized, decisionPaths, type FreeAgent, type Waivers } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { md, withContext } from "../lib/md";
  import { errorWords, f1, f2, rangeWords, s1, slotLabel, waiverAnswer } from "../lib/decisions";
  import { restoreScroll, route, setParams } from "../lib/router.svelte";
  import { fmt } from "../lib/theme";
  import Card from "../components/Card.svelte";
  import Expander from "../components/Expander.svelte";
  import ListDetail from "../components/ListDetail.svelte";
  import Md from "../components/Md.svelte";
  import Meter from "../components/Meter.svelte";
  import PlayerCard from "../components/PlayerCard.svelte";
  import PlayerRow from "../components/PlayerRow.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import StatTile from "../components/StatTile.svelte";
  import Tabs from "../components/Tabs.svelte";
  import MoveCard from "./decisions/MoveCard.svelte";
  import RangeBar from "./decisions/RangeBar.svelte";

  let { options, league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  let data = $state<Waivers | null>(null);
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

  const cards = $derived(data?.cards ?? []);
  const topCard = $derived(cards.find((c) => c.title === "Top claim") ?? null);
  const shown = $derived(new Set(cards.map((c) => `${c.add_sleeper_id}|${c.drop_sleeper_id ?? ""}`)));
  const more = $derived(
    (data?.moves ?? []).filter((m) => m.list_kind !== "nothing" && m.is_best_drop !== false && !shown.has(`${m.add.sleeper_id}|${m.drop?.sleeper_id ?? ""}`)),
  );
  const top = $derived(topCard?.move ?? cards[0]?.move ?? null);
  const lead = $derived(data ? waiverAnswer(data) : "");
  const gainMax = $derived(Math.max(0.5, ...cards.flatMap((c) => (c.move.week_gains ?? []).map((g) => g ?? 0))));
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
    "- **This week** is what the claim adds this week; **the next 4 weeks** add up this week and the next three, so covering a bye counts, and so do the games the dropped player would have started.\n" +
    "- **Who to drop**: the player your lineup misses least over those four weeks. We never suggest dropping someone we have no projection for yet: unknown is not zero.\n" +
    "- **Only the next four weeks count.** In a dynasty league, a young player's future is not in these numbers: look twice before dropping one.\n" +
    "- **Free agents** are ranked by this week's projection in your league's scoring. **Most weeks** is the band half his weeks land in; the thin line is a bad week to a good week (8 weeks in 10); the tick is the projection. **Rest of season** adds up every week left to your league's final.\n" +
    "- **Upside stash**: a free agent whose role grew in his last one to three games (more snaps, targets or carries: a teammate out, a new starter) before his points caught up. **If it holds** is his projection with the bigger role: a what-if, not a forecast. **Lineup gain if it holds** adds up this week and the next three; most stashes add nothing yet, which is why they are stashes, not starters.\n" +
    "- **Buy low**: players on other teams scoring *less* than their work is worth (points minus expected points per game, below zero). Their manager sees a bad box score; the work says it should turn around. **Sell high**: your players scoring *more* than their work supports.\n" +
    "- **Fit** is what the new team gains minus what the old team loses over the next four weeks. A big positive fit means he matters more to the other team than to his own: an easier ask when you buy, a better sale when you sell. To see a whole offer, use the Trade Finder.";

  function faContext(f: FreeAgent): string {
    const bits = [rangeWords(f.p25, f.p75, f.p10, f.p90), f.ros_points != null ? `rest of season ${fmt.whole(f.ros_points)}` : null];
    if (f.injury_status) bits.unshift(f.injury_status);
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
    </ScreenHead>

    <div class="grid grid-cols-2 gap-2 wide:grid-cols-4" data-testid="waiver-tiles">
      <StatTile label="This week" value={top ? s1(top.weekly_gain) : "+0.0"} caption={top ? `${top.add.player_name}` : "no claim helps"} />
      <StatTile label={`Next ${span} weeks`} value={top ? s1(top.horizon_gain) : "+0.0"} caption={span > 1 ? `weeks ${wk}–${last}` : `week ${wk}`} />
      <StatTile label="Your lineup" value={f1(data.lineup_value)} caption={top && top.weekly_gain > 0 ? `→ ${f1(top.lineup_after)} with the claim` : `week ${wk}, in ${scoring}`} />
      <StatTile
        label="Closest call"
        value={data.weakest?.slot ? slotLabel(data.weakest.slot) : "—"}
        caption={data.weakest?.player?.player_name
          ? data.weakest.replacement_name
            ? `${data.weakest.player.player_name} over ${data.weakest.replacement_name} by ${f2(data.weakest.margin)}`
            : `${data.weakest.player.player_name}: nobody on the bench can fill in`
          : "no starter is a decision this week"}
      />
    </div>

    {#if data.inputs_current === false || data.on_current_lineup === false}
      <p class="rounded-lg bg-warn-soft p-3 text-sm text-ink" data-testid="stale">
        These claims were computed before the latest {data.inputs_current === false ? "rosters or injury reports" : "lineup"}: a player may already be gone. They refresh with the nightly update.
      </p>
    {/if}

    {#if cards.length}
      <div class="grid grid-cols-1 gap-3 wide:grid-cols-3" data-testid="waiver-moves">
        {#each cards as c (`${c.add_sleeper_id}|${c.drop_sleeper_id}`)}
          <MoveCard move={c.move} title={c.title} week={wk} lastWeek={last} {ctx} {gainMax} headline={c !== topCard} />
        {/each}
      </div>
    {/if}
    {#if more.length}
      <Expander title={`${more.length} more claims that help, best first`} testid="more-moves">
        <ul class="-mx-3 divide-y divide-line" data-testid="more-list">
          {#each more as m, i (`${m.add.sleeper_id}|${m.drop?.sleeper_id}|${i}`)}
            <li>
              <PlayerRow
                player={{ ...m.add, player_name: m.add.player_name ?? "" }}
                href={m.add.gsis_id ? withContext(`/player/${m.add.gsis_id}`, ctx) : null}
                context={m.words?.why ?? (m.drop ? `drop ${m.drop.player_name} · ${s1(m.weekly_gain)} this week` : `no drop · ${s1(m.weekly_gain)} this week`)}
                value={s1(m.horizon_gain)}
                valueLabel={`${span} weeks`}
                testid="more-move"
              />
            </li>
          {/each}
        </ul>
        <p class="mt-2 text-sm text-ink-3">One row per player: the drop that costs your lineup least. Start-now claims gain this week; the others help later.</p>
      </Expander>
    {/if}

    <!-- H1 (Wave H): the upside stash (2_Waiver_Wire.py's third card region) and buy low / sell high (the Trade Finder's lists) -->
    {#if data.upside}
      <section class="space-y-3" data-testid="upside">
        <h2 class="text-xl font-bold">Upside stash</h2>
        <p class="text-sm text-ink-3">{data.upside.title}.</p>
        {#if data.upside.stashes.length}
          <div class="grid grid-cols-1 gap-3 wide:grid-cols-3">
            {#each data.upside.stashes.slice(0, 3) as u (u.add.sleeper_id ?? u.add.gsis_id)}
              <Card testid="stash">
                <PlayerRow
                  player={{ ...u.add, player_name: u.add.player_name ?? "" }}
                  href={u.add.gsis_id ? withContext(`/player/${u.add.gsis_id}`, ctx) : null}
                  context={u.change_text ? `${u.change_text} since week ${u.since_week}` : null}
                  value={f1(u.scenario_value)}
                  valueLabel="If it holds"
                  testid="stash-player"
                />
                <p class="mt-2 text-base font-semibold leading-snug" data-testid="stash-headline"><Md text={u.headline} {ctx} /></p>
                <ul class="mt-1 space-y-1 text-sm leading-snug text-ink-2" data-testid="stash-lines">
                  {#each u.lines as line, i (i)}<li><Md text={line} {ctx} /></li>{/each}
                </ul>
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
      </section>
    {/if}

    {#if data.trade_lists && (data.trade_lists.buy_line || data.trade_lists.buy_low.length)}
      {@const tl = data.trade_lists}
      <section class="space-y-3" data-testid="buy-sell">
        <h2 class="text-xl font-bold">Buy low, sell high</h2>
        <p class="text-sm text-ink-3">Players scoring below (or above) what their work is worth, in {scoring}: trades to ask about.</p>
        <div class="grid grid-cols-1 gap-3 wide:grid-cols-2">
          <Card title="Buy low" testid="buy-low">
            {#if tl.buy_line}<p class="text-base leading-snug" data-testid="buy-line"><Md text={tl.buy_line} {ctx} /></p>{/if}
            {#if tl.best_buy_by_position && Object.keys(tl.best_buy_by_position).length}
              <h3 class="ll-label mt-3">Best by position</h3>
              <ul class="-mx-4 divide-y divide-line">
                {#each Object.entries(tl.best_buy_by_position) as [pos, r] (pos)}
                  <li>
                    <PlayerRow
                      player={{ ...r.player, player_name: r.player.player_name ?? "" }}
                      href={r.player.gsis_id ? withContext(`/player/${r.player.gsis_id}`, ctx) : null}
                      context={`${r.team_name ?? "another team"} · ${s1(r.diff_per_game)} a game vs his work · you gain ${s1(r.gain_week)} this week`}
                      value={s1(r.fit_horizon)}
                      valueLabel="Fit"
                      testid="buy-best"
                    />
                  </li>
                {/each}
              </ul>
            {/if}
          </Card>
          <Card title="Sell high" testid="sell-high">
            {#if tl.sell_line}<p class="text-base leading-snug" data-testid="sell-line"><Md text={tl.sell_line} {ctx} /></p>{/if}
            {#if tl.sell_high.length}
              <ul class="-mx-4 mt-2 divide-y divide-line">
                {#each tl.sell_high.slice(0, 4) as r (r.player.sleeper_id ?? r.player.gsis_id)}
                  <li>
                    <PlayerRow
                      player={{ ...r.player, player_name: r.player.player_name ?? "" }}
                      href={r.player.gsis_id ? withContext(`/player/${r.player.gsis_id}`, ctx) : null}
                      context={`${s1(r.diff_per_game)} a game vs his work · best fit ${r.team_name ?? "—"}`}
                      value={s1(r.fit_horizon)}
                      valueLabel="Fit"
                      testid="sell-row"
                    />
                  </li>
                {/each}
              </ul>
            {/if}
          </Card>
        </div>
        {#if tl.buy_low.length}
          <Expander title={`Buy low · ${tl.buy_low.length} players scoring below their usage`} testid="buy-list">
            <ul class="-mx-3 divide-y divide-line">
              {#each tl.buy_low as r, i (`${r.player.sleeper_id}|${i}`)}
                <li>
                  <PlayerRow
                    player={{ ...r.player, player_name: r.player.player_name ?? "" }}
                    href={r.player.gsis_id ? withContext(`/player/${r.player.gsis_id}`, ctx) : null}
                    context={`${r.team_name ?? "—"} · PPG ${f1(r.ppg)} vs ${f1(r.xppg)} expected · you gain ${s1(r.gain_week)}, they lose ${f1(r.loss_week)}`}
                    value={s1(r.fit_horizon)}
                    valueLabel={tl.weeks ? `Fit ${tl.weeks}` : "Fit"}
                    testid="buy-row"
                  />
                </li>
              {/each}
            </ul>
          </Expander>
        {/if}
      </section>
    {/if}

    <section class="space-y-3" data-testid="free-agents">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h2 class="text-xl font-bold">Free agents</h2>
        <p class="text-sm text-ink-3">Week {wk} projection in {scoring}, with its range</p>
      </div>
      <Tabs items={tabs} current={position} onpick={(p) => setParams({ position: p === "ALL" ? null : p })} size="sm" label="Position" testid="fa-pos" />
      {#if !fas.length}
        <p class="ll-empty">No free agent at this position has a projection this week.</p>
      {:else}
        <ListDetail>
          {#snippet list()}
            <Card pad={false} testid="fa-list">
              <ul class="divide-y divide-line">
                {#each fas as f, i (f.gsis_id ?? f.sleeper_id ?? i)}
                  <li>
                    <PlayerRow
                      player={{ ...f, player_name: f.player_name ?? "" }}
                      href={f.gsis_id ? withContext(`/player/${f.gsis_id}`, ctx) : null}
                      rank={i + 1}
                      context={faContext(f)}
                      value={f1(f.projection)}
                      valueLabel={`Wk ${wk}`}
                      selected={fa === f}
                      onselect={() => (picked = f.gsis_id ?? f.sleeper_id ?? null)}
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
                  context={fa.injury_status}
                  line={[
                    fa.p25 != null && fa.p75 != null ? `Most weeks ${Math.round(fa.p25)}–${Math.round(fa.p75)} (half his weeks land there).` : null,
                    fa.p10 != null && fa.p90 != null ? `A bad week to a good week: ${Math.round(fa.p10)}–${Math.round(fa.p90)} (8 weeks in 10).` : null,
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  href={fa.gsis_id ? withContext(`/player/${fa.gsis_id}`, ctx) : null}
                  testid="fa-detail"
                >
                  {#snippet extra()}
                    <RangeBar value={fa!.projection} p10={fa!.p10} p25={fa!.p25} p75={fa!.p75} p90={fa!.p90} max={scale} />
                    <div class="mt-3 grid grid-cols-3 gap-2">
                      <StatTile label="Rest of season" value={fmt.whole(fa!.ros_points)} caption={fa!.ros_rank_pos ? `${fa!.position}${fa!.ros_rank_pos} in this league` : null} size="sm" />
                      <StatTile label="Points a game" value={f1(fa!.ppg_std)} caption={fa!.games_played != null ? `${fa!.games_played} games` : null} size="sm" />
                      <StatTile
                        label="Expected a game"
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

    <Expander title="How to read this" testid="howto">
      <div class="text-base leading-snug">{@html md(HOWTO)}</div>
    </Expander>
  {/if}
</main>
