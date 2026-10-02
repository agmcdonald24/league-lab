<script lang="ts">
  // Research · Compare (Wave G): two players side by side. It opens on your closest call this week (My Week's first
  // card), or the two best at a position; a search on each side picks anyone. The answer first (this week's
  // projections and the rest of the season), then the two cards, then paired bars (blue for the first, orange for the second,
  // the better number in bold): this week, the season, the last 3 games, usage, the rest of the season, the next 4
  // opponents. GET /api/compare (the same keys on both sides); the search runs on /api/players (already loaded).
  import { get, paths, peek, researchPaths, type Compare, type CompareSide, type MyWeek, type Players, type SeasonRow } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import { ownerWord } from "../lib/research";
  import { Remote } from "../lib/remote.svelte";
  import { toCompare, toPlayers } from "../lib/shapes";
  import { route, setParams } from "../lib/router.svelte";
  import { fmt, teamLabel } from "../lib/theme";
  import Card from "../components/Card.svelte";
  import PlayerCard from "../components/PlayerCard.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";

  let { options, league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  const pool = new Remote<Players>(toPlayers);
  const cmp = new Remote<Compare>(toCompare);
  $effect(() => pool.load(researchPaths.players(league), onauth));

  const ctx = $derived({ league, team });
  const leagueName = $derived(options.find((o) => o.league_id === league)?.name ?? "this league");
  const params = $derived(route.current.params);
  const a = $derived(params.get("a"));
  const b = $derived(params.get("b"));

  // no pair in the URL: your closest call this week, else the two best at the most common position
  $effect(() => {
    if (a && b) return;
    const l = league;
    const t = team;
    const fallback = () => {
      const ps = pool.data?.players ?? [];
      const wr = ps.filter((p) => p.position === "WR");
      if (wr.length >= 2) setParams({ a: wr[0].gsis_id, b: wr[1].gsis_id });
    };
    if (t === null) return fallback();
    const path = paths.myWeek(l, t);
    const take = (d: MyWeek) => {
      const card = d.cards.find((c) => c.gsis_id && c.alt_gsis_id);
      if (card && league === l) setParams({ a: card.gsis_id, b: card.alt_gsis_id });
      else fallback();
    };
    const hit = peek<MyWeek>(path);
    if (hit) take(hit);
    else get<MyWeek>(path).then(take).catch(fallback);
  });
  $effect(() => cmp.load(a && b ? researchPaths.compare(league, a, b) : null, onauth, true));

  const A = $derived(cmp.data?.a ?? null);
  const B = $derived(cmp.data?.b ?? null);
  // the two sides wear the chart kit's first two series colors (blue, orange: a validated pair), not team colors:
  // two teams' colors can be the same, or read as good / bad (green vs red); the cards keep the team accents
  const colorA = "var(--ll-series-1)";
  const colorB = "var(--ll-div-hot)";

  // ---- the search on each side
  let qa = $state("");
  let qb = $state("");
  const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/[^a-z0-9 ]/g, "");
  const hits = (q: string): SeasonRow[] => {
    const n = norm(q.trim());
    if (n.length < 2) return [];
    return (pool.data?.players ?? []).filter((p) => norm(p.player_name).includes(n)).slice(0, 8);
  };
  function choose(side: "a" | "b", p: SeasonRow) {
    if (side === "a") qa = "";
    else qb = "";
    setParams({ [side]: p.gsis_id });
  }

  type Pick = (s: CompareSide) => number | null | undefined;
  interface Pair {
    label: string;
    get: Pick;
    show: (v: number | null | undefined) => string;
    lowerIsBetter?: boolean;
  }
  const yards: Pick = (s) =>
    s.position === "QB" ? s.season_stats.passing_yards_pg : (s.season_stats.receiving_yards_pg ?? 0) + (s.season_stats.rushing_yards_pg ?? 0);
  const GROUPS: { title: string; pairs: Pair[] }[] = [
    {
      title: "This week",
      pairs: [
        { label: "Projection", get: (s) => s.proj_points, show: (v) => fmt.pts(v) },
        { label: "A bad week (floor)", get: (s) => s.p10, show: (v) => fmt.pts(v) },
        { label: "A good week (ceiling)", get: (s) => s.p90, show: (v) => fmt.pts(v) },
      ],
    },
    {
      title: "This season",
      pairs: [
        { label: "Points a game", get: (s) => s.season_stats.ppg, show: (v) => fmt.pts(v) },
        { label: "Expected points a game", get: (s) => s.season_stats.xppg, show: (v) => fmt.pts(v) },
        { label: "Targets a game", get: (s) => s.season_stats.targets_per_game, show: (v) => fmt.pts(v) },
        { label: "Carries a game", get: (s) => s.season_stats.carries_per_game, show: (v) => fmt.pts(v) },
        { label: "Yards a game", get: yards, show: (v) => fmt.pts(v) },
        { label: "Touchdowns a game", get: (s) => s.season_stats.tds_pg, show: (v) => fmt.pts(v, 2) },
      ],
    },
    {
      title: "Last 3 games",
      pairs: [
        { label: "Points a game", get: (s) => s.form.ppg_l3, show: (v) => fmt.pts(v) },
        { label: "Target share", get: (s) => s.form.target_share_l3, show: (v) => fmt.pct(v) },
        { label: "Carry share", get: (s) => s.form.carry_share_l3, show: (v) => fmt.pct(v) },
        { label: "Snaps", get: (s) => s.form.snap_pct_l3, show: (v) => fmt.pct(v) },
      ],
    },
    {
      title: "Usage this season",
      pairs: [
        { label: "Target share", get: (s) => s.usage.target_share, show: (v) => fmt.pct(v) },
        { label: "Carry share", get: (s) => s.usage.carry_share, show: (v) => fmt.pct(v) },
        { label: "Air-yard share", get: (s) => s.usage.air_yards_share, show: (v) => fmt.pct(v) },
        { label: "First-read share", get: (s) => s.usage.first_read_target_share, show: (v) => fmt.pct(v) },
        { label: "Snaps", get: (s) => s.usage.snap_pct, show: (v) => fmt.pct(v) },
      ],
    },
    {
      title: "Rest of season",
      pairs: [
        { label: "Points", get: (s) => s.ros?.points, show: (v) => fmt.whole(v) },
        { label: "Games", get: (s) => s.ros?.games, show: (v) => fmt.whole(v) },
        { label: "Rank at his position", get: (s) => s.ros?.pos_rank, show: (v) => (v == null ? "—" : `#${v}`), lowerIsBetter: true },
        { label: "Playoff weeks", get: (s) => s.ros?.playoff_points, show: (v) => fmt.whole(v) },
      ],
    },
  ];
  const shownPairs = (ps: Pair[]) => (A && B ? ps.filter((p) => (p.get(A) ?? 0) !== 0 || (p.get(B) ?? 0) !== 0) : []);
  const range = (s: CompareSide) => (s.p25 != null && s.p75 != null ? `most weeks ${fmt.whole(s.p25)}–${fmt.whole(s.p75)}` : "");
</script>

{#snippet picker(side: "a" | "b", label: string)}
  {@const q = side === "a" ? qa : qb}
  {@const hs = hits(q)}
  <div class="relative min-w-0">
    <label class="sr-only" for={`ll-cmp-${side}`}>{label}</label>
    {#if side === "a"}
      <input id="ll-cmp-a" class="ll-input w-full py-1.5 text-sm" type="search" placeholder={label} autocomplete="off" bind:value={qa} data-testid="compare-search-a" />
    {:else}
      <input id="ll-cmp-b" class="ll-input w-full py-1.5 text-sm" type="search" placeholder={label} autocomplete="off" bind:value={qb} data-testid="compare-search-b" />
    {/if}
    {#if hs.length}
      <ul class="absolute inset-x-0 top-full z-20 mt-1 max-h-72 overflow-y-auto rounded-md border border-line bg-surface shadow-lg" data-testid={`compare-hits-${side}`}>
        {#each hs as h (h.gsis_id)}
          <li>
            <button type="button" class="block min-h-11 w-full px-3 py-2 text-left text-sm hover:bg-raised" onclick={() => choose(side, h)}>
              <span class="font-semibold">{h.player_name}</span> <span class="text-ink-3">{h.position} · {teamLabel(h.team) ?? "FA"}</span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
{/snippet}

{#snippet pairRow(p: Pair)}
  {@const va = p.get(A!) ?? null}
  {@const vb = p.get(B!) ?? null}
  {@const top = Math.max(Math.abs(va ?? 0), Math.abs(vb ?? 0)) || 1}
  {@const aWins = va !== null && vb !== null && va !== vb && (p.lowerIsBetter ? va < vb : va > vb)}
  {@const bWins = va !== null && vb !== null && va !== vb && !aWins}
  <div class="py-2" data-testid="pair">
    <div class="mb-1 text-center text-xs font-semibold text-ink-3">{p.label}</div>
    <div class="grid grid-cols-2 items-center gap-2">
      <div class="flex items-center gap-2">
        <span class="tabnum w-12 shrink-0 text-right text-base {aWins ? 'font-extrabold text-ink' : 'text-ink-2'}" data-testid="pair-a">{p.show(va)}</span>
        <div class="relative h-2 flex-1 rounded-sm bg-sunken">
          {#if va !== null}<span class="absolute inset-y-0 right-0 rounded-l-sm" style="width:{p.lowerIsBetter ? 100 * (Math.min(va, vb ?? va) / Math.max(va, 1)) : (Math.abs(va) / top) * 100}%;background:{colorA}"></span>{/if}
        </div>
      </div>
      <div class="flex items-center gap-2">
        <div class="relative h-2 flex-1 rounded-sm bg-sunken">
          {#if vb !== null}<span class="absolute inset-y-0 left-0 rounded-r-sm" style="width:{p.lowerIsBetter ? 100 * (Math.min(vb, va ?? vb) / Math.max(vb, 1)) : (Math.abs(vb) / top) * 100}%;background:{colorB}"></span>{/if}
        </div>
        <span class="tabnum w-12 shrink-0 text-base {bWins ? 'font-extrabold text-ink' : 'text-ink-2'}" data-testid="pair-b">{p.show(vb)}</span>
      </div>
    </div>
  </div>
{/snippet}

<main class="space-y-4" data-testid="compare">
  <ScreenHead eyebrow="Research · Compare" title="Two players, side by side">
    {#snippet answer()}
      {#if A && B}
        <span data-testid="compare-answer"
          ><strong>{A.player_name} projects {fmt.pts(A.proj_points)}, {B.player_name} {fmt.pts(B.proj_points)}</strong> in week {A.week}{#if A.ros && B.ros}; rest
            of season {fmt.whole(A.ros.points)} vs {fmt.whole(B.ros.points)}{/if}, in {leagueName} scoring.</span
        >
      {:else if !a || !b}
        Pick two players.
      {/if}
    {/snippet}
  </ScreenHead>

  <div class="grid grid-cols-2 gap-2" data-testid="compare-pickers">
    {@render picker("a", "Find a player")}
    {@render picker("b", "Find a player")}
  </div>

  {#if cmp.error}
    <p class="ll-error">{cmp.error}</p>
  {:else if !A || !B}
    <div class="grid grid-cols-2 gap-2" aria-label="Loading" data-testid="loading"><div class="ll-skel h-52"></div><div class="ll-skel h-52"></div></div>
  {:else}
    <div class="grid grid-cols-2 gap-2 sm:gap-4" class:opacity-60={cmp.loading}>
      {#each [A, B] as s, i (i)}
        <div class="space-y-1">
          <PlayerCard
            player={s}
            number={fmt.pts(s.proj_points)}
            numberLabel={`Week ${s.week}`}
            context={ownerWord(s, team)}
            href={withContext(`/player/${s.gsis_id}`, ctx)}
            stacked
            testid={`compare-card-${i === 0 ? "a" : "b"}`}
          />
          <p class="text-center text-xs leading-snug text-ink-3">
            {range(s)}{#if s.opponent}{range(s) ? " · " : ""}{s.next4.find((w) => w.week === s.week)?.is_home === false ? "at" : "vs"} {teamLabel(s.opponent)}{s.opp_rank ? ` (#${s.opp_rank} vs ${s.position})` : ""}{/if}
          </p>
        </div>
      {/each}
    </div>

    <div class="flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-sm text-ink-2" data-testid="compare-legend">
      <span class="inline-flex items-center gap-1.5"><span class="h-2 w-4 rounded-sm" style="background:{colorA}"></span>{A.player_name}</span>
      <span class="inline-flex items-center gap-1.5"><span class="h-2 w-4 rounded-sm" style="background:{colorB}"></span>{B.player_name}</span>
      <span class="text-ink-3">the better number in bold</span>
    </div>
    <div class="grid grid-cols-1 gap-3 wide:grid-cols-2">
      {#each GROUPS as g (g.title)}
        {@const ps = shownPairs(g.pairs)}
        {#if ps.length}
          <Card title={g.title} testid="compare-group">
            <div class="divide-y divide-line">{#each ps as p (p.label)}{@render pairRow(p)}{/each}</div>
          </Card>
        {/if}
      {/each}
      <Card title="The next 4 weeks" testid="compare-next">
        <table class="tabnum w-full text-sm">
          <thead><tr class="ll-label text-left"><th class="py-1 font-semibold">Week</th><th class="py-1 font-semibold">{A.player_name.split(" ").slice(-1)[0]}</th><th class="py-1 font-semibold">{B.player_name.split(" ").slice(-1)[0]}</th></tr></thead>
          <tbody>
            {#each A.next4 as w, i (w.week)}
              {@const o = B.next4[i]}
              <tr class="border-t border-line">
                <td class="py-1.5">{w.week}</td>
                <td class="py-1.5">{w.opponent ? `${w.is_home ? "vs" : "at"} ${teamLabel(w.opponent)}` : "bye"}{w.opp_rank ? ` #${w.opp_rank}` : ""}</td>
                <td class="py-1.5">{o?.opponent ? `${o.is_home ? "vs" : "at"} ${teamLabel(o.opponent)}` : "bye"}{o?.opp_rank ? ` #${o.opp_rank}` : ""}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        <p class="mt-2 text-xs text-ink-3">#1 = the defense that gives up the most to his position (the matchup you want).</p>
      </Card>
    </div>
  {/if}
</main>
