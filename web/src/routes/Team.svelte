<script lang="ts">
  // Team Hub (plan G4; app/pages/1_Team_Hub.py on GET /api/team): how good is my team — the answer first (this week's
  // best lineup and its rank), the three values with their ranks, the closest call, then strength by slot against the
  // league (bars: your best starter, the league's average as the tick, the league's best as the end of the scale), the
  // next four weeks against the league's middle, every roster's lineup value, the roster as player rows, "How to read this".
  import { get, peek, Unauthorized, decisionPaths, type Team, type TeamRosterRow } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { md, withContext } from "../lib/md";
  import { acquiredLine, closestCall, errorWords, f1, f2, ordinal, rankText, slotLabel, teamAnswer } from "../lib/decisions";
  import { restoreScroll } from "../lib/router.svelte";
  import { fmt } from "../lib/theme";
  import Bar from "../components/Bar.svelte";
  import Card from "../components/Card.svelte";
  import Expander from "../components/Expander.svelte";
  import Md from "../components/Md.svelte";
  import PlayerRow from "../components/PlayerRow.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import StatTile from "../components/StatTile.svelte";

  let { league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  let data = $state<Team | null>(null);
  let error = $state<string | null>(null);
  const ctx = $derived({ league, team });

  $effect(() => {
    const l = league;
    const t = team;
    error = null;
    if (t === null) {
      data = null;
      return;
    }
    const path = decisionPaths.team(l, t);
    const hit = peek<Team>(path);
    if (hit) {
      data = hit;
      restoreScroll();
      return;
    }
    data = null;
    get<Team>(path)
      .then((d) => {
        if (league !== l || team !== t) return;
        data = d;
        restoreScroll();
      })
      .catch((e) => {
        if (league !== l || team !== t) return;
        if (e instanceof Unauthorized) onauth();
        else error = errorWords(e);
      });
  });

  const rank = (m: "lineup_value" | "horizon_value" | "bench_value") => data?.rankings.find((r) => r.measure === m) ?? null;
  const slotMax = $derived(Math.max(1, ...(data?.slots ?? []).map((s) => Math.max(s.league_best_top_value ?? 0, s.top_value ?? 0))));
  const weekMax = $derived(Math.max(1, ...(data?.weeks ?? []).map((w) => Math.max(w.league_best, w.lineup_value ?? 0))));
  const leagueMax = $derived(Math.max(1, ...(data?.league ?? []).map((r) => r.lineup_value)));
  const starters = $derived((data?.roster ?? []).filter((r) => r.role === "starter" || r.role === "empty"));
  const bench = $derived((data?.roster ?? []).filter((r) => r.role === "bench"));
  const out = $derived((data?.roster ?? []).filter((r) => r.role === "unplayable"));
  const REASON: Record<string, string> = {
    "IR slot": "IR",
    "taxi squad": "Taxi",
    bye: "Bye",
    "NFL injured reserve": "NFL IR",
    "game started (bench)": "Locked · bench",
    "no NFL team": "No NFL team",
  };

  function rowContext(r: TeamRosterRow): string {
    const where = r.role === "starter" ? slotLabel(r.slot) + (r.is_locked ? " · locked" : "") : r.role === "bench" ? "Bench" : (REASON[r.reason ?? ""] ?? r.reason ?? "Out");
    const bits = [where];
    if (r.role === "starter" && r.lineup_margin != null) bits.push(`margin ${f2(r.lineup_margin)}`);
    if (r.report_status === "Questionable") bits.push("Questionable");
    if (r.acquired_label) bits.push(r.acquired_label);
    return bits.join(" · ");
  }
</script>

<main class="space-y-4" data-testid="team">
  {#if team === null}
    <p class="ll-empty" data-testid="pick-team-first">Pick your team above: this screen then shows where your roster ranks in the league, slot by slot.</p>
  {:else if error}
    <p class="ll-error" data-testid="error">{error}</p>
  {:else if !data}
    <div class="space-y-3" aria-label="Loading" data-testid="loading">
      <div class="ll-skel h-24"></div>
      <div class="ll-skel h-48"></div>
    </div>
  {:else}
    <ScreenHead eyebrow={`Your team · week ${data.value.week}`} title={data.team_name}>
      {#snippet answer()}
        <p data-testid="team-answer"><strong class="text-ink">{teamAnswer(data!)}</strong></p>
      {/snippet}
    </ScreenHead>

    <div class="grid grid-cols-2 gap-2 wide:grid-cols-4" data-testid="team-tiles">
      <StatTile label="Lineup value" value={f1(data.value.lineup_value)} caption={rank("lineup_value") ? `${ordinal(rank("lineup_value")!.league_rank)} of ${rank("lineup_value")!.n_rosters} · ${data.value.week_label}` : null} size="lg" />
      <StatTile label={`Next ${data.value.horizon_weeks} weeks`} value={f1(data.value.horizon_value)} caption={rank("horizon_value") ? `${ordinal(rank("horizon_value")!.league_rank)} of ${rank("horizon_value")!.n_rosters} · ${data.value.horizon_label}` : null} size="lg" />
      <StatTile label="Depth (the bench alone)" value={f1(data.value.bench_value)} caption={rank("bench_value") ? `${ordinal(rank("bench_value")!.league_rank)} of ${rank("bench_value")!.n_rosters}` : null} size="lg" />
      <StatTile
        label="Record"
        value={data.profile ? `${data.profile.wins}-${data.profile.losses}` : "—"}
        caption={data.profile?.standing ? `${ordinal(data.profile.standing)} in the standings` : null}
        size="lg"
      />
    </div>

    <div class="grid grid-cols-1 gap-4 wide:grid-cols-2 wide:items-start">
      <div class="space-y-4">
        <Card title="This week" testid="team-week">
          {#if closestCall(data)}<p class="text-base leading-snug"><Md text={closestCall(data)} {ctx} /></p>{/if}
          {#if data.value.worst_week != null && data.value.horizon_weeks > 1}
            <p class="mt-2 text-base text-ink-2">Toughest week ahead: week {data.value.worst_week} ({f1(data.value.worst_week_value)}).</p>
          {/if}
          {#if data.value.empty_slots || (data.value.n_questionable ?? 0) > 0}
            <p class="mt-2 text-sm text-warn">
              Heads-up: {[data.value.empty_slots ? `nobody can play ${data.value.empty_slots} this week` : null, (data.value.n_questionable ?? 0) > 0 ? `${data.value.n_questionable} questionable starter${data.value.n_questionable === 1 ? "" : "s"}` : null]
                .filter(Boolean)
                .join("; ")}.
            </p>
          {/if}
          {#if acquiredLine(data)}<p class="mt-2 text-sm leading-snug text-ink-2"><Md text={acquiredLine(data)} {ctx} /></p>{/if}
        </Card>

        <Card title="Strength by slot vs the league" testid="team-slots">
          <div class="space-y-3">
            {#each data.slots as s (s.slot_type)}
              <div data-testid="slot-bar">
                <Bar
                  value={s.top_value}
                  max={slotMax}
                  mark={s.league_avg_top_value}
                  markLabel="league average"
                  display={s.top_value == null ? "—" : `${f1(s.top_value)} · ${ordinal(s.league_rank_top_value ?? 0)}`}
                  color={s.league_avg_top_value != null && s.top_value != null && s.top_value >= s.league_avg_top_value ? "var(--ll-series-1)" : "var(--ll-div-hot)"}
                >
                  {#snippet labelSnippet()}
                    <span class="font-semibold text-ink">{slotLabel(s.slot_type)}{s.slots > 1 ? ` ×${s.slots}` : ""}</span>
                    {#if s.top_player_name}
                      ·
                      {#if s.top_gsis_id}<a class="ll-name" href={withContext(`/player/${s.top_gsis_id}`, ctx)}>{s.top_player_name}</a>{:else}{s.top_player_name}{/if}
                    {/if}
                  {/snippet}
                </Bar>
                <p class="mt-0.5 text-xs text-ink-3">
                  League average {f1(s.league_avg_top_value)}, best {f1(s.league_best_top_value)}. Next man up: {s.replacement_name ? `${s.replacement_name} (${f1(s.replacement_value)})` : s.top_is_locked ? "locked" : "nobody"}.
                </p>
              </div>
            {/each}
          </div>
          <p class="mt-3 text-xs text-ink-3">The bar is your best starter at the slot this week; the tick is the league's average best starter there. Orange: below the average.</p>
        </Card>

        <Card title={`The next ${data.weeks.length} weeks`} testid="team-horizon">
          <div class="space-y-3">
            {#each data.weeks as w (w.week)}
              <div data-testid="week-bar">
                <Bar
                  label={`Week ${w.week}`}
                  value={w.lineup_value}
                  max={weekMax}
                  mark={w.league_median}
                  markLabel="league middle"
                  display={`${f1(w.lineup_value)} · ${ordinal(w.league_rank)} of ${w.n_rosters}`}
                  color={w.lineup_value != null && w.lineup_value >= w.league_median ? "var(--ll-series-1)" : "var(--ll-div-hot)"}
                />
              </div>
            {/each}
          </div>
          <p class="mt-3 text-xs text-ink-3">Your best lineup each week, byes and injuries included; the tick is the league's middle team that week.</p>
        </Card>
      </div>

      <div class="space-y-4">
        <Card title={`Every roster · ${data.value.week_label}`} testid="team-league">
          <div class="space-y-2">
            {#each data.league as r (r.roster_id)}
              {@const yours = r.roster_id === data.roster_id}
              <div class={yours ? "rounded-md bg-accent-soft px-2 py-1" : "px-2"} data-testid="league-bar" data-yours={yours ? "1" : undefined}>
                <Bar label={r.team_name + (yours ? " (you)" : "")} value={r.lineup_value} max={leagueMax} display={f1(r.lineup_value)} color={yours ? "var(--ll-accent)" : "var(--ll-series-1)"} thick={6} />
              </div>
            {/each}
          </div>
          <p class="mt-3 text-xs text-ink-3">Each roster's best lineup this week, in this league's scoring. {rankText(data, "lineup_value") ? `You: ${rankText(data, "lineup_value")}.` : ""}</p>
        </Card>

        <Card title={`Roster · week ${data.value.week}`} pad={false} testid="team-roster">
          <ul class="divide-y divide-line">
            {#each [...starters, ...bench, ...out] as r, i (r.sleeper_player_id ?? `${r.slot}-${i}`)}
              <li>
                {#if r.role === "empty"}
                  <div class="flex min-h-14 items-center px-3 text-base text-ink-3">{slotLabel(r.slot)}: nobody can play it this week</div>
                {:else}
                  <PlayerRow
                    player={{ ...r, player_name: r.player_name ?? "" }}
                    href={r.gsis_id ? withContext(`/player/${r.gsis_id}`, ctx) : null}
                    context={rowContext(r)}
                    value={r.role === "unplayable" ? "—" : f1(r.player_value)}
                    valueLabel={r.role === "starter" ? "starts" : r.role === "bench" ? "bench" : "out"}
                    testid={`roster-${r.role}`}
                  />
                {/if}
              </li>
            {/each}
          </ul>
        </Card>

        {#if data.profile}
          <p class="text-sm text-ink-2" data-testid="team-season">
            Season so far: {data.profile.wins}-{data.profile.losses}{data.profile.all_play_win_pct != null ? ` · against everyone ${fmt.pct(data.profile.all_play_win_pct)}` : ""}{data.profile.luck_wins != null
              ? ` · luck ${data.profile.luck_wins > 0 ? "+" : ""}${data.profile.luck_wins.toFixed(2)} wins`
              : ""}{data.profile.avg_bench_points_left != null ? ` · ${f1(data.profile.avg_bench_points_left)} a week left on the bench` : ""}.
            <a class="ll-link" href={withContext("/league", { league })}>The whole league</a>
          </p>
        {/if}
      </div>
    </div>

    <Expander title="How to read this" testid="howto">
      <div class="text-base leading-snug">{@html md((data.howto ?? []).map((h) => `- ${h}`).join("\n"))}</div>
    </Expander>
  {/if}
</main>
