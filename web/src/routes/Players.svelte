<script lang="ts">
  // Players · Stats (Wave I-I, II-3; the fifth review § 4): every skill player's numbers over the window you pick, in
  // one sortable table with position presets (WR / TE, RB, QB — Receivers is the WR / TE preset now), whose players
  // (everyone / yours / free agents / other teams), NFL team, search, the window (season / last 3 or 5 games played /
  // last 3 or 5 calendar weeks / a week range), totals or per game, minimum games, a column picker fed by the API's
  // column catalogue (definitions, denominators, status: a column the app does not have is offered disabled, with the
  // reason), a sticky player column and header, saved views on this browser, and 2–4 players side by side.
  // GET /api/players?window=… (one call per position group and window; the rest runs on the phone: instant).
  // Unknown is — with the reason on hover, never 0. Sorting runs over the full filtered set before "Show more".
  // ---- IM-2 (Wave I-M): two views one tap apart — "Key stats" (the preset's columns) and "Full table" (every column
  // for the position that we have, under group headers; components/stats/) — group toggles, every player ("Showing 50
  // of 291 — Show all"), Download CSV (GET /api/players.csv, or built here when the API has no such route).
  import { statsCsvPath, statsPath, type StatsColumn, type StatsFrame, type StatsRow } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import { ownerWord } from "../lib/research";
  import { Remote } from "../lib/remote.svelte";
  import { route, setParams } from "../lib/router.svelte";
  import { fmt, TEAMS, teamLabel } from "../lib/theme";
  import { APP_NAME } from "../lib/brand";
  import Chips from "../components/Chips.svelte";
  import Expander from "../components/Expander.svelte";
  import Md from "../components/Md.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import Tabs from "../components/Tabs.svelte";
  import ErrorCard from "../components/ErrorCard.svelte"; // ---- IH-1: the API down / a 500 / still waiting
  import StatsTable from "../components/stats/StatsTable.svelte"; // ---- IM-2
  import { csv, field as fieldOf, fullColumns, groupOf, show as showOf, title as titleOf, why as whyOf, type Mode, type PosGroup } from "../components/stats/columns"; // ---- IM-2
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
  const group = $derived<PosGroup>(fetchPos === "WR,TE" ? "wrte" : position === "RB" ? "rb" : position === "QB" ? "qb" : "all");
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
  const mode = $derived<Mode>(params.get("mode") === "total" ? "total" : "game");
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
  const keyCols = $derived<StatsColumn[]>((picked.length ? picked : defaults).map((c) => cat.get(c)).filter((c): c is StatsColumn => !!c));
  const offered = $derived(
    (r.data?.catalogue ?? []).filter((c) => c.id !== "games" && c.positions.some((p) => (fetchPos === "ALL" ? true : fetchPos.split(",").includes(p)))),
  );

  // ---- IM-2: the two views. `view=` in the URL (a tap writes it: shareable, kept by a saved view); without it the view
  // last picked on this device, else Full table from 900 px and Key stats on a phone (the PO's call).
  const remembered = accountPrefs.statsTable();
  const wideAtOpen = typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(min-width: 900px)").matches;
  const view = $derived<"key" | "full">(params.get("view") === "full" ? "full" : params.get("view") === "key" ? "key" : (remembered ?? (wideAtOpen ? "full" : "key")));
  function setView(v: string) {
    const next = v === "full" ? "full" : "key";
    setParams({ view: next });
    accountPrefs.setStatsTable(next);
  }
  // the Full table: the answer's `full` list (IM-1) or every available column for the position, grouped; minus the
  // groups toggled off (`hide=`, group names) and the columns unticked in the picker (`off=`, column ids)
  const fullPositions = $derived(fetchPos === "ALL" ? [] : position === "WR" || position === "TE" ? [position] : fetchPos.split(","));
  const fullAll = $derived(r.data ? fullColumns(r.data.catalogue, preset, fullPositions, group) : []);
  const hidden = $derived((params.get("hide") ?? "").split(",").filter(Boolean));
  const off = $derived((params.get("off") ?? "").split(",").filter(Boolean));
  const groupNames = $derived([...new Set(fullAll.map((c) => groupOf(c)))]);
  const fullCols = $derived(fullAll.filter((c) => !hidden.includes(groupOf(c)) && !off.includes(c.id)));
  const cols = $derived<StatsColumn[]>(view === "full" ? fullCols : keyCols);
  function toggleGroup(g: string) {
    const next = hidden.includes(g) ? hidden.filter((x) => x !== g) : [...hidden, g];
    setParams({ hide: next.length ? next.join(",") : null });
  }
  // ---- end IM-2
  const field = (c: StatsColumn) => fieldOf(c, mode);
  const title = (c: StatsColumn) => titleOf(c, mode);

  const sortKey = $derived(params.get("sort") ?? preset?.sort ?? "points");
  const sortCol = $derived(cat.get(sortKey) ?? cat.get(sortKey.replace(/_per_game$/, "")) ?? null);
  const dir = $derived(params.get("dir") === "asc" ? "asc" : "desc");

  let q = $state(new URLSearchParams(location.search).get("q") ?? "");
  const PAGE = 50; // ---- IM-2: the first 50, then "Show all" (every row of the answer: the frame carries up to 1000)
  let showAll = $state(false);
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
  // a new set or filter starts at the top of the list again (the first 50)
  $effect(() => {
    void [path, position, who, nfl, minGames, minOpp];
    showAll = false;
  });

  // ---- IM-2: a cell's text and its reason / sample (components/stats/columns.ts, shared with the table)
  const show = (c: StatsColumn, p: StatsRow) => showOf(c, p, mode);
  const why = (c: StatsColumn, p: StatsRow) => whyOf(c, p, mode);

  function onsort(c: StatsColumn) {
    setParams({ sort: c.id, dir: c.id === sortCol?.id && dir === "desc" ? "asc" : "desc" });
  }
  let timer: ReturnType<typeof setTimeout> | undefined;
  function onq() {
    clearTimeout(timer);
    timer = setTimeout(() => setParams({ q: q.trim() || null }), 250);
  }
  // ---- IM-2: a search typed just before leaving the screen is never written onto the next page's address
  $effect(() => () => clearTimeout(timer));
  function toggleCol(id: string) {
    // ---- IM-2: in the Full table a tick shows / hides one column (`off=`; a column of a hidden group shows its group)
    if (view === "full") {
      const c = cat.get(id);
      if (cols.some((x) => x.id === id)) setParams({ off: [...off, id].join(",") });
      else {
        const nextOff = off.filter((x) => x !== id);
        const g = c ? groupOf(c) : null;
        setParams({ off: nextOff.length ? nextOff.join(",") : null, ...(g && hidden.includes(g) ? { hide: hidden.filter((x) => x !== g).join(",") || null } : {}) });
      }
      return;
    }
    const now = keyCols.map((c) => c.id);
    const next = now.includes(id) ? now.filter((x) => x !== id) : [...now, id];
    setParams({ cols: next.join(",") === defaults.join(",") ? null : next.join(",") });
  }

  // ---- IM-2: ownership columns only when the answer has them (a reference league — IM-3's `ref:` keys — has none)
  const owned = $derived(!r.data || r.data.players.length === 0 || r.data.players.some((p) => "rostered_by_roster_id" in p));
  const ownerOf = (p: StatsRow) => ownerWord(p, team);
  const mine = (p: StatsRow) => team !== null && p.rostered_by_roster_id === team;
  const href = (p: StatsRow) => withContext(`/player/${p.gsis_id}`, ctx);

  // ---- IM-2: Download CSV — GET /api/players.csv with the screen's parameters (IM-1's route); when this server has no
  // such route (404) the file is built here from the table's rows (every filtered row, the columns on screen)
  const winKey = $derived(win === "last3w" ? "last3" : win === "last5w" ? "last5" : win);
  const csvHref = $derived(
    statsCsvPath(league, {
      position: fetchPos,
      window: winKey,
      basis: win === "last3w" || win === "last5w" ? "weeks" : win === "last3" || win === "last5" ? "games" : undefined,
      weeks: win === "weeks" ? `${range[0]}-${range[1]}` : undefined,
      sort: sortCol?.id ?? "points",
      dir,
      cols: cols.map((c) => c.id),
      mode,
      who,
      team,
      nfl,
      q: q.trim(),
      min: minGames,
    }),
  );
  const fileName = $derived(
    `${APP_NAME}-stats-${r.data?.season ?? ""}-${win === "weeks" ? `weeks-${range[0]}-${range[1]}` : win}-${(POS.find((x) => x.key === position)?.label ?? "all").toLowerCase().replace(/[^a-z]+/g, "-")}${view === "full" ? "-full" : ""}.csv`.replace(/-+/g, "-"),
  );
  let csvBusy = $state(false);
  let csvFrom = $state<"server" | "browser" | null>(null);
  let csvRoute: boolean | null = null; // null: not asked yet; false: this server answered 404
  function save(blob: Blob, name: string) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }
  async function downloadCsv(e: MouseEvent) {
    if (e.metaKey || e.ctrlKey || e.shiftKey) return; // a modified click: the browser follows the link itself
    e.preventDefault();
    if (csvBusy) return;
    csvBusy = true;
    try {
      if (csvRoute !== false) {
        try {
          const res = await fetch(csvHref, { credentials: "same-origin", headers: { Accept: "text/csv" } });
          if (res.ok && /csv/i.test(res.headers.get("content-type") ?? "")) {
            csvRoute = true;
            const name = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? fileName;
            save(await res.blob(), decodeURIComponent(name));
            csvFrom = "server";
            return;
          }
          if (res.status === 404) csvRoute = false;
        } catch {
          /* no answer: build it here */
        }
      }
      save(new Blob([csv(filtered, cols, mode, owned ? ownerOf : undefined)], { type: "text/csv;charset=utf-8" }), fileName);
      csvFrom = "browser";
    } finally {
      csvBusy = false;
    }
  }
  // ---- end IM-2

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
    const clear = Object.fromEntries(["position", "who", "nfl", "window", "weeks", "mode", "min", "minopp", "cols", "sort", "dir", "q", "view", "hide", "off"].map((k) => [k, null])); // ---- IM-2: + view, hide, off
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
          ({leader.games} game{leader.games === 1 ? "" : "s"}{cols.some((c) => c.id === "receiving_yards") && sortCol.id !== "receiving_yards" && (leader.position === "WR" || leader.position === "TE")
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
    {#if owned}<!-- ---- IM-2: no ownership in the answer (a reference league): no "whose" chips -->
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
    {/if}
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
    <!-- ---- IM-2: the view (Key stats · Full table), the CSV, the group toggles, the table, every player -->
    <div class="flex flex-wrap items-center gap-x-3 gap-y-2" data-testid="stats-toolbar">
      <Tabs
        items={[
          { key: "key", label: "Key stats" },
          { key: "full", label: "Full table" },
        ]}
        current={view}
        onpick={setView}
        size="sm"
        label="Table view"
        testid="stats-table-view"
      />
      <span class="text-sm text-ink-2" data-testid="stats-col-count">{cols.length} column{cols.length === 1 ? "" : "s"}</span>
      <a
        class="ml-auto inline-flex min-h-9 items-center gap-1 rounded-md border border-line px-2.5 text-sm font-semibold text-accent {csvBusy ? 'opacity-60' : ''}"
        href={csvHref}
        download={fileName}
        onclick={downloadCsv}
        aria-busy={csvBusy}
        data-from={csvFrom ?? undefined}
        data-testid="stats-csv"><span aria-hidden="true">↓</span> Download CSV</a
      >
    </div>
    {#if view === "full" && groupNames.length > 1}
      <div class="ll-chiprow">
        <div class="flex flex-wrap gap-1.5" role="group" aria-label="Column groups: tap to hide or show" data-testid="stats-groups">
          {#each groupNames as g (g)}
            {@const on = !hidden.includes(g)}
            <button
              type="button"
              class="inline-flex min-h-8 items-center gap-1 rounded-full border px-2.5 text-sm font-semibold {on ? 'border-accent/60 bg-accent-soft text-ink' : 'border-dashed border-line-strong text-ink-3'}"
              aria-pressed={on}
              onclick={() => toggleGroup(g)}
              data-testid="stats-group"
              data-group={g}><span aria-hidden="true" class="text-xs">{on ? "✓" : "+"}</span>{g}</button
            >
          {/each}
        </div>
      </div>
    {/if}
    {#if cols.length === 0}
      <p class="ll-empty" data-testid="stats-no-cols">Every column group is hidden. Tap a group above to show its columns.</p>
    {/if}
    {#key view}
      <StatsTable
        rows={filtered}
        {cols}
        grouped={view === "full"}
        {mode}
        limit={showAll ? Infinity : PAGE}
        sortId={sortCol?.id ?? null}
        {dir}
        {onsort}
        {href}
        {mine}
        {sel}
        onselect={toggleSel}
        owner={owned ? ownerOf : null}
        caption={`${POS.find((x) => x.key === position)?.label ?? "All"} players, ${r.data.window.label}: ${view === "full" ? "full table" : "key stats"}${sortCol ? `, sorted by ${title(sortCol).toLowerCase()}` : ""}`}
        dim={r.loading}
      />
    {/key}
    <div class="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-ink-2" data-testid="stats-count">
      <span data-testid="stats-showing">Showing {Math.min(showAll ? filtered.length : PAGE, filtered.length)} of {filtered.length}</span>
      {#if !showAll && filtered.length > PAGE}
        <button type="button" class="inline-flex min-h-9 items-center rounded-md border border-line px-3 font-semibold text-accent" onclick={() => (showAll = true)} data-testid="stats-show-all"
          >Show all {filtered.length}</button
        >
      {:else if showAll && filtered.length > PAGE}
        <button type="button" class="inline-flex min-h-9 items-center rounded-md border border-line px-3 font-semibold text-accent" onclick={() => (showAll = false)} data-testid="stats-show-fewer"
          >Show the first {PAGE}</button
        >
      {/if}
    </div>
    <Expander title="How to read this" testid="howto">
      <div class="space-y-2 text-base leading-snug">
        <Md
          block
          text={r.data.howto +
            `\n- Points are in ${leagueName} scoring. Tap a column to sort by it; tap a name for his card; tick 2–4 players to see them side by side.` +
            `\n- **Key stats** are the numbers to read first. **Full table** shows every column we have for the position, grouped (Receiving, Air yards, Red zone…): tap a group above the table to hide or show it. A greyed number rests on a small sample: tap it, or a dash, for the reason.`}
        />
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
  /* ---- IM-2: the table's own styles live in components/stats/StatsTable.svelte */
</style>
