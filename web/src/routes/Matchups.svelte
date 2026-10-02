<script lang="ts">
  // Research · Matchups (Wave G): the answer first (your starters' best and toughest matchups this week), then your
  // starters with their matchup rank, the defense-vs-position heatmap (team × position, your starters' cells ringed),
  // and the cornerbacks your receivers face (app/lib's sentence, the side his targets go as a bar, the corner's rank).
  // GET /api/matchups/defense (mart_defense_vs_position_current) and /api/matchups/cb (mart_cb_matchups + ranks).
  import { researchPaths, type CbMatchup, type CbMatchups, type DefenseMatrix } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import { rankWord } from "../lib/research";
  import { Remote } from "../lib/remote.svelte";
  import { fmt, seqFill, seqInk, SERIES, teamLabel } from "../lib/theme";
  import Card from "../components/Card.svelte";
  import Expander from "../components/Expander.svelte";
  import Heatmap from "../components/Heatmap.svelte";
  import Md from "../components/Md.svelte";
  import PlayerRow from "../components/PlayerRow.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";

  let { options, league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  const d = new Remote<DefenseMatrix>();
  const c = new Remote<CbMatchups>();
  $effect(() => d.load(researchPaths.defense(league, team), onauth));
  $effect(() => c.load(team === null ? null : researchPaths.cb(league, team), onauth));

  const ctx = $derived({ league, team });
  const leagueName = $derived(options.find((o) => o.league_id === league)?.name ?? "this league");
  const cell = $derived(new Map((d.data?.teams ?? []).map((t) => [`${t.defense}|${t.position}`, t])));
  const nDef = $derived(new Set((d.data?.teams ?? []).map((t) => t.defense)).size || 32);
  const starters = $derived(
    (d.data?.starters ?? [])
      .filter((s) => s.opponent)
      .map((s) => ({ ...s, m: cell.get(`${s.opponent}|${s.position}`) ?? null })),
  );
  const ranked = $derived(starters.filter((s) => s.m?.rank != null).sort((a, b) => a.m!.rank! - b.m!.rank!));
  const best = $derived(ranked[0] ?? null);
  const worst = $derived(ranked.length > 1 ? ranked[ranked.length - 1] : null);

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
  const heatCell = (row: string, col: string) => {
    const t = cell.get(`${row}|${col}`);
    return { v: t?.points_allowed_pg ?? null, display: t?.points_allowed_pg == null ? "—" : t.points_allowed_pg.toFixed(1), title: t?.rank ? `#${t.rank} vs ${col}` : undefined };
  };

  const cbs = $derived(c.data?.matchups ?? []);
  const starterCbs = $derived(cbs.filter((m) => m.is_starter));
  const benchCbs = $derived(cbs.filter((m) => !m.is_starter));
</script>

{#snippet rankChip(rank: number | null | undefined, pos: string)}
  {@const t = rank == null ? 0 : 1 - (rank - 1) / Math.max(1, nDef - 1)}
  <div class="text-right" data-testid="rank-chip">
    <div class="tabnum inline-block min-w-11 rounded-sm px-1.5 py-0.5 text-center text-base font-bold" style="background:{seqFill(0.1 + t * 0.9)};color:{seqInk(0.1 + t * 0.9)}">
      {rank == null ? "—" : `#${rank}`}
    </div>
    <div class="mt-0.5 text-[10px] font-semibold tracking-wide text-ink-3 uppercase">vs {pos}</div>
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
        {#if m.cover_rank != null}
          <div class="text-right">
            <div class="tabnum text-base leading-none font-bold">#{m.cover_rank}<span class="text-xs font-medium text-ink-3"> of {m.cb_n_ranked}</span></div>
            <div class="mt-0.5 text-[10px] font-semibold tracking-wide uppercase {m.cover_label === 'shutdown' ? 'text-bad' : m.cover_label === 'target' ? 'text-good' : 'text-ink-3'}">
              {m.cover_label}
            </div>
          </div>
        {/if}
      {/snippet}
    </PlayerRow>
    <div class="space-y-2 border-t border-line px-3 py-3">
      <p class="text-sm leading-snug"><Md text={m.line} {ctx} /></p>
      {#if m.call_status !== "tight end"}
        <p class="ll-label">His targets by side (the offense's view)</p>
        {@render sideBar(m)}
      {/if}
    </div>
  </article>
{/snippet}

<main class="space-y-5" data-testid="matchups">
  <ScreenHead eyebrow="Research · Matchups" title={d.data?.week ? `Your matchups, week ${d.data.week}` : "Matchups"}>
    {#snippet answer()}
      {#if best}
        <span data-testid="matchups-answer"
          >Best matchup in your lineup: <strong>{best.player_name}</strong> ({best.position}) {best.is_home ? "vs" : "at"}
          {teamLabel(best.opponent)}, #{best.m?.rank} vs {best.position}{#if worst}; toughest: <strong>{worst.player_name}</strong> ({worst.position}) {worst.is_home
              ? "vs"
              : "at"}
            {teamLabel(worst.opponent)}, #{worst.m?.rank} vs {worst.position}{/if}. #1 = the defense that gives up the most to the position.</span
        >
      {:else if d.data && team === null}
        Pick your team above to see your starters' matchups. The heatmap below works for anyone.
      {/if}
    {/snippet}
  </ScreenHead>

  {#if d.error}
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
                    context={`${s.slot ?? s.position} · ${s.is_home ? "vs" : "at"} ${teamLabel(s.opponent)} · ${rankWord(s.m?.rank, nDef)}`}
                  >
                    {#snippet trailing()}{@render rankChip(s.m?.rank, s.position)}{/snippet}
                  </PlayerRow>
                </li>
              {/each}
            </ul>
          </Card>
        {/if}

        {#if team !== null}
          <section class="space-y-2.5" data-testid="cb-section">
            <h2 class="ll-label">Cornerbacks your receivers face</h2>
            {#if c.error}
              <p class="ll-error">{c.error}</p>
            {:else if !c.data}
              <div class="ll-skel h-32"></div>
            {:else if cbs.length === 0}
              <p class="ll-empty">No receivers on your roster with a game this week.</p>
            {:else}
              {#each starterCbs as m (m.gsis_id)}{@render cbCard(m)}{/each}
              <p class="text-xs leading-snug text-ink-3">
                Likely across from him = the outside corner on the side more of his targets go: a lean, not an assignment (nobody publishes who
                covers whom). Rank among {cbs.find((m) => m.cb_n_ranked)?.cb_n_ranked ?? "the"} starting corners since the start of last season, #1 = hardest
                to throw on; shutdown = the top quarter, target = the bottom quarter.
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

      <Card title="Defense vs position" testid="defense">
        <p class="mb-3 text-sm leading-snug text-ink-2">
          Points each defense gives up a game to each position{d.data.weeks_used ? `, weeks 1–${d.data.weeks_used}` : ""}, one scale for every league.
          Stronger color = gives up more = the matchup you want.{#if starters.length}&nbsp;Ringed: your starters' matchups this week (their defenses come first).{/if}
        </p>
        <Heatmap {rows} {cols} cell={heatCell} {marked} lowLabel="gives up fewer" highLabel="gives up more" />
      </Card>
    </div>

    <Expander title="How to read this" testid="howto">
      <div class="text-base leading-snug">
        <Md
          block
          text={"- **#1 vs RB** is the defense that gives up the most points a game to running backs: the matchup you want. #32 is the toughest.\n" +
            "- **Start the receiver whose likely corner ranks lower** when two options are close; don't bench a star for a tough corner: his targets matter more, and the projection already counts the defense.\n" +
            "- The side bar shows where his targets have gone since the start of last season (the offense's left, middle, right); the highlighted side is the one the named corner covers.\n" +
            "- Tight ends mostly draw linebackers and safeties, so they get no cornerback call.\n" +
            `- Three weeks is a small sample: a defense's rank moves a lot early. Points here are on one scale for every league, not ${leagueName}'s.`}
        />
      </div>
    </Expander>
  {/if}
</main>
