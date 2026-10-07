<script lang="ts">
  // ---- IM-5 (Wave I-M): DFS — values, undervalued players and lineups from the site's own salary file (docs/DFS.md).
  // Before a file: this week's projections in the site's scoring, by position, with the three-step how-to. After one
  // (a file, a drop or a paste; parsed in one request; kept in this tab's memory and sessionStorage, "Remove file"):
  // the slate's header, Undervalued / Overpriced against the slate's salary line, the full value table (sortable; each
  // row can be put in every lineup or left out of all), and lineups (cash or tournament, 1-20) with the site's upload
  // CSV. Works with no league and no team (the API takes none); a league in the URL stays in every link.
  // ---- IN-4 (Wave I-N): no upload to start — the board carries the context the projection does not hold (chips, with
  // "Worth a look" per position — off since Wave I-O's grade: one line says why); when the site's salary file for the week is published on the server (dfs/slates/),
  // the screen opens on its values and the upload moves to "Use a different contest's file"; lineups take stacks and a
  // maximum exposure. The context is shown beside the numbers and never changes them.
  import { ApiError, Unauthorized } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import { setParams, route } from "../lib/router.svelte";
  import { fmt } from "../lib/theme";
  import Chips from "../components/Chips.svelte";
  import Expander from "../components/Expander.svelte";
  import PosBadge from "../components/PosBadge.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import Table, { type Column } from "../components/Table.svelte";
  import FileBox from "../components/dfs/FileBox.svelte";
  import HowTo from "../components/dfs/HowTo.svelte";
  import LineupCard from "../components/dfs/LineupCard.svelte";
  import Context from "../components/dfs/Context.svelte";
  import {
    loadProjections,
    loadPublished,
    loadPublishedList,
    type StackRules,
    MAX_BYTES,
    MAX_PLAYERS,
    money,
    postLineups,
    postSlate,
    saveSlate,
    savedSlate,
    SITES,
    type Lineups,
    type Projections,
    type Site,
    type Slate,
    type SlatePlayer,
  } from "../components/dfs/dfs";

  let { league = null, team = null, onauth }: { options?: LeagueOption[]; league?: string | null; team?: number | null; onauth: () => void } = $props();

  const site = $derived<Site>(route.current.params.get("site") === "fd" ? "fd" : "dk");
  const siteName = $derived(site === "dk" ? "DraftKings" : "FanDuel");
  const ctx = $derived({ league, team });
  const dst = $derived(site === "dk" ? "DST" : "DEF");

  // ---- this week's projections (no file needed)
  let proj = $state<Projections | null>(null);
  let projError = $state<string | null>(null);
  $effect(() => {
    const s = site;
    projError = null;
    loadProjections(s)
      .then((p) => {
        if (site === s) proj = p;
      })
      .catch((e) => {
        if (e instanceof Unauthorized) onauth();
        else projError = e instanceof ApiError ? e.message : "Cannot reach isuckatfantasy right now. Try again in a minute.";
      });
  });

  // ---- the slate (one per site, this tab only)
  let slates = $state<Record<Site, Slate | null>>({ dk: savedSlate("dk"), fd: savedSlate("fd") });
  // ---- IN-4: the published slate of the site (the server's file for the week), when there is one
  let published = $state<Record<Site, Slate | null>>({ dk: null, fd: null });
  let pubChecked = $state<Record<Site, boolean>>({ dk: false, fd: false });
  $effect(() => {
    const s = site;
    if (pubChecked[s]) return;
    loadPublishedList(s)
      .then(async (list) => {
        const first = list.slates.find((x) => x.site === s);
        const sl = first ? await loadPublished(first.id) : null;
        published = { ...published, [s]: sl };
      })
      .catch(() => {
        /* none published, or not reachable: the board and the upload, as before */
      })
      .finally(() => (pubChecked = { ...pubChecked, [s]: true }));
  });
  const slate = $derived(slates[site] ?? published[site]);
  const isPublished = $derived(!slates[site] && !!published[site]);
  let busy = $state(false);
  let fileError = $state<string | null>(null);

  // ---- IM-5 fix: a file over 1 MB never leaves the tab; a 413 from either layer (the server's Guard or the route)
  // reads the same plain sentence
  const TOO_BIG = "That file is too big: a salary file is under 1 MB. Export the contest's player list again and add that file.";
  async function addFile(text: string) {
    fileError = null;
    if (new TextEncoder().encode(text).length > MAX_BYTES) {
      fileError = TOO_BIG;
      return;
    }
    busy = true;
    lineups = null;
    try {
      const s = await postSlate(text);
      if (s.site !== site) setParams({ site: s.site });
      slates = { ...slates, [s.site]: s };
      saveSlate(s.site, s);
      otherFile = false;
    } catch (e) {
      if (e instanceof Unauthorized) onauth();
      else if (e instanceof ApiError && e.status === 413) fileError = TOO_BIG;
      else fileError = e instanceof ApiError ? e.message : "Cannot reach isuckatfantasy right now. Try again in a minute.";
    } finally {
      busy = false;
    }
  }
  function removeFile() {
    otherFile = false;
    slates = { ...slates, [site]: null };
    saveSlate(site, null);
    lineups = null;
    picks = {};
  }

  // ---- position chips (lists and table), sorting
  let pos = $state("ALL");
  const posItems = $derived([
    { key: "ALL", label: "All" },
    ...["QB", "RB", "WR", "TE", ...(slate?.contest === "dk_showdown" ? ["K"] : []), "DEF"].map((p) => ({ key: p, label: p === "DEF" ? dst : p })),
  ]);
  const byKey = $derived(new Map((slate?.players ?? []).map((p) => [p.key, p])));
  const inPos = (p: { position: string }) => pos === "ALL" || p.position === pos;
  const under = $derived((slate?.undervalued ?? []).map((k) => byKey.get(k)!).filter((p) => p && inPos(p)).slice(0, 8));
  const over = $derived((slate?.overpriced ?? []).map((k) => byKey.get(k)!).filter((p) => p && inPos(p)).slice(0, 8));
  const nUnder = $derived((slate?.undervalued ?? []).length);

  let sort = $state<keyof SlatePlayer>("value_gap");
  let dir = $state<"asc" | "desc">("desc");
  let showAll = $state(false);
  const sorted = $derived.by(() => {
    const rows = (slate?.players ?? []).filter(inPos);
    const k = sort;
    const sign = dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const x = a[k] as number | string | null;
      const y = b[k] as number | string | null;
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      return (x < y ? -1 : x > y ? 1 : 0) * sign || a.key.localeCompare(b.key);
    });
  });
  const shown = $derived(showAll ? sorted : sorted.slice(0, 60));
  function onsort(key: string) {
    if (sort === key) dir = dir === "asc" ? "desc" : "asc";
    else {
      sort = key as keyof SlatePlayer;
      dir = key === "salary" || key === "name" || key === "opponent" ? "asc" : "desc";
    }
  }
  const columns: Column[] = [
    { key: "name", label: "Player", sortable: true, width: "34%" },
    { key: "salary", label: "Salary", align: "right", sortable: true, phone: false },
    { key: "proj", label: "Proj", align: "right", sortable: true, phone: false, help: "Projected points this week in this site's scoring" },
    { key: "p10", label: "Low", align: "right", sortable: true, phone: false, help: "Low-end outcome: 1 week in 10 lands below it" },
    { key: "p90", label: "High", align: "right", sortable: true, phone: false, help: "High-end outcome: 1 week in 10 lands above it" },
    { key: "pts_per_k", label: "Pts/$1k", align: "right", sortable: true, phone: false, help: "Projected points per $1,000 of salary" },
    { key: "ceil_per_k", label: "High/$1k", align: "right", sortable: true, phone: false, help: "High-end outcome per $1,000 of salary (tournaments)" },
    { key: "value_gap", label: "Gap", align: "right", sortable: true, width: "4.5rem", help: "Projected points above (+) or below (−) what his salary buys at his position on this slate" },
    { key: "opponent", label: "Matchup", sortable: true, phone: false, width: "16%" },
    { key: "context", label: "Context", phone: false, width: "14%", help: "Signals beside the projection; a dashed chip is not in the projection" },
    { key: "pick", label: "Lineups", align: "right", width: "6rem" },
  ];

  // ---- lineups
  let picks = $state<Record<string, "in" | "out">>({});
  let mode = $state<"cash" | "tournament">("cash");
  // ---- IN-4: stacks and exposure (the objective is unchanged: the rules only say which lineups count)
  let withQb = $state<"0" | "1" | "2">("0");
  let bringBack = $state(false);
  let noDefVsQb = $state(false);
  let exposure = $state(100);
  const stackRules = $derived<StackRules | null>(withQb === "0" && !bringBack && !noDefVsQb ? null : { with_qb: Number(withQb) as 0 | 1 | 2, bring_back: bringBack, no_def_vs_qb: noDefVsQb });
  const exposureShare = $derived(exposure >= 100 ? null : Math.max(10, Math.min(100, Math.round(exposure))) / 100);
  const flat = $derived(slate?.contest !== "dk_showdown");
  let otherFile = $state(false);
  let n = $state(3);
  let lineups = $state<Lineups | null>(null);
  let building = $state(false);
  let buildError = $state<string | null>(null);
  const leftOut = $derived((slate?.players ?? []).filter((p) => p.out && picks[p.key] !== "in")); // ---- IM-5 fix: told here, not sent
  const locks = $derived(Object.keys(picks).filter((k) => picks[k] === "in"));
  const excludes = $derived(Object.keys(picks).filter((k) => picks[k] === "out"));
  function setPick(key: string, v: string) {
    const next = { ...picks };
    if (v === "in" || v === "out") next[key] = v;
    else delete next[key];
    picks = next;
  }
  async function build() {
    if (!slate) return;
    building = true;
    buildError = null;
    try {
      // ---- IM-5 fix: the server takes at most 800 players: those who can play (or are set always in), the highest
      // projected first when a slate is bigger
      const pool = slate.players.filter((p) => (p.proj !== null && !p.out) || picks[p.key] === "in");
      const kept = pool.length <= MAX_PLAYERS ? pool : [...pool.filter((p) => picks[p.key] === "in"), ...pool.filter((p) => picks[p.key] !== "in").sort((a, b) => (b.proj ?? 0) - (a.proj ?? 0))].slice(0, MAX_PLAYERS);
      const keys = new Set(kept.map((p) => p.key));
      const nn = Math.max(1, Math.min(20, Math.round(n) || 1));
      const rules = { stack: flat ? stackRules : null, max_exposure: nn > 1 ? exposureShare : null };
      // ---- IN-4: a published slate is named, not sent (the server has its players)
      lineups = isPublished && slate.slate_id
        ? await postLineups({ slate_id: slate.slate_id, locks: locks.filter((k) => keys.has(k)), excludes: excludes.filter((k) => keys.has(k)), mode, n: nn, ...rules })
        : await postLineups({
            contest: slate.contest,
            players: kept,
            locks: locks.filter((k) => keys.has(k)),
            excludes: excludes.filter((k) => keys.has(k)),
            mode,
            n: nn,
            ...rules,
          });
    } catch (e) {
      if (e instanceof Unauthorized) onauth();
      else buildError = e instanceof ApiError ? e.message : "Cannot reach isuckatfantasy right now. Try again in a minute.";
    } finally {
      building = false;
    }
  }
  function download() {
    if (!lineups?.upload_csv) return;
    const url = URL.createObjectURL(new Blob([lineups.upload_csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = lineups.filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // ---- before a file: the projections by position
  let projPos = $state("ALL");
  const projRows = $derived((proj?.players ?? []).filter((p) => projPos === "ALL" || p.position === projPos).slice(0, 40));
  // ---- IO-1 fix round: "Worth a look" is off the screen (graded: not distinguishable from chance); one quiet line from
  // the record says so under the board's intro and the slate's (meta.worth_line; absent without the record)
  const meta = $derived(slate?.context_meta ?? proj?.context_meta ?? null);
  let openRow = $state<string | null>(null);

  const name = (p: { player_name?: string | null; name?: string }) => p.player_name ?? p.name ?? "";
  const poss = (site: string) => (site.endsWith("s") ? `${site}'` : `${site}'s`); // DraftKings' · FanDuel's
  const gapWords = (g: number | null) => (g === null ? "—" : fmt.signed(g));
  const href = (gsis: string | null) => (gsis && league ? withContext(`/player/${gsis}`, ctx) : null);
  const contestWords = (s: Slate) => `${s.site_name} ${s.contest_label.replace(/^(DraftKings|FanDuel) /, "")} · week ${s.week} · ${s.games.length} game${s.games.length === 1 ? "" : "s"}`;
</script>

{#snippet who(p: { gsis_id: string | null; position: string; team: string | null; status: string | null; out: boolean } & { player_name?: string | null; name?: string })}
  {@const h = href(p.gsis_id)}
  <span class="flex min-w-0 items-center gap-1.5">
    <PosBadge pos={p.position === "DEF" ? "DEF" : p.position} />
    <span class="min-w-0 truncate">
      {#if h}<a class="ll-link font-semibold" href={h}>{name(p)}</a>{:else}<span class="font-semibold">{name(p)}</span>{/if}
      <span class="text-sm text-ink-3"> {p.team ?? ""}</span>
      {#if p.status}<span class="text-xs font-bold {p.out ? 'text-bad' : 'text-warn'}"> {p.status}</span>{/if}
    </span>
  </span>
{/snippet}

{#snippet valueRow(p: SlatePlayer)}
  <li class="py-2" data-testid="dfs-value-row">
    <div class="flex items-center gap-2">
      <div class="min-w-0 flex-1">{@render who(p)}</div>
      <span class="tabnum text-sm text-ink-2">{money(p.salary)}</span>
      <span class="tabnum w-12 text-right font-bold">{fmt.pts(p.proj)}</span>
    </div>
    <p class="mt-0.5 pl-9 text-sm text-ink-2">
      <span class="tabnum font-semibold {p.value_call === 'undervalued' ? 'text-good' : 'text-bad'}">{p.value_call === "undervalued" ? "▲" : "▼"} {gapWords(p.value_gap)}</span>
      vs the slate's line ({fmt.pts(p.line_points)}) · {fmt.pts(p.pts_per_k, 2)} pts per $1,000
    </p>
    {#if p.reason}<p class="pl-9 text-sm text-ink-3" data-testid="dfs-reason">{p.reason}</p>{/if}
    {#if p.context?.length}<div class="mt-1 pl-9"><Context signals={p.context} /></div>{/if}
  </li>
{/snippet}

{#snippet worthLine()}
  {#if meta?.worth_line}<p class="text-sm text-ink-3" data-testid="dfs-worth-line">{meta.worth_line}</p>{/if}
{/snippet}

{#snippet contextHonest()}
  {#if meta}
    <Expander title="What the projection already holds" testid="dfs-holds">
      <p class="mb-2 text-sm text-ink-2" data-testid="dfs-context-honest">{meta.words} A chip with a solid border is in the projection; a dashed border is not.</p>
      <ul class="space-y-1 text-sm text-ink-2">
        <li><span class="font-semibold text-ink">Defense against his position</span> (its rank and the points it gives up): {meta.projection.defense?.WR ? meta.in_words : meta.out_words}.</li>
        <li><span class="font-semibold text-ink">The cornerback</span> (receivers): {meta.projection.corner?.WR ? meta.in_words : meta.out_words}.{meta.matchup_words ? ` ${meta.matchup_words}` : ""}{#if meta.corner_record}<span data-testid="dfs-corner-record">{` ${meta.corner_record}`}</span>{/if}</li>
        <li><span class="font-semibold text-ink">Role trend</span> (his share of the targets, carries and snaps, his last two games against the ones before): {meta.projection.role?.WR ? meta.in_words : meta.out_words} (it reads his last 3 games and the season). Routes run per dropback: {meta.projection.routes?.WR ? meta.in_words : meta.out_words}, and not available during the season.</li>
        <li><span class="font-semibold text-ink">The betting line</span> (over/under, spread, the team's expected points): {meta.lines ? (meta.projection.game?.WR ? meta.in_words : meta.out_words) + "." : "no line for this week yet."}</li>
        <li data-testid="dfs-weather-honest"><span class="font-semibold text-ink">Weather</span>: {meta.projection.weather?.WR ? meta.in_words : meta.out_words}; {meta.forecast ? "outdoor games carry the forecast at kickoff when it is unusual: wind 15 mph or more, rain 0.1 in or more, snow, below freezing. Since 2016, passers averaged 7.1 yards per attempt under 10 mph of wind, 6.8 at 15–20 mph and 6.2 at 20+ (observed weather, 2,639 games); the forecast can miss." : "no forecast for this week's games yet."}</li>
      </ul>
    </Expander>
  {/if}
{/snippet}

<main class="space-y-5 pb-6" data-testid="dfs">
  <ScreenHead eyebrow={`DFS · ${siteName}${slate ? ` · week ${slate.week}` : proj ? ` · week ${proj.week}` : ""}`} title="Daily fantasy values">
    {#snippet answer()}
      {#if slate}
        <span data-testid="dfs-answer"
          >{slate.counts.matched} of {slate.counts.on_file} players on {isPublished ? "the published" : "your"} {slate.site_name} file valued; {nUnder} project above what their salary buys on this
          slate.</span
        >
      {:else}
        <span data-testid="dfs-answer">This week's projections in {siteName} scoring. Add the contest's salary file to see who is undervalued against its salaries.</span>
      {/if}
    {/snippet}
  </ScreenHead>

  <div class="flex flex-wrap items-center justify-between gap-2">
    <Chips label="Site" testid="dfs-site" current={site} items={SITES} onpick={(s) => setParams({ site: s === "dk" ? null : s })} />
    <p class="text-sm text-ink-3" data-testid="dfs-honest">
      Projections are estimates, not promises: <a class="ll-link" href={withContext("/about", ctx)}>the model's record is on About</a>.
    </p>
  </div>

  {#if !slate}
    <section class="grid grid-cols-1 gap-4 wide:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
      <!-- the board first on a phone (it is what the screen opens for); on a desktop the file sits on the left -->
      <div class="order-2 min-w-0 space-y-3 wide:order-1">
        <FileBox {site} {busy} onfile={addFile} />
        {#if fileError}<p class="rounded-md bg-bad-soft p-3 text-sm" role="alert" data-testid="dfs-file-error">{fileError}</p>{/if}
        <div class="rounded-lg border border-line bg-surface p-4">
          <h2 class="mb-2 text-lg font-bold">Where the file is</h2>
          <HowTo {site} />
        </div>
        {@render contextHonest()}
      </div>
      <section class="order-1 min-w-0 space-y-2 wide:order-2" data-testid="dfs-projections">
        <h2 class="text-lg leading-tight font-bold">This week's projections{proj ? `, week ${proj.week}` : ""}</h2>
        <p class="text-sm text-ink-3">
          In {siteName} scoring. The range is the low-end to high-end outcome (8 weeks in 10 land between). The chips are context beside the projection; tap a player for the
          reasons.
        </p>
        {@render worthLine()}
        <Chips label="Position" testid="dfs-proj-pos" current={projPos} items={[{ key: "ALL", label: "All" }, ...["QB", "RB", "WR", "TE", ...(site === "dk" ? ["K"] : []), "DEF"].map((p) => ({ key: p, label: p === "DEF" ? dst : p }))]} onpick={(p) => (projPos = p)} />
        {#if projError}
          <p class="text-sm text-bad" role="alert">{projError}</p>
        {:else if !proj}
          <div class="ll-skel h-40" aria-label="Loading"></div>
        {:else}
          <ol class="divide-y divide-line rounded-lg border border-line bg-surface px-3">
            {#each projRows as p, i (p.key)}
              <li class="py-2" data-testid="dfs-proj-row">
                <div class="flex items-center gap-2">
                  <span class="w-6 shrink-0 text-right text-xs text-ink-3">{i + 1}</span>
                  <div class="min-w-0 flex-1">
                    {@render who(p)}
                    {#if p.matchup}<p class="truncate pl-9 text-xs text-ink-3">{p.matchup}</p>{/if}
                  </div>
                  <span class="tabnum hidden text-sm text-ink-3 sm:inline">{fmt.pts(p.p10)}–{fmt.pts(p.p90)}</span>
                  <span class="tabnum w-12 text-right font-bold">{fmt.pts(p.proj)}</span>
                  <button
                    type="button"
                    class="grid h-8 w-8 shrink-0 place-items-center rounded-md text-ink-3 hover:text-ink"
                    aria-expanded={openRow === p.key}
                    aria-label={`Context for ${name(p)}`}
                    onclick={() => (openRow = openRow === p.key ? null : p.key)}
                    data-testid="dfs-proj-open">{openRow === p.key ? "▴" : "▾"}</button
                  >
                </div>
                {#if p.context?.length}<div class="mt-1 pl-14"><Context signals={p.context} /></div>{/if}
                {#if openRow === p.key}<div class="mt-1.5 pl-14" data-testid="dfs-proj-detail"><Context full signals={p.context ?? []} /></div>{/if}
              </li>
            {/each}
          </ol>
        {/if}
      </section>
    </section>
  {:else}
    <section class="space-y-2 rounded-lg border border-line bg-surface p-4" data-testid="dfs-slate-head">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h2 class="text-lg font-bold">{contestWords(slate)}{isPublished && slate.label && slate.label !== "main" ? ` · ${slate.label}` : ""}</h2>
        {#if isPublished}
          <button type="button" class="min-h-9 rounded-md px-1 text-sm font-semibold text-ink-3 underline hover:text-ink" aria-expanded={otherFile} onclick={() => (otherFile = !otherFile)} data-testid="dfs-other-file"
            >Use a different contest's file</button
          >
        {:else}
          <button type="button" class="min-h-9 rounded-md border border-line-strong px-3 text-sm font-semibold text-ink-2 hover:text-ink" onclick={removeFile} data-testid="dfs-remove"
            >{published[site] ? "Back to the published slate" : "Remove file"}</button
          >
        {/if}
      </div>
      {#if isPublished}
        <p class="text-sm text-ink-2" data-testid="dfs-published">
          {poss(slate.site_name)} salary file for week {slate.week}, published here so you do not have to add one: the salaries are the site's own, for its main contest. Another contest
          (a different slate or game) has its own salaries.
        </p>
        {#if otherFile}
          <div class="grid grid-cols-1 gap-3 wide:grid-cols-2" data-testid="dfs-other-box">
            <FileBox {site} {busy} onfile={addFile} />
            <div class="min-w-0"><HowTo {site} /></div>
          </div>
          {#if fileError}<p class="rounded-md bg-bad-soft p-3 text-sm" role="alert" data-testid="dfs-file-error">{fileError}</p>{/if}
        {/if}
      {/if}
      <p class="text-sm text-ink-2">
        <span class="tabnum font-semibold">{slate.counts.matched}</span> players matched to ours,
        <span class="tabnum font-semibold">{slate.counts.unmatched}</span> not matched (not valued){slate.counts.skipped ? `, ${slate.counts.skipped} rows unreadable` : ""}. Salary cap
        {money(slate.cap)}.
      </p>
      {#each slate.notes as note, i (i)}<p class="text-sm text-ink-3">{note}</p>{/each}
      {@render worthLine()}
      {#if slate.unmatched.length || slate.skipped.length}
        <Expander title={`See unmatched (${slate.unmatched.length + slate.skipped.length})`} testid="dfs-unmatched">
          <p class="mb-2 text-sm text-ink-3">We never guess a player: these are not valued and not in lineups.</p>
          <ul class="space-y-1 text-sm">
            {#each slate.unmatched as u (u.key)}<li><span class="font-semibold">{u.name}</span> <span class="text-ink-3">{u.position} · {u.team} · {money(u.salary)}</span> — {u.reason}</li>{/each}
            {#each slate.skipped as k (k.row)}<li><span class="font-semibold">Row {k.row}</span> {k.name} — {k.reason}</li>{/each}
          </ul>
        </Expander>
      {/if}
    </section>

    <Chips label="Position" testid="dfs-pos" current={pos} items={posItems} onpick={(p) => (pos = p)} />

    <section class="grid grid-cols-1 gap-4 wide:grid-cols-2">
      <div class="min-w-0 rounded-lg border border-line bg-surface p-4" data-testid="dfs-undervalued">
        <h2 class="text-lg font-bold">Undervalued</h2>
        <p class="text-sm text-ink-3">Projected well above what his salary buys at his position on this slate. Against this slate's salaries, not a promise.</p>
        {#if under.length}<ul class="mt-1 divide-y divide-line">{#each under as p (p.key)}{@render valueRow(p)}{/each}</ul>
        {:else}<p class="mt-2 text-sm text-ink-2">Nobody here sits a typical miss above the slate's line.</p>{/if}
      </div>
      <div class="min-w-0 rounded-lg border border-line bg-surface p-4" data-testid="dfs-overpriced">
        <h2 class="text-lg font-bold">Overpriced</h2>
        <p class="text-sm text-ink-3">Projected well below what his salary buys at his position on this slate.</p>
        {#if over.length}<ul class="mt-1 divide-y divide-line">{#each over as p (p.key)}{@render valueRow(p)}{/each}</ul>
        {:else}<p class="mt-2 text-sm text-ink-2">Nobody here sits a typical miss below the slate's line.</p>{/if}
      </div>
    </section>
    {@render contextHonest()}
    {#if Object.values(slate.fit).some((f) => f)}
      <Expander title="How the slate's line is drawn" testid="dfs-fit">
        <ul class="space-y-1 text-sm text-ink-2">
          {#each Object.entries(slate.fit) as [p, f] (p)}<li>{#if f}{f.words}{:else}{p === "DEF" ? dst : p}: fewer than 8 priced players, no line.{/if}</li>{/each}
        </ul>
      </Expander>
    {/if}

    <section class="space-y-2" data-testid="dfs-table">
      <h2 class="text-lg leading-tight font-bold">Every player on the slate</h2>
      <p class="text-sm text-ink-3">Tap a column to sort. "Lineups": put a player in every lineup, or leave him out of all.</p>
      <Table rows={shown} {columns} rowKey={(r) => r.key} sort={String(sort)} {dir} {onsort} dense testid="dfs-value-table">
        {#snippet cell(p: SlatePlayer, key: string)}
          {#if key === "name"}{@render who(p)}<span class="block pl-9 text-xs text-ink-3 sm:hidden">{money(p.salary)} · {fmt.pts(p.proj)} projected</span>
          {:else if key === "salary"}{money(p.salary)}
          {:else if key === "proj" || key === "p10" || key === "p90"}{fmt.pts(p[key])}
          {:else if key === "pts_per_k" || key === "ceil_per_k"}{fmt.pts(p[key], 2)}
          {:else if key === "value_gap"}<span class={p.value_call === "undervalued" ? "text-good" : p.value_call === "overpriced" ? "text-bad" : ""}>{gapWords(p.value_gap)}</span>
          {:else if key === "opponent"}<span class="text-sm text-ink-2">{p.matchup ?? (p.opponent ? `vs ${p.opponent}` : "—")}</span>
          {:else if key === "context"}<Context signals={p.context ?? []} />
          {:else if key === "pick"}
            <select
              class="min-h-8 w-full rounded-sm border border-line bg-sunken px-1 text-xs"
              aria-label={`Lineups: ${name(p)}`}
              value={picks[p.key] ?? ""}
              onchange={(e) => setPick(p.key, (e.currentTarget as HTMLSelectElement).value)}
              data-testid="dfs-pick"
            >
              <option value="">Either</option>
              <option value="in">Always in</option>
              <option value="out">Leave out</option>
            </select>
          {/if}
        {/snippet}
      </Table>
      {#if sorted.length > shown.length}
        <button type="button" class="min-h-10 rounded-md border border-line-strong px-4 text-sm font-semibold" onclick={() => (showAll = true)} data-testid="dfs-show-all"
          >Show all {sorted.length}</button
        >
      {/if}
    </section>

    <section class="space-y-3 rounded-lg border border-line bg-surface p-4" data-testid="dfs-build">
      <h2 class="text-lg font-bold">Build lineups</h2>
      <div class="flex flex-wrap items-end gap-3">
        <Chips label="Aim" testid="dfs-mode" current={mode} items={[{ key: "cash", label: "Cash: projected points" }, { key: "tournament", label: "Tournament: high-end outcome" }]} onpick={(m) => (mode = m as "cash" | "tournament")} />
        <label class="text-sm">
          <span class="ll-label block">Lineups</span>
          <input class="mt-1 min-h-10 w-20 rounded-md border border-line bg-sunken px-2 tabnum" type="number" min="1" max="20" bind:value={n} data-testid="dfs-n" />
        </label>
        <button type="button" class="min-h-10 rounded-md bg-accent px-4 text-sm font-bold text-on-accent disabled:opacity-60" disabled={building} onclick={build} data-testid="dfs-build-go"
          >{building ? "Building…" : "Build lineups"}</button
        >
      </div>
      {#if flat}
        <div class="space-y-2 rounded-md border border-line p-3" data-testid="dfs-stacks">
          <Chips
            label="Stack"
            testid="dfs-stack"
            current={withQb}
            items={[
              { key: "0", label: "No stack" },
              { key: "1", label: "QB + 1 pass catcher" },
              { key: "2", label: "QB + 2 pass catchers" },
            ]}
            onpick={(k) => (withQb = k as "0" | "1" | "2")}
          />
          <div class="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
            <label class="inline-flex min-h-9 items-center gap-2"><input type="checkbox" bind:checked={bringBack} data-testid="dfs-bring-back" /> Bring-back: one from his opponent</label>
            <label class="inline-flex min-h-9 items-center gap-2"><input type="checkbox" bind:checked={noDefVsQb} data-testid="dfs-no-def" /> No defense against my quarterback</label>
            <label class="inline-flex items-center gap-2">
              Most lineups per player
              <input class="min-h-9 w-20 rounded-md border border-line bg-sunken px-2 tabnum" type="number" min="10" max="100" step="5" bind:value={exposure} data-testid="dfs-exposure" />%
            </label>
          </div>
          <p class="text-xs text-ink-3">A stack is a quarterback with his own receivers or tight end (and a bring-back, one player from the other side of his game). The rules only choose which lineups count; the projections are unchanged.</p>
        </div>
      {/if}
      <p class="text-sm text-ink-3">
        The best lineups under the {money(slate.cap)} cap and {poss(slate.site_name)} roster rules, each different by at least one player.
        {locks.length ? `${locks.length} always in. ` : ""}{excludes.length ? `${excludes.length} left out. ` : ""}Players who cannot play are left out unless you put them in.
      </p>
      {#if buildError}<p class="text-sm text-bad" role="alert">{buildError}</p>{/if}
      {#if lineups}
        {#each lineups.notes as note, i (i)}<p class="text-sm text-ink-2" data-testid="dfs-build-note">{note}</p>{/each}
        {#if leftOut.length}
          <p class="text-sm text-ink-3">Left out (cannot play): {leftOut.map((p) => `${p.name}${p.status ? ` (${p.status})` : ""}`).join(", ")}.</p>
        {/if}
        {#if lineups.lineups.length}
          <div class="flex flex-wrap items-center gap-2">
            <button type="button" class="min-h-10 rounded-md border border-line-strong px-4 text-sm font-semibold" onclick={download} data-testid="dfs-download"
              >Download for upload ({lineups.lineups.length} lineup{lineups.lineups.length === 1 ? "" : "s"})</button
            >
            <span class="text-sm text-ink-3">The CSV {poss(slate.site_name)} lineup upload takes, with the file's own player ids.</span>
          </div>
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 wide:grid-cols-3" data-testid="dfs-lineups">
            {#each lineups.lineups as lu, i (i)}<LineupCard lineup={lu} index={i} cap={lineups.cap} {league} {team} {site} contextOf={(k) => byKey.get(k)?.context ?? []} />{/each}
          </div>
        {/if}
      {/if}
    </section>
  {/if}

  <Expander title={`How ${siteName} scores it`} testid="dfs-scoring">
    <ul class="list-disc space-y-1 pl-5 text-sm text-ink-2">
      {#each (slate?.scoring ?? proj?.scoring ?? []) as line, i (i)}<li>{line}</li>{/each}
    </ul>
    <p class="mt-2 text-sm text-ink-3">As {siteName} publishes it, October 2026: check the site's rules page.</p>
  </Expander>

  <footer class="border-t border-line pt-3 text-sm text-ink-3" data-testid="dfs-footer">
    isuckatfantasy is not affiliated with DraftKings or FanDuel. Daily fantasy contests are not offered or legal everywhere and are for adults: check your state's
    rules.
  </footer>
</main>
