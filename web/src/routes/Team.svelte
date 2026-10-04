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
  import TeamBadge from "../components/TeamBadge.svelte"; // ---- IC-4: a team unit's badge
  import { ago } from "../lib/card"; // ---- IH-2: the MFL roster freshness line
  import { APP_NAME } from "../lib/brand"; // ---- IH-2

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

  const rank = (m: "lineup_value" | "horizon_value" | "bench_value") => data?.ranks?.[m] ?? null;
  const slotMax = $derived(Math.max(1, ...(data?.slot_strength ?? []).map((s) => Math.max(s.league?.best ?? 0, s.top?.value ?? 0))));
  const weekMax = $derived(Math.max(1, ...(data?.weekly ?? []).map((w) => Math.max(w.league?.best ?? 0, w.lineup_value ?? 0))));
  const leagueSorted = $derived([...(data?.league ?? [])].sort((a, b) => b.lineup_value - a.lineup_value));
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

  // 1_Team_Hub.py's "How to read this", the screen's own words
  const HOWTO =
    "- **Lineup value** is the projected points of the best lineup you can start this week, in your league's scoring, with FLEX and superflex filled by whoever is worth most there. The rank next to it is where that puts you in the league.\n" +
    "- **Margin** is how much your lineup loses without that starter. The smallest one is your **closest call**: check the news on those two players before kickoff.\n" +
    "- **Next 4 weeks** adds up your best lineup for each of the next four weeks, byes and injuries included. Low here but high this week? Look for cover now.\n" +
    "- **Depth** is the lineup your bench alone could put out. Low depth means one injury hurts: a trade or a claim for a starter matters more to you than to most.\n" +
    "- **By slot**: your best starter at each slot against the league's average (the tick) and its best (the end of the scale). An orange bar is below the average: that is where a claim or a trade helps most.";

  function rowContext(r: TeamRosterRow): string {
    const where = r.role === "starter" ? slotLabel(r.slot) + (r.is_locked ? " · locked" : "") : r.role === "bench" ? "Bench" : (REASON[r.reason ?? ""] ?? r.reason ?? "Out");
    const bits = [where];
    if (r.role === "starter" && r.margin != null) bits.push(`margin ${f2(r.margin)}`);
    if (r.no_projection) bits.push("no projection"); // ---- IG-1: the dash in the number says it too
    if (r.report_status === "Questionable") bits.push("Questionable");
    if (r.acquired) bits.push(r.acquired);
    return bits.join(" · ");
  }
  // ---- IH-2: an MFL league's roster freshness ("MFL rosters updated 4:05 AM ET ›", the exact day and time on tap) — My
  // Week's IG-3 line, on the page that shows the roster
  function rosterRead(iso: string | null | undefined): { clock: string; exact: string; ago: string } | null {
    if (!iso) return null;
    const t = new Date(iso);
    if (Number.isNaN(t.getTime())) return null;
    const exact = t.toLocaleString("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
    const clock = t.toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });
    return { clock: `${clock} ET`, exact: `${exact} ET`, ago: ago(iso) };
  }
  // ---- end IH-2
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
        <p data-testid="team-answer"><Md text={teamAnswer(data!)} {ctx} /></p>
      {/snippet}
    </ScreenHead>

    <div class="grid grid-cols-2 gap-2 wide:grid-cols-4" data-testid="team-tiles">
      <StatTile label="Lineup value" value={f1(data.value.lineup_value)} caption={rank("lineup_value") ? `${ordinal(rank("lineup_value")!.league_rank)} of ${rank("lineup_value")!.n_rosters} · ${data.value.week_label}` : null} size="lg" />
      <StatTile label={`Next ${data.value.horizon_weeks} weeks`} value={f1(data.value.horizon_value)} caption={rank("horizon_value") ? `${ordinal(rank("horizon_value")!.league_rank)} of ${rank("horizon_value")!.n_rosters} · ${data.value.horizon_label}` : null} size="lg" />
      <StatTile label="Depth (the bench alone)" value={f1(data.value.bench_value)} caption={rank("bench_value") ? `${ordinal(rank("bench_value")!.league_rank)} of ${rank("bench_value")!.n_rosters}` : null} size="lg" />
      <StatTile
        label="Record"
        value={data.season ? `${data.season.wins}-${data.season.losses}` : "—"}
        caption={data.season?.standing ? `${ordinal(data.season.standing)} in the standings` : null}
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
            {#each data.slot_strength as s (s.slot_type)}
              {@const v = s.top?.value ?? null}
              {@const avg = s.league?.avg ?? null}
              <div data-testid="slot-bar">
                <Bar
                  value={v}
                  max={slotMax}
                  mark={avg}
                  markLabel="league average"
                  display={v == null ? "—" : s.league?.rank ? `${f1(v)} · ${ordinal(s.league.rank)}` : f1(v)}
                  color={avg == null || v == null || v >= avg ? "var(--ll-series-1)" : "var(--ll-div-hot)"}
                >
                  {#snippet labelSnippet()}
                    <span class="font-semibold text-ink">{slotLabel(s.slot_type)}{s.slots > 1 ? ` ×${s.slots}` : ""}</span>
                    {#if s.top?.player_name}
                      ·
                      {#if s.top.unit}<!-- ---- IC-4: a team unit by its team: the badge, "Bengals QB" -->
                        <span class="inline-flex items-center gap-1 align-middle" data-testid="slot-unit"><TeamBadge team={s.top.team} /><a
                            class="ll-name"
                            href={withContext(`/player/${encodeURIComponent(s.top.sleeper_id ?? "")}`, ctx)}>{s.top.short_name ?? s.top.player_name}</a
                          ></span
                        >
                      {:else if s.top.gsis_id}<a class="ll-name" href={withContext(`/player/${s.top.gsis_id}`, ctx)}>{s.top.player_name}</a>{:else}{s.top.player_name}{/if}
                    {/if}
                  {/snippet}
                </Bar>
                <p class="mt-0.5 text-xs text-ink-3">
                  {#if s.league}League average {f1(s.league.avg)}, best {f1(s.league.best)}.{/if}
                  Next man up: {s.replacement_name ? `${s.replacement_short ?? s.replacement_name} (${f1(s.replacement_value)})` : s.top?.is_locked ? "locked" : "nobody"}.
                </p>
              </div>
            {/each}
          </div>
          <p class="mt-3 text-xs text-ink-3">The bar is your best starter at the slot this week; the tick is the league's average best starter there. Orange: below the average.</p>
        </Card>

        <Card title={`The next ${data.weekly.length} weeks`} testid="team-horizon">
          <div class="space-y-3">
            {#each data.weekly as w (w.week)}
              {@const mid = w.league?.median ?? null}
              <div data-testid="week-bar">
                <Bar
                  label={`Week ${w.week}`}
                  value={w.lineup_value}
                  max={weekMax}
                  mark={mid}
                  markLabel="league middle"
                  display={w.league?.rank ? `${f1(w.lineup_value)} · ${ordinal(w.league.rank)} of ${w.league.n}` : f1(w.lineup_value)}
                  color={mid == null || w.lineup_value == null || w.lineup_value >= mid ? "var(--ll-series-1)" : "var(--ll-div-hot)"}
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
            {#each leagueSorted as r (r.roster_id)}
              {@const yours = r.is_me ?? r.roster_id === data.roster_id}
              <div class={yours ? "rounded-md bg-accent-soft px-2 py-1" : "px-2"} data-testid="league-bar" data-yours={yours ? "1" : undefined}>
                <Bar label={r.team_name + (yours ? " (you)" : "")} value={r.lineup_value} max={leagueMax} display={f1(r.lineup_value)} color={yours ? "var(--ll-accent)" : "var(--ll-series-1)"} thick={6} />
              </div>
            {/each}
          </div>
          <p class="mt-3 text-xs text-ink-3">Each roster's best lineup this week, in this league's scoring. {rankText(data, "lineup_value") ? `You: ${rankText(data, "lineup_value")}.` : ""}</p>
        </Card>

        <Card title={`Roster · week ${data.value.week}`} pad={false} testid="team-roster">
          <ul class="divide-y divide-line">
            {#each [...starters, ...bench, ...out] as r, i (r.sleeper_id ?? `${r.slot}-${i}`)}
              <li>
                {#if r.role === "empty"}
                  <div class="flex min-h-14 items-center px-3 text-base text-ink-3">{slotLabel(r.slot)}: nobody can play it this week</div>
                {:else}
                  <PlayerRow
                    player={{ ...r, player_name: r.player_name ?? "" }}
                    href={r.gsis_id ? withContext(`/player/${r.gsis_id}`, ctx) : r.unit && r.sleeper_id ? withContext(`/player/${encodeURIComponent(r.sleeper_id)}`, ctx) : null}
                    context={rowContext(r)}
                    value={r.role === "unplayable" ? "—" : f1(r.value)}
                    valueLabel={r.role === "starter" ? "starts" : r.role === "bench" ? "bench" : "out"}
                    testid={`roster-${r.role}`}
                  />
                {/if}
              </li>
            {/each}
          </ul>
        </Card>
        <!-- ---- IH-2: an MFL league's own roster freshness, under the roster it qualifies (My Week's IG-3 words) -->
        {#if data.roster_updated_at}
          {@const mu = rosterRead(data.roster_updated_at)}
          {#if mu}
            <details class="-mt-2 text-xs leading-snug text-ink-3" data-testid="team-mfl-updated">
              <summary class="inline-flex min-h-9 cursor-pointer items-center gap-1"
                >{data.roster_source ?? "MFL"} rosters updated <time datetime={data.roster_updated_at} title={mu.exact} data-testid="team-mfl-updated-time">{mu.clock}</time>
                <span class="chev" aria-hidden="true">›</span></summary
              >
              <p class="mt-1" data-testid="team-mfl-updated-exact">
                This roster was read from MyFantasyLeague {mu.exact} ({mu.ago}); {APP_NAME} reads it again after 10 minutes. The projections are the morning build's.
              </p>
            </details>
          {/if}
        {/if}
        <!-- ---- end IH-2 -->

        {#if data.season}
          <p class="text-sm text-ink-2" data-testid="team-season">
            Season so far: {data.season.wins}-{data.season.losses}{data.season.all_play_win_pct != null ? ` · against everyone ${fmt.pct(data.season.all_play_win_pct)}` : ""}{data.season.luck_wins != null
              ? ` · luck ${data.season.luck_wins > 0 ? "+" : ""}${data.season.luck_wins.toFixed(2)} wins`
              : ""}{data.season.avg_bench_points_left != null ? ` · ${f1(data.season.avg_bench_points_left)} a week left on the bench` : ""}.
            <a class="ll-link" href={withContext("/league", ctx)}>The whole league</a>
          </p>
        {/if}
      </div>
    </div>

    <Expander title="How to read this" testid="howto">
      <div class="text-base leading-snug">{@html md(HOWTO)}</div>
    </Expander>
  {/if}
</main>
