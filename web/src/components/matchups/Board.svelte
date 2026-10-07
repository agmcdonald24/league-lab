<script lang="ts">
  // ---- IN-3 (Wave I-N): the matchup board — every player at a position with a game this week, laid out player by
  // player (Andrew, 2026-10-06: "a search for a player kind of thing, or just start laying them out … at least for
  // receivers"). GET /api/matchups/board: his game, his projection and range in the chosen scoring, the defense against
  // his position, for a wide receiver the cornerback call, and the one tone of the two together. Search by name, filter
  // by game and tone, sort, paged; a row opens the evidence that exists (MatchupEvidence). The state lives in the URL
  // (`bpos`, `q`, `game`, `tone`, `bsort`, `boff`) so a board can be shared.
  import { boardPath, boardShowPath, type BoardRow, type MatchupBoard } from "../../lib/api";
  import { withContext } from "../../lib/md";
  import { givesUpShort, type Tone } from "../../lib/research";
  import { Remote } from "../../lib/remote.svelte";
  import { route, setParams } from "../../lib/router.svelte";
  import { fmt, teamLabel } from "../../lib/theme";
  import Chips from "../Chips.svelte";
  import Headshot from "../Headshot.svelte";
  import MatchupEvidence from "../MatchupEvidence.svelte";
  import ToneChip from "./ToneChip.svelte";

  let { league, team, onauth, owners }: { league: string; team: number | null; onauth: () => void; owners: boolean } = $props();

  const LIMIT = 25;
  const POS = [
    { key: "WR", label: "WR" },
    { key: "TE", label: "TE" },
    { key: "RB", label: "RB" },
    { key: "QB", label: "QB" },
  ];
  const PLURAL: Record<string, string> = { WR: "wide receivers", TE: "tight ends", RB: "running backs", QB: "quarterbacks" };
  const params = $derived(route.current.params);
  const pos = $derived((params.get("bpos") ?? "WR").toUpperCase());
  const qParam = $derived(params.get("q") ?? "");
  const game = $derived(params.get("game") ?? "");
  const tone = $derived(params.get("tone") ?? "");
  const sort = $derived(params.get("bsort") ?? "projection");
  const offset = $derived(Math.max(0, Number(params.get("boff") ?? 0) || 0));
  // ---- IO-4 (Wave I-O): a game that has kicked off moves below the games to come, marked Started / Final; once one has,
  // "Still to play" is the default (the server decides; `bshow=all` in the URL shows every game)
  const show = $derived(params.get("bshow") ?? "");
  const STATE_WORD: Record<string, string> = { started: "Started", final: "Final" };

  let q = $derived(qParam); // a Back, a shared link: the box shows the URL's search; typing writes it until the URL follows
  let timer: ReturnType<typeof setTimeout> | undefined;
  function onq() {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const s = q.trim();
      if (s.length === 1) return; // one letter is not a search yet
      setParams({ q: s || null, boff: null });
    }, 250);
  }
  $effect(() => () => clearTimeout(timer));

  const b = new Remote<MatchupBoard>();
  const path = $derived(
    boardShowPath(boardPath(league, { position: pos, q: qParam, game, tone, sort: pos === "WR" || sort !== "corner" ? sort : "projection", offset, limit: LIMIT }), show),
  );
  $effect(() => b.load(path, onauth, true));

  let open = $state<string | null>(null);
  $effect(() => {
    void path;
    open = null;
  });

  const kickoff = (iso: string | null) => {
    if (!iso) return "";
    const d = new Date(iso);
    return `${d.toLocaleString("en-US", { weekday: "short", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" })} ET`;
  };
  const gameWords = (g: { home: string; away: string; kickoff_at: string | null; state?: string | null }) =>
    `${teamLabel(g.away)} at ${teamLabel(g.home)} · ${kickoff(g.kickoff_at)}${gameState(g)}`;
  const defenseShort = (r: BoardRow) => {
    const d = r.context.defense;
    if (d.tough_rank == null || !d.n_ranked) return "no games to rank yet";
    return givesUpShort(d.n_ranked + 1 - d.tough_rank, d.n_ranked, r.position);
  };
  // "McDuffie #3 of 74" (likely) · "Hughes #66 or Henderson" (unclear: both named) · "No call"
  const lastOf = (name: string | null) => (name ?? "").split(" ").slice(1).join(" ") || name || "?";
  const cornerShort = (r: BoardRow) => {
    const c = r.context.cb;
    if (!c || c.certainty === "no call") return "No call";
    const n = r.cb_detail?.n_ranked;
    const one = (name: string | null, rank: number | null, withN: boolean) => `${lastOf(name)} ${rank != null ? `#${rank}${withN && n ? ` of ${n}` : ""}` : "(unranked)"}`;
    const named = r.cb_detail?.named ?? [];
    if (c.certainty === "likely" || named.length < 2) return one(c.corner, c.corner_rank, true);
    return named.map((k) => one(k.name, k.rank, false)).join(" or ");
  };
  const owner = (r: BoardRow) => (team !== null && r.rostered_by_roster_id === team ? "Yours" : (r.rostered_by_team ?? "Free agent"));
  const range = (r: BoardRow) => (r.p10 == null || r.p90 == null ? "" : `${fmt.pts(r.p10)}–${fmt.pts(r.p90)}`);
  const status = (r: BoardRow) => (r.report_status && r.report_status !== "Active" ? r.report_status : null);
  const toneItems = $derived([
    { key: "", label: "All" },
    { key: "favorable", label: `▲ Favorable${b.data?.counts?.favorable != null ? ` (${b.data.counts.favorable})` : ""}` },
    { key: "neutral", label: `Neutral${b.data?.counts?.neutral != null ? ` (${b.data.counts.neutral})` : ""}` },
    { key: "difficult", label: `▼ Difficult${b.data?.counts?.difficult != null ? ` (${b.data.counts.difficult})` : ""}` },
  ]);
  const shown = $derived(b.data ? { from: b.data.total ? b.data.offset + 1 : 0, to: b.data.offset + b.data.rows.length } : null);
  const showItems = $derived([
    { key: "to_play", label: "Still to play" },
    { key: "all", label: "All games" },
  ]);
  const gameState = (g: { state?: string | null }) => (g.state ? ` · ${STATE_WORD[g.state] ?? ""}` : "");
  const ctx = $derived({ league, team });
  const GRID = "wide:grid wide:grid-cols-[minmax(13rem,1.7fr)_minmax(7.5rem,0.9fr)_minmax(6rem,0.7fr)_minmax(10rem,1.3fr)_minmax(9rem,1.1fr)_minmax(6.5rem,0.7fr)] wide:items-center wide:gap-3";
</script>

<section class="space-y-3" data-testid="board">
  <div class="space-y-2.5 rounded-lg border border-line bg-surface p-3" style="box-shadow:var(--ll-shadow)">
    <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
      <Chips items={POS} current={pos} label="Position" testid="board-pos" onpick={(k) => setParams({ bpos: k === "WR" ? null : k, boff: null, ...(k !== "WR" && sort === "corner" ? { bsort: null } : {}) })} />
      <label class="flex min-w-0 flex-1 basis-56 items-center gap-2">
        <span class="sr-only">Search a player by name</span>
        <input
          type="search"
          class="ll-input w-full py-1.5 text-sm"
          placeholder="Search a player"
          maxlength="40"
          autocomplete="off"
          bind:value={q}
          oninput={onq}
          data-testid="board-search"
        />
      </label>
    </div>
    <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
      {#if (b.data?.started_games ?? 0) > 0}
        <Chips items={showItems} current={b.data?.show ?? "to_play"} label="Games" testid="board-show" onpick={(k) => setParams({ bshow: k, boff: null })} />
      {/if}
      <Chips items={toneItems} current={tone} label="Matchup" testid="board-tone" onpick={(k) => setParams({ tone: k || null, boff: null })} />
      <div class="flex min-w-0 flex-1 flex-wrap items-center gap-2">
        <select
          class="ll-input min-w-0 flex-1 py-1.5 text-sm"
          aria-label="Game"
          value={game}
          onchange={(e) => setParams({ game: e.currentTarget.value || null, boff: null })}
          data-testid="board-game"
        >
          <option value="">All games</option>
          {#each b.data?.games ?? [] as g (g.game_id)}<option value={g.game_id}>{gameWords(g)}</option>{/each}
        </select>
        <select
          class="ll-input min-w-0 flex-1 py-1.5 text-sm"
          aria-label="Sort"
          value={sort}
          onchange={(e) => setParams({ bsort: e.currentTarget.value === "projection" ? null : e.currentTarget.value, boff: null })}
          data-testid="board-sort"
        >
          <option value="projection">Sort: projected points</option>
          <option value="tone">Sort: best matchup first</option>
          {#if pos === "WR"}<option value="corner">Sort: easiest corner first</option>{/if}
        </select>
      </div>
    </div>
    {#if b.data}
      <p class="text-xs leading-snug text-ink-3" data-testid="board-honest-short">
        Projected points in {b.data.scoring} scoring. The defense is in the projection; the corner is not (context only).
        {#if b.data.position_note}{b.data.position_note}{/if}
      </p>
    {/if}
  </div>

  {#if b.error && !b.data}
    <p class="ll-error">{b.error}</p>
  {:else if !b.data}
    <div class="space-y-2" aria-label="Loading" data-testid="board-loading">
      {#each [0, 1, 2, 3] as i (i)}<div class="ll-skel h-16"></div>{/each}
    </div>
  {:else if b.data.notice}
    <p class="ll-empty" data-testid="board-notice">{b.data.notice}</p>
  {:else if b.data.rows.length === 0}
    <p class="ll-empty" data-testid="board-empty">
      {qParam ? `No ${PLURAL[pos] ?? "players"} named like “${qParam}” with a game this week.` : `No ${PLURAL[pos] ?? "players"} match these filters this week.`}
    </p>
  {:else}
    <div class="overflow-hidden rounded-lg border border-line bg-surface {b.loading ? 'opacity-70' : ''}" style="box-shadow:var(--ll-shadow)">
      <div class="hidden border-b border-line px-3 py-2 {GRID}" aria-hidden="true">
        <span class="ll-label">Player</span>
        <span class="ll-label">Game</span>
        <span class="ll-label">Projected</span>
        <span class="ll-label">Defense vs {pos}</span>
        <span class="ll-label">{pos === "WR" ? "Corner across" : owners ? "Who has him" : ""}</span>
        <span class="ll-label">Matchup</span>
      </div>
      <ul class="divide-y divide-line" data-testid="board-rows">
        {#each b.data.rows as r (r.gsis_id)}
          {@const isOpen = open === r.gsis_id}
          <li data-testid="board-row" data-gsis={r.gsis_id} data-tone={r.context.tone ?? "none"} data-state={r.game_state ?? "to-play"} class={r.game_state ? "bg-raised/30" : ""}>
            <button
              type="button"
              class="block w-full px-3 py-2.5 text-left hover:bg-raised {GRID} {isOpen ? 'bg-raised' : ''}"
              aria-expanded={isOpen}
              onclick={() => (open = isOpen ? null : r.gsis_id)}
              data-testid="board-row-open"
            >
              <span class="flex min-w-0 items-center gap-2.5">
                <Headshot url={r.headshot_url} name={r.player_name} team={r.team} size={36} />
                <span class="min-w-0 flex-1">
                  <span class="block truncate font-semibold text-ink" data-testid="board-name">{r.player_name}</span>
                  <span class="block truncate text-xs text-ink-3">
                    {r.position} · {teamLabel(r.team) ?? "—"}{#if status(r)} · <span class="font-semibold text-warn">{status(r)}</span>{/if}{#if owners}<span class="wide:hidden"> · {owner(r)}</span>{/if}
                    <span class="wide:hidden"> · {r.is_home === false ? "at" : "vs"} {teamLabel(r.opponent)}</span>{#if r.game_state}<span class="wide:hidden">&nbsp;·&nbsp;</span><span class="rounded bg-raised px-1.5 py-0.5 text-[11px] font-semibold tracking-wide text-ink-2 uppercase wide:hidden" data-testid="board-state">{STATE_WORD[r.game_state]}</span>{/if}
                  </span>
                </span>
                <span class="wide:hidden"><ToneChip tone={r.context.tone as Tone | null} testid="board-tone-chip" /></span>
              </span>
              <span class="hidden min-w-0 wide:block">
                <span class="block font-semibold">{r.is_home === false ? "at" : "vs"} {teamLabel(r.opponent)}</span>
                <span class="block text-xs text-ink-3">{#if r.game_state}<span class="rounded bg-raised px-1.5 py-0.5 text-[11px] font-semibold tracking-wide text-ink-2 uppercase" data-testid="board-state-wide">{STATE_WORD[r.game_state]}</span>{:else}{kickoff(r.kickoff_at)}{/if}</span>
              </span>
              <span class="mt-1.5 block wide:mt-0">
                <span class="text-xs text-ink-3 wide:hidden">Projects&nbsp;</span><span class="tabnum font-bold" data-testid="board-proj">{fmt.pts(r.proj_points)}</span>
                <span class="tabnum text-xs text-ink-3 wide:block">{range(r) ? (range(r)) : ""}</span>
              </span>
              <span class="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 wide:mt-0">
                <span class="text-xs text-ink-3 wide:hidden">Defense</span>
                <ToneChip tone={r.context.defense.tone as Tone | null} size="sm" testid="board-defense-chip" />
                <span class="text-xs text-ink-2">{defenseShort(r)}</span>
              </span>
              {#if r.position === "WR"}
                <span class="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 wide:mt-0" data-testid="board-corner">
                  <span class="text-xs text-ink-3 wide:hidden">Corner</span>
                  <span class="text-sm">{cornerShort(r)}</span>
                  <!-- ---- IO-4 fix round: the corner is information (graded: no measurable effect) — plain text, no colour -->
                  {#if r.context.cb?.shutdown}<span class="text-xs text-ink-3" data-testid="board-shutdown">top-quarter corner</span>{/if}
                  <span class="text-[11px] font-semibold tracking-wide text-ink-3 uppercase">{r.context.cb?.certainty ?? "no call"}</span>
                </span>
              {:else}
                <span class="hidden truncate text-sm text-ink-2 wide:block">{owners ? owner(r) : ""}</span>
              {/if}
              <span class="hidden wide:block"><ToneChip tone={r.context.tone as Tone | null} testid="board-tone-chip-wide" /></span>
            </button>
            {#if isOpen}
              <div class="space-y-2 border-t border-line bg-raised/40 px-3 py-3 text-sm leading-snug" data-testid="board-detail">
                {#if r.context.words}<p class="text-ink" data-testid="board-words">{r.context.words}</p>{/if}
                {#if r.position === "WR" && owners}<p class="text-xs text-ink-3">Who has him: {owner(r)}</p>{/if}
                {#if r.cb_detail}
                  <div class="space-y-1" data-testid="board-cb-detail">
                    {#each r.cb_detail.named as k, i (i)}
                      <p><span class="text-ink-3">{i === 0 ? (r.context.cb?.certainty === "likely" ? "Likely across from him:" : "Either") : "or"}</span> <strong>{k.name}</strong> <span class="text-ink-3">({k.side})</span>: {k.words}</p>
                    {/each}
                    {#if r.cb_detail.certainty_words}<p class="text-xs text-ink-3">{r.cb_detail.certainty_words}</p>{/if}
                    {#if r.cb_detail.history}<p class="text-ink-2" data-testid="board-history">{r.cb_detail.history}</p>{/if}
                  </div>
                {/if}
                {#if r.matchup_evidence}
                  <div class="rounded-md bg-surface px-3 py-2"><MatchupEvidence ev={r.matchup_evidence} testid="board-evidence" /></div>
                {:else}
                  <p class="text-xs text-ink-3">No evidence to show for this game yet.</p>
                {/if}
                <a class="ll-link text-sm font-semibold" href={withContext(`/player/${r.gsis_id}`, ctx)} data-testid="board-player-link">{r.player_name}: his numbers ›</a>
              </div>
            {/if}
          </li>
        {/each}
      </ul>
    </div>
    <div class="flex flex-wrap items-center justify-between gap-2 text-sm text-ink-2" data-testid="board-pager">
      <span data-testid="board-count">Showing {shown?.from}–{shown?.to} of {b.data.total} {PLURAL[pos] ?? "players"}{b.data.show === "to_play" && (b.data.started_games ?? 0) > 0 ? " still to play" : ""}</span>
      <span class="flex gap-2">
        <button
          type="button"
          class="min-h-9 rounded-md border border-line-strong px-3 font-semibold disabled:opacity-40"
          disabled={b.data.offset === 0}
          onclick={() => setParams({ boff: b.data && b.data.offset - LIMIT > 0 ? String(b.data.offset - LIMIT) : null })}
          data-testid="board-prev">Previous</button
        >
        <button
          type="button"
          class="min-h-9 rounded-md border border-line-strong px-3 font-semibold disabled:opacity-40"
          disabled={b.data.offset + b.data.rows.length >= b.data.total}
          onclick={() => setParams({ boff: String((b.data?.offset ?? 0) + LIMIT) })}
          data-testid="board-next">Next</button
        >
      </span>
    </div>
    <p class="text-xs leading-snug text-ink-3" data-testid="board-honest">
      Projected points this week in {b.data.scoring} scoring, with the range 8 weeks in 10 land in (low-end to high-end).
      {b.data.projection_words}
      {b.data.tone_words}
    </p>
  {/if}
</section>
