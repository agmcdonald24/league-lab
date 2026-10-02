<script lang="ts">
  import { ApiError, get, paths, peek, Unauthorized, type MyWeek, type Status, type UserLeagues } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import { opponentLine, recordLine } from "../lib/week";
  import { restoreScroll } from "../lib/router.svelte";
  import Expander from "../components/Expander.svelte";
  import LineupTable from "../components/LineupTable.svelte";
  import Md from "../components/Md.svelte";
  import TopBar from "../components/TopBar.svelte";

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
      loading = false;
      restoreScroll();
      return;
    }
    loading = true;
    get<MyWeek>(path)
      .then((d) => {
        if (league !== l || team !== t) return;
        data = d;
        loading = false;
        restoreScroll();
      })
      .catch((e) => {
        if (league !== l || team !== t) return;
        loading = false;
        data = null;
        if (e instanceof Unauthorized) onauth();
        else if (e instanceof ApiError && e.status === 404) error = "That team is not in this league. Pick your team above.";
        else if (e instanceof ApiError && e.status === 502) error = "Sleeper did not answer. Try again in a minute.";
        else if (e instanceof ApiError && e.status === 503) error = "The numbers are not ready yet. Try again in a few minutes.";
        else error = e instanceof Error ? e.message : String(e);
      });
  });
</script>

<TopBar {options} {league} {team} {onauth} />

<main class="space-y-4 px-4 pb-10" data-testid="my-week">
  {#if team === null}
    <div class="rounded-2xl border border-dashed border-zinc-300 p-4 text-[15px] dark:border-zinc-700" data-testid="pick-prompt">
      {#if noTeamHere}
        <p data-testid="no-team">
          You have no team in <strong>{leagueRow?.name}</strong> (you may run it without playing in it). Pick the team to see above: its
          lineup to start and its closest calls.
        </p>
      {:else}
        Pick your team above to see your week: the lineup to start and the closest calls.
      {/if}
      {#if leagueRow?.scoring_label}<p class="mt-1 text-sm text-zinc-500">{leagueRow.scoring_label}</p>{/if}
    </div>
  {:else if error}
    <p class="rounded-2xl border border-red-200 p-4 text-[15px] text-red-800 dark:border-red-900 dark:text-red-300">{error}</p>
  {:else if !data}
    <div class="animate-pulse space-y-3" aria-label="Loading" data-testid="loading">
      <div class="h-7 w-2/3 rounded bg-zinc-200 dark:bg-zinc-800"></div>
      <div class="h-4 w-1/2 rounded bg-zinc-200 dark:bg-zinc-800"></div>
      {#each [0, 1, 2] as i (i)}<div class="h-24 rounded-2xl bg-zinc-100 dark:bg-zinc-900"></div>{/each}
    </div>
  {:else}
    <section class="space-y-1" class:opacity-60={loading}>
      <p class="text-[12px] font-semibold tracking-wide text-green-700 uppercase dark:text-green-400">
        {data.week ? `My week · week ${data.week}` : "My week"}
      </p>
      <h1 class="text-2xl leading-tight font-bold" data-testid="team-name">{data.team_name}</h1>
      {#if record}<p class="text-[14px] text-zinc-600 dark:text-zinc-300" data-testid="record-line"><Md text={record} {ctx} /></p>{/if}
      {#if versus}<p class="text-[15px] leading-snug" data-testid="opponent-line"><Md text={versus} {ctx} /></p>{/if}
      {#if data.league_line}<p class="text-[14px] text-zinc-600 dark:text-zinc-300" data-testid="league-line"><Md text={data.league_line} {ctx} /></p>{/if}
      {#if status?.warning}
        <details class="text-[13px] text-amber-800 dark:text-amber-300" data-testid="stale-warning">
          <summary class="inline-flex items-center gap-1">⚠️ Injury news may be stale <span class="chev" aria-hidden="true">›</span></summary>
          <p class="mt-1 leading-snug">{status.warning}</p>
        </details>
      {/if}
    </section>

    {#if data.week !== null}
      <section class="space-y-2.5">
        <h2 class="text-[15px] font-semibold">The calls that matter</h2>
        {#if data.cards.length === 0 && data.notice}
          <p class="rounded-2xl bg-zinc-100 p-4 text-[15px] dark:bg-zinc-900" data-testid="no-calls"><Md text={data.notice} {ctx} /></p>
        {/if}
        {#each data.cards as c (c.slot)}
          <article class="space-y-1.5 rounded-2xl border border-zinc-200 p-4 dark:border-zinc-800" data-testid="decision-card">
            {#each c.blocks as b, i (i)}
              {#if b.kind === "caption"}
                <p class="text-[13px] leading-snug text-zinc-500 dark:text-zinc-400"><Md text={b.text} {ctx} /></p>
              {:else}
                <p class="text-[15px] leading-snug"><Md text={b.text} {ctx} /></p>
              {/if}
            {/each}
          </article>
        {/each}
      </section>

      <section class="space-y-2">
        <h2 class="text-[15px] font-semibold">Your lineup</h2>
        {#if data.lineup.length}
          <LineupTable rows={data.lineup} {ctx} testid="lineup" />
        {:else}
          <p class="text-sm text-zinc-500">No proposed lineup for this week yet.</p>
        {/if}
      </section>

      <Expander title="Your full lineup: every slot, how close each call is, the bench, and who can't play" testid="lineup-full">
        <LineupTable rows={data.lineup_full} full {ctx} testid="lineup-full-table" />
      </Expander>
      {#if data.howto}
        <Expander title="How to read this" testid="howto"><Md text={data.howto} {ctx} block class="text-[14px] leading-snug" /></Expander>
      {/if}
      <Expander title="Movers on your roster (last 3 games vs before)" testid="movers">
        {#if data.movers.length === 0}
          <p class="text-sm text-zinc-500">
            No trend calls yet — nothing is called before a player's fourth game. The Trends page shows an early read.
          </p>
        {:else}
          <ul class="divide-y divide-zinc-100 text-[15px] dark:divide-zinc-800">
            {#each data.movers as m, i (i)}
              <li class="py-2">
                {#if m.gsis_id}<a class="ll-link" href={withContext(`/player/${m.gsis_id}`, ctx)}>{m.player_name}</a>{:else}{m.player_name}{/if}
                <span class="text-zinc-500"> · {m.position}</span>
                {#if m.momentum !== null}<span class="tabnum float-right text-zinc-600 dark:text-zinc-300">{m.momentum > 0 ? "+" : ""}{m.momentum.toFixed(2)}</span>{/if}
                <div class="text-[13px] text-zinc-500">{m.tags ?? ""}</div>
              </li>
            {/each}
          </ul>
        {/if}
      </Expander>
    {:else if data.notice}
      <p class="rounded-2xl bg-zinc-100 p-4 dark:bg-zinc-900">{data.notice}</p>
    {/if}
  {/if}

  {#if status?.freshness}
    <footer class="pt-2 text-[12px] leading-snug text-zinc-500 dark:text-zinc-400"><Md text={status.freshness} /></footer>
  {/if}
</main>
