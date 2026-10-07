<script lang="ts">
  import { ApiError, get, paths, peek, Unauthorized, type PlayerCard } from "../lib/api";
  import { cardHeadLine, cardMissing, cardSections, howtoWords } from "../lib/card"; // IG-1: projLabel (IP-4: now in the head)
  import { withContext } from "../lib/md";
  import { learnLeagueName } from "../lib/names.svelte";
  import { back, restoreScroll, route } from "../lib/router.svelte";
  import { fmt } from "../lib/theme";
  import Expander from "../components/Expander.svelte";
  import GameLog from "../components/GameLog.svelte";
  import Md from "../components/Md.svelte";
  import NewsLine from "../components/NewsLine.svelte"; // ---- N1
  import CardHead from "../components/card/CardHead.svelte"; // ---- IP-4: the card's head, ratings and charts
  import { panels } from "../components/card/lazy"; // the ratings and the charts: a chunk of their own
  import SectionBox from "../components/Section.svelte";
  import ScheduleTable from "../components/ScheduleTable.svelte"; // ---- IF-4
  import { isRef, PANE_FOOT, refLabel, refScoringLabel } from "../lib/refleague"; // ---- IN-2: browsing without a league

  let { gsis, league, team, onauth }: { gsis: string; league: string | null; team: number | null; onauth: () => void } = $props();

  let data = $state<PlayerCard | null>(null);
  let error = $state<string | null>(null);

  const ctx = $derived({ league, team });
  // ---- IN-2: browsing without a league, "home" is Players (My Week needs a league)
  const browsing = $derived(isRef(league));
  const home = $derived(withContext(browsing ? "/players" : "/", ctx));
  // the sections in the card's order (lib/card.ts: the research pane shows the same card)
  const sections = $derived(data ? cardSections(data) : []);
  const headLine = $derived(data ? cardHeadLine(data) : "");
  const missing = $derived(data ? cardMissing(data) : []);
  // ---- IP-4: the sections in the card's layout — this week (projection + why, availability + news) leads, then the
  // charts, then the rest in lib/card.ts's order; the scoring's name for the head
  const RATED = ["QB", "RB", "WR", "TE"];
  const LEAD = ["projection", "availability"];
  const lead = $derived(LEAD.map((k) => sections.find((x) => x.key === k)).filter((x) => !!x));
  const rest = $derived(sections.filter((x) => !LEAD.includes(x.key)));
  let innerW = $state(0);
  const wideScreen = $derived(innerW >= 900);
  const scoringWord = $derived(data ? (browsing ? refScoringLabel(league) : data.league_name) : "");
  // ---- end IP-4

  $effect(() => {
    const id = gsis;
    const l = league;
    const t = team;
    error = null;
    if (!l) return;
    const path = paths.player(id, l, t);
    const hit = peek<PlayerCard>(path);
    if (hit) {
      data = hit;
      restoreScroll();
      return;
    }
    data = null;
    get<PlayerCard>(path)
      .then((d) => {
        if (gsis !== id || league !== l) return;
        data = d;
        learnLeagueName(d.league_id, d.league_name);
        restoreScroll();
      })
      .catch((e) => {
        if (gsis !== id) return;
        if (e instanceof Unauthorized) onauth();
        else if (e instanceof ApiError && e.status === 404) error = `No player with id ${id}. Search for him above.`;
        else if (e instanceof ApiError && e.status === 502) error = "Sleeper did not answer. Try again in a minute.";
        else error = e instanceof Error ? e.message : String(e);
      });
  });
</script>

<svelte:window bind:innerWidth={innerW} /><!-- ---- IP-4: the chart's height -->

<!-- IB-1 (Wave I-B): the page sits in the app's frame (the tab bar, the search field are the top bar's); Back goes
     where you came from (My Week when the app was opened on this page) -->
<div class="-mt-1 mb-2 flex items-center">
  <button
    type="button"
    class="-ml-2 flex min-h-11 shrink-0 items-center gap-1 rounded-md px-2 text-base font-semibold text-accent"
    onclick={() => back(home)}
    data-testid="back"
  >
    <span aria-hidden="true" class="text-xl leading-none">‹</span>{route.current.depth > 0 ? "Back" : browsing ? "Players" : "My week"}
  </button>
</div>

<main class="space-y-3" data-testid="player">
  {#if error}
    <p class="ll-error">{error}</p>
  {:else if !data}
    <div class="space-y-3" aria-label="Loading" data-testid="loading">
      <div class="ll-skel h-32"></div>
      {#each [0, 1, 2] as i (i)}<div class="ll-skel h-28"></div>{/each}
    </div>
  {:else}
    <h1 class="sr-only" data-testid="player-name">{data.player_name}</h1>
    <!-- ---- IP-4 (Wave I-P): the card — the head (picture on his team's colour, one headline number: this week's
         projection and its range, his value), the ratings and the first chart, then every section the card had,
         reorganised: one column on a phone, two from 900 px, three from 1280 px (lib/card.ts's sections, unchanged) -->
    <CardHead d={data} line={headLine} scoring={scoringWord} testid="player-header" />
    <div class="grid grid-cols-1 gap-3 wide:grid-cols-12 wide:items-start">
      {#if RATED.includes(data.position)}
        <div class="wide:col-span-5 xl:col-span-4">{#await panels() then P}<P.Ratings gsis={data.gsis_id} position={data.position} {onauth} />{/await}</div>
      {/if}
      {#if league}
        <div class={RATED.includes(data.position) ? "wide:col-span-7 xl:col-span-8" : "wide:col-span-12"}>
          {#await panels() then P}<P.PointsChart gsis={data.gsis_id} {league} season={data.season} scoring={scoringWord} schedule={data.schedule ?? []} tall={wideScreen} position={data.position} />{/await}
        </div>
      {/if}
    </div>
    <div class="gap-3 wide:columns-2 xl:columns-3 [&>*]:mb-3 [&>*]:break-inside-avoid" data-testid="card-sections">
      {#each lead as x (x.key)}
        <SectionBox section={x.sec} {ctx} testid={`section-${x.key}`}>
          <!-- ---- IA-3 (Wave I-A): why this number, the market line, what the model leans on -->
          {#if x.key === "projection" && (data.why || data.market || data.leans_on)}
            <div class="space-y-1.5 border-t border-line pt-2.5" data-testid="player-why">
              {#if data.why}
                <p class="ll-label text-accent">Why this number</p>
                <p class="text-base leading-snug font-semibold" data-testid="player-why-sentence">{data.why.sentence}</p>
                <!-- ---- IE-2 (Wave I-E): the scoring arithmetic ("0.42 rushing TDs × 6.98715") is audit detail, not the
                     first answer about a player: under "How we calculated this", collapsed -->
                <Expander title="How we calculated this" testid="player-how">
                  <ul class="space-y-0.5 text-sm text-ink-2" data-testid="player-why-pieces">
                    {#each data.why.pieces as w (w.stat)}<li class="tabnum">{w.words}</li>{/each}
                  </ul>
                  <p class="mt-1 text-sm text-ink-2">His projected stat line, each piece counted in {browsing ? refScoringLabel(league) : data.league_name} scoring: they add up to the {fmt.pts(data.why.points)}.</p>
                </Expander>
                <!-- ---- end IE-2 -->
              {/if}
              {#if data.market?.words}
                <p class="text-base leading-snug {data.market.far ? 'font-semibold' : ''}" data-testid="player-market">{data.market.words}</p>
              {:else if data.market?.why}
                <p class="text-sm text-ink-3" data-testid="player-market-none">{data.market.why}</p>
              {/if}
              {#if data.leans_on}
                <p class="text-sm leading-snug text-ink-3" data-testid="player-leans"><Md text={data.leans_on.words} {ctx} /></p>
              {/if}
            </div>
          {/if}
          <!-- ---- end IA-3 -->
          <!-- ---- N1 (Wave I-D): the news line under the availability lines -->
          {#if x.key === "availability"}<NewsLine card={data} testid="player-news" />{/if}
          <!-- ---- end N1 -->
        </SectionBox>
      {/each}
      {#if league && RATED.includes(data.position)}{#await panels() then P}<P.RoleChart gsis={data.gsis_id} {league} season={data.season} position={data.position} />{/await}{/if}
      {#if league && data.position !== "DEF"}<GameLog gsis={data.gsis_id} {league} season={data.season} {onauth} leagueName={browsing ? refScoringLabel(league) : data.league_name} />{/if}<!-- IN-2: the scoring -->
      {#each rest as x (x.key)}
        <SectionBox section={x.sec} {ctx} testid={`section-${x.key}`} />
      {/each}
      <!-- ---- IF-4: the compact schedule (week · opponent · projected) behind "Schedule" -->
      {#if data.schedule?.length}
        <Expander title="Schedule" testid="player-schedule"><ScheduleTable rows={data.schedule} position={data.position} /></Expander>
      {/if}
      <!-- ---- end IF-4 -->
    </div>
    <!-- ---- end IP-4 -->
    {#if missing.length}
      <p class="text-sm leading-snug text-ink-3" data-testid="missing">
        Not shown for {data.league_name} yet: {missing.join(", ")}.
      </p>
    {/if}
    <Expander title="How to read this" testid="howto"><Md text={howtoWords(data.howto)} {ctx} block class="text-base leading-snug" /></Expander>
    <!-- ---- IN-2: browsing without a league — the scoring, and one quiet line at the foot -->
    {#if browsing}
      <p class="border-t border-line pt-3 text-sm text-ink-3" data-testid="player-foot">
        Priced in {refLabel(league)}. <a class="ll-link" href="/leagues">{data.foot ?? PANE_FOOT}</a>
      </p>
    {/if}
  {/if}
</main>

<style>
  /* ---- IP-4: the card's columns are a phone's width at every size: the section tiles two to a row (as in the pane) */
  [data-testid="card-sections"] :global([data-testid="metrics"]) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
</style>
