<script lang="ts">
  // Research · Players (Wave G): every skill player's season as one sortable list with headshots. The answer first
  // (the points leader at the filter), then search, position, NFL team and whose players, then the table: a phone
  // keeps Player · Points a game · Points; from 640 px the usage columns join. GET /api/players (mart_player_season +
  // points in this league's scoring), loaded once per league; the filters and the sort run on the phone (instant).
  import { researchPaths, type Players, type SeasonRow } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import { ownerWord, whoFilter, type Who } from "../lib/research";
  import { Remote } from "../lib/remote.svelte";
  import { toPlayers } from "../lib/shapes";
  import { route, setParams } from "../lib/router.svelte";
  import { fmt, TEAMS, teamLabel } from "../lib/theme";
  import Chips from "../components/Chips.svelte";
  import Expander from "../components/Expander.svelte";
  import Headshot from "../components/Headshot.svelte";
  import Md from "../components/Md.svelte";
  import PosBadge from "../components/PosBadge.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import Table, { type Column } from "../components/Table.svelte";
  import TeamBadge from "../components/TeamBadge.svelte";

  let { options, league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  const r = new Remote<Players>(toPlayers);
  $effect(() => r.load(researchPaths.players(league), onauth));

  const ctx = $derived({ league, team });
  const leagueName = $derived(options.find((o) => o.league_id === league)?.name ?? "this league");
  const params = $derived(route.current.params);
  const position = $derived(["QB", "RB", "WR", "TE"].includes((params.get("position") ?? "").toUpperCase()) ? params.get("position")!.toUpperCase() : "ALL");
  const who = $derived((["all", "mine", "fa", "rostered"].includes(params.get("who") ?? "") ? params.get("who") : "all") as Who);
  const nfl = $derived(params.get("nfl") ?? "");
  const SORTS = ["points_per_game", "points", "games_played", "targets", "target_share", "carries", "carry_share", "passing_yards", "avg_offense_snap_pct"];
  const sort = $derived(SORTS.includes(params.get("sort") ?? "") ? params.get("sort")! : "points");
  const dir = $derived(params.get("dir") === "asc" ? "asc" : "desc");
  let q = $state(new URLSearchParams(location.search).get("q") ?? "");
  let limit = $state(50);

  const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/[^a-z0-9 ]/g, "");
  const filtered = $derived.by(() => {
    const needle = norm(q.trim());
    const xs = (r.data?.players ?? []).filter(
      (p) =>
        (position === "ALL" || p.position === position) &&
        (!nfl || teamLabel(p.team) === nfl || p.team === nfl) &&
        whoFilter(who, team)(p) &&
        (!needle || norm(p.player_name).includes(needle)),
    );
    const key = sort as keyof SeasonRow;
    const sign = dir === "asc" ? 1 : -1;
    return [...xs].sort((a, b) => {
      const av = a[key] as number | null;
      const bv = b[key] as number | null;
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      return (av - bv) * sign;
    });
  });
  const shown = $derived(filtered.slice(0, limit));
  const leader = $derived([...filtered].sort((a, b) => (b.points ?? -1) - (a.points ?? -1))[0] ?? null);

  const columns = $derived<Column[]>([
    { key: "player", label: "Player" },
    { key: "points_per_game", label: "Pts/g", align: "right", sortable: true, width: "4.25rem" },
    { key: "points", label: "Pts", align: "right", sortable: true, width: "4rem" },
    { key: "games_played", label: "G", align: "right", sortable: true, phone: false, width: "3rem" },
    ...(position === "QB"
      ? [{ key: "passing_yards", label: "Pass yds", align: "right" as const, sortable: true, phone: false, width: "5.5rem" }]
      : [
          { key: "targets", label: "Tgt", align: "right" as const, sortable: true, phone: false, width: "3.5rem" },
          { key: "target_share", label: "Tgt %", align: "right" as const, sortable: true, phone: false, width: "4.25rem" },
          { key: "carries", label: "Car", align: "right" as const, sortable: true, phone: false, width: "3.5rem" },
        ]),
    { key: "avg_offense_snap_pct", label: "Snap %", align: "right", sortable: true, phone: false, width: "4.5rem" },
    { key: "owner", label: "Team in league", phone: false, width: "10rem" },
  ]);

  function onsort(k: string) {
    setParams({ sort: k, dir: k === sort && dir === "desc" ? "asc" : "desc" });
  }
  let timer: ReturnType<typeof setTimeout> | undefined;
  function onq() {
    clearTimeout(timer);
    timer = setTimeout(() => setParams({ q: q.trim() || null }), 250);
  }
</script>

<main class="space-y-4" data-testid="players">
  <ScreenHead eyebrow="Research · Players" title={r.data ? `Every player, ${r.data.season}` : "Every player"}>
    {#snippet answer()}
      {#if leader}
        <span data-testid="players-answer"
          ><strong>Most points: {leader.player_name}, {fmt.pts(leader.points)}</strong> ({fmt.pts(leader.points_per_game)} a game) in {leagueName} scoring · {filtered.length}
          player{filtered.length === 1 ? "" : "s"}.</span
        >
      {:else if r.data}
        No player matches these filters.
      {/if}
    {/snippet}
  </ScreenHead>

  <div class="space-y-2.5">
    <label class="sr-only" for="ll-players-q">Find a player</label>
    <input id="ll-players-q" class="ll-input w-full" type="search" placeholder="Find a player" autocomplete="off" bind:value={q} oninput={onq} data-testid="players-search" />
    <div class="flex flex-wrap items-center gap-2">
      <Chips
        label="Position"
        testid="pos"
        current={position}
        onpick={(p) => setParams({ position: p === "ALL" ? null : p })}
        items={["ALL", "QB", "RB", "WR", "TE"].map((p) => ({ key: p, label: p === "ALL" ? "All" : p }))}
      />
      <Chips
        label="Whose"
        testid="who"
        current={who}
        onpick={(w) => setParams({ who: w === "all" ? null : w })}
        items={[
          { key: "all", label: "Everyone" },
          { key: "mine", label: "Yours" },
          { key: "fa", label: "Free agents" },
          { key: "rostered", label: "Rostered" },
        ]}
      />
      <label class="sr-only" for="ll-players-nfl">NFL team</label>
      <select id="ll-players-nfl" class="ll-input py-1.5 text-sm" value={nfl} onchange={(e) => setParams({ nfl: e.currentTarget.value || null })} data-testid="players-team">
        <option value="">Every NFL team</option>
        {#each Object.keys(TEAMS).map((k) => teamLabel(k)!).sort() as t (t)}<option value={t}>{t}</option>{/each}
      </select>
    </div>
  </div>

  {#if r.error}
    <p class="ll-error">{r.error}</p>
  {:else if !r.data}
    <div class="space-y-2" aria-label="Loading" data-testid="loading">{#each [0, 1, 2, 3, 4, 5] as i (i)}<div class="ll-skel h-12"></div>{/each}</div>
  {:else}
    <Table
      rows={shown}
      {columns}
      rowKey={(p) => p.gsis_id}
      {sort}
      {dir}
      {onsort}
      highlight={(p) => team !== null && p.rostered_by_roster_id === team}
      testid="players-table"
    >
      {#snippet cell(p, key)}
        {#if key === "player"}
          <div class="flex min-w-0 items-center gap-2.5">
            <Headshot url={p.headshot_url} name={p.player_name} team={p.team} size={34} />
            <div class="min-w-0">
              <a class="ll-name block truncate font-semibold" href={withContext(`/player/${p.gsis_id}`, ctx)}>{p.player_name}</a>
              <div class="mt-0.5 flex items-center gap-1"><PosBadge pos={p.position} /><TeamBadge team={p.team} /></div>
            </div>
          </div>
        {:else if key === "points_per_game"}<span class="font-bold">{fmt.pts(p.points_per_game)}</span>
        {:else if key === "points"}{fmt.pts(p.points)}
        {:else if key === "target_share"}{fmt.pct(p.target_share)}
        {:else if key === "avg_offense_snap_pct"}{fmt.pct(p.avg_offense_snap_pct)}
        {:else if key === "owner"}<span class="block truncate text-sm text-ink-2">{ownerWord(p, team)}</span>
        {:else}{(p[key as keyof SeasonRow] as number | null) ?? "—"}
        {/if}
      {/snippet}
    </Table>
    {#if filtered.length > shown.length}
      <button type="button" class="w-full rounded-md border border-line py-3 text-sm font-semibold text-accent" onclick={() => (limit += 100)} data-testid="more"
        >Show {Math.min(100, filtered.length - shown.length)} more of {filtered.length - shown.length}</button
      >
    {/if}
    <Expander title="How to read this" testid="howto">
      <div class="text-base leading-snug">
        <Md
          block
          text={`- Season totals for every player, points in ${leagueName} scoring. Tap a column to sort by it; tap a name for his card.\n` +
            "- **Tgt %** is his share of his team's targets in the games he played: a player who missed games is not marked down for it. **Snap %** counts every play, runs included.\n" +
            "- A dash means the number could not be worked out (no targets, no snaps recorded), never zero."}
        />
      </div>
    </Expander>
  {/if}
</main>
