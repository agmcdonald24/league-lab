<script lang="ts">
  // IN-6 (Wave I-N): the League screen's first two blocks — "Power rankings" (every team by its best lineup's expected
  // points per week over the rest of the season; record, points and schedule beside it) and "Rest of season" (simulated
  // seasons of the weeks left: projected record, playoff odds, top seed, bye). Asked after the screen shows (GET
  // /api/league/outlook: up to a few seconds the first time on a league not kept every night). A table keeps the team
  // fixed and scrolls the rest at 375; bars for the numbers from 900 px. Every column header opens its definition.
  // IO-2 (Wave I-O): the power rankings first (`part=power`: no simulation), the rest of the season when it is ready;
  // movement (▲ ▼ places, the playoff odds' change) only from last week's kept ranking (the API's `moved`).
  import { ApiError, get, peek, Unauthorized, outlookPath, outlookPowerPath, type LeagueOutlookMoved, type PowerRow } from "../../lib/api";
  import { errorWords } from "../../lib/decisions";
  import Card from "../Card.svelte";
  import { chance, gapTag, movedLabel, movedWords, oddsChange, ordinal, projectedRecord, record, scheduleLeft, titleWords, winsRange } from "./outlook";

  let { league, team, onauth, onload }: { league: string; team: number | null; onauth: () => void; onload?: (d: LeagueOutlookMoved) => void } = $props();

  let data = $state<LeagueOutlookMoved | null>(null);
  let error = $state<string | null>(null);
  let seasonError = $state<string | null>(null); // ---- IO-2: the season block's own failure (the rankings stay)
  $effect(() => {
    const l = league;
    const t = team;
    error = null;
    seasonError = null;
    const path = outlookPath(l, t);
    const hit = peek<LeagueOutlookMoved>(path);
    if (hit) {
      data = hit;
      return;
    }
    const quick = peek<LeagueOutlookMoved>(outlookPowerPath(l, t));
    data = quick ?? null;
    const same = () => league === l && team === t;
    const why = (e: unknown) => (e instanceof ApiError && e.status === 404 && e.message ? e.message : errorWords(e)); // the API's reason
    let tries = 0;
    const ask = () =>
      get<LeagueOutlookMoved>(path)
        .then((d) => {
          if (same()) data = d;
        })
        .catch((e) => {
          if (!same()) return;
          if (e instanceof Unauthorized) return onauth();
          // one season simulation at a time on the server: a 429 `busy` is asked again a few seconds later (3 times)
          const busy = e instanceof ApiError && e.status === 429 && (e.body as { code?: string } | null)?.code === "busy";
          if (busy && tries++ < 3) {
            setTimeout(() => {
              if (same()) void ask();
            }, 3000);
            return;
          }
          if (data) seasonError = why(e);
          else error = why(e);
        });
    if (quick) {
      void ask();
      return;
    }
    // the power rankings first (no simulation: the first paint of a league not kept every night), then the season
    get<LeagueOutlookMoved>(outlookPowerPath(l, t))
      .then((d) => {
        if (!same()) return;
        if (!data) data = d;
        void ask();
      })
      .catch((e) => {
        if (!same()) return;
        if (e instanceof Unauthorized) return onauth();
        void ask();
      });
  });
  $effect(() => {
    if (data) onload?.(data);
  });

  // one definition open per block (a header tap opens it; the same tap closes it)
  let defPower = $state<string | null>(null);
  let defSeason = $state<string | null>(null);
  const power = $derived(data?.power.rows ?? []);
  const n = $derived(power.length);
  const byId = $derived(new Map(power.map((p) => [p.roster_id, p])));
  const perMax = $derived(Math.max(1, ...power.map((p) => p.per_week)));
  const perMin = $derived(Math.max(0, Math.min(...power.map((p) => p.per_week)) - 15));
  const ol = $derived(data?.outlook);
  const showPlayoff = $derived(!!ol && ol.available && ol.playoff_teams != null);
  const showBye = $derived(showPlayoff && !!ol?.byes);
  const showTitle = $derived(showPlayoff && !!ol?.title); // ---- IO-2: title odds
  const games = $derived.by(() => {
    const p = power[0];
    const r = ol?.rows[0];
    return p && r ? p.wins + p.losses + p.ties + r.games_left : 0;
  });
  function name(id: number): string {
    return byId.get(id)?.team_name ?? `Team ${id}`;
  }
  function toggle(which: "power" | "season", key: string) {
    if (which === "power") defPower = defPower === key ? null : key;
    else defSeason = defSeason === key ? null : key;
  }
  const weeksWords = $derived.by(() => {
    const w = ol?.weeks ?? [];
    return w.length > 1 ? `weeks ${w[0]}–${w[w.length - 1]}` : w.length ? `week ${w[0]}` : "";
  });
</script>

{#snippet head(which: "power" | "season", key: string, label: string, cls = "")}
  {@const open = (which === "power" ? defPower : defSeason) === key}
  <th scope="col" class="px-2 py-1.5 align-bottom font-semibold {cls}">
    <button
      type="button"
      class="ll-label inline-flex items-center gap-1 text-left leading-tight {open ? 'text-accent' : ''}"
      aria-expanded={open}
      onclick={() => toggle(which, key)}
      data-testid={`def-${key}`}>{label}<span class="text-ink-3" aria-hidden="true">ⓘ</span></button
    >
  </th>
{/snippet}

{#snippet teamCell(p: PowerRow | undefined, id: number, mine: boolean)}
  <th scope="row" class="ll-fix sticky left-0 z-10 min-w-0 px-3 py-2 text-left font-normal {mine ? 'bg-accent-row' : 'bg-surface'}">
    {#if mine}<span class="absolute inset-y-1 left-0 w-1 rounded-r bg-accent" aria-hidden="true"></span>{/if}
    <span class="line-clamp-2 block text-sm leading-tight font-semibold break-words wide:text-base">{p?.team_name ?? name(id)}{mine ? " (you)" : ""}</span>
    {#if p?.manager_name}<span class="hidden truncate text-xs text-ink-3 wide:block">{p.manager_name}</span>{/if}
  </th>
{/snippet}

{#if error}
  <p class="ll-empty text-sm" data-testid="outlook-error">No power rankings for this league right now: {error}</p>
{:else if !data}
  <div class="grid grid-cols-1 gap-4" aria-label="Loading the power rankings" data-testid="outlook-loading">
    <div class="ll-skel h-48"></div>
  </div>
{:else}
  <div class="grid grid-cols-1 gap-4" data-testid="outlook">
    <Card title="Power rankings" pad={false} testid="power">
      <div class="space-y-1 px-4 pb-2 text-sm text-ink-2">
        <p data-testid="power-words">{data.power.words}</p>
        {#if data.power.note}<p class="text-ink-3">{data.power.note}</p>{/if}
        {#if defPower}<p class="rounded-md bg-raised px-3 py-2 text-ink" data-testid="league-def">{data.definitions[defPower]}</p>{/if}
      </div>
      <div class="ll-scroll overflow-x-auto" data-testid="power-scroll">
        <table class="w-full border-collapse text-sm">
          <thead class="border-b border-line text-left text-ink-3">
            <tr>
              <th scope="col" class="ll-fix sticky left-0 z-10 bg-surface px-3 py-1.5 text-left align-bottom"><span class="ll-label">Team</span></th>
              {@render head("power", "power", "Per week", "text-right wide:w-[34%]")}
              {@render head("power", "record", "Record · points for")}
              {@render head("power", "points_against", "Against", "text-right")}
              {@render head("power", "schedule_left", "Schedule left")}
            </tr>
          </thead>
          <tbody class="divide-y divide-line">
            {#each power as p (p.roster_id)}
              <tr class={p.mine ? "bg-accent-row" : ""} data-testid="power-row" data-yours={p.mine ? "1" : undefined}>
                {@render teamCell(p, p.roster_id, p.mine)}
                <td class="px-2 py-2 text-right whitespace-nowrap">
                  <div class="flex items-center justify-end gap-2">
                    <span class="hidden h-2 flex-1 overflow-hidden rounded-sm bg-sunken wide:block" aria-hidden="true">
                      <span class="block h-full rounded-r-sm" style="width:{(Math.max(0, p.per_week - perMin) / Math.max(1, perMax - perMin)) * 100}%;background:{p.mine ? 'var(--ll-accent)' : 'var(--ll-series-1)'}"></span>
                    </span>
                    {#if p.moved != null}<span
                        class="tabnum shrink-0 text-xs font-semibold {p.moved > 0 ? 'text-good' : p.moved < 0 ? 'text-bad' : 'text-ink-3'}"
                        title={movedLabel(p.moved)}
                        aria-label={movedLabel(p.moved)}
                        data-testid="moved">{movedWords(p.moved)}</span
                      >{/if}<!-- IO-2 -->
                    <span class="tabnum min-w-[4.75rem] pr-1 text-right text-base font-semibold"><span class="text-xs text-ink-3">{p.rank}.</span> {p.per_week.toFixed(1)}</span>
                  </div>
                </td>
                <td class="px-2 py-2 whitespace-nowrap">
                  <span class="tabnum font-semibold">{record(p.wins, p.losses, p.ties)}</span>
                  {#if p.points_for != null}<span class="tabnum text-ink-2"> · {Math.round(p.points_for)} ({ordinal(p.points_for_rank ?? 0)})</span>{/if}
                  {#if gapTag(p)}<span class="block text-xs text-ink-3" title={p.gap_words ?? ""} data-testid="gap">{gapTag(p)}</span>{/if}
                </td>
                <td class="tabnum px-2 py-2 text-right whitespace-nowrap text-ink-2">{p.points_against != null ? Math.round(p.points_against) : "—"}</td>
                <td class="tabnum px-2 py-2 whitespace-nowrap text-ink-2">{scheduleLeft(p, n)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="px-4 pt-2 pb-3 text-xs text-ink-3" data-testid="no-arrows">{data.power.movement_note}</p>
    </Card>

    <Card title="Rest of season" pad={false} testid="season">
      {#if ol?.pending && seasonError}
        <p class="px-4 pb-4 text-base text-ink-2" data-testid="season-error">No outlook for the rest of the season right now: {seasonError}</p>
      {:else if ol?.pending}
        <!-- ---- IO-2: the rankings are on screen; the season is being played out -->
        <div class="space-y-2 px-4 pb-4" aria-label="Simulating the rest of the season" data-testid="season-pending">
          <p class="text-sm text-ink-3">Playing out the rest of the season…</p>
          <div class="ll-skel h-24"></div>
        </div>
      {:else if !ol || !ol.available}
        <p class="px-4 pb-4 text-base text-ink-2" data-testid="no-outlook">No outlook for the rest of the season: {ol?.reason ?? "not available"}.</p>
      {:else}
        <div class="space-y-1 px-4 pb-2 text-sm text-ink-2">
          <p data-testid="season-words">
            {ol.seasons.toLocaleString("en-US")} simulated seasons of {weeksWords}: each game drawn from both lineups' ranges, the same pieces as this week's odds{showPlayoff
              ? `. ${ol.playoff_teams} teams make the playoffs; a tie on wins goes to points for.`
              : "."}
          </p>
          <p class="text-ink-3" data-testid="season-assumes">It assumes {ol.assumptions.join("; ")}.</p>
          <p class="text-ink-3" data-testid="season-honest">Context, not a graded forecast: the weekly pieces are graded; the season outlook has only been replayed on two past seasons of two leagues.</p>
          {#if ol.playoff_reason}<p class="text-ink-3" data-testid="no-playoff">No playoff odds: {ol.playoff_reason}.</p>{/if}
          {#if defSeason}<p class="rounded-md bg-raised px-3 py-2 text-ink" data-testid="league-def">{data.definitions[defSeason]}</p>{/if}
        </div>
        <div class="ll-scroll overflow-x-auto" data-testid="season-scroll">
          <table class="w-full border-collapse text-sm">
            <thead class="border-b border-line text-left text-ink-3">
              <tr>
                <th scope="col" class="ll-fix sticky left-0 z-10 bg-surface px-3 py-1.5 text-left align-bottom"><span class="ll-label">Team</span></th>
                {@render head("season", "projected_record", "Projected record", "wide:w-[30%]")}
                {#if showPlayoff}{@render head("season", "playoff_odds", "Playoffs", "wide:w-[26%]")}{/if}
                {@render head("season", "top_seed", "Top seed", "text-right")}
                {#if showBye}{@render head("season", "bye", "Bye", "text-right")}{/if}
                {#if showTitle}{@render head("season", "title", "Title", "text-right")}{/if}<!-- IO-2 -->
              </tr>
            </thead>
            <tbody class="divide-y divide-line">
              {#each ol.rows as o (o.roster_id)}
                {@const p = byId.get(o.roster_id)}
                <tr class={o.mine ? "bg-accent-row" : ""} data-testid="season-row" data-yours={o.mine ? "1" : undefined}>
                  {@render teamCell(p, o.roster_id, o.mine)}
                  <td class="px-2 py-2 whitespace-nowrap">
                    <div class="flex items-center gap-3">
                      <span class="min-w-[4.5rem]">
                        <span class="tabnum block font-semibold">{projectedRecord(o, p)}</span>
                        <span class="tabnum block text-xs text-ink-3">{winsRange(o)}</span>
                      </span>
                      {#if games}
                        <!-- the middle 80% of the win totals as a band, the average as a tick (0 … the season's games) -->
                        <span class="relative hidden h-2 flex-1 rounded-sm bg-sunken wide:block" aria-hidden="true">
                          <span class="absolute inset-y-0 rounded-sm" style="left:{(o.wins_p10 / games) * 100}%;width:{(Math.max(0.15, o.wins_p90 - o.wins_p10) / games) * 100}%;background:var(--ll-series-1);opacity:.45"></span>
                          <span class="absolute -inset-y-1 w-0.5 rounded-sm bg-ink" style="left:{(o.wins_mean / games) * 100}%"></span>
                        </span>
                      {/if}
                    </div>
                  </td>
                  {#if showPlayoff}
                    <td class="px-2 py-2 whitespace-nowrap">
                      <div class="flex items-center gap-2">
                        <span class="tabnum w-10 text-base font-semibold {o.status === 'clinched' ? 'text-good' : o.status === 'eliminated' ? 'text-ink-3' : ''}" data-testid="playoff-odds">{chance(o.playoff, o.status)}</span>
                        <span class="hidden h-2 flex-1 overflow-hidden rounded-sm bg-sunken wide:block" aria-hidden="true">
                          <span class="block h-full rounded-r-sm" style="width:{(o.playoff ?? 0) * 100}%;background:{o.mine ? 'var(--ll-accent)' : 'var(--ll-series-1)'}"></span>
                        </span>
                      </div>
                      {#if oddsChange(o.playoff_change)}<span class="tabnum block text-xs whitespace-nowrap {(o.playoff_change ?? 0) > 0 ? 'text-good' : 'text-bad'}" data-testid="odds-change">{oddsChange(o.playoff_change)}</span>{/if}<!-- IO-2 -->
                    </td>
                  {/if}
                  <td class="tabnum px-2 py-2 text-right whitespace-nowrap text-ink-2">{chance(o.top_seed, o.status === "eliminated" ? "eliminated" : null)}</td>
                  {#if showBye}<td class="tabnum px-2 py-2 text-right whitespace-nowrap text-ink-2">{chance(o.bye, o.status === "eliminated" ? "eliminated" : null)}</td>{/if}
                  {#if showTitle}<td class="tabnum px-2 py-2 text-right font-semibold whitespace-nowrap" data-testid="title-odds">{chance(o.title, o.status === "eliminated" ? "eliminated" : null)}</td>{/if}<!-- IO-2 -->
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        {#if showTitle && ol.bracket}
          <!-- ---- IO-2: the bracket, said once; never graded -->
          <p class="px-4 pt-2 pb-3 text-xs text-ink-3" data-testid="title-words">{titleWords(ol.playoff_teams ?? 0, ol.byes ?? 0, ol.bracket)}</p>
        {:else}
          <p class="px-4 pt-2 pb-3 text-xs text-ink-3" data-testid="no-title">No title odds: {ol.title_reason ?? "the playoff bracket is not simulated"}.</p>
        {/if}
      {/if}
    </Card>
  </div>
{/if}

<style>
  /* the team column stays put while the numbers scroll (a phone); an opaque cell hides what slides under it */
  .ll-fix {
    width: 8.75rem;
    min-width: 8.75rem;
    max-width: 8.75rem;
    box-shadow: 1px 0 0 var(--ll-line);
  }
  @media (min-width: 900px) {
    .ll-fix {
      width: 15rem;
      min-width: 15rem;
      max-width: 15rem;
    }
  }
  .ll-scroll {
    overscroll-behavior-x: contain;
  }
  :global(.bg-accent-row) {
    background: color-mix(in srgb, var(--ll-accent) 12%, var(--ll-surface));
  }
</style>
