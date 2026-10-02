<script lang="ts">
  // About the numbers (Wave G; was "Our record", plan F2): where the projections come from — the model explanation
  // (the Streamlit Rankings page's "The model" words: what it learned from, what it predicts, the ranges, how it was
  // graded, what it does not know, what we tried) — then the record against Sleeper's own projections, week by week
  // (GET /api/record: the summary and two numbers, the start/sit table, the by-position table, "How to read this").
  import { paths, type RecordAnswer } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { aboutSections, MODEL_ANSWER } from "../lib/about";
  import { RECORD_HOWTO, recordView } from "../lib/record";
  import { Remote } from "../lib/remote.svelte";
  import Card from "../components/Card.svelte";
  import Expander from "../components/Expander.svelte";
  import Md from "../components/Md.svelte";
  import Metrics from "../components/Metrics.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";

  let { options, league, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  const r = new Remote<RecordAnswer>();
  $effect(() => r.load(paths.record(league), onauth));

  const name = $derived(options.find((o) => o.league_id === league)?.name ?? "this league");
  const view = $derived(r.data ? recordView(r.data, name) : null);
  const sections = $derived(aboutSections(view?.leagueName ?? name));
  const num = (v: number | null | undefined, d = 0) => (v === null || v === undefined ? "—" : v.toFixed(d));
</script>

<main class="space-y-5" data-testid="about">
  <ScreenHead eyebrow={`About the numbers · ${name}`} title="Where the numbers come from">
    {#snippet answer()}<Md text={MODEL_ANSWER} />{/snippet}
  </ScreenHead>

  <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 wide:grid-cols-3" data-testid="model">
    {#each sections as s (s.key)}
      <Card title={s.title} testid={`model-${s.key}`}>
        <p class="text-base leading-snug text-ink-2"><Md text={s.text} /></p>
      </Card>
    {/each}
  </div>

  <section class="space-y-3" data-testid="record">
    <h2 class="text-xl font-extrabold tracking-tight" id="record">Our record against Sleeper's projections</h2>
    <p class="text-sm leading-snug text-ink-3">
      Every week we also save Sleeper's own projections (the ones in the Sleeper app) before the first kickoff, count them your league's way, and check after the
      games whose were closer and who called the start/sit decisions right.
    </p>
    {#if r.error}
      <p class="ll-error">{r.error}</p>
    {:else if !view}
      <div class="space-y-3" aria-label="Loading" data-testid="loading"><div class="ll-skel h-24"></div><div class="ll-skel h-32"></div></div>
    {:else}
      <div
        class="space-y-2.5 rounded-lg p-4 {view.kind === 'scored' || view.kind === 'starting' ? 'border border-line bg-surface' : 'bg-raised'}"
        style={view.kind === "scored" || view.kind === "starting" ? "box-shadow:var(--ll-shadow)" : undefined}
        data-testid={view.kind === "scored" ? "record-answer" : "record-empty"}
      >
        <p class="text-base leading-snug"><Md text={view.lines.join("  \n")} /></p>
        {#if view.metrics.length}<Metrics metrics={view.metrics} />{/if}
        {#if view.caption}<p class="text-sm leading-snug text-ink-3">{view.caption}</p>{/if}
      </div>

      {#if view.calls.length}
        <div class="space-y-2">
          <h3 class="ll-label">Start/sit calls, week by week</h3>
          <div class="overflow-hidden rounded-lg border border-line bg-surface">
            <table class="w-full table-fixed border-collapse text-base" data-testid="record-table">
              <thead>
                <tr class="ll-label border-b border-line bg-raised text-left">
                  <th class="w-[3.25rem] px-3 py-2 font-semibold">Week</th>
                  <th class="py-2 text-right font-semibold">Calls</th>
                  <th class="py-2 text-right font-semibold">We got right</th>
                  <th class="py-2 text-right font-semibold">Sleeper got right</th>
                  <th class="py-2 pr-3 text-right font-semibold">We differed</th>
                </tr>
              </thead>
              <tbody>
                {#each view.calls as w (w.week)}
                  <tr class="border-b border-line last:border-0">
                    <td class="tabnum px-3 py-2">{w.week}</td>
                    <td class="tabnum py-2 text-right">{num(w.pairs_n)}</td>
                    <td class="tabnum py-2 text-right font-bold">{num(w.pairs_ours_right)}</td>
                    <td class="tabnum py-2 text-right">{num(w.pairs_sleeper_right)}</td>
                    <td class="tabnum py-2 pr-3 text-right">{num(w.pairs_disagree)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      {/if}
      {#if view.byPosition.length}
        <Expander title="Projections by position, week by week" testid="record-positions">
          <table class="w-full table-fixed border-collapse text-sm" data-testid="record-positions-table">
            <thead>
              <tr class="ll-label border-b border-line text-left">
                <th class="w-[3rem] py-1.5 pr-1 font-semibold">Week</th>
                <th class="w-[2.75rem] py-1.5 pr-1 font-semibold">Pos</th>
                <th class="py-1.5 text-right font-semibold">Our miss</th>
                <th class="py-1.5 text-right font-semibold">Sleeper's miss</th>
                <th class="py-1.5 text-right font-semibold">Our order</th>
              </tr>
            </thead>
            <tbody>
              {#each view.byPosition as w (`${w.week}-${w.position}`)}
                <tr class="border-b border-line last:border-0">
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
      <Expander title="How to read the record" testid="howto"><Md text={RECORD_HOWTO(view.leagueName)} block class="text-base leading-snug" /></Expander>
    {/if}
  </section>
</main>
