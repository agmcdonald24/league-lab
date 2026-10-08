<script lang="ts">
  import { APP_NAME } from "../lib/brand";
  // About the numbers (Wave G; was "Our record", plan F2): where the projections come from — the model explanation
  // (the Streamlit Rankings page's "The model" words: what it learned from, what it predicts, the ranges, how it was
  // graded, what it does not know, what we tried) — then the record against Sleeper's own projections, week by week
  // (GET /api/record: the summary and two numbers, the start/sit table, the by-position table, "How to read this").
  import { aboutPath, paths, type AboutAnswer, type RecordAnswer } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { aboutSections, MODEL_ANSWER } from "../lib/about";
  import { RECORD_HOWTO, recordView } from "../lib/record";
  import { withContext } from "../lib/md"; // ---- V-2: the link to the Team page
  import { Remote } from "../lib/remote.svelte";
  import Card from "../components/Card.svelte";
  import Expander from "../components/Expander.svelte";
  import Md from "../components/Md.svelte";
  import Metrics from "../components/Metrics.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import Bar from "../components/Bar.svelte";
  import StatTile from "../components/StatTile.svelte";
  import Tabs from "../components/Tabs.svelte";

  let { options, league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props(); // V-2: team

  const r = new Remote<RecordAnswer>();
  $effect(() => r.load(paths.record(league), onauth));

  const name = $derived(options.find((o) => o.league_id === league)?.name ?? "this league");
  const view = $derived(r.data ? recordView(r.data, name) : null);
  const sections = $derived(aboutSections(view?.leagueName ?? name));
  const num = (v: number | null | undefined, d = 0) => (v === null || v === undefined ? "—" : v.toFixed(d));

  // H1 (Wave H): what the projection leans on most and its grades (GET /api/about)
  const ab = new Remote<AboutAnswer>();
  $effect(() => ab.load(aboutPath(league), onauth));
  let impPos = $state("QB");
  const imp = $derived(ab.data?.importance ?? null);
  const impRows = $derived(imp?.positions.find((p) => p.position === impPos) ?? imp?.positions[0] ?? null);
  const impMax = $derived(Math.max(0.05, ...(impRows?.features ?? []).map((f) => f.importance ?? 0)));
  const grades = $derived(ab.data?.grades ?? null);
  const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);
  const GRADES_HOWTO = $derived((grades?.howto ?? []).map((h) => `- ${h}`).join("\n"));

  // ---- V-1 (Wave I-G): the decision record block (GET /api/record `decisions`)
  const dec = $derived(r.data?.decisions ?? null);
  const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}`;
  const DECISIONS_HOWTO = [
    "- **Ours** is the lineup we recommended for each team before the week's first kickoff, kept since: later news does not change it.",
    "- **Started** is what each team really started, at Sleeper's points. **Best** is the best lineup the same roster could have started knowing the scores — nobody can do that; it shows how much was left on the bench.",
    "- **Added** is ours minus started: what following our lineups would have added (below zero: the managers' own lineups did better).",
    "- **Coin flips** are the cards' closest calls (under 55%). **Landed** counts the weeks the player we started outscored the one on the bench (a tie counts half); **expected** is what our percentages said. Over a season the two should be close.",
    "- A week marked with a star was played before this record existed: its lineups were rebuilt from the projections locked then, with the final injury report — kinder to us than a real Thursday-morning call.",
  ].join("\n");
  // ---- end V-1
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

  <!-- ---- N1 (Wave I-D): where the card's news line comes from (docs/ESPN_TERMS.md) -->
  <p class="text-sm leading-snug text-ink-3" data-testid="about-news-source">
    The news line on a player's card is the latest headline from ESPN's public player news (RotoWire's updates and ESPN's own stories), with its source and a link to ESPN; {APP_NAME} keeps only the headline, its date, the source and the link.<!-- IG-2: was "keeps none of it" -->
  </p>
  <!-- ---- end N1 -->
  <!-- ---- IG-2 (Wave I-G): the event store (docs/HOSTING.md § "Events") -->
  <p class="text-sm leading-snug text-ink-3" data-testid="about-events">
    {APP_NAME} keeps a record of what it showed: each injury-report change, headline and brief, with its source, link and time, so the advice can point to the news behind it.
  </p>
  <!-- ---- end IG-2 -->
  <!-- ---- N2: PlayerWire's briefs come first on the news line (docs/PLAYERWIRE.md) -->
  <p class="text-sm leading-snug text-ink-3" data-testid="about-news-playerwire">
    Some cards show a PlayerWire brief first: a short note on the player that a person checked before it was published, with its source, a link to it, and whether the news is official, reported, corroborated or disputed. A brief that is taken back disappears from the card.
  </p>
  <!-- ---- end N2 -->

  {#if imp}
    <section class="space-y-3" data-testid="importance">
      <h2 class="text-xl font-extrabold tracking-tight">What it leans on most</h2>
      <p class="text-sm leading-snug text-ink-3" data-testid="importance-tops">
        {imp.positions.map((p) => `${p.position}: ${p.top.charAt(0).toLowerCase()}${p.top.slice(1)}`).join(" · ")}
      </p>
      <Tabs items={imp.positions.map((p) => ({ key: p.position, label: p.position }))} current={impRows?.position ?? impPos} onpick={(k) => (impPos = k)} size="sm" label="Position" testid="importance-pos" />
      {#if impRows}
        <Card testid="importance-card">
          <p class="text-base leading-snug" data-testid="importance-lead"><Md text={impRows.lead} /></p>
          <div class="mt-3 space-y-2.5" data-testid="importance-bars">
            {#each impRows.features as f, ix (`${f.rank}#${ix}`)}
              <Bar label={`${f.rank}. ${f.feature_label}`} value={f.importance} max={impMax} display={f.importance === null ? "—" : `+${f.importance.toFixed(2)}`} testid="importance-bar" />
            {/each}
          </div>
          <p class="mt-3 text-sm text-ink-3">{imp.unit}</p>
        </Card>
      {/if}
      <p class="text-sm leading-snug text-ink-3" data-testid="importance-how">{imp.how_measured}</p>
    </section>
  {/if}

  {#if grades}
    <section class="space-y-3" data-testid="grades">
      <h2 class="text-xl font-extrabold tracking-tight">How the model is doing</h2>
      <p class="text-base leading-snug" data-testid="grades-answer">{grades.answer}</p>
      <!-- ---- IG-3: the grades' qualification next to the headline grade (a league we do not score every night) -->
      {#if ab.data?.grade_note}
        <p class="rounded-md bg-raised px-3 py-2 text-sm leading-snug text-ink" data-testid="grades-qualification">{ab.data.grade_note}</p>
      {/if}
      <!-- ---- end IG-3 -->
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 wide:grid-cols-4">
        {#each grades.positions as g, ix (`${g.position}#${ix}`)}
          <Card title={g.position} testid="grade-card">
            <div class="grid grid-cols-2 gap-2">
              <StatTile label="Order · this season" value={num(g.season.spearman, 2)} caption={`backtest ${num(g.backtest.spearman, 2)}`} size="sm" testid="grade-order" />
              <StatTile label="Avg miss · this season" value={num(g.season.mae, 1)} caption={`backtest ${num(g.backtest.mae, 1)} points`} size="sm" testid="grade-miss" />
              <StatTile label="Inside the range" value={pct(g.season.coverage_80)} caption={`backtest ${pct(g.backtest.coverage_80)} · aim 80%`} size="sm" testid="grade-range" />
              <StatTile label="Weeks scored" value={g.season.weeks_scored} caption={grades.backtest_seasons ? `backtest ${grades.backtest_seasons}` : null} size="sm" />
            </div>
          </Card>
        {/each}
      </div>
      <Expander title="How to read the grades" testid="grades-howto"><Md text={GRADES_HOWTO} block class="text-base leading-snug" /></Expander>
      {#if ab.data?.rankings_howto}
        <!-- IA-3 (PO merge): the same paragraph the rest-of-season screen shows under its answer -->
        <Expander title="How to read the rankings" testid="rankings-howto"><Md text={ab.data.rankings_howto} block class="text-base leading-snug" /></Expander>
      {/if}
    </section>
  {/if}
  {#if ab.data?.why}<p class="text-sm leading-snug text-ink-3" data-testid="about-why">{ab.data.why}</p>{/if}

  <!-- ---- IR-4 (Wave I-R): what changed and when; what each number has been checked against (api provenance.py) -->
  {#if ab.data?.versions}
    {@const v = ab.data.versions}
    <section class="space-y-3" data-testid="about-versions">
      <h2 class="text-xl font-extrabold tracking-tight" id="versions">What changed and when</h2>
      <p class="text-base leading-snug">{v.words} Now: {v.current}{v.kd ? ` (kickers and defenses ${v.kd})` : ""}{v.published_words ? `, data published ${v.published_words}` : ""}.</p>
      <ol class="divide-y divide-line rounded-lg border border-line bg-surface text-base" data-testid="about-versions-list">
        {#each v.list as x, ix (`${x.version}#${ix}`)}
          <li class="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 px-3 py-2 sm:grid-cols-[4.5rem_10rem_minmax(0,1fr)]">
            <span class="tabnum text-ink-3">{x.date_words}</span>
            <span class="font-semibold">{x.version}</span>
            <span class="col-span-2 leading-snug text-ink-2 sm:col-span-1">{x.words}</span>
          </li>
        {/each}
      </ol>
      {#if v.by_week}<p class="text-sm leading-snug text-ink-3" data-testid="about-versions-weeks">This season's weeks, by the version they were made with: {v.by_week}.</p>{/if}
    </section>
  {/if}
  {#if ab.data?.checked}
    {@const c = ab.data.checked}
    {@const two = (x: number | null | undefined) => (x === null || x === undefined ? "—" : x.toFixed(2))}
    {@const one = (x: number | null | undefined) => (x === null || x === undefined ? "—" : x.toFixed(1))}
    <section class="space-y-3" data-testid="about-checked">
      <h2 class="text-xl font-extrabold tracking-tight" id="checked">What each number has been checked against</h2>
      <p class="text-base leading-snug">{c.head}</p>
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 wide:grid-cols-3">
        {#each c.rows as r, ix (`${r.position}#${ix}`)}
          <Card title={r.position} testid="about-checked-card">
            <dl class="space-y-1.5 text-sm leading-snug">
              {#if r.next}<div><dt class="inline font-semibold">Next week:</dt> <dd class="inline">{r.next.words} · order {two(r.next.order)} · miss {one(r.next.mae)}</dd></div>{/if}
              {#if r.later}<div><dt class="inline font-semibold">Two to eight weeks ahead:</dt> <dd class="inline">{r.later.words} · order {two(r.later.order)} · miss {one(r.later.mae)}</dd></div>{/if}
              {#if r.next4}<div><dt class="inline font-semibold">Next four weeks:</dt> <dd class="inline">order {two(r.next4.order)} · miss {one(r.next4.mae)}{r.next4.base_order !== null ? ` (his own record: ${two(r.next4.base_order)} · ${one(r.next4.base_mae)})` : ""}</dd></div>{/if}
              {#if r.ros}<div><dt class="inline font-semibold">Rest of season:</dt> <dd class="inline">order {two(r.ros.order)} · miss {one(r.ros.mae)}{r.ros.base_order !== null ? ` (his own record: ${two(r.ros.base_order)} · ${one(r.ros.base_mae)})` : ""}</dd></div>{/if}
            </dl>
          </Card>
        {/each}
      </div>
      <p class="text-sm leading-snug text-ink-3" data-testid="about-checked-windows">{c.windows_words}</p>
      {#if c.useful}<p class="text-base leading-snug" data-testid="about-useful">{c.useful.words}</p>{/if}
      <div class="text-sm leading-snug text-ink-2" data-testid="about-not-graded">
        <p class="font-semibold">Not graded yet:</p>
        <ul class="list-disc pl-5">{#each c.not_graded as n, ix (ix)}<li>{n}</li>{/each}</ul>
      </div>
      <p class="text-sm leading-snug text-ink-3" data-testid="about-checked-rule">{c.rule}</p>
    </section>
  {/if}
  <!-- ---- end IR-4 -->

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
      <!-- ---- M4 (Wave I-G): how the weeks were priced, one sentence (GET /api/record `pricing.sentence`) -->
      {#if r.data?.pricing?.sentence}<p class="text-sm leading-snug text-ink-3" data-testid="record-pricing">{r.data.pricing.sentence}</p>{/if}

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
                {#each view.calls as w, ix (`${w.week}#${ix}`)}
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
      <!-- ---- V-1 (Wave I-G): our lineups against the ones started (GET /api/record `decisions`; METRICS § "The decision record") -->
      {#if dec?.available && dec.season_totals}
        {@const tot = dec.season_totals}
        {@const cf = dec.calls?.coin_flips}
        <div class="space-y-2.5" data-testid="record-decisions">
          <h3 class="ll-label">Our lineups against the ones started</h3>
          {#if dec.sentences?.edge}<p class="text-base leading-snug" data-testid="decisions-edge">{dec.sentences.edge}</p>{/if}
          <!-- ---- IR-4: the qualifier right under the claim it qualifies (was at the foot of the block) -->
          {#if dec.note}<p class="text-sm leading-snug text-ink-3" data-testid="decisions-note">* {dec.note}</p>{/if}
          <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <StatTile label="Our lineups would have added" value={signed(tot.edge)} unit="pts" caption={`${signed(tot.edge / tot.roster_weeks)} per team per week`} size="sm" testid="decisions-tile-edge" />
            <StatTile label="Best lineup in hindsight" value={`+${tot.regret.toFixed(1)}`} unit="pts" caption={`${(tot.regret / tot.roster_weeks).toFixed(1)} per team per week over the one started`} size="sm" testid="decisions-tile-regret" />
            {#if cf && cf.n && cf.won !== null && cf.expected !== null}
              <StatTile label="Coin flips landed" value={`${Math.round((100 * cf.won) / cf.n)}%`} caption={`${Math.round((100 * cf.expected) / cf.n)}% expected · ${cf.n} calls`} size="sm" testid="decisions-tile-flips" />
            {/if}
          </div>
          <div class="overflow-hidden rounded-lg border border-line bg-surface">
            <table class="w-full table-fixed border-collapse text-base" data-testid="decisions-table">
              <thead>
                <tr class="ll-label border-b border-line bg-raised text-left">
                  <th class="w-[3.25rem] px-3 py-2 font-semibold">Week</th>
                  <th class="py-2 text-right font-semibold">Started</th>
                  <th class="py-2 text-right font-semibold">Ours</th>
                  <th class="py-2 text-right font-semibold">Best</th>
                  <th class="py-2 pr-3 text-right font-semibold">Added</th>
                </tr>
              </thead>
              <tbody>
                {#each dec.weeks ?? [] as w, ix (`${w.week}#${ix}`)}
                  <tr class="border-b border-line last:border-0">
                    <td class="tabnum px-3 py-2">{w.week}{w.record_source === "reconstructed" ? "*" : ""}</td>
                    <td class="tabnum py-2 text-right">{w.submitted.toFixed(1)}</td>
                    <td class="tabnum py-2 text-right">{w.app.toFixed(1)}</td>
                    <td class="tabnum py-2 text-right">{w.optimum.toFixed(1)}</td>
                    <td class="tabnum py-2 pr-3 text-right font-bold">{signed(w.edge)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
          <p class="text-sm leading-snug text-ink-3">Points summed over the league's {dec.weeks?.[0]?.rosters ?? ""} teams each week.</p>
          {#if dec.sentences?.calls}<p class="text-base leading-snug" data-testid="decisions-calls">{dec.sentences.calls}</p>{/if}
          {#if dec.sentences?.news}<p class="text-sm leading-snug text-ink-3" data-testid="decisions-news">{dec.sentences.news}</p>{/if}
          <!-- ---- V-2 (Wave I-H): Sleeper's projections as a lineup, and the way to your own team's calls -->
          {#if dec.sentences?.market}<p class="text-base leading-snug" data-testid="decisions-market">{dec.sentences.market}</p>{/if}
          {#if team !== null}
            <p class="text-base"><a class="ll-link" href={withContext("/team", { league, team })} data-testid="decisions-team-link">Your team's calls this season ›</a></p>
          {/if}
          <!-- ---- end V-2 -->
          <Expander title="How to read our lineups' record" testid="decisions-howto"><Md text={DECISIONS_HOWTO} block class="text-base leading-snug" /></Expander>
        </div>
      {:else if dec && !dec.available}
        <p class="text-sm leading-snug text-ink-3" data-testid="record-decisions-empty">Our lineups are graded against the ones started once a week on the record has been scored.</p>
      {/if}
      <!-- ---- end V-1 -->
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
              {#each view.byPosition as w, ix (`${w.week}-${w.position}#${ix}`)}
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
  <!-- ---- U-1: the usage notice (lib/usage.ts; docs/HOSTING.md § "Usage"); INF-1: and Google Analytics (lib/analytics.ts) -->
  <p class="mt-6 border-t border-line pt-3 text-sm text-ink-3" data-testid="usage-notice">{APP_NAME} counts screen views — which screen, which league and team, when — and nothing about you. It also uses Google Analytics: the same screen views and a few taps (a player opened, Compare, a trade evaluated, the link to edit your lineup), with the league and team numbers and the app's version — never your username, team name or password. Google sets a cookie to tell visits apart and sees your browser and rough location, as on any site that uses it.</p>
  <!-- ---- IK-4: the account's privacy line (docs/ACCOUNTS.md § "Built, phase 1") -->
  <p class="mt-2 text-sm text-ink-3" data-testid="account-notice">An account is optional. If you make one, {APP_NAME} keeps your email address if you give one, the names and public keys of your passkeys, the leagues and teams you save, your saved views and watchlist, and a Yahoo or ESPN connection only if you make one (encrypted) — nothing else, never a provider password — and screen counts never carry it. Delete it on the Account page at any time: everything goes at once.</p>
</main>
