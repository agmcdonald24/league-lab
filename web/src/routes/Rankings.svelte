<script lang="ts">
  // ---- IP-2 (Wave I-P): Rankings — this week's (or the rest of the season's) rankings at a position, for anyone, in the
  // scoring the bar holds (the league's own with a league). GET /api/rankings: the rank, the player, his game, the
  // projection with its range as a bar, his status, the defense's matchup tone (never the corner: Wave I-O graded it, no
  // measurable effect), who has him (with a league), and tiers drawn as lines (a tier = players the first of them
  // outscores in fewer than 55 weeks in 100). A row opens the player's pane; two to four picked rows go to Compare, whose
  // first answer is "Who should I start?". Everything the screen shows is in the URL (position, view, q, off, pick).
  import { rankingsPath, type RankPosition, type RankRow, type Rankings } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { openPane } from "../lib/pane.svelte";
  import { isRef, refLabel } from "../lib/refleague";
  import { Remote } from "../lib/remote.svelte";
  import { route, setParams } from "../lib/router.svelte";
  import type { Tone } from "../lib/research";
  import { fmt, teamLabel } from "../lib/theme";
  import Chips from "../components/Chips.svelte";
  import ErrorCard from "../components/ErrorCard.svelte";
  import Headshot from "../components/Headshot.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import TeamBadge from "../components/TeamBadge.svelte";
  import ToneChip from "../components/matchups/ToneChip.svelte";
  import {
    bar,
    compareHref,
    kickoff,
    LIMIT,
    MAX_PICKS,
    picksOf,
    PLURAL,
    POSITIONS,
    positionOf,
    scaleOf,
    STATE_WORD,
    statusOf,
    tierBreak,
    togglePick,
    VIEWS,
    viewOf,
  } from "../components/rankings/rank";

  let { options, league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  const params = $derived(route.current.params);
  const pos = $derived(positionOf(params.get("position")));
  const view = $derived(viewOf(params.get("view")));
  const qParam = $derived(params.get("q") ?? "");
  const offset = $derived(Math.max(0, Math.min(1000, Number(params.get("off") ?? 0) || 0)));
  const picks = $derived(picksOf(params.get("pick")));
  const browsing = $derived(isRef(league));
  const scoringName = $derived(browsing ? refLabel(league) : (options.find((o) => o.league_id === league)?.name ?? "this league"));

  let q = $derived(qParam); // a Back, a shared link: the box shows the URL's search; typing writes it
  let timer: ReturnType<typeof setTimeout> | undefined;
  function onq() {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const s = q.trim();
      if (s.length === 1) return; // one letter is not a search yet
      setParams({ q: s || null, off: null });
    }, 250);
  }
  $effect(() => () => clearTimeout(timer));

  const r = new Remote<Rankings>();
  const path = $derived(rankingsPath(league, { position: pos, view, q: qParam, offset, limit: LIMIT }));
  $effect(() => r.load(path, onauth, true));
  const d = $derived(r.data);
  const rows = $derived(d?.rows ?? []);
  const scale = $derived(scaleOf(rows, view));
  const posItems = $derived(
    ((d?.positions?.length ? d.positions : POSITIONS) as RankPosition[]).map((p) => ({ key: p, label: p === "FLEX" ? "Flex" : p })),
  );
  const owners = $derived(!browsing && rows.some((x) => "rostered_by_team" in x));
  const shown = $derived(d ? { from: d.total ? d.offset + 1 : 0, to: d.offset + rows.length } : null);
  const pickedNames = $derived(new Map(rows.filter((x) => x.gsis_id && picks.includes(x.gsis_id)).map((x) => [x.gsis_id as string, x.player_name])));

  const owner = (x: RankRow) => (team !== null && x.rostered_by_roster_id === team ? "Yours" : (x.rostered_by_team ?? "Free agent"));
  const range = (x: RankRow) => (x.p10 == null || x.p90 == null ? "no range" : `${fmt.whole(x.p10)}–${fmt.whole(x.p90)}`);
  // ---- IQ-4: a player on a bye is ranked by his remaining games; his row says so
  const game = (x: RankRow) =>
    x.opponent ? `${x.is_home === false ? "at" : "vs"} ${teamLabel(x.opponent)}` : x.bye_this_week ? "Bye this week" : "no game this week";
  // ---- end IQ-4
  const when = (x: RankRow) => (x.game_state ? STATE_WORD[x.game_state] : kickoff(x.kickoff_at));
  function pick(g: string | null) {
    if (!g) return;
    const next = togglePick(picks, g);
    setParams({ pick: next.length ? next.join(",") : null });
  }
  function open(x: RankRow) {
    if (x.gsis_id) openPane(x.gsis_id, { from: "list", context: { name: x.player_name } });
  }
  const GRID =
    "wide:grid wide:items-center wide:gap-3 " +
    "wide:grid-cols-[2rem_minmax(12rem,1.6fr)_minmax(7rem,0.8fr)_minmax(13rem,1.7fr)_minmax(6.5rem,0.7fr)_minmax(7rem,0.8fr)]";
</script>

<main class="space-y-4" data-testid="rankings">
  <ScreenHead eyebrow={browsing ? `Rankings · ${scoringName}` : "Players · Rankings"} title={view === "week" ? "Who to start this week" : "Rest-of-season rankings"} testid="rankings-head">
    {#snippet answer()}
      {#if d && !d.notice}
        <span data-testid="rankings-answer"
          >{d.total} {PLURAL[pos]} ranked by {view === "week" ? `week ${d.week}'s` : "the rest of the season's"} projection in {d.scoring} scoring{d.tiers
            ? `, in ${d.tiers} tier${d.tiers === 1 ? "" : "s"}`
            : ""}. Pick two to four to see who to start.</span
        >
      {:else}
        Every player ranked by his projection in {scoringName} scoring.
      {/if}
    {/snippet}
  </ScreenHead>

  <div class="space-y-2.5 rounded-lg border border-line bg-surface p-3" style="box-shadow:var(--ll-shadow)" data-testid="rankings-controls">
    <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
      <Chips items={VIEWS} current={view} label="When" testid="rankings-view" onpick={(k) => setParams({ view: k === "week" ? null : k, off: null })} />
      <Chips items={posItems} current={pos} label="Position" testid="rankings-pos" onpick={(k) => setParams({ position: k, off: null })} />
    </div>
    <label class="flex min-w-0 items-center gap-2">
      <span class="sr-only">Search a player by name</span>
      <input type="search" class="ll-input w-full py-1.5 text-sm wide:max-w-sm" placeholder="Search a player" maxlength="40" autocomplete="off" bind:value={q} oninput={onq} data-testid="rankings-search" />
    </label>
    {#if d?.tier_words}
      <p class="text-xs leading-snug text-ink-3" data-testid="rankings-tier-words">{d.tier_words}</p>
    {/if}
  </div>

  {#if r.error && !d}
    {#if r.failure && r.failure.kind !== "notfound" && r.failure.kind !== "other"}<ErrorCard failure={r.failure} onretry={() => r.retry()} />{:else}<p class="ll-error" data-testid="rankings-error">{r.error}</p>{/if}
  {:else if r.failure?.kind === "slow" && !d}
    <ErrorCard failure={r.failure} onretry={() => r.retry()} />
  {:else if !d}
    <div class="space-y-2" aria-label="Loading" data-testid="rankings-loading">
      {#each [0, 1, 2, 3, 4] as i (i)}<div class="ll-skel h-14"></div>{/each}
    </div>
  {:else if d.notice}
    <p class="ll-empty" data-testid="rankings-notice">{d.notice}</p>
  {:else if rows.length === 0}
    <p class="ll-empty" data-testid="rankings-empty">{qParam ? `No ${PLURAL[pos]} named like “${qParam}”.` : `No ${PLURAL[pos]} to rank yet.`}</p>
  {:else}
    {#if r.error}<p class="ll-error text-sm">{r.error}</p>{/if}
    <div class="overflow-hidden rounded-lg border border-line bg-surface {r.loading ? 'opacity-70' : ''}" style="box-shadow:var(--ll-shadow)">
      <div class="hidden border-b border-line py-2 pr-3 pl-12 {GRID}" aria-hidden="true">
        <span class="ll-label">#</span>
        <span class="ll-label">Player</span>
        <span class="ll-label">{view === "week" ? "Game" : "This week"}</span>
        <span class="ll-label">{view === "week" ? "Projected · range 8 weeks in 10" : "Rest of season · the range around it"}</span>
        <span class="ll-label">{view === "week" ? "Matchup" : "Games left"}</span>
        <span class="ll-label">{owners ? "Who has him" : "Status"}</span>
      </div>
      <ul data-testid="rankings-rows">
        {#each rows as x, i (`${x.key}#${i}`)}
          {@const b = bar(x, scale)}
          {@const picked = !!x.gsis_id && picks.includes(x.gsis_id)}
          {#if tierBreak(rows, i)}
            <li class="flex items-center gap-2 border-t-2 border-line-strong bg-raised/50 px-3 py-1 first:border-t-0" data-testid="tier-break" data-tier={x.tier}>
              <span class="text-[11px] font-bold tracking-[0.08em] text-ink-2 uppercase">Tier {x.tier}</span>
              <span class="h-px flex-1 bg-line" aria-hidden="true"></span>
            </li>
          {/if}
          {@const unclear = x.starter_unclear ?? null}
          {@const fixed = x.starter_corrected ?? null}
          <li
            class="flex items-stretch border-t border-line first:border-t-0 {picked ? 'bg-accent-soft' : ''}"
            style={unclear ? "border-left:3px dashed var(--ll-ink-3)" : ""}
            data-testid="rankings-row"
            data-key={x.key}
            data-tier={x.tier ?? ""}
            data-unclear={unclear ? "1" : null}
            data-corrected={fixed ? "1" : null}
          >
            <button
              type="button"
              class="grid w-10 shrink-0 place-items-center text-ink-3 hover:text-accent disabled:opacity-30"
              aria-pressed={picked}
              aria-label={picked ? `Unpick ${x.player_name}` : `Pick ${x.player_name} to compare`}
              disabled={!x.gsis_id || (!picked && picks.length >= MAX_PICKS)}
              onclick={() => pick(x.gsis_id)}
              data-testid="rankings-pick"
            >
              <span class="grid h-5 w-5 place-items-center rounded-sm border-2 {picked ? 'border-accent bg-accent text-on-accent' : 'border-line-strong'}" aria-hidden="true">
                {#if picked}<svg viewBox="0 0 16 16" width="12" height="12"><path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" stroke-width="2.5" /></svg>{/if}
              </span>
            </button>
            <button type="button" class="block min-w-0 flex-1 py-2.5 pr-3 text-left hover:bg-raised {GRID}" onclick={() => open(x)} data-testid="rankings-open">
              <!-- line 1 (phone) / the rank and the player (wide) -->
              <span class="tabnum hidden text-sm font-bold text-ink-3 wide:block" data-testid="rankings-rank">{x.rank}</span>
              <span class="flex min-w-0 items-center gap-2.5">
                <span class="tabnum w-6 shrink-0 text-right text-sm font-bold text-ink-3 wide:hidden">{x.rank}</span>
                {#if x.position === "DEF"}
                  <span class="grid h-9 w-9 shrink-0 place-items-center"><TeamBadge team={x.team} size="md" /></span>
                {:else}
                  <Headshot url={x.headshot_url} name={x.player_name} team={x.team} size={36} />
                {/if}
                <span class="min-w-0 flex-1">
                  <span class="flex min-w-0 items-center gap-1.5">
                    <span class="truncate font-semibold text-ink" data-testid="rankings-name">{x.player_name}</span>
                    {#if unclear}<span class="hidden shrink-0 rounded-sm bg-raised px-1.5 py-0.5 text-[11px] font-bold tracking-wide whitespace-nowrap text-ink-2 ring-1 ring-line-strong ring-inset wide:inline" data-testid="rankings-unclear-chip">Starter unclear</span>{/if}
                    {#if fixed}<span class="hidden shrink-0 rounded-sm bg-accent-soft px-1.5 py-0.5 text-[11px] font-bold tracking-wide whitespace-nowrap text-ink-2 ring-1 ring-line-strong ring-inset wide:inline" data-testid="rankings-corrected-chip">Starter corrected</span>{/if}
                  </span>
                  <span class="block truncate text-xs text-ink-3">
                    {x.position} · {teamLabel(x.team) ?? "—"}{#if statusOf(x)} · <span class="font-semibold text-warn">{statusOf(x)}</span>{/if}<span class="wide:hidden">
                      · {game(x)}{#if view === "season" && x.ros_games} · {x.ros_games} games left{/if}</span
                    >
                  </span>
                </span>
                <span class="flex shrink-0 flex-col items-end gap-0.5 wide:hidden">
                  <span class="tabnum block font-bold" data-testid="rankings-proj">{view === "week" ? fmt.pts(x.proj_points) : fmt.whole(x.proj_points)}</span>
                  {#if view === "week"}<ToneChip tone={(x.matchup?.tone ?? null) as Tone | null} size="sm" testid="rankings-chip" />{/if}
                </span>
              </span>
              <!-- the game (wide) -->
              <span class="hidden min-w-0 wide:block">
                <span class="block font-semibold">{game(x)}</span>
                <span class="block text-xs text-ink-3">{when(x)}</span>
              </span>
              <!-- the projection and its range: under the name on a phone -->
              <span class="mt-1 flex items-center gap-2 pl-[4.25rem] wide:mt-0 wide:pl-0">
                <span class="tabnum hidden w-12 shrink-0 text-right font-bold wide:block">{view === "week" ? fmt.pts(x.proj_points) : fmt.whole(x.proj_points)}</span>
                <span class="relative h-2.5 min-w-0 flex-1 rounded-sm bg-sunken" role="img" aria-label={`range ${range(x)}, projected ${fmt.pts(x.proj_points)}`} data-testid="rankings-bar">
                  {#if b}
                    <span class="absolute inset-y-0 rounded-sm" style="left:{b.lo}%;width:{Math.max(1, b.hi - b.lo)}%;background:color-mix(in oklab, var(--ll-series-1) 35%, transparent)"></span>
                    <span class="absolute -inset-y-0.5 w-0.5 rounded-sm" style="left:{b.mid}%;background:var(--ll-series-1)"></span>
                  {/if}
                </span>
                <span class="tabnum w-14 shrink-0 text-xs text-ink-3">{range(x)}</span>
              </span>
              <!-- the matchup (wide) -->
              <span class="hidden wide:block">
                {#if view === "week"}
                  <span title={x.matchup?.words ?? "No read of this defense yet"}><ToneChip tone={(x.matchup?.tone ?? null) as Tone | null} size="sm" testid="rankings-chip-wide" /></span>
                {:else}
                  <span class="tabnum text-sm">{x.ros_games ?? "—"}<span class="text-xs text-ink-3">{x.ros_points_per_game != null ? ` · ${fmt.pts(x.ros_points_per_game)} per game` : ""}</span></span>
                {/if}
              </span>
              <span class="hidden truncate text-sm text-ink-2 wide:block">{owners ? owner(x) : (statusOf(x) ?? (x.game_state ? STATE_WORD[x.game_state] : ""))}</span>
              {#if owners}<span class="mt-1 block truncate pl-[4.25rem] text-xs text-ink-3 wide:hidden">Who has him: {owner(x)}</span>{/if}
              {#if unclear}
                <!-- fix round: the sentence under the row (no tier: he is left out of them) -->
                <span class="mt-1 block pl-[4.25rem] text-xs leading-snug text-ink-2 wide:col-span-full wide:pl-[2.75rem]" data-testid="rankings-unclear-words"
                  ><span class="mr-1 rounded-sm bg-raised px-1.5 py-0.5 text-[11px] font-bold tracking-wide whitespace-nowrap text-ink-2 ring-1 ring-line-strong ring-inset wide:hidden" data-testid="rankings-unclear-chip-phone">Starter unclear</span>{unclear.words} No tier.</span
                >
              {/if}
              {#if fixed}
                <!-- ---- IQ-2: who starts, set by hand: one sentence under the row -->
                <span class="mt-1 block pl-[4.25rem] text-xs leading-snug text-ink-2 wide:col-span-full wide:pl-[2.75rem]" data-testid="rankings-corrected-words"
                  ><span class="mr-1 rounded-sm bg-accent-soft px-1.5 py-0.5 text-[11px] font-bold tracking-wide whitespace-nowrap text-ink-2 ring-1 ring-line-strong ring-inset wide:hidden" data-testid="rankings-corrected-chip-phone">Starter corrected</span>{fixed.words}</span
                >
              {/if}
            </button>
          </li>
        {/each}
      </ul>
    </div>
    <div class="flex flex-wrap items-center justify-between gap-2 text-sm text-ink-2" data-testid="rankings-pager">
      <span data-testid="rankings-count">Showing {shown?.from}–{shown?.to} of {d.total} {PLURAL[pos]}</span>
      <span class="flex gap-2">
        <button type="button" class="min-h-9 rounded-md border border-line-strong px-3 font-semibold disabled:opacity-40" disabled={d.offset === 0} onclick={() => setParams({ off: d && d.offset - LIMIT > 0 ? String(d.offset - LIMIT) : null })} data-testid="rankings-prev">Previous</button>
        <button type="button" class="min-h-9 rounded-md border border-line-strong px-3 font-semibold disabled:opacity-40" disabled={d.offset + rows.length >= d.total} onclick={() => setParams({ off: String((d?.offset ?? 0) + LIMIT) })} data-testid="rankings-next">Next</button>
      </span>
    </div>
    <div class="space-y-1 text-xs leading-snug text-ink-3" data-testid="rankings-honest">
      {#if d.assumes}<p>{d.assumes}</p>{/if}
      <!-- ---- IQ-4: what we know about the rest of season -->
      {#if view === "season" && d.ros_grade}<p data-testid="rankings-ros-grade">{d.ros_grade.words}</p>{/if}
      <!-- ---- end IQ-4 -->
      {#if d.tier_rule}<p>{d.tier_rule}</p>{/if}
      {#if d.unclear_words}<p data-testid="rankings-unclear-foot">{d.unclear_words}</p>{/if}
      {#if browsing}<p>Open your league to see who has him, in your league's own scoring.</p>{/if}
    </div>
  {/if}

  <!-- ---- IR-1 (Wave I-R): nobody who cannot play is ranked. They are listed here: the status, its source and time, the
  reason in words — never a number, never a tier -->
  {#if d && !d.notice && d.not_playing?.length}
    <section class="rounded-lg border border-line bg-surface p-3" style="box-shadow:var(--ll-shadow)" data-testid="rankings-not-playing" aria-labelledby="rk-np-h">
      <h2 id="rk-np-h" class="text-sm font-bold text-ink">Not playing <span class="font-normal text-ink-3">· {d.not_playing.length}</span></h2>
      {#if d.not_playing_words}<p class="mt-0.5 text-xs leading-snug text-ink-3">{d.not_playing_words}</p>{/if}
      <ul class="mt-2 grid gap-x-6 gap-y-1 wide:grid-cols-2">
        {#each d.not_playing as x (x.key)}
          <li data-testid="rankings-not-playing-row" data-key={x.key} data-code={x.code}>
            <button type="button" class="flex w-full min-w-0 items-center gap-2.5 rounded-md p-1.5 text-left hover:bg-raised" onclick={() => x.gsis_id && openPane(x.gsis_id, { from: "list", context: { name: x.player_name } })}>
              <Headshot url={x.headshot_url ?? null} name={x.player_name ?? undefined} team={x.team} size={32} />
              <span class="min-w-0 flex-1">
                <span class="flex min-w-0 items-center gap-1.5">
                  <span class="truncate font-semibold text-ink">{x.player_name}</span>
                  <span class="shrink-0 rounded-sm bg-raised px-1.5 py-0.5 text-[11px] font-bold tracking-wide whitespace-nowrap text-warn ring-1 ring-line-strong ring-inset" data-testid="rankings-not-playing-status">{x.status ?? "No number yet"}</span>
                </span>
                <span class="block truncate text-xs text-ink-3">{x.position} · {teamLabel(x.team) ?? "—"}{x.why ? ` · ${x.why}` : ""}</span>
                <span class="block text-xs leading-snug text-ink-2" data-testid="rankings-not-playing-words">{x.words}</span>
              </span>
              <span class="tabnum shrink-0 font-bold text-ink-3" title="No projection: he cannot play">—</span>
            </button>
          </li>
        {/each}
      </ul>
    </section>
  {/if}
  <!-- ---- end IR-1 -->

  {#if picks.length > 0}
    <!-- after the list: it sticks to the bottom of the screen while the list scrolls under it -->
    <div class="ll-rk-bar sticky z-20 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-accent bg-surface px-3 py-2 shadow-lg" data-testid="rankings-picks">
      <span class="min-w-0 text-sm text-ink-2">
        {picks.length} picked{pickedNames.size ? `: ${[...pickedNames.values()].join(", ")}` : ""}{picks.length < 2 ? " — pick one more" : ""}
      </span>
      <span class="flex shrink-0 items-center gap-2">
        <button type="button" class="min-h-9 px-2 text-sm font-semibold text-ink-3 hover:text-ink" onclick={() => setParams({ pick: null })} data-testid="rankings-picks-clear">Clear</button>
        {#if picks.length >= 2}
          <a href={compareHref(league, team, picks)} class="inline-flex min-h-9 items-center rounded-md bg-accent px-3 text-sm font-semibold text-on-accent" data-testid="rankings-compare"
            >Who should I start? Compare {picks.length} ›</a
          >
        {/if}
      </span>
    </div>
  {/if}
</main>

<style>
  .ll-rk-bar {
    bottom: calc(var(--ll-bar-h) + env(safe-area-inset-bottom) + 0.5rem);
  }
  @media (min-width: 56.25rem) {
    .ll-rk-bar {
      bottom: 0.75rem;
    }
  }
</style>
