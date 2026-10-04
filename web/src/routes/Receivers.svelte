<script lang="ts">
  // Research · Receivers (Wave G): the role behind a receiver's points. The answer first (the biggest share of his
  // team's targets, the biggest riser over his last 3 games), then the list (target share as the headline number) and
  // the picked receiver's role as bars against the yardstick (what the season's top 12 at his position average):
  // target share, targets per game, air-yard share, how far downfield, first-read share, snaps; then the share over his
  // last 3 and 5 games vs the season. GET /api/receivers (mart_player_season + mart_player_recent_form).
  import { researchPaths, type ReceiverRow, type Receivers } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import { ownerWord, whoFilter, type Who } from "../lib/research";
  import { Remote } from "../lib/remote.svelte";
  import { toReceivers } from "../lib/shapes";
  import { route, setParams } from "../lib/router.svelte";
  import { fmt } from "../lib/theme";
  import Bar from "../components/Bar.svelte";
  import Card from "../components/Card.svelte";
  import Chips from "../components/Chips.svelte";
  import Expander from "../components/Expander.svelte";
  import ListDetail from "../components/ListDetail.svelte";
  import Md from "../components/Md.svelte";
  import PlayerCard from "../components/PlayerCard.svelte";
  import PlayerRow from "../components/PlayerRow.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import ErrorCard from "../components/ErrorCard.svelte"; // ---- IH-1: the API down / a 500 / still waiting

  let { options, league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  const r = new Remote<Receivers>(toReceivers);
  $effect(() => r.load(researchPaths.receivers(league), onauth));

  const ctx = $derived({ league, team });
  const leagueName = $derived(options.find((o) => o.league_id === league)?.name ?? "this league");
  const params = $derived(route.current.params);
  const position = $derived((params.get("position") ?? "").toUpperCase() === "TE" ? "TE" : "WR");
  const who = $derived((["all", "mine", "fa"].includes(params.get("who") ?? "") ? params.get("who") : "all") as Who);
  let more = $state(false);

  const rows = $derived(
    (r.data?.receivers ?? [])
      .filter((p) => p.position === position && whoFilter(who, team)(p))
      .sort((a, b) => (b.target_share ?? -1) - (a.target_share ?? -1)),
  );
  const shown = $derived(more ? rows : rows.slice(0, 30));
  const ys = $derived(r.data?.yardsticks?.[position] ?? {});
  const top = $derived(rows[0] ?? null);
  const riser = $derived(
    [...rows]
      .filter((p) => p.target_share_l3 !== null && p.target_share !== null && (p.games_played ?? 0) >= 3)
      .sort((a, b) => b.target_share_l3! - b.target_share! - (a.target_share_l3! - a.target_share!))[0] ?? null,
  );
  const picked = $derived(rows.find((p) => p.gsis_id === params.get("pick")) ?? rows[0] ?? null);

  // the role bars: label, the row's key, the bar's top, how to show it
  const METRICS: { key: keyof ReceiverRow; label: string; max: number; show: (v: number | null) => string }[] = [
    { key: "target_share", label: "Share of his team's targets", max: 0.4, show: (v) => fmt.pct(v) },
    { key: "targets_per_game", label: "Targets per game", max: 12, show: (v) => fmt.pts(v) },
    { key: "air_yards_share", label: "Share of his team's air yards", max: 0.55, show: (v) => fmt.pct(v) },
    { key: "adot", label: "How far downfield (yards per target)", max: 20, show: (v) => fmt.pts(v) },
    { key: "first_read_target_share", label: "First-read share (the quarterback's first look)", max: 0.45, show: (v) => fmt.pct(v) },
    { key: "route_participation", label: "On the field for pass plays", max: 1, show: (v) => fmt.pct(v) },
    { key: "avg_offense_snap_pct", label: "Snaps", max: 1, show: (v) => fmt.pct(v) },
  ];

  // routes are estimated after the season: until then the route numbers come as null or 0 (unknown is not zero)
  const ROUTES = new Set<keyof ReceiverRow>(["route_participation", "tprr_proxy", "yprr_proxy"]);
  const known = (p: ReceiverRow, k: keyof ReceiverRow) => p[k] !== null && !(ROUTES.has(k) && !p[k]);

  function pick(p: ReceiverRow) {
    setParams({ pick: p.gsis_id });
    if (window.innerWidth < 900) document.querySelector('[data-testid="receivers-detail"]')?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
</script>

<main class="space-y-4" data-testid="receivers">
  <ScreenHead eyebrow="Research · Receivers" title="Receivers' roles">
    {#snippet answer()}
      {#if top}
        <span data-testid="receivers-answer"
          ><strong>Biggest share of his team's targets: {top.player_name}</strong> ({fmt.pct(top.target_share)}; the top-12 {position}s average {fmt.pct(
            ys.target_share ?? null,
          )}).{#if riser && riser.target_share_l3! - riser.target_share! > 0.02}
            <strong>Rising: {riser.player_name}</strong> ({fmt.pct(riser.target_share_l3)} over his last 3 games, {fmt.pct(riser.target_share)} for the season).{/if}</span
        >
      {:else if r.data}
        No receiver matches these filters.
      {/if}
    {/snippet}
  </ScreenHead>

  <div class="flex flex-wrap items-center gap-2">
    <Chips label="Position" testid="pos" current={position} onpick={(p) => setParams({ position: p === "WR" ? null : p, pick: null })} items={[{ key: "WR", label: "WR" }, { key: "TE", label: "TE" }]} />
    <Chips
      label="Whose"
      testid="who"
      current={who}
      onpick={(w) => setParams({ who: w === "all" ? null : w, pick: null })}
      items={[
        { key: "all", label: "Everyone" },
        { key: "mine", label: "Yours" },
        { key: "fa", label: "Free agents" },
      ]}
    />
  </div>

  {#if r.error}
    <!-- ---- IH-1: a card with Try again for the API down / a 500 / Sleeper; a 404's own words stay a plain line -->
    {#if r.failure && r.failure.kind !== "notfound" && r.failure.kind !== "other"}<ErrorCard failure={r.failure} onretry={() => r.retry()} />{:else}<p class="ll-error">{r.error}</p>{/if}
  {:else if r.failure?.kind === "slow"}
    <ErrorCard failure={r.failure} onretry={() => r.retry()} /><!-- ---- IH-1: still waiting after 25 s -->
  {:else if !r.data}
    <div class="space-y-3" aria-label="Loading" data-testid="loading"><div class="ll-skel h-48"></div>{#each [0, 1, 2] as i (i)}<div class="ll-skel h-14"></div>{/each}</div>
  {:else}
    <ListDetail detailFirst>
      {#snippet list()}
        <section class="overflow-hidden rounded-lg border border-line bg-surface" style="box-shadow:var(--ll-shadow)" data-testid="receivers-list">
          <header class="flex items-baseline justify-between border-b border-line bg-raised px-3 py-2">
            <h2 class="ll-label">{rows.length} {position}s</h2>
            <span class="ll-label">Share of team passes</span><!-- IF-4: the dictionary -->
          </header>
          {#if rows.length === 0}<p class="p-4 text-ink-2">No receiver matches these filters.</p>{/if}
          <ul class="divide-y divide-line">
            {#each shown as p (p.gsis_id)}
              <li>
                <PlayerRow
                  player={p}
                  href={withContext(`/player/${p.gsis_id}`, ctx)}
                  context={`${fmt.pts(p.targets_per_game)} targets per game · ${ownerWord(p, team)}`}
                  value={fmt.pct(p.target_share)}
                  valueLabel={p.target_share_l3 !== null ? `last 3: ${fmt.pct(p.target_share_l3)}` : undefined}
                  yours={team !== null && p.rostered_by_roster_id === team}
                  selected={picked?.gsis_id === p.gsis_id}
                  onselect={() => pick(p)}
                />
              </li>
            {/each}
          </ul>
          {#if rows.length > shown.length}
            <button type="button" class="w-full border-t border-line py-3 text-sm font-semibold text-accent" onclick={() => (more = true)}>Show all {rows.length}</button>
          {/if}
        </section>
      {/snippet}
      {#snippet detail()}
        {#if picked}
          {@const accent = "var(--ll-series-1)"}
          <div class="space-y-3" data-testid="receivers-detail">
            <PlayerCard
              player={picked}
              number={fmt.pct(picked.target_share)}
              numberLabel="Share of team passes"
              line={`${fmt.pts(picked.targets_per_game)} targets per game · ${fmt.pts(picked.ppg)} points per game in ${leagueName} scoring · ${picked.games_played} games`}
              context={ownerWord(picked, team)}
              href={withContext(`/player/${picked.gsis_id}`, ctx)}
            />
            <Card title="His role vs the top 12" testid="role-bars">
              <div class="space-y-3">
                {#each METRICS.filter((m) => known(picked, m.key)) as m (m.key)}
                  <Bar
                    label={m.label}
                    value={picked[m.key] as number}
                    max={m.max}
                    display={m.show(picked[m.key] as number)}
                    color={accent}
                    mark={(ys[m.key] as number | null | undefined) ?? null}
                    markLabel={`Top-12 ${position} average: ${m.show((ys[m.key] as number | null | undefined) ?? null)}`}
                  />
                {/each}
              </div>
              <p class="mt-3 flex items-center gap-1.5 text-xs text-ink-3">
                <span class="inline-block h-3 w-0.5 rounded bg-ink"></span> the top-12 {position}s' average (the 12 with the most points per game)
              </p>
            </Card>
            <Card title="His share of the targets, lately" testid="form-bars">
              <div class="space-y-3">
                <Bar label="Last 3 games" value={picked.target_share_l3} max={0.4} display={fmt.pct(picked.target_share_l3)} color={accent} />
                <Bar label="Last 5 games" value={picked.target_share_l5} max={0.4} display={fmt.pct(picked.target_share_l5)} color={accent} />
                <Bar label="Season" value={picked.target_share} max={0.4} display={fmt.pct(picked.target_share)} color="var(--ll-ink-3)" />
              </div>
            </Card>
          </div>
        {/if}
      {/snippet}
    </ListDetail>

    <Expander title="How to read this" testid="howto">
      <div class="text-base leading-snug">
        <Md
          block
          text={"- **Use it to tell a real role from a busy stretch**: a receiver whose share of the targets is at or above the top-12 average is a weekly starter; one rising over his last 3 games is a waiver or trade target before his points catch up.\n" +
            "- **Share of team passes** (target share) is his share of his team's targets in the games he played: 20% is about one in five. **Air yards** is how far downfield his targets travel; a big share means the big plays.\n" +
            "- **First-read share** is how often he is the quarterback's first look: his first-read targets ÷ his team's charted dropbacks with a first read. **On the field for pass plays** is an estimate, filled in after the season.\n" +
            "- The tick on each bar is what the season's top 12 at his position average."}
        />
      </div>
    </Expander>
  {/if}
</main>
