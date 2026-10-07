<script lang="ts">
  // IP-4 (Wave I-P): his points by week (bars) against the projection made before each game (the line) and its range,
  // low-end to high-end (the band) — GET /api/player/{gsis}/games (the game log GameLog reads: one request) and
  // /api/player/{gsis}/projections (the frozen board). A week without a kept projection shows the bar alone; a week
  // he did not play (or this week, not played yet) shows the projection as a hollow point and no bar.
  import { cardPaths, get, peek, researchPaths, type Games, type PastProjections, type ScheduleRow } from "../../lib/api";
  import { fmt, teamLabel } from "../../lib/theme";
  import WeekChart from "./WeekChart.svelte";

  let { gsis, league, season, scoring, schedule = [], tall = false, testid = "card-points" }: {
    gsis: string;
    league: string;
    season: number;
    scoring: string;
    schedule?: ScheduleRow[];
    tall?: boolean; // the full page from 900 px: a taller plot beside the ratings
    testid?: string;
  } = $props();

  let games = $state<Games | null>(null);
  let proj = $state<PastProjections | null>(null);
  let failed = $state(false);

  $effect(() => {
    const id = gsis;
    const gp = researchPaths.games(id, league, season);
    const pp = cardPaths.projections(id, league);
    const g0 = peek<Games>(gp) ?? null;
    const p0 = peek<PastProjections>(pp) ?? null;
    games = g0;
    proj = p0;
    failed = false;
    if (!g0) get<Games>(gp).then((d) => gsis === id && (games = d)).catch(() => gsis === id && (failed = true));
    if (!p0)
      get<PastProjections>(pp)
        .then((d) => gsis === id && (proj = d))
        .catch(() => gsis === id && (proj = { gsis_id: id, season, through_week: 0, weeks: [], why: null, notes: [] }));
  });

  interface Wk {
    week: number;
    opp: string | null;
    played: boolean;
    points: number | null;
    p: number | null;
    lo: number | null;
    hi: number | null;
    source: string | null;
  }
  const rows = $derived.by((): Wk[] => {
    if (!games || !proj) return [];
    const reg = games.games.filter((g) => (g.season_type ?? "REG") === "REG" && g.season === season);
    // eslint-disable-next-line svelte/prefer-svelte-reactivity -- a local lookup built and read inside one derivation
    const by = new Map<number, Wk>();
    for (const g of reg) {
      if (!g.played) continue;
      by.set(g.week, { week: g.week, opp: g.opponent ? `${g.is_home ? "vs" : "at"} ${teamLabel(g.opponent)}` : null, played: true, points: g.points, p: null, lo: null, hi: null, source: null });
    }
    for (const w of proj.weeks) {
      const s = schedule.find((r) => r.week === w.week);
      const cur = by.get(w.week) ?? { week: w.week, opp: s?.opponent ? `${s.is_home ? "vs" : "at"} ${teamLabel(s.opponent)}` : null, played: false, points: null, p: null, lo: null, hi: null, source: null };
      by.set(w.week, { ...cur, p: w.proj_points, lo: w.p10, hi: w.p90, source: w.source });
    }
    return [...by.values()].sort((a, b) => a.week - b.week);
  });
  const both = $derived(rows.filter((r) => r.played && r.points !== null && r.p !== null));
  const above = $derived(both.filter((r) => r.points! > r.p!).length);
  const inside = $derived(both.filter((r) => r.lo !== null && r.hi !== null && r.points! >= r.lo && r.points! <= r.hi).length);
  const SRC: Record<string, string> = { kickoff: "shown before kickoff", refit: "rebuilt after kickoff" };

  function describe(i: number): string {
    const r = rows[i];
    if (!r) return "";
    const head = `Week ${r.week}${r.opp ? ` ${r.opp}` : ""}: `;
    const pts = r.played ? `${fmt.pts(r.points)} points` : r.source === null && r.p !== null ? "not played yet" : "did not play";
    const pj = r.p === null ? "" : ` · projected ${fmt.pts(r.p)}${r.lo !== null && r.hi !== null ? ` (${fmt.pts(r.lo)}–${fmt.pts(r.hi)})` : ""}${r.source ? `, ${SRC[r.source] ?? r.source}` : ""}`;
    return head + pts + pj;
  }
</script>

<section class="rounded-xl border border-line bg-surface p-4" style="box-shadow:var(--ll-shadow)" data-testid={testid} aria-labelledby="{testid}-title">
  <h2 id="{testid}-title" class="text-lg leading-tight font-bold">{proj && proj.weeks.length === 0 ? "Points by week" : "Points against the projection"}</h2>
  {#if failed}
    <p class="mt-2 text-sm text-ink-3">The game log did not load. Open the page again in a minute.</p>
  {:else if !games || !proj}
    <div class="ll-skel mt-3 h-44" aria-label="Loading"></div>
  {:else if rows.length === 0}
    <p class="mt-2 text-sm text-ink-3" data-testid="card-points-empty">No games in {season} yet.</p>
  {:else}
    <p class="mt-1 mb-3 text-sm leading-snug text-ink-2" data-testid="card-points-answer">
      {#if both.length}
        Above his projection in <strong class="text-ink">{above} of {both.length}</strong> game{both.length === 1 ? "" : "s"}, inside its range (low-end to high-end) in
        <strong class="text-ink">{inside} of {both.length}</strong>. {scoring} scoring.
      {:else}
        {proj.why ?? `His points by week in ${scoring} scoring.`}
      {/if}
    </p>
    <WeekChart
      weeks={rows.map((r) => r.week)}
      bars={{ label: "His points", color: "var(--ll-series-1)", values: rows.map((r) => (r.played ? r.points : null)) }}
      lines={rows.some((r) => r.p !== null) ? [{ key: "proj", label: "Projected before the game", color: "var(--ll-ink-2)", values: rows.map((r) => r.p) }] : []}
      band={rows.some((r) => r.lo !== null) ? { label: "Low-end to high-end", color: "var(--ll-ink-3)", lo: rows.map((r) => r.lo), hi: rows.map((r) => r.hi) } : null}
      tick={(v) => String(v)}
      {describe}
      ariaLabel="His points by week against the projection made before each game"
      columns={[
        { label: "Opp.", cell: (i) => rows[i].opp ?? "—" },
        { label: "Points", cell: (i) => (rows[i].played ? fmt.pts(rows[i].points) : "did not play") },
        { label: "Projected", cell: (i) => fmt.pts(rows[i].p) },
        { label: "Range", cell: (i) => (rows[i].lo !== null && rows[i].hi !== null ? `${fmt.pts(rows[i].lo)}–${fmt.pts(rows[i].hi)}` : "—") },
      ]}
      height={tall ? 240 : 180}
      testid="card-points-chart"
    />
    {#if proj.notes.length || (proj.why && both.length)}
      <p class="mt-1 text-xs leading-snug text-ink-3" data-testid="card-points-notes">{[...proj.notes, ...(proj.why && both.length ? [proj.why] : [])].join(" ")}</p>
    {/if}
  {/if}
</section>
