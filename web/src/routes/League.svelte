<script lang="ts">
  import { APP_NAME } from "../lib/brand";
  // League (plan G4; app/pages/8_League.py on GET /api/league): the answer first (your schedule luck and your bench;
  // without a team, the league's luckiest and unluckiest), then the standings with the record against everyone, who
  // has been lucky (bars either side of 0), points left on the bench, the latest moves, the draft where Sleeper has it.
  import { get, peek, Unauthorized, decisionPaths, type LeagueView, type TransactionRow } from "../lib/api";
  import { weekOddsPath, type WeekOdds, type WeekOddsGame } from "../lib/api"; // ---- IH-3
  import type { LeagueOption } from "../lib/leagues";
  import { md, withContext } from "../lib/md";
  import { allPlayRecord, errorWords, f1, luckLine, moveKind, moveWords, s1 } from "../lib/decisions";
  import { restoreScroll } from "../lib/router.svelte";
  import { fmt, seqFill, seqInk } from "../lib/theme";
  import Bar from "../components/Bar.svelte";
  import Card from "../components/Card.svelte";
  import Expander from "../components/Expander.svelte";
  import Headshot from "../components/Headshot.svelte";
  import Md from "../components/Md.svelte";
  import PosBadge from "../components/PosBadge.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import { gapLine } from "../lib/providers"; // ---- II-5: "Transactions: not available for MFL leagues yet"

  let { options, league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  let data = $state<LeagueView | null>(null);
  let error = $state<string | null>(null);
  const ctx = $derived({ league, team });
  // ---- II-5 (Wave I-I): a platform whose moves League Lab does not read says so (never "No completed moves")
  let movesGap = $state<string | null>(null);
  $effect(() => {
    const l = league;
    movesGap = null;
    void gapLine(l, "transactions").then((v) => {
      if (l === league) movesGap = v;
    });
  });
  // ---- end II-5

  $effect(() => {
    const l = league;
    const t = team;
    error = null;
    const path = decisionPaths.league(l, t);
    const hit = peek<LeagueView>(path);
    if (hit) {
      data = hit;
      restoreScroll();
      return;
    }
    data = null;
    get<LeagueView>(path)
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

  // ---- IH-3: this week's odds per game, asked after the screen shows (one lineup per team: 1-5 s the first time);
  // information only — the lineup calls stay on My Week. Nothing is shown when the ask fails or has no numbers.
  let odds = $state<WeekOdds | null>(null);
  $effect(() => {
    const l = league;
    if (!data) return;
    const path = weekOddsPath(l);
    const hit = peek<WeekOdds>(path);
    if (hit) {
      odds = hit;
      return;
    }
    odds = null;
    get<WeekOdds>(path)
      .then((o) => {
        if (league === l) odds = o;
      })
      .catch(() => {
        if (league === l) odds = null;
      });
  });
  const oddsBy = $derived(new Map((odds?.games ?? []).filter((g) => g.p != null).map((g) => [g.matchup_id, g])));
  /** "53% · 120 expected" for one side of a game; "" without a number */
  function sideOdds(g: WeekOddsGame | undefined, rid: number): string {
    const sd = g ? (g.a.roster_id === rid ? g.a : g.b.roster_id === rid ? g.b : null) : null;
    if (!sd || sd.percent == null) return "";
    return `${sd.percent}%` + (sd.expected != null ? ` · ${Math.round(sd.expected)} expected` : "");
  }
  // a house league's screen has no "this week" games block (IC-4 serves the on-demand path): the odds bring their own
  const ownOdds = $derived(!!odds && odds.week != null && oddsBy.size > 0 && !(data?.matchups ?? []).some((m) => !m.played && m.week === odds?.week));
  // my game first, as IC-4's card orders them
  const ownGames = $derived(
    (odds?.games ?? []).filter((g) => g.p != null).sort((x, y) => Number(isMine(y)) - Number(isMine(x)) || x.matchup_id - y.matchup_id),
  );
  function isMine(g: WeekOddsGame): boolean {
    return team != null && (g.a.roster_id === team || g.b.roster_id === team);
  }
  // ---- end IH-3
  const allPlay = $derived(new Map((data?.all_play ?? []).map((r) => [r.roster_id, r])));
  const luck = $derived([...(data?.all_play ?? [])].filter((r) => r.luck_wins != null).sort((a, b) => (b.luck_wins ?? 0) - (a.luck_wins ?? 0)));
  const luckMax = $derived(Math.max(0.5, ...luck.map((r) => Math.abs(r.luck_wins ?? 0))));
  // the league's name from the picker (the API does not send it; a shared link to a league never opened here: "The league")
  const leagueName = $derived.by(() => {
    const n = options.find((o) => o.league_id === league)?.name;
    return n && n !== "This league" ? n : "The league";
  });
  const bench = $derived([...(data?.profiles ?? [])].sort((a, b) => (b.total_bench_points_left ?? 0) - (a.total_bench_points_left ?? 0)));
  const benchMax = $derived(Math.max(1, ...bench.map((r) => r.total_bench_points_left ?? 0)));
  // one card per transaction (a trade or an add + drop is one move)
  const moves = $derived.by(() => {
    // eslint-disable-next-line svelte/prefer-svelte-reactivity -- a scratch grouping inside a derived, never observed
    const by = new Map<string, TransactionRow[]>();
    for (const t of data?.transactions ?? []) by.set(t.transaction_id, [...(by.get(t.transaction_id) ?? []), t]);
    return [...by.values()].slice(0, 15);
  });
  const draftRounds = $derived(data?.draft ? [...new Set(data.draft.map((d) => d.round))] : []);
  const [showDraft, moreDraft] = $derived.by(() => {
    const d = data?.draft ?? [];
    const n = data ? data.standings.length * 2 : 20; // the first two rounds up front
    return [d.slice(0, n), d.slice(n)];
  });

  // weekly scoring rank (8_League.py's heatmap): teams by their average rank, one column per week; more = a better week
  const n = $derived(data?.standings.length ?? 0);
  const weekCols = $derived([...new Set((data?.all_play_week ?? []).map((w) => w.week))].sort((a, b) => a - b).map((w) => ({ key: String(w), label: `Wk ${w}` })));
  const rankRows = $derived.by(() => {
    const by: Record<number, { name: string; sum: number; k: number }> = {};
    for (const w of data?.all_play_week ?? []) {
      const r = (by[w.roster_id] ??= { name: w.team_name, sum: 0, k: 0 });
      r.sum += w.week_points_rank;
      r.k += 1;
    }
    return Object.entries(by)
      .sort((a, b) => a[1].sum / a[1].k - b[1].sum / b[1].k)
      .map(([id, r]) => ({ key: id, label: Number(id) === team ? `${r.name} (you)` : r.name }));
  });
  function rankCell(row: string, col: string) {
    const w = data?.all_play_week.find((x) => String(x.roster_id) === row && String(x.week) === col);
    if (!w) return { t: null, display: "—", title: "no score" };
    return {
      t: n > 1 ? (n - w.week_points_rank) / (n - 1) : 0.5,
      display: String(w.week_points_rank),
      title: `${w.team_name} · week ${w.week}: ${f1(w.points)} points, rank ${w.week_points_rank}${w.result ? `, ${w.result}` : ""}`,
    };
  }

  /** A week column older than the last 5 is hidden on a phone, older than the last 10 everywhere. */
  function colClass(i: number): string {
    const back = weekCols.length - i;
    return back > 10 ? "hidden" : back > 5 ? "hidden wide:block" : "";
  }

  function when(iso: string): string {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }
</script>

<main class="space-y-4" data-testid="league">
  {#if error}
    <p class="ll-error" data-testid="error">{error}</p>
  {:else if !data}
    <div class="space-y-3" aria-label="Loading" data-testid="loading">
      <div class="ll-skel h-24"></div>
      <div class="ll-skel h-64"></div>
    </div>
  {:else}
    <ScreenHead eyebrow={`League · ${data.season} · ${data.weeks_scored} week${data.weeks_scored === 1 ? "" : "s"} played`} title={leagueName}>
      {#snippet answer()}
        <p data-testid="league-answer"><Md text={luckLine(data!, team)} {ctx} /></p>
        <p class="mt-1 text-sm text-ink-3">Luck = wins minus the wins your points deserve (your record if you had played every team every week).</p>
      {/snippet}
    </ScreenHead>

    <div class="grid grid-cols-1 gap-4 wide:grid-cols-2 wide:items-start">
      <div class="min-w-0 space-y-4">
      <Card title="Standings" pad={false} testid="standings">
        <div class="grid grid-cols-[1.75rem_minmax(0,1fr)_3.25rem_3.75rem_3.75rem] items-center gap-x-2 px-3 pt-1 pb-1.5 text-label font-semibold tracking-[0.08em] text-ink-3 uppercase">
          <span class="text-right">#</span><span>Team</span><span class="text-right">W-L</span><span class="text-right">Points</span><span class="text-right" title="Your record if you had played every team every week">All-play</span>
        </div>
        <ol class="divide-y divide-line">
          {#each data.standings as s (s.roster_id)}
            {@const yours = s.roster_id === team}
            {@const ap = allPlay.get(s.roster_id)}
            <li
              class="relative grid min-h-12 grid-cols-[1.75rem_minmax(0,1fr)_3.25rem_3.75rem_3.75rem] items-center gap-x-2 px-3 py-1.5 {yours ? 'bg-accent-soft' : ''}"
              data-testid="standing-row"
              data-yours={yours ? "1" : undefined}
            >
              {#if yours}<span class="absolute inset-y-1 left-0 w-1 rounded-r bg-accent" aria-hidden="true"></span>{/if}
              <span class="tabnum text-right text-sm font-semibold text-ink-3">{s.standing}</span>
              <span class="min-w-0">
                <span class="line-clamp-2 block text-base leading-tight font-semibold break-words">{s.team_name}</span>
                <span class="block truncate text-xs text-ink-3">{s.manager_name ?? ""}</span>
              </span>
              <span class="tabnum text-right text-base font-semibold">{s.wins}-{s.losses}{s.ties ? `-${s.ties}` : ""}</span>
              <span class="tabnum text-right text-base">{f1(s.points_for)}</span>
              <span class="tabnum text-right text-sm text-ink-2">{ap ? allPlayRecord(ap) : "—"}</span>
            </li>
          {/each}
        </ol>
      </Card>

      <!-- ---- IC-4 (Wave I-D): this week's matchups and the last scored week's, each game once (both games of a double header) -->
      {#each data.matchups ?? [] as m (m.week)}
        <Card title={m.played ? `Week ${m.week} results` : `Week ${m.week} matchups`} pad={false} testid={m.played ? "league-results" : "league-matchups"}>
          {#if m.double_header}
            <p class="px-3 pb-1 text-sm text-ink-2" data-testid="double-header">A double header: every team plays two games this week, each against its own opponent.</p>
          {/if}
          <ul class="divide-y divide-line">
            {#each m.games as g (g.matchup_id)}
              <li class="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-x-2 px-3 py-1.5 {g.mine ? 'bg-accent-soft' : ''}" data-testid="league-game" data-mine={g.mine ? "1" : undefined}>
                {#each [g.a, g.b] as sd, j (j)}
                  {#if j === 1}<span class="text-xs text-ink-3">vs</span>{/if}
                  <span class="min-w-0 {j === 1 ? 'text-right' : ''}">
                    <span class="line-clamp-2 text-base leading-tight break-words {sd.roster_id === team ? 'font-bold' : sd.result === 'W' ? 'font-semibold' : ''}">{sd.team_name}</span>
                    {#if sd.points != null}<span class="tabnum block text-xs text-ink-3">{f1(sd.points)}{sd.result ? ` · ${sd.result}` : ""}</span>{/if}
                    {#if !m.played && sideOdds(oddsBy.get(g.matchup_id), sd.roster_id)}<span class="tabnum block text-xs text-ink-3" data-testid="game-odds">{sideOdds(oddsBy.get(g.matchup_id), sd.roster_id)}</span>{/if}<!-- IH-3 -->
                  </span>
                {/each}
              </li>
            {/each}
          </ul>
          {#if !m.played && oddsBy.size}<p class="px-3 pt-1 pb-2 text-xs text-ink-3" data-testid="odds-note">How often each team wins, from both best lineups' ranges ({odds?.assumptions}).</p>{/if}<!-- IH-3 -->
        </Card>
      {/each}
      <!-- ---- end IC-4 -->
      <!-- ---- IH-3: a house league's games this week with both teams' chance (the on-demand path's sit in IC-4's card above) -->
      {#if ownOdds && odds}
        <Card title={`Week ${odds.week} matchups`} pad={false} testid="league-odds">
          <ul class="divide-y divide-line">
            {#each ownGames as g (g.matchup_id)}
              {@const mine = isMine(g)}
              <li class="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-x-2 px-3 py-1.5 {mine ? 'bg-accent-soft' : ''}" data-testid="league-game" data-mine={mine ? "1" : undefined}>
                {#each [g.a, g.b] as sd, j (j)}
                  {#if j === 1}<span class="text-xs text-ink-3">vs</span>{/if}
                  <span class="min-w-0 {j === 1 ? 'text-right' : ''}">
                    <span class="line-clamp-2 text-base leading-tight break-words {sd.roster_id === team ? 'font-bold' : ''}">{sd.team_name}</span>
                    <span class="tabnum block text-xs text-ink-3" data-testid="game-odds">{sideOdds(g, sd.roster_id)}</span>
                  </span>
                {/each}
              </li>
            {/each}
          </ul>
          <p class="px-3 pt-1 pb-2 text-xs text-ink-3" data-testid="odds-note">How often each team wins, from both best lineups' ranges ({odds.assumptions}).</p>
        </Card>
      {/if}
      <!-- ---- end IH-3 -->
      {#if weekCols.length}
        <Card title="Weekly scoring rank" testid="week-ranks">
          <!-- the last 5 weeks on a phone, the last 10 from 900 px: the grid never scrolls sideways -->
          <div
            class="grid grid-cols-[minmax(0,1fr)_repeat(var(--cp),2.25rem)] gap-[2px] wide:grid-cols-[minmax(0,11rem)_repeat(var(--cw),minmax(2.25rem,3.5rem))]"
            style="--cp:{Math.min(5, weekCols.length)};--cw:{Math.min(10, weekCols.length)}"
            data-testid="rank-grid"
          >
            <span></span>
            {#each weekCols as c, i (c.key)}<span class="ll-label pb-1 text-center {colClass(i)}">{c.label}</span>{/each}
            {#each rankRows as r (r.key)}
              {@const yours = Number(r.key) === team}
              <span class="truncate pr-2 text-sm leading-8 {yours ? 'font-bold text-ink' : 'text-ink-2'}" data-testid="rank-row">{r.label}</span>
              {#each weekCols as c, i (c.key)}
                {@const x = rankCell(r.key, c.key)}
                <span
                  class="tabnum h-8 rounded-sm text-center text-sm leading-8 font-semibold {yours ? 'ring-2 ring-accent ring-inset' : ''} {colClass(i)}"
                  style="background:{x.t === null ? 'var(--ll-sunken)' : seqFill(0.08 + x.t * 0.92)};color:{x.t === null ? 'var(--ll-ink-3)' : seqInk(0.08 + x.t * 0.92)}"
                  title={x.title}>{x.display}</span
                >
              {/each}
            {/each}
          </div>
          <p class="mt-2 text-xs text-ink-3">Where each team's score ranked that week (1 = the week's top score; darker = higher). A team that keeps landing near the top but keeps losing is unlucky; the opposite is riding a soft schedule.</p>
        </Card>
      {/if}
      </div>

      <div class="space-y-4">
        <Card title="Who has been lucky" testid="luck">
          <div class="space-y-2">
            {#each luck as r (r.roster_id)}
              {@const yours = r.roster_id === team}
              <div class={yours ? "rounded-md bg-accent-soft px-2 py-1" : "px-2"} data-testid="luck-bar" data-yours={yours ? "1" : undefined}>
                <Bar
                  label={r.team_name + (yours ? " (you)" : "")}
                  value={r.luck_wins}
                  min={-luckMax}
                  max={luckMax}
                  display={`${s1(r.luck_wins)} wins`}
                  color="var(--ll-div-hot)"
                  negColor="var(--ll-div-due)"
                  thick={6}
                />
              </div>
            {/each}
          </div>
          <p class="mt-3 text-xs text-ink-3">Right of the line: more wins than the points deserve (a soft schedule). Left: fewer (a hard one). Past luck says nothing about the weeks left: they depend on your points and the schedule ahead.</p><!-- II-4 -->
        </Card>

        {#if data.profiles}
        <Card title="Points left on the bench (hindsight)" testid="bench"><!-- ---- II-4: hindsight labelled -->
            <div class="space-y-2">
              {#each bench as r (r.roster_id)}
                {@const yours = r.roster_id === team}
                <div class={yours ? "rounded-md bg-accent-soft px-2 py-1" : "px-2"} data-testid="bench-bar">
                  <Bar label={r.team_name + (yours ? " (you)" : "")} value={r.total_bench_points_left} max={benchMax} display={f1(r.total_bench_points_left)} thick={6} color={yours ? "var(--ll-accent)" : "var(--ll-series-1)"} />
                </div>
              {/each}
            </div>
            <p class="mt-3 text-xs text-ink-3">How much a better lineup would have added, {data.weeks_scored} week{data.weeks_scored === 1 ? "" : "s"}. High numbers mark managers who don't sweat start / sit: useful to know when you trade with them.</p>
          </Card>
        {:else}
          <p class="ll-empty text-sm" data-testid="no-profiles">Points left on the bench need every lineup of the league's past weeks: they show for the leagues {APP_NAME} Lab keeps every night.</p>
        {/if}
      </div>
    </div>

    <div class="grid grid-cols-1 gap-4 wide:grid-cols-2 wide:items-start">
      <Card title="Latest moves" pad={false} testid="moves">
        {#if !moves.length && movesGap}
          <p class="px-4 pb-4 text-base text-ink-2" data-testid="moves-unavailable">{movesGap}.</p><!-- II-5 -->
        {:else if !moves.length}
          <p class="px-4 pb-4 text-base text-ink-2">No completed moves yet this season.</p>
        {:else}
          <ul class="divide-y divide-line">
            {#each moves as tx (tx[0].transaction_id)}
              <li class="px-3 py-2" data-testid="move">
                <div class="flex items-baseline justify-between gap-2 text-sm">
                  <span class="min-w-0 truncate"><span class="font-semibold">{tx[0].team_name ?? "—"}</span> <span class="text-ink-3">· {moveKind(tx[0].transaction_type)}</span></span>
                  <span class="shrink-0 text-ink-3">{tx[0].week ? `Week ${tx[0].week} · ` : ""}{when(tx[0].created_at)}</span>
                </div>
                <ul class="mt-1 space-y-1">
                  {#each tx as t, i (`${t.sleeper_player_id}-${t.action}-${i}`)}
                    <li class="flex items-center gap-2">
                      <Headshot url={t.headshot_url} name={t.player_name ?? ""} team={t.team} size={28} />
                      <span class="w-11 shrink-0 text-xs font-semibold tracking-wide uppercase {t.action === 'add' ? 'text-good' : 'text-bad'}">{moveWords(t.transaction_type, t.action)}</span>
                      <span class="min-w-0 flex-1 truncate text-base">
                        {#if t.gsis_id}<a class="ll-name" href={withContext(`/player/${t.gsis_id}`, ctx)}>{t.player_name}</a>{:else}{t.player_name ?? "—"}{/if}
                        {#if t.transaction_type === "trade" && t.team_name !== tx[0].team_name}<span class="text-xs text-ink-3"> ({t.team_name})</span>{/if}
                      </span>
                      <PosBadge pos={t.position} />
                      {#if t.waiver_bid != null && t.action === "add"}<span class="tabnum shrink-0 text-sm text-ink-2">${t.waiver_bid}</span>{/if}
                    </li>
                  {/each}
                </ul>
              </li>
            {/each}
          </ul>
        {/if}
      </Card>

      <Card title={data.draft ? `The draft · ${draftRounds.length} rounds` : "The draft"} pad={false} testid="draft">
        {#if !data.draft}
          <p class="px-4 pb-4 text-base text-ink-2" data-testid="no-draft">
            {data.source === "sleeper"
              ? `The draft review needs the league's history: it shows for the leagues ${APP_NAME} keeps every night.`
              : "No draft for this league this season yet."}
          </p>
        {:else}
          {#snippet pick(d: NonNullable<LeagueView["draft"]>[number])}
            <li class="flex items-center gap-2 px-3 py-1.5" data-testid="pick">
              <span class="tabnum w-12 shrink-0 text-sm font-semibold text-ink-3">{d.round}.{String(d.draft_slot ?? d.pick_no).padStart(2, "0")}</span>
              <Headshot url={d.headshot_url} name={d.player_name ?? ""} team={d.drafted_team} size={28} />
              <span class="min-w-0 flex-1">
                <span class="block truncate text-base">
                  {#if d.gsis_id}<a class="ll-name font-semibold" href={withContext(`/player/${d.gsis_id}`, ctx)}>{d.player_name}</a>{:else}<span class="font-semibold">{d.player_name}</span>{/if}
                </span>
                <span class="block truncate text-xs text-ink-3">{d.team_name ?? ""}{d.is_keeper ? " · keeper" : ""}</span>
              </span>
              <PosBadge pos={d.position} />
              <span class="tabnum w-24 shrink-0 text-right text-xs whitespace-nowrap text-ink-2" title="His rank at the position by draft pick → by points so far">
                {d.position_rank_by_pick != null ? `${d.position}${d.position_rank_by_pick}` : "—"} → {d.position_rank_by_points != null ? `${d.position}${d.position_rank_by_points}` : "—"}
              </span>
            </li>
          {/snippet}
          <ul class="divide-y divide-line">
            {#each showDraft as d (d.pick_no)}{@render pick(d)}{/each}
          </ul>
          {#if moreDraft.length}
            <div class="p-3">
              <Expander title={`The other ${moreDraft.length} picks`} testid="draft-more">
                <ul class="-mx-3 divide-y divide-line">
                  {#each moreDraft as d (d.pick_no)}{@render pick(d)}{/each}
                </ul>
              </Expander>
            </div>
          {/if}
          <p class="px-4 pb-3 text-xs text-ink-3">Pick → where he ranks at his position by points so far ({fmt.whole(data.weeks_scored)} weeks): a WR taken 8th among WRs who is 2nd was a steal.</p>
        {/if}
      </Card>
    </div>

    <Expander title="How to read this" testid="howto">
      <div class="text-base leading-snug">
        {@html md(
          "- **Who has been lucky**: each team's record if it had played every other team every week is what its points deserve; luck is the real wins minus those. A 2-0 team with a big minus is scoring like a 1-1 team.\n" +
            "- **All-play** is that record against everyone, every week.\n" +
            "- **Points left on the bench (hindsight)** is how much the best lineup *knowing the final scores* would have added: hindsight, not an avoidable mistake — before kickoff nobody knows the scores. High numbers over many weeks mark managers who don't sweat start / sit: useful when you trade with them.\n" + // ---- II-4
            "- **Latest moves**: completed claims, adds, drops and trades, newest first: who is chasing the same positions and what bids clear.\n" +
            "- **The draft**: every pick and where the player ranks at his position by points so far.",
        )}
      </div>
    </Expander>
  {/if}
</main>
