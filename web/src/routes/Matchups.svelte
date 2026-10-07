<script lang="ts">
  // Research · Matchups (Wave G): the answer first (your starters' best and toughest matchups this week), then your
  // starters with their matchup rank, the defense-vs-position heatmap (team × position, your starters' cells ringed),
  // and the cornerbacks your receivers face (app/lib's sentence, the side his targets go as a bar, the corner's rank).
  // GET /api/matchups/defense (mart_defense_vs_position_current) and /api/matchups/cb (mart_cb_matchups + ranks).
  import { researchPaths, type CbMatchup, type CbMatchups, type DefenseCell, type DefenseMatrix } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { withContext } from "../lib/md";
  // ---- IB-3: the tone first, one rank direction (1 = the toughest for the offense), the rank in words
  import { certaintyOf, defenseTone, givesUpShort, TONE_COLOR, TONE_GLYPH, TONE_WORD, toneWash, toughRank, type Tone } from "../lib/research";
  import { Remote } from "../lib/remote.svelte";
  import { toCb, toDefense } from "../lib/shapes";
  import { fmt, SERIES, teamLabel } from "../lib/theme";
  import Card from "../components/Card.svelte";
  import Chips from "../components/Chips.svelte"; // ---- IN-3
  import Expander from "../components/Expander.svelte";
  import Heatmap from "../components/Heatmap.svelte";
  import Md from "../components/Md.svelte";
  import MatchupEvidence from "../components/MatchupEvidence.svelte"; // ---- IF-3
  import PlayerRow from "../components/PlayerRow.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  // ---- IN-3 (Wave I-N): matchups for everyone — the board (every player at a position this week, with search); with a
  // league and a team the screen gains "My players · Everyone" (default: mine, as before; Everyone adds who has him)
  import Board from "../components/matchups/Board.svelte";
  import { isRef, refLabel } from "../lib/refleague";
  import { route, setParams } from "../lib/router.svelte";
  // ---- end IN-3

  let { options, league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  const d = new Remote<DefenseMatrix>(toDefense);
  const c = new Remote<CbMatchups>(toCb);
  $effect(() => d.load(researchPaths.defense(league, team), onauth));
  $effect(() => c.load(team === null ? null : researchPaths.cb(league, team), onauth));

  const ctx = $derived({ league, team });
  // ---- IN-3: browsing says the scoring ("Half PPR"), never a league name it does not have
  const leagueName = $derived(isRef(league) ? refLabel(league) : (options.find((o) => o.league_id === league)?.name ?? "this league"));
  const browsing = $derived(isRef(league) || team === null);
  const view = $derived(browsing || route.current.params.get("view") === "everyone" ? "everyone" : "mine");
  // ---- end IN-3
  const cell = $derived(new Map((d.data?.teams ?? []).map((t) => [`${t.defense}|${t.position}`, t])));
  const nDef = $derived(new Set((d.data?.teams ?? []).map((t) => t.defense)).size || 32);
  const starters = $derived(
    (d.data?.starters ?? [])
      .filter((s) => s.opponent)
      .map((s) => ({ ...s, m: cell.get(`${s.opponent}|${s.position}`) ?? null })),
  );
  // ---- IB-3: per cell the tone and the rank the screen's way (the API's; mirrored for an answer saved before them)
  const nAt = (pos: string) => cell.size ? [...cell.values()].filter((t) => t.position === pos && t.rank != null).length || nDef : nDef;
  const toneOf = (t: DefenseCell | null | undefined): Tone | null => (t ? (t.tone ?? defenseTone(t.rank, t.n_ranked ?? nAt(t.position))) : null);
  const toughOf = (t: DefenseCell | null | undefined) => (t ? (t.tough_rank ?? toughRank(t.rank, t.n_ranked ?? nAt(t.position))) : null);
  const wordsOf = (t: DefenseCell | null | undefined) => (t ? givesUpShort(t.rank, t.n_ranked ?? nAt(t.position), t.position) : "");
  // the best matchup = the defense that gives up the most (the highest "toughest" rank); the toughest = rank 1's end
  const ranked = $derived(starters.filter((s) => toughOf(s.m) != null).sort((a, b) => toughOf(b.m)! - toughOf(a.m)!));
  const best = $derived(ranked[0] ?? null);
  const worst = $derived(ranked.length > 1 ? ranked[ranked.length - 1] : null);
  // ---- end IB-3

  // the heatmap: your starters' opponents first, then the defenses that give up the most across the positions
  const marked = $derived(Object.fromEntries(starters.map((s) => [`${s.opponent}|${s.position}`, s.player_name])));
  const rows = $derived.by(() => {
    const defs = [...new Set((d.data?.teams ?? []).map((t) => t.defense))];
    const mean = (def: string) => {
      const rs = (d.data?.positions ?? []).map((p) => cell.get(`${def}|${p}`)?.rank).filter((x): x is number => x != null);
      return rs.length ? rs.reduce((a, b) => a + b, 0) / rs.length : 99;
    };
    const faced = new Set(starters.map((s) => s.opponent));
    return defs
      .sort((a, b) => Number(faced.has(b)) - Number(faced.has(a)) || mean(a) - mean(b))
      .map((def) => ({ key: def, label: teamLabel(def) ?? def }));
  });
  const cols = $derived((d.data?.positions ?? []).map((p) => ({ key: p, label: p })));
  // ---- IB-3: the cell's tone is its fill (a wash of the state color) and a glyph; the number stays printed; the title
  // says the tone, the rank the screen's way and the words
  const heatCell = (row: string, col: string) => {
    const t = cell.get(`${row}|${col}`);
    const tone = toneOf(t);
    const pts = t?.points_allowed_pg == null ? "—" : t.points_allowed_pg.toFixed(1);
    const k = toughOf(t);
    return {
      v: t?.points_allowed_pg ?? null,
      tone,
      display: tone && TONE_GLYPH[tone] ? `${TONE_GLYPH[tone]} ${pts}` : pts,
      title: tone ? `${TONE_WORD[tone]} · ${wordsOf(t)} · #${k} toughest vs ${col}` : undefined,
    };
  };
  // ---- end IB-3

  // IA-1: receivers only — a tight end mostly draws linebackers and safeties, so he is left out instead of explained
  const cbs = $derived((c.data?.matchups ?? []).filter((m) => m.position !== "TE" && m.call_status !== "tight end"));
  const starterCbs = $derived(cbs.filter((m) => m.is_starter));
  const benchCbs = $derived(cbs.filter((m) => !m.is_starter));
  // ---- IB-3: the call's tone (the API's; for an answer saved before it: the likely corner's quarter on a clear call)
  // ---- IO-4 fix round (Wave I-O): the corner is information, never a tone — graded on 2,190 called receiver-games, a
  // likely shutdown or easy corner made no measurable difference (IO-1). The chip says who is likely across in plain
  // words (his quarter) and how sure the call is, in neutral ink.
  const QUARTER: Record<string, string> = { shutdown: "Top-quarter corner", solid: "Middle-half corner", target: "Bottom-quarter corner" };
  const cornerInfo = (m: CbMatchup): string =>
    m.call_status !== "called" ? "No call" : certaintyOf(m) !== "likely" ? "Either corner" : m.cover_label ? (QUARTER[m.cover_label] ?? "Unranked corner") : "Unranked corner";
</script>

<!-- ---- IB-3: the tone chip (the signal: a word in the state color on its wash), the rank under it, small and grey -->
{#snippet toneChip(tone: Tone | null, small: string)}
  <div class="text-right" data-testid="tone-chip" data-tone={tone ?? "none"}>
    <div class="inline-block rounded-sm px-2 py-0.5 text-center text-sm font-bold whitespace-nowrap" style="background:{toneWash(tone)};color:{tone ? TONE_COLOR[tone] : 'var(--ll-ink-3)'}">
      {#if tone && TONE_GLYPH[tone]}<span aria-hidden="true">{TONE_GLYPH[tone]} </span>{/if}{tone ? TONE_WORD[tone] : "No read"}
    </div>
    {#if small}<div class="tabnum mt-0.5 text-[11px] text-ink-3" data-testid="rank-small">{small}</div>{/if}
  </div>
{/snippet}

{#snippet sideBar(m: CbMatchup)}
  {@const parts = [
    { k: "left", label: "Left", v: m.left_share ?? 0 },
    { k: "middle", label: "Middle", v: m.middle_share ?? 0 },
    { k: "right", label: "Right", v: m.right_share ?? 0 },
  ]}
  {@const on = m.call_status === "called" ? m.alignment_lean : null}
  <div data-testid="side-bar">
    <div class="flex h-2.5 gap-0.5 overflow-hidden rounded-sm" aria-hidden="true">
      {#each parts as p (p.k)}
        <span style="width:{p.v * 100}%;background:{p.k === on ? SERIES.actual : 'var(--ll-sunken)'}"></span>
      {/each}
    </div>
    <div class="mt-1 flex justify-between text-xs text-ink-3">
      {#each parts as p (p.k)}<span class={p.k === on ? "font-semibold text-ink" : ""}>{p.label} {fmt.pct(p.v)}</span>{/each}
    </div>
  </div>
{/snippet}

{#snippet cbCard(m: CbMatchup)}
  <article class="overflow-hidden rounded-lg border border-line bg-surface" style="box-shadow:var(--ll-shadow)" data-testid="cb-card">
    <PlayerRow
      player={m}
      href={withContext(`/player/${m.gsis_id}`, ctx)}
      context={`${m.is_home ? "vs" : "at"} ${teamLabel(m.opponent) ?? "?"} · projects ${fmt.pts(m.proj_points)}`}
      yours={false}
    >
      {#snippet trailing()}
        <!-- ---- IO-4 fix round: the corner named (his quarter) and the call's certainty, neutral (was the corner's tone) -->
        <div class="text-right" data-testid="cb-info">
          <div class="inline-block rounded-sm bg-raised px-2 py-0.5 text-sm font-semibold whitespace-nowrap text-ink-2">{cornerInfo(m)}</div>
          <div class="mt-0.5 text-[11px] text-ink-3" data-testid="rank-small">{certaintyOf(m)}</div>
        </div>
      {/snippet}
    </PlayerRow>
    <div class="space-y-2 border-t border-line px-3 py-3">
      <!-- ---- IB-3: who is across from him, the rank in words, how sure the call is, his history with them -->
      {#if m.named_corners?.length}
        <ul class="space-y-1 text-sm leading-snug" data-testid="cb-corners">
          {#each m.named_corners as k, i (i)}
            <li>
              <span class="text-ink-3">{i === 0 ? (certaintyOf(m) === "likely" ? "Likely across from him:" : "Either") : "or"}</span>
              <strong>{k.name}</strong> <span class="text-ink-3">({k.side})</span>: {k.words}
            </li>
          {/each}
        </ul>
      {/if}
      <p class="text-xs leading-snug text-ink-3" data-testid="cb-certainty">
        <span class="font-semibold uppercase tracking-wide">{certaintyOf(m)}</span>{m.certainty_words ? m.certainty_words.replace(/^[a-z ]+:/, ":") : ""}
      </p>
      {#if m.history}<p class="text-sm leading-snug text-ink-2" data-testid="cb-history">{m.history}</p>{/if}
      <!-- ---- end IB-3 -->
      <!-- ---- IF-3: these corners vs the corners the defense's rank was earned with (shown when they changed) -->
      {#if m.matchup_evidence?.matchup_uncertain}
        <div class="rounded-md bg-warn-soft px-3 py-2"><MatchupEvidence ev={m.matchup_evidence} testid="cb-evidence" /></div>
      {/if}
      {#if m.call_status !== "tight end"}
        <p class="ll-label">His targets by side (the offense's view)</p>
        {@render sideBar(m)}
      {/if}
    </div>
  </article>
{/snippet}

<!-- ---- IN-3: the heatmap card, on both views (the board's view keeps it under the board) -->
{#snippet defenseCard()}
  {#if d.data}
    <Card title="Defense vs position" testid="defense">
      <p class="mb-3 text-sm leading-snug text-ink-2">
        Points each defense gives up per game to each position{d.data.weeks_used ? `, weeks 1–${d.data.weeks_used}` : ""}, in {leagueName} scoring.
        <strong class="text-good">▲ Favorable</strong>: one of the 10 that give up the most; <strong class="text-bad">▼ Difficult</strong>: one of the 10
        that give up the fewest; the rest neutral.{#if starters.length && view === "mine"}&nbsp;Ringed: your starters' matchups this week (their defenses come first).{/if}
      </p>
      <Heatmap {rows} {cols} cell={heatCell} marked={view === "mine" ? marked : {}} tones />
    </Card>
  {/if}
{/snippet}

<main class="space-y-5" data-testid="matchups">
  <ScreenHead eyebrow="Research · Matchups" title={d.data?.week ? `${view === "everyone" ? "Matchups" : "Your matchups"}, week ${d.data.week}` : "Matchups"}>
    {#snippet answer()}
      {#if view === "everyone"}
        <span data-testid="board-answer"
          >Every player's matchup this week: the defense against his position and, for a receiver, the corner likely across from him.</span
        >
      {:else if best}
        <span data-testid="matchups-answer"
          >Best matchup in your lineup: <strong>{best.player_name}</strong> ({best.position}) {best.is_home ? "vs" : "at"}
          {teamLabel(best.opponent)}, who {wordsOf(best.m)}: <strong style="color:{TONE_COLOR[toneOf(best.m) ?? 'neutral']}">{TONE_WORD[toneOf(best.m) ?? "neutral"].toLowerCase()}</strong>{#if worst}. Toughest: <strong>{worst.player_name}</strong> ({worst.position}) {worst.is_home
              ? "vs"
              : "at"}
            {teamLabel(worst.opponent)}, who {wordsOf(worst.m)}: <strong style="color:{TONE_COLOR[toneOf(worst.m) ?? 'neutral']}">{TONE_WORD[toneOf(worst.m) ?? "neutral"].toLowerCase()}</strong>{/if}.</span
        >
      {:else if d.data && team === null}
        Pick your team above to see your starters' matchups. The heatmap below works for anyone.
      {/if}
    {/snippet}
  </ScreenHead>

  <!-- ---- IN-3: with a league and a team, the switch; browsing, the board alone -->
  {#if !browsing}
    <Chips
      items={[
        { key: "mine", label: "My players" },
        { key: "everyone", label: "Everyone" },
      ]}
      current={view}
      label="Whose matchups"
      testid="matchups-view"
      onpick={(k) => setParams({ view: k === "everyone" ? "everyone" : null })}
    />
  {/if}
  {#if view === "everyone"}
    <div class="grid grid-cols-1 gap-5">
      <Board {league} {team} {onauth} owners={!isRef(league)} />
      {@render defenseCard()}
    </div>
  {:else if d.error}
    <!-- ---- end IN-3 -->
    <p class="ll-error">{d.error}</p>
  {:else if !d.data}
    <div class="space-y-3" aria-label="Loading" data-testid="loading">
      {#each [0, 1, 2] as i (i)}<div class="ll-skel h-14"></div>{/each}
      <div class="ll-skel h-64"></div>
    </div>
  {:else}
    <div class="grid grid-cols-1 gap-5 wide:grid-cols-2 wide:items-start">
      <div class="space-y-5">
        {#if starters.length}
          <Card title="Your starters this week" pad={false} testid="starters">
            <ul class="divide-y divide-line">
              {#each starters as s (s.gsis_id)}
                <li>
                  <PlayerRow
                    player={s}
                    href={withContext(`/player/${s.gsis_id}`, ctx)}
                    context={`${s.slot ?? s.position} · ${s.is_home ? "vs" : "at"} ${teamLabel(s.opponent)} · ${wordsOf(s.m)}`}
                  >
                    {#snippet trailing()}{@render toneChip(toneOf(s.m), toughOf(s.m) == null ? "" : `#${toughOf(s.m)} toughest vs ${s.position}`)}{/snippet}
                  </PlayerRow>
                </li>
              {/each}
            </ul>
          </Card>
        {/if}

        {#if team !== null}
          <section class="space-y-2.5" data-testid="cb-section">
            <h2 class="text-lg leading-tight font-bold" data-testid="cb-title">The cornerbacks your receivers face</h2>
            {#if c.error}
              <p class="ll-error">{c.error}</p>
            {:else if !c.data}
              <div class="ll-skel h-32"></div>
            {:else if cbs.length === 0}
              <p class="ll-empty">No wide receivers on your roster with a game this week.</p>
            {:else}
              {#each starterCbs as m (m.gsis_id)}{@render cbCard(m)}{/each}
              <p class="text-xs leading-snug text-ink-3" data-testid="cb-caption">
                Likely across from him = the outside corner on the side more of his targets go: a lean, not an assignment (nobody publishes who
                covers whom). <strong>Likely</strong>: his targets lean 15 points or more to one side; <strong>unclear</strong>: either outside corner.
                Top quarter = among the quarter of {cbs.find((m) => m.cb_n_ranked)?.cb_n_ranked ?? "the"} starting corners hardest to throw on since the start of
                last season (#1 = the hardest); bottom quarter = the easiest quarter. The corner is shown for context: it is not in the projection and does not move the
                matchup.
              </p>
              {#if benchCbs.length}
                <Expander title={`Your bench receivers (${benchCbs.length})`} testid="cb-bench">
                  <div class="space-y-2.5">{#each benchCbs as m (m.gsis_id)}{@render cbCard(m)}{/each}</div>
                </Expander>
              {/if}
            {/if}
          </section>
        {/if}
      </div>

      {@render defenseCard()}
    </div>

    <Expander title="How to read this" testid="howto">
      <div class="text-base leading-snug">
        <Md
          block
          text={"- **Favorable** means the defense gives up a lot to his position (one of the 10 that give up the most): a matchup you want. **Difficult** is one of the 10 that give up the fewest. The rest are neutral.\n" +
            "- **Ranks run one way on this screen: #1 is the toughest for the offense** — the defense that gives up the fewest points to the position, the corner hardest to throw on.\n" +
            "- **The cornerback is context, not a reason to start or sit someone**: graded against past games, a likely shutdown or easy corner made no measurable difference to a receiver's points against his projection, so it moves no matchup here. A call marked **unclear** could be either corner.\n" +
            "- The side bar shows where his targets have gone since the start of last season (the offense's left, middle, right); the highlighted side is the one the named corner covers.\n" +
            `- A few weeks is a small sample: a defense's rank moves a lot early. Points here are in ${leagueName} scoring.`}
        />
      </div>
    </Expander>
  {/if}
</main>
