<script lang="ts">
  // Our record (plan F2): League Lab's projections against Sleeper's own, week by week, in this league's scoring.
  // The answer first (the summary sentences and two numbers), then the start/sit table, the by-position table behind
  // an expander, "How to read this". The honest empty state when the API has no record (an unknown league, or no
  // week saved before kickoff yet): the Streamlit page's words.
  import { ApiError, get, paths, peek, Unauthorized, type RecordAnswer } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { RECORD_HOWTO, recordView } from "../lib/record";
  import { restoreScroll } from "../lib/router.svelte";
  import Expander from "../components/Expander.svelte";
  import Md from "../components/Md.svelte";
  import Metrics from "../components/Metrics.svelte";

  let { options, league, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  let data = $state<RecordAnswer | null>(null);
  let error = $state<string | null>(null);

  const name = $derived(options.find((o) => o.league_id === league)?.name ?? "this league");
  const view = $derived(data ? recordView(data, name) : null);
  const num = (v: number | null | undefined, d = 0) => (v === null || v === undefined ? "—" : v.toFixed(d));

  $effect(() => {
    const l = league;
    error = null;
    const path = paths.record(l);
    const hit = peek<RecordAnswer>(path);
    if (hit) {
      data = hit;
      restoreScroll();
      return;
    }
    data = null;
    get<RecordAnswer>(path)
      .then((d) => {
        if (league !== l) return;
        data = d;
        restoreScroll();
      })
      .catch((e) => {
        if (league !== l) return;
        if (e instanceof Unauthorized) onauth();
        else if (e instanceof ApiError && e.status === 404) error = "League Lab cannot find this league on Sleeper. Pick another above.";
        else if (e instanceof ApiError && e.status === 503) error = "The numbers are not ready yet. Try again in a few minutes.";
        else error = e instanceof Error ? e.message : String(e);
      });
  });
</script>


<main class="space-y-4" data-testid="record">
  <p class="text-[12px] font-semibold tracking-wide text-green-700 uppercase dark:text-green-400">Our record · {name}</p>
  {#if error}
    <p class="rounded-2xl border border-red-200 p-4 text-[15px] text-red-800 dark:border-red-900 dark:text-red-300">{error}</p>
  {:else if !view}
    <div class="animate-pulse space-y-3" aria-label="Loading" data-testid="loading">
      <div class="h-24 rounded-2xl bg-zinc-100 dark:bg-zinc-900"></div>
      <div class="h-32 rounded-2xl bg-zinc-100 dark:bg-zinc-900"></div>
    </div>
  {:else}
    <section
      class="space-y-2.5 rounded-2xl p-4 {view.kind === 'scored' || view.kind === 'starting'
        ? 'border border-zinc-200 dark:border-zinc-800'
        : 'bg-zinc-100 dark:bg-zinc-900'}"
      data-testid={view.kind === "scored" ? "record-answer" : "record-empty"}
    >
      <p class="text-[15px] leading-snug"><Md text={view.lines.join("  \n")} /></p>
      {#if view.metrics.length}<Metrics metrics={view.metrics} />{/if}
      {#if view.caption}<p class="text-[13px] leading-snug text-zinc-500 dark:text-zinc-400">{view.caption}</p>{/if}
    </section>

    {#if view.calls.length}
      <section class="space-y-2">
        <h2 class="text-[15px] font-semibold">Start/sit calls, week by week</h2>
        <table class="w-full table-fixed border-collapse text-[15px]" data-testid="record-table">
          <thead>
            <tr class="border-b border-zinc-200 text-left text-[11px] tracking-wide text-zinc-500 uppercase dark:border-zinc-800 dark:text-zinc-400">
              <th class="w-[3.25rem] py-1.5 pr-1 font-medium">Week</th>
              <th class="py-1.5 text-right font-medium">Calls</th>
              <th class="py-1.5 text-right font-medium">We got right</th>
              <th class="py-1.5 text-right font-medium">Sleeper got right</th>
              <th class="py-1.5 text-right font-medium">We differed</th>
            </tr>
          </thead>
          <tbody>
            {#each view.calls as w (w.week)}
              <tr class="border-b border-zinc-100 last:border-0 dark:border-zinc-800/70">
                <td class="tabnum py-2 pr-1">{w.week}</td>
                <td class="tabnum py-2 text-right">{num(w.pairs_n)}</td>
                <td class="tabnum py-2 text-right font-medium">{num(w.pairs_ours_right)}</td>
                <td class="tabnum py-2 text-right">{num(w.pairs_sleeper_right)}</td>
                <td class="tabnum py-2 text-right">{num(w.pairs_disagree)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    {/if}
    {#if view.byPosition.length}
      <Expander title="Projections by position, week by week" testid="record-positions">
        <table class="w-full table-fixed border-collapse text-[14px]" data-testid="record-positions-table">
          <thead>
            <tr class="border-b border-zinc-200 text-left text-[11px] tracking-wide text-zinc-500 uppercase dark:border-zinc-800 dark:text-zinc-400">
              <th class="w-[3rem] py-1.5 pr-1 font-medium">Week</th>
              <th class="w-[2.75rem] py-1.5 pr-1 font-medium">Pos</th>
              <th class="py-1.5 text-right font-medium">Our miss</th>
              <th class="py-1.5 text-right font-medium">Sleeper's miss</th>
              <th class="py-1.5 text-right font-medium">Our order</th>
            </tr>
          </thead>
          <tbody>
            {#each view.byPosition as w (`${w.week}-${w.position}`)}
              <tr class="border-b border-zinc-100 last:border-0 dark:border-zinc-800/70">
                <td class="tabnum py-1.5 pr-1">{w.week}</td>
                <td class="py-1.5 pr-1">{w.position}</td>
                <td class="tabnum py-1.5 text-right">{num(w.ours_mae, 2)}</td>
                <td class="tabnum py-1.5 text-right">{num(w.sleeper_mae, 2)}</td>
                <td class="tabnum py-1.5 text-right">{num(w.ours_spearman, 2)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </Expander>
    {/if}
    <Expander title="How to read this" testid="howto"><Md text={RECORD_HOWTO(view.leagueName)} block class="text-[14px] leading-snug" /></Expander>
  {/if}
</main>
