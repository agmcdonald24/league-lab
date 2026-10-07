<script lang="ts">
  // IP-4 (Wave I-P): his role by week — target share, carry share and snap share as lines (the game log's own columns:
  // GET /api/player/{gsis}/games, the request the game log already makes), each one toggled. A game he did not play
  // breaks the line (unknown is not zero).
  import { get, peek, researchPaths, type Games } from "../../lib/api";
  import { teamLabel } from "../../lib/theme";
  import WeekChart from "./WeekChart.svelte";

  let { gsis, league, season, position, testid = "card-role" }: { gsis: string; league: string; season: number; position: string; testid?: string } = $props();

  const SERIES = [
    { key: "target_share", label: "Target share", color: "var(--ll-series-1)" },
    { key: "carry_share", label: "Carry share", color: "var(--ll-pos-rb)" },
    { key: "offense_snap_pct", label: "Snap share", color: "var(--ll-div-hot)" },
  ] as const;
  type Key = (typeof SERIES)[number]["key"];
  const DEFAULT: Record<string, Key[]> = { QB: ["carry_share", "offense_snap_pct"], RB: ["carry_share", "target_share", "offense_snap_pct"] };

  let games = $state<Games | null>(null);
  let on = $state<Key[]>([]);
  $effect(() => {
    const id = gsis;
    const p = researchPaths.games(id, league, season);
    on = DEFAULT[position] ?? ["target_share", "offense_snap_pct"];
    const g0 = peek<Games>(p) ?? null;
    games = g0;
    if (!g0) get<Games>(p).then((d) => gsis === id && (games = d)).catch(() => gsis === id && (games = { games: [] }));
  });

  // ---- the record's sentence on what "role up / down" has meant for the weeks after (IP-3's `summary()["role"]`,
  // GET /api/context/record): shown only when graded; its absence (an older server, a record not built) shows nothing
  let record = $state<string | null>(null);
  $effect(() => {
    get<Record<string, { graded?: boolean; words?: string | null } | undefined>>("/api/context/record")
      .then((r) => (record = r?.role?.graded && r.role.words ? r.role.words : null))
      .catch(() => (record = null));
  });

  const played = $derived((games?.games ?? []).filter((g) => g.played && (g.season_type ?? "REG") === "REG" && g.season === season).sort((a, b) => a.week - b.week));
  const val = (g: Games["games"][number], k: Key) => (g[k] as number | null | undefined) ?? null;
  const has = (k: Key) => played.some((g) => val(g, k) !== null && (k !== "carry_share" || (val(g, k) ?? 0) > 0) && (k !== "target_share" || position !== "QB"));
  const avail = $derived(SERIES.filter((s) => has(s.key)));
  const lines = $derived(avail.filter((s) => on.includes(s.key)).map((s) => ({ key: s.key, label: s.label, color: s.color, values: played.map((g) => val(g, s.key)) })));
  const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);
  const opp = (i: number) => (played[i]?.opponent ? `${played[i].is_home ? "vs" : "at"} ${teamLabel(played[i].opponent)}` : "");
  function toggle(k: Key) {
    on = on.includes(k) ? on.filter((x) => x !== k) : [...on, k];
  }
</script>

<section class="rounded-xl border border-line bg-surface p-4" style="box-shadow:var(--ll-shadow)" data-testid={testid} aria-labelledby="{testid}-title">
  <h2 id="{testid}-title" class="text-lg leading-tight font-bold">His role by week</h2>
  {#if !games}
    <div class="ll-skel mt-3 h-44" aria-label="Loading"></div>
  {:else if played.length === 0}
    <p class="mt-2 text-sm text-ink-3" data-testid="card-role-empty">No games in {season} yet.</p>
  {:else}
    <div class="mt-2 mb-2 flex flex-wrap gap-1.5" role="group" aria-label="Lines shown">
      {#each avail as s (s.key)}
        <button
          type="button"
          class="inline-flex min-h-9 items-center gap-1.5 rounded-full border px-3 text-sm font-semibold {on.includes(s.key) ? 'border-line-strong bg-raised text-ink' : 'border-line text-ink-3'}"
          aria-pressed={on.includes(s.key)}
          onclick={() => toggle(s.key)}
          data-testid={`role-toggle-${s.key}`}
          ><span class="inline-block h-2 w-2 rounded-full" style="background:{on.includes(s.key) ? s.color : 'var(--ll-ink-3)'}" aria-hidden="true"></span>{s.label}</button
        >
      {/each}
    </div>
    <WeekChart
      weeks={played.map((g) => g.week)}
      {lines}
      floor={0.5}
      tick={(v) => `${Math.round(v * 100)}%`}
      describe={(i) => `Week ${played[i].week} ${opp(i)}: ` + avail.map((s) => `${s.label.toLowerCase()} ${pct(val(played[i], s.key))}`).join(" · ")}
      ariaLabel="His target share, carry share and snap share by week"
      columns={avail.map((s) => ({ label: s.label, cell: (i: number) => pct(val(played[i], s.key)) }))}
      testid="card-role-chart"
    />
    <p class="mt-1 text-xs leading-snug text-ink-3">Shares of his team's targets, carries and offensive plays in each game he played.</p>
    {#if record}<p class="mt-1.5 border-t border-line pt-1.5 text-xs leading-snug text-ink-2" data-testid="card-role-record">{record}</p>{/if}
  {/if}
</section>
