<script lang="ts">
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
  let data = $state<RosList | null>(null);
  let error = $state<string | null>(null);
  let slots = $state<string[]>([]); // the league's lineup slots (from My Week): K / DEF tabs only when it has them

  const ctx = $derived({ league, team });
  const position = $derived.by(() => {
    const p = (route.current.params.get("position") ?? "ALL").toUpperCase();
    return [...BASE, "K", "DEF", "ALL"].includes(p) ? p : "ALL";
  });
  const positions = $derived.by(() => {
    if (data?.positions?.length) return [...data.positions.filter((p) => p !== "ALL"), "ALL"];
    const extra = ["K", "DEF"].filter((p) => slots.includes(p) || position === p);
    return [...BASE, ...extra, "ALL"];
  });
  const leagueName = $derived(options.find((o) => o.league_id === league)?.name ?? "this league");
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
    const path = paths.ros(l, p);
    const hit = peek<RosList>(path);
    if (hit) {
      data = hit;
      restoreScroll();
      return;
    }
    data = null;
    get<RosList>(path)
      .then((d) => {
        if (league !== l || position !== p) return;
        data = d;
        restoreScroll();
      })
      .catch((e) => {
        if (league !== l || position !== p) return;
        if (e instanceof Unauthorized) onauth();
        else if (e instanceof ApiError && e.status === 404) error = "League Lab cannot find this league on Sleeper. Pick another above.";
        else if (e instanceof ApiError && e.status === 502) error = "Sleeper did not answer. Try again in a minute.";
        else if (e instanceof ApiError && e.status === 503) error = "The numbers are not ready yet. Try again in a few minutes.";
        else error = e instanceof Error ? e.message : String(e);
      });
  });

  function pick(p: string) {
    setParams({ position: p });
  }

  // ---- IA-3: the sort (a header tap; again flips it), the open rows, the pieces of the screen's position
  let sortKey = $state<SortKey>("rank");
  let sortDir = $state<"asc" | "desc">("asc");
  let open = $state<Record<string, boolean>>({});
  $effect(() => {
    void position;
    void league;
    sortKey = "rank";
    sortDir = "asc";
    open = {};
  });
  const pieceCols = $derived(position === "ALL" ? [] : (data?.piece_columns?.[position] ?? PIECE_COLUMNS[position] ?? []));
  const shown = $derived(sortPlayers(players, sortKey, sortDir, position));
  const rankAt = $derived(new Map(players.map((p, i) => [p, rankOf(p, i, position)])));
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
  const ncols = $derived(4 + (vw >= 640 ? 3 : 0) + (vw >= 900 ? pieceCols.length : 0));
  function toggle(k: string) {
    open = { ...open, [k]: !open[k] };
  }
  // ---- end IA-3
  const label = (p: string) => (p === "ALL" ? "All" : p);
</script>


<svelte:window bind:innerWidth={vw} />

<main class="space-y-4" data-testid="ros">
  <header class="space-y-1.5">
    <p class="text-label font-bold tracking-[0.08em] text-accent uppercase">Rest of season · {leagueName}</p>
    <h1 class="text-2xl leading-tight font-extrabold tracking-tight wide:text-3xl">Who scores the most from here</h1>
  </header>
  <Chips label="Position" testid="ros-pos" current={position} onpick={pick} items={positions.map((p) => ({ key: p, label: label(p) }))} />

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
      <p class="text-lg leading-snug"><Md text={answerLine(players[0], position)} {ctx} /></p>
      {#if team !== null}<p class="text-base leading-snug" data-testid="ros-yours">{yoursLine(players, team, position)}</p>{/if}
      <p class="text-sm leading-snug text-ink-3">
        {span ? `${span[0].toUpperCase()}${span.slice(1)}` : "The weeks left"} in {leagueName} scoring, up to the league's final. A bye
        is a week with no game: he plays one fewer. Ranked among everyone at the position, rostered or free agent.
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
          {@render head("ros_games", "Games", "hidden w-[3.5rem] text-right sm:table-cell", "Games left (byes out)")}
          {@render head("ros_points", "Points", "w-[3.75rem] text-right", "Rest of season, this league's scoring")}
          {@render head("range", "Likely", "hidden w-[7rem] pl-3 text-left sm:table-cell", "Where 8 seasons in 10 would land")}
          {@render head("playoff_points", "Playoffs", "hidden w-[4.5rem] text-right sm:table-cell", "Points in the playoff weeks")}
          {#each pieceCols as c (c)}
            {@render head(`pg:${c}`, PIECE_LABELS[c]?.[0] ?? c, "hidden w-[3.75rem] text-right wide:table-cell", `${PIECE_LABELS[c]?.[1] ?? c} a game, projected`)}
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
          <tr class="border-b border-line align-middle {open[k] ? '' : 'last:border-0'} {yours ? 'bg-accent-soft' : ''}" data-testid="ros-row">
            <td class="tabnum py-2 pr-1 pl-3 font-semibold text-ink-3">{rankAt.get(p) ?? "—"}</td>
            <td class="py-2 pr-1 leading-snug break-words">
              <div class="flex min-w-0 items-center gap-2">
                <Headshot url={p.headshot_url ?? null} team={p.team} size={32} />
                <div class="min-w-0">
                  {#if p.gsis_id}
                    <a class="ll-name font-semibold" href={withContext(`/player/${p.gsis_id}`, ctx)}>{p.player_name}</a>
                  {:else}
                    {p.player_name}
                  {/if}
                  <div class="mt-0.5 flex min-w-0 items-center gap-1 text-xs text-ink-3">
                    <PosBadge pos={p.position} />{#if p.position !== "DEF"}<TeamBadge team={p.team} />{/if}
                    {#if p.bye_weeks?.length}<span class="shrink-0 tabnum" data-testid="ros-bye">bye {p.bye_weeks.join(", ")} ·</span>{/if}
                    <span class="truncate {yours ? 'font-semibold text-accent' : ''}">{yours ? "yours" : (p.rostered_by_team ?? "free agent")}</span>
                  </div>
                </div>
              </div>
            </td>
            <td class="tabnum hidden py-2 text-right text-ink-2 sm:table-cell">{p.ros_games ?? "—"}</td>
            <td class="tabnum py-2 text-right font-bold" data-testid="ros-points">{whole(p.ros_points) ?? "—"}<span class="block text-[11px] font-normal text-ink-3 sm:hidden">{p.ros_games ?? "—"} g</span></td>
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
                    <p class="text-xs text-ink-3">A game, projected over the {p.ros_games ?? 0} games left.</p>
                  {/if}
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
                      <p class="text-xs text-ink-3">Each piece counted in {leagueName} scoring: they add up to his points a game.</p>
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
