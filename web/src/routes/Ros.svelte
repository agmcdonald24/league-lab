<script lang="ts">
  import { APP_NAME } from "../lib/brand";
  // Rest of season (plan F2): the answer first (#1 at the position), then "Yours", then the list
  // (Rank · Player · Points · Games · Playoffs) from GET /api/ros. Position switch: QB RB WR TE, K and DEF only when
  // the league starts them, All = the overall rank. The switch rewrites the URL in place (no Back step).
  import { ApiError, get, paths, peek, Unauthorized, type MyWeek, type RosList, type RosPlayer } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { md, withContext } from "../lib/md";
  import { answerLine, rankOf, weeksSpan, whole, yoursLine } from "../lib/ros";
  // ---- IA-3 (Wave I-A): headshots, the range bar, the pieces (columns from 900 px, a tap-to-expand row everywhere),
  // the sort, "why this number", the market line and the rankings' honesty line
  import { byeWords, PIECE_COLUMNS, PIECE_LABELS, pieceText, rangeBar, rangeWords, RANKINGS_HOWTO, sortPlayers, type SortKey } from "../lib/ros";
  import Headshot from "../components/Headshot.svelte";
  // ---- end IA-3
  // ---- IB-3 (Wave I-B): "Value to my lineup" first (a view toggle at the top; the default with a team picked)
  import { valueText } from "../lib/ros"; // ---- II-4: IB-3's view helpers (ROS_VIEWS, lineupPath …) gave way to SEASON_VIEWS
  import Tabs from "../components/Tabs.svelte";
  // ---- end IB-3
  // ---- II-4 (Wave I-I): the three named views — My roster outlook (default) / Potential upgrades (before acquisition
  // cost) / Rest-of-season projections — each with its counterfactual said at the top (GET /api/ros?view=…)
  import { perGameText, PROJECTIONS_VIEW, SEASON_SHORT, SEASON_VIEWS, seasonAnswer, seasonPath, seasonView, UPGRADE_WHO, upgradeWho } from "../lib/ros";
  // ---- end II-4
  import { restoreScroll, route, setParams } from "../lib/router.svelte";
  import Expander from "../components/Expander.svelte";
  import Chips from "../components/Chips.svelte";
  import PosBadge from "../components/PosBadge.svelte";
  import TeamBadge from "../components/TeamBadge.svelte";
  import Md from "../components/Md.svelte";

  let {
    options,
    league,
    team,
    onauth,
  }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  const BASE = ["QB", "RB", "WR", "TE"];
  // ---- IC-4 (Wave I-D): MyFantasyLeague's team units (a team QB / a team K): their own chips, the team's badge where
  // a player's face goes, the line their weeks are priced from
  const UNITS = ["TMQB", "TMPK"];
  const UNIT_LABEL: Record<string, string> = { TMQB: "Team QB", TMPK: "Team K" };
  const isUnit = (p: RosPlayer) => !!p.unit || UNITS.includes(p.position ?? "");
  // ---- end IC-4
  let data = $state<RosList | null>(null);
  let error = $state<string | null>(null);
  let slots = $state<string[]>([]); // the league's lineup slots (from My Week): K / DEF tabs only when it has them

  const ctx = $derived({ league, team });
  const position = $derived.by(() => {
    const p = (route.current.params.get("position") ?? "ALL").toUpperCase();
    return [...BASE, "K", "DEF", ...UNITS, "ALL"].includes(p) ? p : "ALL"; // IC-4: the team units
  });
  const positions = $derived.by(() => {
    if (data?.positions?.length) return [...data.positions.filter((p) => p !== "ALL"), "ALL"];
    const extra = ["K", "DEF", ...UNITS].filter((p) => slots.includes(p) || position === p); // IC-4: TMQB / TMPK
    return [...BASE, ...extra, "ALL"];
  });
  const leagueName = $derived(options.find((o) => o.league_id === league)?.name ?? "this league");
  // ---- IB-3: the view and, in "Value to my lineup", whose players (in the URL: shareable, no Back step)
  const view = $derived(seasonView(route.current.params.get("view"), team)); // ---- II-4
  const who = $derived(upgradeWho(route.current.params.get("who"))); // ---- II-4
  const isLineup = $derived(view !== "projections" && team !== null); // ---- II-4: a value column (outlook / upgrades)
  const viewLabel = $derived(SEASON_VIEWS.find((v) => v.key === view)?.label ?? "Rest-of-season projections"); // ---- II-4
  const sv = $derived(data?.season_view ?? (view === "projections" ? PROJECTIONS_VIEW : null)); // ---- II-4: the counterfactual

  // ---- end IB-3
  const players = $derived(data?.players ?? []);
  const span = $derived(data ? weeksSpan(data.from_week, data.last_week) : null);

  // K / DEF: does this league start them? The /api/ros contract does not say (requested of F3: `positions`); My Week's
  // lineup does, and it is usually in memory already (the user came from My Week).
  $effect(() => {
    const l = league;
    const t = team;
    if (t === null) return;
    const path = paths.myWeek(l, t);
    const hit = peek<MyWeek>(path);
    const take = (d: MyWeek) => (slots = d.lineup_full.map((r) => r.position ?? "").concat(d.lineup_full.map((r) => r.slot)));
    if (hit) take(hit);
    else
      get<MyWeek>(path)
        .then((d) => league === l && take(d))
        .catch(() => {});
  });

  $effect(() => {
    const l = league;
    const p = position;
    error = null;
    const path = seasonPath(l, p, team, view, who); // ---- II-4 (IB-3: lineupPath / paths.ros)
    const hit = peek<RosList>(path);
    if (hit) {
      data = hit;
      restoreScroll();
      return;
    }
    data = null;
    get<RosList>(path)
      .then((d) => {
        if (league !== l || position !== p || path !== currentPath()) return;
        data = d;
        restoreScroll();
      })
      .catch((e) => {
        if (league !== l || position !== p || path !== currentPath()) return;
        if (e instanceof Unauthorized) onauth();
        else if (e instanceof ApiError && e.status === 404) error = `${APP_NAME} cannot find this league on Sleeper. Pick another above.`;
        else if (e instanceof ApiError && e.status === 502) error = "Sleeper did not answer. Try again in a minute.";
        else if (e instanceof ApiError && e.status === 503) error = "The numbers are not ready yet. Try again in a few minutes.";
        else error = e instanceof Error ? e.message : String(e);
      });
  });

  function pick(p: string) {
    setParams({ position: p });
  }
  // ---- IB-3
  const currentPath = () => seasonPath(league, position, team, view, who); // ---- II-4
  function pickView(v: string) {
    setParams({ view: v === "outlook" ? null : v, who: null }); // ---- II-4: My roster outlook is the default
  }
  function pickWho(w: string) {
    setParams({ who: w === "all" ? null : w });
  }
  // ---- end IB-3

  // ---- IA-3: the sort (a header tap; again flips it), the open rows, the pieces of the screen's position
  let sortKey = $state<SortKey>("rank");
  let sortDir = $state<"asc" | "desc">("asc");
  let open = $state<Record<string, boolean>>({});
  $effect(() => {
    void position;
    void league;
    void view; // ---- IB-3
    void who; // ---- IB-3
    sortKey = "rank";
    sortDir = "asc";
    open = {};
  });
  const pieceCols = $derived(position === "ALL" ? [] : (data?.piece_columns?.[position] ?? PIECE_COLUMNS[position] ?? []));
  const shown = $derived(sortPlayers(players, sortKey, sortDir, isLineup ? "LINEUP" : position));
  const rankAt = $derived(new Map(players.map((p, i) => [p, isLineup ? (p.lineup_rank ?? i + 1) : rankOf(p, i, position)])));
  const maxP90 = $derived(Math.max(1, ...players.map((p) => p.p90 ?? p.ros_points ?? 0)));
  function sortBy(k: SortKey) {
    if (sortKey === k) sortDir = sortDir === "asc" ? "desc" : "asc";
    else {
      sortKey = k;
      sortDir = k === "rank" ? "asc" : "desc";
    }
  }
  const ariaSort = (k: SortKey) => (sortKey === k ? (sortDir === "asc" ? "ascending" : "descending") : undefined);
  const arrow = (k: SortKey) => (sortKey === k ? (sortDir === "asc" ? "▲" : "▼") : "");
  const rowKey = (p: RosPlayer, i: number) => p.gsis_id ?? p.player_key ?? `${p.player_name}-${i}`;
  // the expand row spans the columns showing at this width (a larger colspan adds phantom columns to a fixed table)
  let vw = $state(typeof window === "undefined" ? 390 : window.innerWidth);
  const ncols = $derived(4 + (vw >= 640 ? 3 : 0) + (vw >= 900 ? pieceCols.length : 0) + (isLineup ? 1 : 0) - (isLineup && vw < 640 ? 1 : 0) + (view === "projections" && vw >= 640 ? 1 : 0)); // II-4: per game
  function toggle(k: string) {
    open = { ...open, [k]: !open[k] };
  }
  // ---- end IA-3
  const label = (p: string) => (p === "ALL" ? "All" : (UNIT_LABEL[p] ?? p)); // IC-4
</script>


<svelte:window bind:innerWidth={vw} />

<main class="space-y-4" data-testid="ros">
  <header class="space-y-1.5">
    <p class="text-label font-bold tracking-[0.08em] text-accent uppercase">Rest of season · {leagueName}</p>
    <h1 class="text-2xl leading-tight font-extrabold tracking-tight wide:text-3xl" data-testid="ros-title">
      {team !== null ? viewLabel : "Rest-of-season projections"}<!-- ---- II-4 -->
    </h1>
  </header>
  <!-- ---- IB-3: the view toggle (Value to my lineup leads; it needs a team) -->
  {#if team !== null}
    <!-- ---- II-4: the three named views (short labels on a phone; the heading carries the full name) -->
    <Tabs items={SEASON_VIEWS.map((v) => ({ key: v.key, label: vw < 640 ? SEASON_SHORT[v.key] : v.label }))} current={view} onpick={pickView} fill size="sm" label="Season view" testid="ros-view" />
  {/if}
  <Chips label="Position" testid="ros-pos" current={position} onpick={pick} items={positions.map((p) => ({ key: p, label: label(p) }))} />
  {#if view === "upgrades" && team !== null}<!-- ---- II-4: whose players (yours are My roster outlook) -->
    <Chips label="Whose" testid="ros-who" current={who} onpick={pickWho} items={UPGRADE_WHO} />
  {/if}

  {#if error}
    <p class="ll-error">{error}</p>
  {:else if !data}
    <div class="space-y-3" aria-label="Loading" data-testid="loading">
      <div class="ll-skel h-16"></div>
      {#each [0, 1, 2, 3, 4] as i (i)}<div class="ll-skel h-8"></div>{/each}
    </div>
  {:else if players.length === 0}
    <p class="rounded-lg bg-raised p-4 text-base" data-testid="ros-empty">
      No weeks left in {leagueName}'s season: rest-of-season totals come back with next season's schedule.
    </p>
  {:else}
    <section class="relative space-y-1.5 overflow-hidden rounded-lg border border-line bg-surface p-4 pl-5" style="box-shadow:var(--ll-shadow)" data-testid="ros-answer">
      {#if isLineup}
        <!-- ---- IB-3: the lineup view's answer: the top row and why, then what the number means -->
        <p class="text-lg leading-snug" data-testid="ros-lineup-answer"><Md text={seasonAnswer(view, players[0], data.window?.span ?? span)} {ctx} /></p>
      {:else}
        <p class="text-lg leading-snug"><Md text={answerLine(players[0], position)} {ctx} /></p>
        {#if team !== null}<p class="text-base leading-snug" data-testid="ros-yours">{yoursLine(players, team, position)}</p>{/if}
      {/if}
      <!-- ---- II-4: the view's counterfactual, said once; an acquisition view names the costs it leaves out -->
      {#if sv}
        <p class="text-sm leading-snug text-ink-2" data-testid="ros-counterfactual"><span class="font-semibold text-ink">{sv.label}:</span> {sv.counterfactual}</p>
        {#if sv.costs_not_included.length && view === "upgrades"}
          <p class="text-sm leading-snug text-ink-2" data-testid="ros-costs">Not included: {sv.costs_not_included.join(", ")}.</p>
        {/if}
      {:else if isLineup && data.lineup_note}<p class="text-sm leading-snug text-ink-2" data-testid="ros-lineup-note">{data.lineup_note}</p>{/if}
      <!-- ---- end II-4 -->
      <p class="text-sm leading-snug text-ink-3">
        {span ? `${span[0].toUpperCase()}${span.slice(1)}` : "The weeks left"} in {leagueName} scoring, up to the league's final. A bye
        is a week with no game: he plays one fewer.{view === "projections" ? " Ranked among everyone at the position, rostered or free agent." : ""}<!-- II-4 -->
        {#if data?.lines_note}{" " + data.lines_note}{/if}
      </p>
      <span class="absolute inset-y-0 left-0 w-1 bg-accent" aria-hidden="true"></span>
    </section>

    <!-- ---- IA-3: how to read the rankings (the honesty line), then the table -->
    <section class="rounded-lg border border-line bg-raised p-4 text-sm leading-snug text-ink-2" data-testid="ros-honesty">
      <Md text={data.howto_rankings ?? RANKINGS_HOWTO} {ctx} />
    </section>

    {#snippet head(k: SortKey, text: string, cls: string, title?: string)}
      <th class="py-2 font-semibold {cls}" aria-sort={ariaSort(k)} {title}>
        <button type="button" class="ll-label inline-flex min-h-8 items-center gap-0.5 font-semibold uppercase hover:text-ink" onclick={() => sortBy(k)} data-testid={`ros-sort-${k}`}>
          {text}<span class="text-[9px] text-accent" aria-hidden="true">{arrow(k)}</span>
        </button>
      </th>
    {/snippet}

    <div class="overflow-hidden rounded-lg border border-line bg-surface" style="box-shadow:var(--ll-shadow)">
    <table class="w-full table-fixed border-collapse text-base" data-testid="ros-table">
      <thead>
        <tr class="border-b border-line bg-raised text-left text-ink-3">
          {@render head("rank", "Rank", "w-[3.75rem] pr-1 pl-3")}
          <th class="ll-label py-2 pr-1 font-semibold">Player</th>
          {#if isLineup}{@render head("lineup_points", "Value", "w-[3.75rem] text-right", view === "upgrades" ? "What he would add to your lineup over the weeks left, before acquisition cost" : "What your lineup loses without him over the weeks left")}{/if}<!-- II-4 -->
          {@render head("ros_games", "Games", "hidden w-[3.5rem] text-right sm:table-cell", "Games left (byes out)")}
          {@render head("ros_points", "Points", `w-[3.75rem] text-right ${isLineup ? "hidden sm:table-cell" : ""}`, "Rest of season, this league's scoring")}
          {#if view === "projections"}<th class="ll-label hidden w-[4.5rem] py-2 text-right font-semibold sm:table-cell" title="Points per game over the games left">Per game</th>{/if}<!-- II-4 -->
          {@render head("range", "Likely", "hidden w-[7rem] pl-3 text-left sm:table-cell", "Where 8 seasons in 10 would land")}
          {@render head("playoff_points", "Playoffs", "hidden w-[4.5rem] text-right sm:table-cell", "Points in the playoff weeks")}
          {#each pieceCols as c (c)}
            {@render head(`pg:${c}`, PIECE_LABELS[c]?.[0] ?? c, "hidden w-[3.75rem] text-right wide:table-cell", `${PIECE_LABELS[c]?.[1] ?? c} per game, projected`)}
          {/each}
          <th class="w-[2.25rem] py-2 pr-2"><span class="sr-only">More</span></th>
        </tr>
      </thead>
      <tbody>
        {#each shown as p, i (rowKey(p, i))}
          {@const yours = team !== null && p.rostered_by_roster_id === team}
          {@const k = rowKey(p, i)}
          {@const bar = rangeBar(p, maxP90)}
          {@const bye = byeWords(p.bye_weeks)}
          <tr class="{isLineup && p.lineup_why ? '' : 'border-b'} border-line align-middle {open[k] ? '' : 'last:border-0'} {yours ? 'bg-accent-soft' : ''}" data-testid="ros-row">
            <td class="tabnum py-2 pr-1 pl-3 font-semibold text-ink-3">{rankAt.get(p) ?? "—"}</td>
            <td class="py-2 pr-1 leading-snug break-words">
              <div class="flex min-w-0 items-center gap-2">
                {#if isUnit(p)}<span class="inline-flex w-8 shrink-0 justify-center" data-testid="ros-unit-badge"><TeamBadge team={p.team} /></span
                  >{:else}<Headshot url={p.headshot_url ?? null} team={p.team} size={32} />{/if}
                <div class="min-w-0">
                  {#if p.gsis_id}
                    <a class="ll-name font-semibold" href={withContext(`/player/${p.gsis_id}`, ctx)}>{p.player_name}</a>
                  {:else if isUnit(p) && p.player_key && p.priced_from}
                    <a class="ll-name font-semibold" href={withContext(`/player/${p.player_key}`, ctx)} data-testid="ros-unit-name">{p.player_name}</a>
                  {:else}
                    {p.player_name}
                  {/if}
                  <div class="mt-0.5 flex min-w-0 items-center gap-1 text-xs text-ink-3">
                    <PosBadge pos={isUnit(p) ? (UNIT_LABEL[p.position ?? ""] ?? p.position) : p.position} />{#if p.position !== "DEF" && !isUnit(p)}<TeamBadge team={p.team} />{/if}
                    {#if p.bye_weeks?.length}<span class="shrink-0 tabnum" data-testid="ros-bye">bye {p.bye_weeks.join(", ")} ·</span>{/if}
                    <span class="truncate {yours ? 'font-semibold text-accent' : ''}">{yours ? "yours" : (p.rostered_by_team ?? "free agent")}</span>
                  </div>
                </div>
              </div>
            </td>
            {#if isLineup}
              <td class="tabnum py-2 text-right font-bold" data-testid="ros-value">{valueText(p.lineup_points)}<span class="block text-[11px] font-normal text-ink-3 sm:hidden">{whole(p.ros_points) ?? "—"} pts</span></td>
            {/if}
            <td class="tabnum hidden py-2 text-right text-ink-2 sm:table-cell">{p.ros_games ?? "—"}</td>
            <td class="tabnum py-2 text-right {isLineup ? 'hidden font-semibold text-ink-2 sm:table-cell' : 'font-bold'}" data-testid="ros-points">{whole(p.ros_points) ?? "—"}<span class="block text-[11px] font-normal text-ink-3 sm:hidden">{p.ros_games ?? "—"} g</span></td>
            {#if view === "projections"}<td class="tabnum hidden py-2 text-right text-ink-2 sm:table-cell" data-testid="ros-per-game">{perGameText(p)}</td>{/if}<!-- II-4 -->
            <td class="hidden py-2 pl-3 sm:table-cell">
              {#if bar}
                <div class="relative h-2 w-full rounded-full bg-sunken" aria-hidden="true">
                  <div class="absolute inset-y-0 rounded-full" style="left:{bar.lo}%;width:{Math.max(bar.hi - bar.lo, 1)}%;background:color-mix(in oklab, var(--ll-series-1) 45%, transparent)"></div>
                  <div class="absolute top-1/2 h-2.5 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-sm" style="left:{bar.mid}%;background:var(--ll-series-1)"></div>
                </div>
                <span class="tabnum block pt-0.5 text-[11px] text-ink-3">{rangeWords(p)}</span>
              {:else}<span class="text-ink-3">—</span>{/if}
            </td>
            <td class="tabnum hidden py-2 text-right text-ink-2 sm:table-cell">{whole(p.playoff_points) ?? "—"}</td>
            {#each pieceCols as c (c)}
              <td class="tabnum hidden py-2 text-right text-ink-2 wide:table-cell" data-testid={`ros-pg-${c}`}>{pieceText(c, p.per_game?.[c])}</td>
            {/each}
            <td class="py-2 pr-2 text-right">
              <button type="button" class="inline-flex size-8 items-center justify-center rounded-sm text-ink-3 hover:bg-raised hover:text-ink"
                aria-expanded={!!open[k]} aria-label={`${open[k] ? "Hide" : "Show"} the pieces of ${p.player_name}'s number`}
                onclick={() => toggle(k)} data-testid="ros-toggle">
                <span aria-hidden="true" class="text-lg leading-none transition-transform {open[k] ? 'rotate-90' : ''}">›</span>
              </button>
            </td>
          </tr>
          {#if isLineup && p.lineup_why}
            <!-- ---- IB-3: why he ranks here for this roster, the row's full width (the name column is narrow on a phone) -->
            <tr class="border-b border-line {open[k] ? '' : 'last:border-0'} {yours ? 'bg-accent-soft' : ''}">
              <td colspan={ncols} class="px-3 pt-0 pb-2 text-xs leading-snug text-ink-2 sm:pl-[4.25rem]" data-testid="ros-lineup-why">{p.lineup_why}
                <!-- ---- II-4: injury cover apart (never in the value); an upgrade's next step (where its cost is priced) -->
                {#if view === "outlook" && p.cover}<span class="mt-0.5 block text-ink-3" data-testid="ros-cover">{p.cover.words}</span>{/if}
                {#if view === "upgrades" && p.acquire}<a class="ll-link mt-0.5 inline-block font-semibold" href={withContext(p.acquire.path, ctx)} data-testid="ros-acquire" data-kind={p.acquire.kind}>{p.acquire.words} ›</a>{/if}
                <!-- ---- end II-4 -->
              </td>
            </tr>
          {/if}
          {#if open[k]}
            <tr class="border-b border-line {yours ? 'bg-accent-soft' : 'bg-raised'}" data-testid="ros-expand">
              <td colspan={ncols} class="px-3 pt-1 pb-3">
                <div class="space-y-2.5">
                  {#if p.per_game && Object.keys(p.per_game).length}
                    <div class="grid grid-cols-3 gap-2 sm:grid-cols-6" data-testid="ros-pieces">
                      {#each Object.entries(p.per_game) as [c, v] (c)}
                        <div class="rounded-sm bg-surface px-2 py-1.5">
                          <p class="ll-label text-ink-3">{PIECE_LABELS[c]?.[1] ?? c}</p>
                          <p class="tabnum text-lg font-bold">{pieceText(c, v)}</p>
                        </div>
                      {/each}
                    </div>
                    <p class="text-xs text-ink-3">Per game, projected over the {p.ros_games ?? 0} games left.</p><!-- II-4 -->
                  {/if}
                  {#if p.priced_from_words}<p class="text-sm text-ink-2" data-testid="ros-priced-from">{p.priced_from_words}.</p>{/if}
                  <p class="text-sm text-ink-2" data-testid="ros-facts">
                    {p.ros_games ?? 0} games left{bye ? ` (${bye})` : ""} · playoffs {whole(p.playoff_points) ?? "—"}{rangeWords(p) ? ` · likely ${rangeWords(p)}` : ""}
                  </p>
                  {#if p.why}
                    <div class="space-y-1" data-testid="ros-why">
                      <p class="ll-label text-accent">Why this number</p>
                      <p class="text-base leading-snug font-semibold">{p.why.sentence}</p>
                      <ul class="space-y-0.5 text-sm text-ink-2">
                        {#each p.why.pieces as w (w.stat)}<li class="tabnum">{w.words}</li>{/each}
                      </ul>
                      <p class="text-xs text-ink-3">Each piece counted in {leagueName} scoring: they add up to his points per game.</p><!-- II-4 -->
                    </div>
                  {:else if p.position === "K" || p.position === "DEF"}
                    <p class="text-sm text-ink-3">A kicker's or a defense's number comes from its team's scoring chances, not a stat line we can break down.</p>
                  {/if}
                  {#if p.market_words}
                    <p class="text-sm" data-testid="ros-market"><span class="font-semibold">Week {data.market_week}:</span> {p.market_words}</p>
                  {/if}
                  {#if data.leans_on?.[p.position]}
                    <p class="text-sm text-ink-3" data-testid="ros-leans"><Md text={data.leans_on[p.position].words} {ctx} /></p>
                  {/if}
                </div>
              </td>
            </tr>
          {/if}
        {/each}
      </tbody>
    </table>
    </div>
    <!-- ---- end IA-3 -->

    <Expander title="How to read this" testid="howto">
      <div class="text-base leading-snug">
        {@html md(
          "- **Rest of season** adds up every week left in your league's season, up to its final: the list for trades and waivers.\n" +
            "- A bye is a week with no game: he plays one fewer, it is not a low score.\n" +
            "- **Likely** is where 8 seasons in 10 would land if every week were its own roll of the dice; a role change or an injury moves the weeks together, so the real range is wider.\n" +
            "- **Playoffs** is the part of the total that falls in your league's playoff weeks.",
        )}
      </div>
    </Expander>
  {/if}
</main>
