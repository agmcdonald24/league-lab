<script lang="ts">
  // Research · Trends (Wave G): over- vs under-performing. The answer first — who is due (scoring below what his work
  // is worth) and who is running hot — then every player as a row with his gap as a bar (actual minus expected
  // points a game, this league's scoring), filters for the view, the position and whose players. From 900 px the
  // picked player's detail sits on the right: his card, the two numbers as bars, his role alert, his last 3 games, his
  // points by week. GET /api/trends (mart_player_trend_tags + actual vs expected + role alerts).
  import { researchPaths, type Trends, type TrendRow } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import { gapWords, NEAR, ownerWord, whoFilter, workLine, type Who } from "../lib/research";
  import { Remote } from "../lib/remote.svelte";
  import { navigate, route, setParams } from "../lib/router.svelte";
  import { fmt, SERIES } from "../lib/theme";
  import Bar from "../components/Bar.svelte";
  import Card from "../components/Card.svelte";
  import Chips from "../components/Chips.svelte";
  import Expander from "../components/Expander.svelte";
  import GameLog from "../components/GameLog.svelte";
  import ListDetail from "../components/ListDetail.svelte";
  import Md from "../components/Md.svelte";
  import PlayerCard from "../components/PlayerCard.svelte";
  import PlayerRow from "../components/PlayerRow.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import StatTile from "../components/StatTile.svelte";

  let { options, league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  const r = new Remote<Trends>();
  $effect(() => r.load(researchPaths.trends(league), onauth));

  const ctx = $derived({ league, team });
  const leagueName = $derived(options.find((o) => o.league_id === league)?.name ?? "this league");
  const params = $derived(route.current.params);
  const view = $derived((["all", "due", "hot"].includes(params.get("view") ?? "") ? params.get("view") : "all") as "all" | "due" | "hot");
  const position = $derived(["QB", "RB", "WR", "TE"].includes((params.get("position") ?? "").toUpperCase()) ? params.get("position")!.toUpperCase() : "ALL");
  const who = $derived((["all", "mine", "fa"].includes(params.get("who") ?? "") ? params.get("who") : "all") as Who);
  let more = $state(false);

  const pool = $derived((r.data?.players ?? []).filter((p) => p.gap !== null && (position === "ALL" || p.position === position) && whoFilter(who, team)(p)));
  const rows = $derived.by(() => {
    const xs = pool.filter((p) => (view === "due" ? p.gap! < -NEAR : view === "hot" ? p.gap! > NEAR : true));
    return [...xs].sort((a, b) => (view === "due" ? a.gap! - b.gap! : view === "hot" ? b.gap! - a.gap! : Math.abs(b.gap!) - Math.abs(a.gap!)));
  });
  const shown = $derived(more ? rows : rows.slice(0, 30));
  const due = $derived(pool.filter((p) => p.gap! < -NEAR).sort((a, b) => a.gap! - b.gap!)[0] ?? null);
  const hot = $derived(pool.filter((p) => p.gap! > NEAR).sort((a, b) => b.gap! - a.gap!)[0] ?? null);
  const span = $derived(Math.max(4, ...rows.map((p) => Math.abs(p.gap ?? 0))));
  const picked = $derived(rows.find((p) => p.gsis_id === params.get("pick")) ?? rows[0] ?? null);
  const href = (p: TrendRow) => withContext(`/player/${p.gsis_id}`, ctx);

  const setView = (v: string) => setParams({ view: v === "all" ? null : v });
  const setPos = (p: string) => setParams({ position: p === "ALL" ? null : p });
  const setWho = (w: string) => setParams({ who: w === "all" ? null : w });
</script>

{#snippet gapBar(p: TrendRow)}
  {@const g = p.gap ?? 0}
  {@const w = Math.min(50, (Math.abs(g) / span) * 50)}
  <div class="w-[5.5rem] text-right" data-testid="gap">
    <div class="tabnum text-base leading-none font-bold {g > NEAR ? 'text-ink' : g < -NEAR ? 'text-ink' : 'text-ink-3'}">{fmt.signed(g)}</div>
    <div class="relative mt-1.5 h-1.5 rounded-sm bg-sunken" aria-hidden="true">
      <span class="absolute inset-y-[-2px] left-1/2 w-px bg-line-strong"></span>
      <span
        class="absolute inset-y-0"
        style="background:{g >= 0 ? SERIES.hot : SERIES.due};{g >= 0 ? `left:50%;width:${w}%;border-radius:0 3px 3px 0` : `right:50%;width:${w}%;border-radius:3px 0 0 3px`}"
      ></span>
    </div>
  </div>
{/snippet}

{#snippet answerCard(p: TrendRow, label: string, testid: string)}
  <PlayerCard
    player={p}
    number={fmt.signed(p.gap)}
    numberLabel={label}
    line={`${workLine(p.ppg, p.xppg)} · ${ownerWord(p, team)}`}
    href={href(p)}
    compact
    {testid}
  />
{/snippet}

<main class="space-y-4" data-testid="trends">
  <ScreenHead eyebrow="Research · Trends" title="Who is due, who is running hot">
    {#snippet answer()}
      {#if r.data && (due || hot)}
        {#if due}<strong>Due to pick up: {due.player_name}</strong> ({workLine(due.ppg, due.xppg)}).{/if}
        {#if hot}<strong>Running hot: {hot.player_name}</strong> ({workLine(hot.ppg, hot.xppg)}).{/if}
        Points a game in {leagueName} scoring.
      {:else if r.data}
        Nobody here scores far from what his work is worth yet.
      {/if}
    {/snippet}
  </ScreenHead>

  {#if r.error}
    <p class="ll-error">{r.error}</p>
  {:else if !r.data}
    <div class="space-y-3" aria-label="Loading" data-testid="loading">
      <div class="ll-skel h-28"></div>
      {#each [0, 1, 2, 3] as i (i)}<div class="ll-skel h-14"></div>{/each}
    </div>
  {:else}
    {#if due || hot}
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2" data-testid="trends-answer">
        {#if due}{@render answerCard(due, "Due", "card-due")}{/if}
        {#if hot}{@render answerCard(hot, "Hot", "card-hot")}{/if}
      </div>
    {/if}

    <div class="flex flex-wrap items-center gap-2">
      <Chips
        label="View"
        testid="view"
        current={view}
        onpick={setView}
        items={[
          { key: "all", label: "Everyone" },
          { key: "due", label: "Due" },
          { key: "hot", label: "Running hot" },
        ]}
      />
      <Chips label="Position" testid="pos" current={position} onpick={setPos} items={["ALL", "QB", "RB", "WR", "TE"].map((p) => ({ key: p, label: p === "ALL" ? "All" : p }))} />
      <Chips
        label="Whose"
        testid="who"
        current={who}
        onpick={setWho}
        items={[
          { key: "all", label: "Everyone" },
          { key: "mine", label: "Yours" },
          { key: "fa", label: "Free agents" },
        ]}
      />
    </div>

    <ListDetail phoneDetail={false}>
      {#snippet list()}
        <section class="overflow-hidden rounded-lg border border-line bg-surface" style="box-shadow:var(--ll-shadow)" data-testid="trends-list">
          <header class="flex items-baseline justify-between border-b border-line bg-raised px-3 py-2">
            <h2 class="ll-label">{rows.length} player{rows.length === 1 ? "" : "s"}</h2>
            <span class="ll-label">vs his work</span>
          </header>
          {#if rows.length === 0}
            <p class="p-4 text-base text-ink-2" data-testid="trends-empty">No player matches these filters.</p>
          {/if}
          <ul class="divide-y divide-line">
            {#each shown as p (p.gsis_id)}
              <li>
                <PlayerRow
                  player={p}
                  href={href(p)}
                  context={`${fmt.pts(p.ppg)} a game · worth ${fmt.pts(p.xppg)}`}
                  yours={team !== null && p.rostered_by_roster_id === team}
                  selected={picked?.gsis_id === p.gsis_id}
                  onselect={() => (window.innerWidth < 900 ? navigate(href(p)) : setParams({ pick: p.gsis_id }))}
                >
                  {#snippet trailing()}{@render gapBar(p)}{/snippet}
                </PlayerRow>
              </li>
            {/each}
          </ul>
          {#if rows.length > shown.length}
            <button type="button" class="w-full border-t border-line py-3 text-sm font-semibold text-accent" onclick={() => (more = true)} data-testid="more"
              >Show all {rows.length}</button
            >
          {/if}
        </section>
      {/snippet}
      {#snippet detail()}
        {#if picked && r.data}
          <div class="space-y-3" data-testid="trends-detail">
            <PlayerCard
              player={picked}
              number={fmt.signed(picked.gap)}
              numberLabel="vs work"
              line={`${workLine(picked.ppg, picked.xppg)}: ${gapWords(picked.gap)}.`}
              context={ownerWord(picked, team)}
              href={href(picked)}
            >
              {#snippet extra()}
                {@const top = Math.max(picked.ppg ?? 0, picked.xppg ?? 0) * 1.15 || 1}
                <div class="space-y-2.5">
                  <Bar label="Points a game" value={picked.ppg} max={top} display={fmt.pts(picked.ppg)} color={SERIES.actual} />
                  <Bar label="Expected points a game (what his work is worth)" value={picked.xppg} max={top} display={fmt.pts(picked.xppg)} color={SERIES.expected} />
                </div>
              {/snippet}
            </PlayerCard>
            {#if picked.role_alert}
              <Card tone="raised" testid="role-alert">
                <p class="ll-label">{picked.role_alert.direction === "up" ? "▲ Bigger role" : "▼ Smaller role"} · {picked.role_alert.label}</p>
                <p class="mt-1 text-base leading-snug">{picked.role_alert.change_text}</p>
                {#if picked.role_alert.cause_text}<p class="mt-1 text-sm text-ink-2">Why: {picked.role_alert.cause_text}</p>{/if}
              </Card>
            {/if}
            <div class="grid grid-cols-3 gap-2">
              <StatTile label="Target share, last 3" value={fmt.pct(picked.target_share_l3)} size="sm" />
              <StatTile label="Snaps, last 3" value={fmt.pct(picked.snap_share_l3)} size="sm" />
              <StatTile label="Points, last 3" value={fmt.pts(picked.points_l3)} size="sm" />
            </div>
            {#if picked.tags}<p class="text-sm text-ink-2">Trend: {picked.tags}</p>{/if}
            <GameLog gsis={picked.gsis_id} {league} season={r.data.season} {onauth} {leagueName} />
          </div>
        {/if}
      {/snippet}
    </ListDetail>

    <Expander title="How to read this" testid="howto">
      <div class="text-base leading-snug">
        <Md
          block
          text={"- **Due** scores below what his work is worth: his targets and carries usually bring more points. Hold him, or buy him while he is cheap.\n" +
            "- **Running hot** scores above what his work is worth (long touchdowns, a big play): expect him to cool off. A good time to sell.\n" +
            "- **Expected points a game** is what his targets and carries are usually worth, in your league's scoring; the bar is points a game minus that.\n" +
            "- Three games is a small sample: a gap is a question to look into, not a verdict. Tap a name for his card and his points week by week."}
        />
      </div>
    </Expander>
  {/if}
</main>
