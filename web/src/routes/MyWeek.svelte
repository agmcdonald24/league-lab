<script lang="ts">
  import { ApiError, get, paths, peek, Unauthorized, type MyWeek, type Status, type UserLeagues } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import { learnLeagueName } from "../lib/names.svelte";
  import { checkedLine, opponentLine, recordLine } from "../lib/week";
  import type { Availability, AvailabilityStatus } from "../lib/shapes";
  import { restoreScroll } from "../lib/router.svelte";
  import Expander from "../components/Expander.svelte";
  import LineupTable from "../components/LineupTable.svelte";
  import Md from "../components/Md.svelte";

  let {
    options,
    league,
    team,
    mine,
    status,
    onauth,
  }: {
    options: LeagueOption[];
    league: string;
    team: number | null;
    mine: UserLeagues | null;
    status: Status | null;
    onauth: () => void;
  } = $props();

  let data = $state<MyWeek | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(false);

  const ctx = $derived({ league, team });
  const leagueRow = $derived(options.find((l) => l.league_id === league) ?? null);
  // the user signed in with a username and has no team in this league (a commissioner-only league)
  const noTeamHere = $derived(!!mine && !!leagueRow?.mine && leagueRow.roster_id === null);
  // Home's line "**Team** · 0-2, #10 in the league · week 4 vs **X**" without the team (shown as the heading); the
  // opponent gets its own line when the API sends the contract's object
  const record = $derived(data ? recordLine(data) : "");
  const versus = $derived(data ? opponentLine(data) : "");
  // I0-A: the availability overlay — when injuries were last checked, and who moved since the nightly build
  const avail = $derived((data as (MyWeek & { availability?: Availability | null }) | null)?.availability ?? null);
  const checked = $derived(
    checkedLine(avail?.checked_at ?? (status as (Status & { availability?: AvailabilityStatus }) | null)?.availability?.checked_at),
  );

  $effect(() => {
    const l = league;
    const t = team;
    error = null;
    if (t === null) {
      data = null;
      return;
    }
    const path = paths.myWeek(l, t);
    const hit = peek<MyWeek>(path);
    if (hit) {
      data = hit;
      learnLeagueName(hit.league_id, hit.league_name);
      loading = false;
      restoreScroll();
      return;
    }
    loading = true;
    get<MyWeek>(path)
      .then((d) => {
        if (league !== l || team !== t) return;
        data = d;
        learnLeagueName(d.league_id, d.league_name);
        loading = false;
        restoreScroll();
      })
      .catch((e) => {
        if (league !== l || team !== t) return;
        loading = false;
        data = null;
        if (e instanceof Unauthorized) onauth();
        else if (e instanceof ApiError && e.status === 404)
          error = /league/i.test(e.message) && !/team/i.test(e.message) ? "Sleeper has no league with that id. Check the link, or pick a league above."
                                                                       : "That team is not in this league. Pick your team above.";
        else if (e instanceof ApiError && e.status === 502) error = "Sleeper did not answer. Try again in a minute.";
        else if (e instanceof ApiError && e.status === 503) error = "The numbers are not ready yet. Try again in a few minutes.";
        else error = e instanceof Error ? e.message : String(e);
      });
  });
</script>


<main class="space-y-4" data-testid="my-week">
  {#if team === null}
    <div class="ll-empty" data-testid="pick-prompt">
      {#if noTeamHere}
        <p data-testid="no-team">
          You have no team in <strong>{leagueRow?.name}</strong> (you may run it without playing in it). Pick the team to see above: its
          lineup to start and its closest calls.
        </p>
      {:else}
        Pick your team above to see your week: the lineup to start and the closest calls.
      {/if}
      {#if leagueRow?.scoring_label}<p class="mt-1 text-sm text-ink-3">{leagueRow.scoring_label}</p>{/if}
    </div>
  {:else if error}
    <p class="ll-error">{error}</p>
  {:else if !data}
    <div class="space-y-3" aria-label="Loading" data-testid="loading">
      <div class="ll-skel h-7 w-2/3"></div>
      <div class="ll-skel h-4 w-1/2"></div>
      {#each [0, 1, 2] as i (i)}<div class="ll-skel h-24"></div>{/each}
    </div>
  {:else}
    <section class="space-y-1" class:opacity-60={loading}>
      <p class="text-label font-bold tracking-[0.08em] text-accent uppercase">
        {data.week ? `My week · week ${data.week}` : "My week"}
      </p>
      <h1 class="text-2xl leading-tight font-extrabold tracking-tight wide:text-3xl" data-testid="team-name">{data.team_name}</h1>
      {#if record}<p class="text-sm text-ink-2" data-testid="record-line"><Md text={record} {ctx} /></p>{/if}
      {#if versus}<p class="text-base leading-snug" data-testid="opponent-line"><Md text={versus} {ctx} /></p>{/if}
      {#if data.league_line}<p class="text-sm text-ink-2" data-testid="league-line"><Md text={data.league_line} {ctx} /></p>{/if}
      {#if checked}<p class="text-sm text-ink-3" data-testid="injuries-checked">{checked}</p>{/if}
      {#if status?.warning}
        <details class="text-sm text-warn" data-testid="stale-warning">
          <summary class="inline-flex items-center gap-1">⚠️ Injury news may be stale <span class="chev" aria-hidden="true">›</span></summary>
          <p class="mt-1 leading-snug">{status.warning}</p>
        </details>
      {/if}
    </section>

    {#if data.week !== null}
      <div class="grid grid-cols-1 gap-4 wide:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] wide:items-start">
        <section class="space-y-2.5">
          <h2 class="ll-label">The calls that matter</h2>
          {#if data.cards.length === 0 && data.notice}
            <p class="rounded-lg bg-raised p-4 text-base" data-testid="no-calls"><Md text={data.notice} {ctx} /></p>
          {/if}
          {#each data.cards as c (c.slot)}
            <article class="relative space-y-1.5 overflow-hidden rounded-lg border border-line bg-surface p-4 pl-5" style="box-shadow:var(--ll-shadow)" data-testid="decision-card">
              {#each c.blocks as b, i (i)}
                {#if b.kind === "caption"}
                  <p class="text-sm leading-snug text-ink-3"><Md text={b.text} {ctx} /></p>
                {:else}
                  <p class="text-base leading-snug"><Md text={b.text} {ctx} /></p>
                {/if}
              {/each}
              <span class="absolute inset-y-0 left-0 w-1 bg-accent" aria-hidden="true"></span>
            </article>
          {/each}
        </section>

        <div class="space-y-3">
          <section class="space-y-2 rounded-lg border border-line bg-surface p-4" style="box-shadow:var(--ll-shadow)">
            <h2 class="ll-label">Your lineup</h2>
            {#if avail?.changes?.length}
              <ul class="space-y-1 text-sm leading-snug text-warn" data-testid="availability-changes">
                {#each avail.changes as c, i (i)}<li>{c}</li>{/each}
              </ul>
            {/if}
            {#if data.lineup.length}
              <LineupTable rows={data.lineup} {ctx} testid="lineup" />
            {:else}
              <p class="text-sm text-ink-3">No proposed lineup for this week yet.</p>
            {/if}
          </section>

          <Expander title="Your full lineup: every slot, how close each call is, the bench, and who can't play" testid="lineup-full">
            <LineupTable rows={data.lineup_full} full {ctx} testid="lineup-full-table" />
          </Expander>
          {#if data.howto}
            <Expander title="How to read this" testid="howto"><Md text={data.howto} {ctx} block class="text-base leading-snug" /></Expander>
          {/if}
          <Expander title="Movers on your roster (last 3 games vs before)" testid="movers">
            {#if data.movers.length === 0}
              <p class="text-sm text-ink-3">No trend calls yet — nothing is called before a player's fourth game.</p>
            {:else}
              <ul class="divide-y divide-line text-base">
                {#each data.movers as m, i (i)}
                  <li class="py-2">
                    {#if m.gsis_id}<a class="ll-link" href={withContext(`/player/${m.gsis_id}`, ctx)}>{m.player_name}</a>{:else}{m.player_name}{/if}
                    <span class="text-ink-3"> · {m.position}</span>
                    {#if m.momentum !== null}<span class="tabnum float-right text-ink-2">{m.momentum > 0 ? "+" : ""}{m.momentum.toFixed(2)}</span>{/if}
                    <div class="text-sm text-ink-3">{m.tags ?? ""}</div>
                  </li>
                {/each}
              </ul>
            {/if}
          </Expander>
          <a class="block rounded-lg border border-line bg-surface p-4 text-base font-semibold" href={withContext("/trends?who=mine", ctx)} data-testid="to-research"
            >Who on your roster is due, who is running hot <span class="text-accent">›</span></a
          >
        </div>
      </div>
    {:else if data.notice}
      <p class="rounded-lg bg-raised p-4">{data.notice}</p>
    {/if}
  {/if}

  {#if status?.freshness}
    <footer class="pt-2 text-xs leading-snug text-ink-3"><Md text={status.freshness} /></footer>
  {/if}
</main>
