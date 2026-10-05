<script lang="ts">
  // Players · Stats (Wave I-I, II-3; the fifth review § 4): every skill player's numbers over the window you pick, in
  // one sortable table with position presets (WR / TE, RB, QB — Receivers is the WR / TE preset now), whose players
  // (everyone / yours / free agents / other teams), NFL team, search, the window (season / last 3 or 5 games played /
  // last 3 or 5 calendar weeks / a week range), totals or per game, minimum games, a column picker fed by the API's
  // column catalogue (definitions, denominators, status: a column the app does not have is offered disabled, with the
  // reason), a sticky player column and header, saved views on this browser, and 2–4 players side by side.
  // GET /api/players?window=… (one call per position group and window; the rest runs on the phone: instant).
  // Unknown is — with the reason on hover, never 0. Sorting runs over the full filtered set before "Show more".
  import { statsPath, type StatsColumn, type StatsFrame, type StatsRow } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import { ownerWord } from "../lib/research";
  import { Remote } from "../lib/remote.svelte";
  import { paneLink } from "../lib/pane.svelte"; // ---- IB-1: a name opens the research pane
  import { route, setParams } from "../lib/router.svelte";
  import { fmt, TEAMS, teamLabel } from "../lib/theme";
  import Chips from "../components/Chips.svelte";
  import Expander from "../components/Expander.svelte";
  import Headshot from "../components/Headshot.svelte";
  import Md from "../components/Md.svelte";
  import PosBadge from "../components/PosBadge.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import ErrorCard from "../components/ErrorCard.svelte"; // ---- IH-1: the API down / a 500 / still waiting
  import TeamBadge from "../components/TeamBadge.svelte";
  import { accountPrefs, type StatsView } from "../lib/prefs"; // ---- IK-4: the saved views through prefs (an account keeps them)

  let { options, league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  const params = $derived(route.current.params);
  const ctx = $derived({ league, team });
  const leagueName = $derived(options.find((o) => o.league_id === league)?.name ?? "this league");

  // ---- the URL's state (a shared link reopens the same view)
  type Pos = "ALL" | "WRTE" | "WR" | "TE" | "RB" | "QB";
  const POS: { key: Pos; label: string }[] = [
    { key: "ALL", label: "All" },
    { key: "WRTE", label: "WR / TE" },
    { key: "WR", label: "WR" },
    { key: "TE", label: "TE" },
    { key: "RB", label: "RB" },
    { key: "QB", label: "QB" },
  ];
  const position = $derived.by<Pos>(() => {
    const p = (params.get("position") ?? "").toUpperCase().replace(/[^A-Z]/g, "");
    return (POS.some((x) => x.key === p) ? p : "ALL") as Pos;
  });
  const fetchPos = $derived(position === "WR" || position === "TE" || position === "WRTE" ? "WR,TE" : position);
  const group = $derived<"wrte" | "rb" | "qb" | "all">(fetchPos === "WR,TE" ? "wrte" : position === "RB" ? "rb" : position === "QB" ? "qb" : "all");
  type Who = "all" | "mine" | "fa" | "others";
  const who = $derived((["all", "mine", "fa", "others"].includes(params.get("who") ?? "") ? params.get("who") : params.get("who") === "rostered" ? "others" : "all") as Who);
  const nfl = $derived(params.get("nfl") ?? "");
  const WINDOWS = [
    { key: "season", label: "Season" },
    { key: "last3", label: "Last 3 games played" },
    { key: "last5", label: "Last 5 games played" },
    { key: "last3w", label: "Last 3 calendar weeks" },
    { key: "last5w", label: "Last 5 calendar weeks" },
    { key: "weeks", label: "Week range (calendar)" },
  ];
  const win = $derived(WINDOWS.some((w) => w.key === params.get("window")) ? params.get("window")! : "season");
  const range = $derived.by<[number, number]>(() => {
    const m = (params.get("weeks") ?? "").match(/^(\d{1,2})-(\d{1,2})$/);
    return m ? [Number(m[1]), Number(m[2])] : [1, 18];
  });
  const mode = $derived(params.get("mode") === "total" ? "total" : "game");
  const minGames = $derived(Math.max(1, Number(params.get("min") ?? "1") || 1));
  // opportunities = targets + carries (+ pass attempts for a quarterback) in the window
  const minOpp = $derived(Math.max(0, Number(params.get("minopp") ?? "0") || 0));
  const opps = (p: StatsRow) => (num(p.targets) ?? 0) + (num(p.carries) ?? 0) + (p.position === "QB" ? (num(p.attempts) ?? 0) : 0);

  const r = new Remote<StatsFrame>();
  const path = $derived(
    statsPath(league, {
      position: fetchPos,
      window: win === "last3w" ? "last3" : win === "last5w" ? "last5" : win,
      basis: win === "last3w" || win === "last5w" ? "weeks" : win === "last3" || win === "last5" ? "games" : undefined,
      weeks: win === "weeks" ? `${range[0]}-${range[1]}` : undefined,
    }),
  );
  $effect(() => r.load(path, onauth, true));

  // ---- the columns: the preset's defaults, or the URL's pick (the column picker)
  const cat = $derived(new Map((r.data?.catalogue ?? []).map((c) => [c.id, c])));
  const ALL_COLS = ["games", "points", "targets", "target_share", "carries", "carry_share", "snap_share"];
  const preset = $derived(r.data?.presets.find((p) => p.key === group) ?? null);
  const defaults = $derived(preset ? preset.columns : ALL_COLS);
  const picked = $derived((params.get("cols") ?? "").split(",").filter((c) => c && cat.has(c)));
  const cols = $derived<StatsColumn[]>((picked.length ? picked : defaults).map((c) => cat.get(c)).filter((c): c is StatsColumn => !!c));
  const offered = $derived(
    (r.data?.catalogue ?? []).filter((c) => c.id !== "games" && c.positions.some((p) => (fetchPos === "ALL" ? true : fetchPos.split(",").includes(p)))),
  );
  const field = (c: StatsColumn) => (c.per_game && mode === "game" ? `${c.id}_per_game` : c.id);
  const head = (c: StatsColumn) => (c.per_game && mode === "game" ? `${c.short}/G` : c.short);
  const title = (c: StatsColumn) => (c.per_game && mode === "game" ? `${c.label} per game` : c.label);

  const sortKey = $derived(params.get("sort") ?? preset?.sort ?? "points");
  const sortCol = $derived(cat.get(sortKey) ?? cat.get(sortKey.replace(/_per_game$/, "")) ?? null);
  const dir = $derived(params.get("dir") === "asc" ? "asc" : "desc");

  let q = $state(new URLSearchParams(location.search).get("q") ?? "");
  let limit = $state(50);
  const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/[^a-z0-9 ]/g, "");
  const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

  const filtered = $derived.by(() => {
    const needle = norm(q.trim());
    const xs = (r.data?.players ?? []).filter(
      (p) =>
        (position === "WR" || position === "TE" ? p.position === position : true) &&
        (who === "all" ||
          (who === "mine" && team !== null && p.rostered_by_roster_id === team) ||
          (who === "fa" && p.rostered_by_roster_id === null) ||
          (who === "others" && p.rostered_by_roster_id !== null && p.rostered_by_roster_id !== team)) &&
        (!nfl || teamLabel(p.team) === nfl || p.team === nfl) &&
        (p.games ?? 0) >= minGames &&
        (minOpp === 0 || opps(p) >= minOpp) &&
        (!needle || norm(p.player_name).includes(needle)),
    );
    const key = sortCol ? field(sortCol) : "points";
    const sign = dir === "asc" ? 1 : -1;
    // the whole filtered set is sorted before the page is cut ("Show more" never hides a better row)
    return [...xs].sort((a, b) => {
      const av = num(a[key]);
      const bv = num(b[key]);
      if (av === null && bv === null) return a.player_name.localeCompare(b.player_name);
      if (av === null) return 1;
      if (bv === null) return -1;
      return (av - bv) * sign || a.player_name.localeCompare(b.player_name);
    });
  });
  const shown = $derived(filtered.slice(0, limit));
  // a new set or filter starts at the top of the list again
  $effect(() => {
    void [path, position, who, nfl, minGames, minOpp];
    limit = 50;
  });

  function show(c: StatsColumn, p: StatsRow): string {
    const v = num(p[field(c)]);
    if (v === null) return "—";
    if (c.format === "pct") return fmt.pct(v, 1);
    if (c.format === "pts" || c.format === "dec1") return fmt.pts(v, 1);
    if (c.format === "dec2") return fmt.pts(v, 2);
    return c.per_game && mode === "game" ? fmt.pts(v, 1) : fmt.whole(v);
  }
  /** the reason a cell is —, or the sample behind a number ("23 of 57 team carries in 2 games") */
  function why(c: StatsColumn, p: StatsRow): string {
    const v = num(p[field(c)]);
    if (v === null) return c.reason ?? "not available";
    const g = `${p.games} game${p.games === 1 ? "" : "s"}`;
    const n = (k: string) => num(p[k]);
    switch (c.id) {
      case "target_share":
        return `${n("targets")} of ${n("team_targets")} team targets in his ${g}`;
      case "carry_share":
        return `${n("carries")} of ${n("team_carries")} team carries in his ${g}`;
      case "rb_carry_share":
        return `${n("carries")} of ${n("team_rb_carries")} running-back carries in his ${g}`;
      case "first_read_target_share":
        return `${n("first_read_targets")} of ${n("team_first_read_targets")} charted first-read targets, ${n("charted_games")} charted games`;
      case "route_participation":
        return `${n("routes_proxy")} of ${n("team_dropbacks_with_participation")} dropbacks on the field (an estimate)`;
      case "snap_share":
        return `mean of ${n("snap_games")} games with snap counts`;
      // ---- IL-1: Next Gen Stats — the weeks NGS published of his games, and NGS's own denominator (the weight)
      case "time_to_throw":
      case "ngs_cpoe":
        return `NGS published ${n("ngs_pass_weeks")} of his ${g} (15+ pass attempts): ${n("ngs_pass_attempts")} attempts, weighted by attempts`;
      case "ryoe_per_attempt":
        return `NGS published ${n("ngs_rush_weeks")} of his ${g} (10+ carries): ${n("ngs_rush_attempts")} carries, weighted by carries`;
      case "separation":
        return `NGS published ${n("ngs_rec_weeks")} of his ${g} (5+ targets): ${n("ngs_targets")} targets, weighted by targets`;
      case "yac_over_expected":
        return `NGS published ${n("ngs_rec_weeks")} of his ${g} (5+ targets): ${n("ngs_receptions")} receptions, weighted by receptions`;
      // ---- end IL-1
      default:
        return c.per_game && mode === "game" ? `${c.label} ${fmt.whole(n(c.id))} in ${g}` : `${c.label}: ${g}`;
    }
  }

  function onsort(c: StatsColumn) {
    setParams({ sort: c.id, dir: c.id === sortCol?.id && dir === "desc" ? "asc" : "desc" });
  }
  let timer: ReturnType<typeof setTimeout> | undefined;
  function onq() {
    clearTimeout(timer);
    timer = setTimeout(() => setParams({ q: q.trim() || null }), 250);
  }
  function toggleCol(id: string) {
    const now = cols.map((c) => c.id);
    const next = now.includes(id) ? now.filter((x) => x !== id) : [...now, id];
    setParams({ cols: next.join(",") === defaults.join(",") ? null : next.join(",") });
  }

  // ---- saved views (this browser only; a per-viewer convenience)
  // ---- IK-4: read and written through lib/prefs.ts (`ll.stats.views`, unchanged) so a signed-in account keeps them too
  type View = StatsView;
  const readViews = (): View[] => accountPrefs.statsViews();
  let views = $state<View[]>(readViews());
  let viewName = $state("");
  function saveView() {
    // eslint-disable-next-line svelte/prefer-svelte-reactivity -- a scratch copy of the address, never observed
    const keep = new URLSearchParams(location.search);
    keep.delete("league");
    keep.delete("team");
    keep.delete("sel");
    const name = viewName.trim() || `${POS.find((x) => x.key === position)?.label} · ${WINDOWS.find((w) => w.key === win)?.label}`;
    views = [...views.filter((v) => v.name !== name), { name, qs: keep.toString() }].slice(-8);
    viewName = "";
    accountPrefs.setStatsViews(views); // ---- IK-4 (a private window: the view stays for this visit)
  }
  function openView(v: View) {
    const want = Object.fromEntries(new URLSearchParams(v.qs));
    const clear = Object.fromEntries(["position", "who", "nfl", "window", "weeks", "mode", "min", "minopp", "cols", "sort", "dir", "q"].map((k) => [k, null]));
    setParams({ ...clear, ...want });
    q = want.q ?? "";
  }
  function dropView(v: View) {
    views = views.filter((x) => x.name !== v.name);
    accountPrefs.setStatsViews(views); // ---- IK-4
  }

  // ---- 2–4 players side by side
  const sel = $derived((params.get("sel") ?? "").split(",").filter(Boolean).slice(0, 4));
  function toggleSel(id: string) {
    const next = sel.includes(id) ? sel.filter((x) => x !== id) : sel.length >= 4 ? sel : [...sel, id];
    setParams({ sel: next.length ? next.join(",") : null });
  }
  const selected = $derived(sel.map((id) => r.data?.players.find((p) => p.gsis_id === id)).filter((p): p is StatsRow => !!p));
  const leader = $derived(filtered[0] ?? null);
  const weeksMax = $derived(Math.max(r.data?.window.through_week ?? 18, 1));
</script>

<main class="space-y-4" data-testid="players">
  <ScreenHead eyebrow="Players · Stats" title={r.data ? `Stats, ${r.data.season}` : "Stats"}>
    {#snippet answer()}
      {#if leader && sortCol}
        <span data-testid="players-answer"
          ><strong>{dir === "asc" ? "Lowest" : "Highest"} {title(sortCol).toLowerCase()}: {leader.player_name}, {show(sortCol, leader)}</strong>
          ({leader.games} game{leader.games === 1 ? "" : "s"}{cols.some((c) => c.id === "receiving_yards") && sortCol.id !== "receiving_yards"
            ? `, ${fmt.pts(num(leader.receiving_yards_per_game))} receiving yards per game`
            : ""}) · {filtered.length} player{filtered.length === 1 ? "" : "s"} · {r.data?.window.label}.</span
        >
      {:else if r.data}
        No player matches these filters.
      {/if}
    {/snippet}
  </ScreenHead>

  <div class="space-y-2.5">
    <label class="sr-only" for="ll-players-q">Find a player</label>
    <input id="ll-players-q" class="ll-input w-full" type="search" placeholder="Find a player" autocomplete="off" bind:value={q} oninput={onq} data-testid="players-search" />
    <!-- on a phone each chip row scrolls sideways inside itself (the page never does); from 640 px they wrap -->
    <div class="ll-chiprow">
      <Chips
        label="Position"
        testid="pos"
        current={position}
        onpick={(p) => setParams({ position: p === "ALL" ? null : p, cols: null, sort: null, dir: null })}
        items={POS}
      />
    </div>
    <div class="ll-chiprow">
      <Chips
        label="Whose"
        testid="who"
        current={who}
        onpick={(w) => setParams({ who: w === "all" ? null : w })}
        items={[
          { key: "all", label: "Everyone" },
          { key: "mine", label: "Yours" },
          { key: "fa", label: "Free agents" },
          { key: "others", label: "Other teams" },
        ]}
      />
    </div>
    <div class="flex flex-wrap items-center gap-2" data-testid="stats-window">
      <label class="sr-only" for="ll-players-nfl">NFL team</label>
      <select id="ll-players-nfl" class="ll-input min-w-0 flex-1 py-1.5 text-sm sm:flex-none" value={nfl} onchange={(e) => setParams({ nfl: e.currentTarget.value || null })} data-testid="players-team">
        <option value="">Every NFL team</option>
        {#each Object.keys(TEAMS).map((k) => teamLabel(k)!).sort() as t (t)}<option value={t}>{t}</option>{/each}
      </select>
      <label class="sr-only" for="ll-stats-window">Window</label>
      <select id="ll-stats-window" class="ll-input min-w-0 flex-1 py-1.5 text-sm sm:flex-none" value={win} onchange={(e) => setParams({ window: e.currentTarget.value === "season" ? null : e.currentTarget.value })} data-testid="stats-window-pick">
        {#each WINDOWS as w (w.key)}<option value={w.key}>{w.label}</option>{/each}
      </select>
      {#if win === "weeks"}
        <span class="flex items-center gap-1.5">
          <label class="text-sm text-ink-2" for="ll-stats-lo">Weeks</label>
          <select id="ll-stats-lo" class="ll-input py-1.5 text-sm" value={range[0]} onchange={(e) => setParams({ weeks: `${Math.min(Number(e.currentTarget.value), range[1])}-${range[1]}` })} data-testid="stats-weeks-lo">
            {#each Array.from({ length: weeksMax }, (_, i) => i + 1) as w (w)}<option value={w}>{w}</option>{/each}
          </select>
          <span class="text-sm text-ink-2">to</span>
          <select class="ll-input py-1.5 text-sm" aria-label="to week" value={Math.min(range[1], weeksMax)} onchange={(e) => setParams({ weeks: `${range[0]}-${Math.max(Number(e.currentTarget.value), range[0])}` })} data-testid="stats-weeks-hi">
            {#each Array.from({ length: weeksMax }, (_, i) => i + 1) as w (w)}<option value={w}>{w}</option>{/each}
          </select>
        </span>
      {/if}
      <span class="flex items-center gap-2">
        <Chips
          label="Totals or per game"
          testid="mode"
          current={mode}
          onpick={(m) => setParams({ mode: m === "game" ? null : m })}
          items={[
            { key: "game", label: "Per game" },
            { key: "total", label: "Totals" },
          ]}
        />
        <label class="text-sm whitespace-nowrap text-ink-2" for="ll-stats-min">Min. games</label>
        <select id="ll-stats-min" class="ll-input py-1.5 text-sm" value={minGames} onchange={(e) => setParams({ min: e.currentTarget.value === "1" ? null : e.currentTarget.value })} data-testid="stats-min">
          {#each [1, 2, 3, 4, 5, 8, 10] as n (n)}<option value={n}>{n}</option>{/each}
        </select>
      </span>
      <span class="flex items-center gap-2" title="targets + carries (+ pass attempts for a quarterback) in the window">
        <label class="text-sm whitespace-nowrap text-ink-2" for="ll-stats-minopp">Min. opportunities</label>
        <select id="ll-stats-minopp" class="ll-input py-1.5 text-sm" value={minOpp} onchange={(e) => setParams({ minopp: e.currentTarget.value === "0" ? null : e.currentTarget.value })} data-testid="stats-minopp">
          {#each [0, 5, 10, 20, 40, 80] as n (n)}<option value={n}>{n === 0 ? "any" : n}</option>{/each}
        </select>
      </span>
    </div>
    {#if r.data}
      <p class="text-sm text-ink-2" data-testid="stats-window-label">
        <strong>{r.data.window.label}</strong>{r.data.window.note ? ` · ${r.data.window.note}` : ""}{r.data.window.through_week
          ? ` · games through week ${r.data.window.through_week}`
          : ""}
      </p>
    {/if}
    <details class="rounded-md border border-line bg-surface px-3 py-2" data-testid="stats-columns">
      <summary class="cursor-pointer text-sm font-semibold text-accent">Columns ({cols.length}) and saved views</summary>
      <div class="mt-2 grid gap-1 sm:grid-cols-2">
        {#each offered as c (c.id)}
          <label class="flex items-start gap-2 text-sm {c.available ? '' : 'text-ink-3'}" title={c.available ? c.definition : (c.reason ?? c.definition)}>
            <input type="checkbox" class="mt-1" checked={cols.some((x) => x.id === c.id)} disabled={!c.available} onchange={() => toggleCol(c.id)} data-testid={`col-${c.id}`} />
            <span
              >{c.label}{#if !c.available}<span class="block text-xs" data-testid={`col-why-${c.id}`}>{c.status === "planned" ? "Planned" : "Not available"}: {c.reason}</span
                >{:else if c.status === "derived" && c.coverage}<span class="block text-xs text-ink-2">{c.coverage}</span>{/if}</span
            >
          </label>
        {/each}
      </div>
      <div class="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-2">
        <label class="sr-only" for="ll-stats-view">Name this view</label>
        <input id="ll-stats-view" class="ll-input py-1 text-sm" placeholder="Name this view" bind:value={viewName} data-testid="stats-view-name" />
        <button type="button" class="rounded-md border border-line px-2.5 py-1 text-sm font-semibold text-accent" onclick={saveView} data-testid="stats-view-save">Save view</button>
        {#each views as v (v.name)}
          <span class="inline-flex items-center rounded-full border border-line text-sm">
            <button type="button" class="px-2.5 py-1" onclick={() => openView(v)} data-testid="stats-view">{v.name}</button>
            <button type="button" class="px-1.5 py-1 text-ink-2" aria-label={`Forget ${v.name}`} onclick={() => dropView(v)}>×</button>
          </span>
        {/each}
      </div>
    </details>
    {#if group === "wrte"}
      <p class="text-sm"><a class="text-accent underline" href={withContext("/receivers?view=cards", ctx)} data-testid="role-cards">Receivers' role cards</a> <span class="text-ink-2">— usage by half, score, down, field zone and quarterback</span></p>
    {/if}
  </div>

  {#if selected.length}
    <section class="rounded-lg border border-line bg-surface p-3" data-testid="stats-compare">
      <div class="mb-2 flex flex-wrap items-center gap-2">
        <h2 class="text-base font-semibold">Side by side ({selected.length} of 4)</h2>
        {#if selected.length >= 2}
          <a class="text-sm text-accent underline" href={withContext(`/compare?a=${selected[0].gsis_id}&b=${selected[1].gsis_id}`, ctx)} data-testid="stats-open-compare"
            >Open {selected[0].player_name} and {selected[1].player_name} in Compare</a
          >
        {:else}<span class="text-sm text-ink-2">Pick one to four more.</span>{/if}
        <button type="button" class="ml-auto text-sm text-ink-2 underline" onclick={() => setParams({ sel: null })}>Clear</button>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm tabnum">
          <thead><tr><th class="py-1 text-left font-normal text-ink-2">{r.data?.window.label}</th>{#each selected as p (p.gsis_id)}<th class="px-2 py-1 text-right">{p.player_name}</th>{/each}</tr></thead>
          <tbody>
            <tr><td class="py-1 text-ink-2">Games</td>{#each selected as p (p.gsis_id)}<td class="px-2 text-right">{p.games}</td>{/each}</tr>
            {#each cols.filter((c) => c.id !== "games") as c (c.id)}
              <tr><td class="py-1 text-ink-2">{title(c)}</td>{#each selected as p (p.gsis_id)}<td class="px-2 text-right" title={why(c, p)}>{show(c, p)}</td>{/each}</tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>
  {/if}

  {#if r.error}
    <!-- ---- IH-1: a card with Try again for the API down / a 500 / Sleeper; a 404's own words stay a plain line -->
    {#if r.failure && r.failure.kind !== "notfound" && r.failure.kind !== "other"}<ErrorCard failure={r.failure} onretry={() => r.retry()} />{:else}<p class="ll-error">{r.error}</p>{/if}
  {:else if r.failure?.kind === "slow"}
    <ErrorCard failure={r.failure} onretry={() => r.retry()} /><!-- ---- IH-1: still waiting after 25 s -->
  {:else if !r.data}
    <div class="space-y-2" aria-label="Loading" data-testid="loading">{#each [0, 1, 2, 3, 4, 5] as i (i)}<div class="ll-skel h-12"></div>{/each}</div>
  {:else}
    <div class="ll-stats overflow-auto rounded-lg border border-line bg-surface {r.loading ? 'opacity-60' : ''}" style="box-shadow:var(--ll-shadow)" data-testid="stats-scroll">
      <table class="min-w-full border-collapse text-base" data-testid="players-table">
        <thead>
          <tr>
            <th class="ll-stick-x ll-label bg-raised px-2 py-2 pl-3 text-left" style="min-width:11rem">Player</th>
            {#each cols as c (c.id)}
              <th
                class="ll-label bg-raised px-2 py-2 text-right whitespace-nowrap"
                aria-sort={sortCol?.id === c.id ? (dir === "asc" ? "ascending" : "descending") : undefined}
                title={`${title(c)} — ${c.definition}${c.denominator ? ` Denominator: ${c.denominator}.` : ""}`}
              >
                <button type="button" class="inline-flex min-h-8 items-center gap-0.5 uppercase {sortCol?.id === c.id ? 'text-ink' : ''}" onclick={() => onsort(c)} data-testid={`sort-${c.id}`}
                  >{head(c)}<span aria-hidden="true" class="text-[9px]">{sortCol?.id === c.id ? (dir === "asc" ? "▲" : "▼") : ""}</span></button
                >
              </th>
            {/each}
            <th class="ll-label hidden bg-raised px-2 py-2 pr-3 text-left sm:table-cell">Team in league</th>
          </tr>
        </thead>
        <tbody>
          {#each shown as p (p.gsis_id)}
            <tr class="border-t border-line {team !== null && p.rostered_by_roster_id === team ? 'll-mine' : ''}" data-testid="players-table-row">
              <td class="ll-stick-x bg-surface py-2 pr-2 pl-3">
                <div class="flex min-w-0 items-center gap-2">
                  <input
                    type="checkbox"
                    class="shrink-0"
                    aria-label={`Select ${p.player_name} to compare`}
                    checked={sel.includes(p.gsis_id)}
                    disabled={!sel.includes(p.gsis_id) && sel.length >= 4}
                    onchange={() => toggleSel(p.gsis_id)}
                    data-testid="stats-select"
                  />
                  <Headshot url={p.headshot_url} name={p.player_name} team={p.team} size={30} />
                  <div class="min-w-0">
              <a
                class="ll-name block truncate font-semibold"
                href={withContext(`/player/${p.gsis_id}`, ctx)}
                {@attach paneLink(p.gsis_id, { from: "list", context: { name: p.player_name } })}>{p.player_name}</a
              >
                    <div class="mt-0.5 flex items-center gap-1"><PosBadge pos={p.position} /><TeamBadge team={p.team} /></div>
                  </div>
                </div>
              </td>
              {#each cols as c (c.id)}
                <td class="px-2 py-2 text-right tabnum whitespace-nowrap {num(p[field(c)]) === null ? 'text-ink-3' : ''}" title={why(c, p)} data-col={c.id}>{show(c, p)}</td>
              {/each}
              <td class="hidden px-2 py-2 pr-3 text-sm text-ink-2 sm:table-cell"><span class="block max-w-[10rem] truncate">{ownerWord(p, team)}</span></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    {#if filtered.length > shown.length}
      <button type="button" class="w-full rounded-md border border-line py-3 text-sm font-semibold text-accent" onclick={() => (limit += 100)} data-testid="more"
        >Show {Math.min(100, filtered.length - shown.length)} more of {filtered.length - shown.length}</button
      >
    {/if}
    <Expander title="How to read this" testid="howto">
      <div class="space-y-2 text-base leading-snug">
        <Md block text={r.data.howto + `\n- Points are in ${leagueName} scoring. Tap a column to sort by it; tap a name for his card; tick 2–4 players to see them side by side.`} />
        <dl class="space-y-1.5 text-sm" data-testid="stats-definitions">
          {#each cols as c (c.id)}
            <div><dt class="inline font-semibold">{title(c)}</dt> <dd class="inline text-ink-2">— {c.definition}{c.denominator ? ` Denominator: ${c.denominator}.` : ""} Source: {c.source}.</dd></div>
          {/each}
        </dl>
      </div>
    </Expander>
  {/if}
</main>

<style>
  @media (max-width: 639px) {
    .ll-chiprow :global([role="group"]) {
      flex-wrap: nowrap;
      overflow-x: auto;
      scrollbar-width: none;
    }
    .ll-chiprow :global([role="group"] > button) {
      flex-shrink: 0;
    }
  }
  /* the table scrolls inside its box (never the page): the header row and the player column stay put */
  .ll-stats {
    max-height: 75vh;
    max-width: 100%;
  }
  .ll-stats thead th {
    position: sticky;
    top: 0;
    z-index: 2;
  }
  .ll-stats .ll-stick-x {
    position: sticky;
    left: 0;
    z-index: 1;
    max-width: 13rem;
  }
  .ll-stats thead .ll-stick-x {
    z-index: 3;
  }
  .ll-stats tr.ll-mine td {
    background: linear-gradient(var(--color-accent-soft), var(--color-accent-soft)), var(--color-surface);
  }
</style>
