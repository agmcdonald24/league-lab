<script lang="ts">
  // The player card's chart: points by week in this league's scoring, with the expected points (what his work is
  // usually worth) beside them; this season or last (GET /api/player/{gsis}/games). The answer above the chart.
  import { researchPaths, type Games } from "../lib/api";
  import { pts1 } from "../lib/card"; // ---- IP-4 fix round: the API's rounding (one number, one way on the card)
  import { Remote } from "../lib/remote.svelte";
  import Card from "./Card.svelte";
  import LineChart from "./LineChart.svelte";
  import Tabs from "./Tabs.svelte";

  let { gsis, league, season, onauth, leagueName = "this league" }: { gsis: string; league: string; season: number; onauth: () => void; leagueName?: string } =
    $props();

  let pick = $state<number | null>(null);
  const shown = $derived(pick ?? season);
  const r = new Remote<Games>();
  $effect(() => r.load(researchPaths.games(gsis, league, shown), onauth, true));

  const played = $derived((r.data?.games ?? []).filter((g) => g.played));
  const points = $derived(
    played.map((g) => ({ week: g.week, label: `Week ${g.week} ${g.is_home ? "vs" : "at"} ${g.opponent ?? "?"}`, actual: g.points, expected: g.expected_points })),
  );
  const avg = (xs: (number | null)[]) => {
    const v = xs.filter((x): x is number => x !== null);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  };
  // ---- IX-2: a game he played far less than usual — "Left early" only when the play-by-play named him hurt
  // (left_early_kind "hurt"), else the plain fact ("short"); and his target share on the field with its sample: under
  // 10 offensive snaps a dash and "too few snaps" (the estimate is noise on a handful of snaps)
  type Mark = { week: number; left_early?: boolean; left_early_kind?: "hurt" | "short" | null; left_early_words?: string | null;
    on_field_target_share?: number | null; on_field_basis?: string | null; offense_snaps?: number | null; target_share?: number | null };
  const marked = $derived((played as unknown as Mark[]).filter((g) => g.left_early && g.left_early_words));
  const ON_FIELD_MIN_SNAPS = 10;
  const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(100 * v)}%`);
  function onField(g: Mark): string {
    if (g.on_field_target_share === null || g.on_field_target_share === undefined) return "";
    if (g.offense_snaps == null || g.offense_snaps < ON_FIELD_MIN_SNAPS) return `Target share on the field: — too few snaps (${g.offense_snaps ?? 0}).`;
    return `Target share on the field: ${pct(g.on_field_target_share)} (whole game ${pct(g.target_share)}; ${g.offense_snaps} snaps).`;
  }
  const estimated = $derived(marked.some((g) => g.on_field_basis === "snaps"));
  // ---- end IX-2
  const ppg = $derived(avg(played.map((g) => g.points)));
  const xppg = $derived(avg(played.map((g) => g.expected_points)));
</script>

<Card title="Points by week" testid="game-log">
  {#snippet action()}
    <Tabs
      size="sm"
      label="Season"
      testid="game-log-season"
      current={String(shown)}
      items={[
        { key: String(season), label: String(season) },
        { key: String(season - 1), label: String(season - 1) },
      ]}
      onpick={(k) => (pick = Number(k))}
    />
  {/snippet}
  {#if r.error}
    <p class="text-sm text-ink-3">{r.error}</p>
  {:else if !r.data}
    <div class="ll-skel h-48" aria-label="Loading"></div>
  {:else if points.length === 0}
    <p class="text-sm text-ink-3" data-testid="game-log-empty">No games played in {shown} yet.</p>
  {:else}
    <p class="mb-3 text-base leading-snug" data-testid="game-log-answer">
      <strong>{pts1(ppg)} points per game</strong> over {points.length} game{points.length === 1 ? "" : "s"}{#if xppg !== null}
        &nbsp;on work worth <strong>{pts1(xppg)}</strong>
        <!-- ---- IF-4 (the decision-quality review: '"Expect him to pick up" follows below-expected historical scoring'): the
             observed gap and its uncertainty, no promise of regression -->
        ({pts1(Math.abs(ppg! - xppg))} {ppg! - xppg >= 0 ? "above" : "below"} what his opportunities suggest over {points.length} game{points.length === 1 ? "" : "s"}:
        an observed gap, not a forecast){/if}, in {leagueName} scoring.
    </p>
    <LineChart {points} actualLabel="Points" expectedLabel="Expected points" />
    <!-- ---- IX-2 -->
    {#if marked.length}
      <ul class="mt-3 space-y-1 text-sm leading-snug text-ink-2" data-testid="game-log-marks">
        {#each marked as g (g.week)}
          <li data-testid="game-log-mark" data-kind={g.left_early_kind}><strong class="text-ink">Week {g.week}</strong>: {g.left_early_words}. {onField(g)}</li>
        {/each}
      </ul>
      <p class="mt-1 text-xs leading-snug text-ink-3" data-testid="game-log-onfield-key">
        Target share on the field: his targets ÷ his team's targets on the plays he was on the field{estimated
          ? ` — here an estimate from his share of the team's snaps (who was on the field on each play is published after the season)`
          : ""}.
      </p>
    {/if}
    <!-- ---- end IX-2 -->
  {/if}
</Card>
