<script lang="ts">
  import { ApiError, get, paths, peek, Unauthorized, type PlayerCard } from "../lib/api";
  import { cardHeadLine, cardMissing, cardSections, howtoWords, projLabel } from "../lib/card"; // IG-1: projLabel
  import { withContext } from "../lib/md";
  import { learnLeagueName } from "../lib/names.svelte";
  import { back, restoreScroll, route } from "../lib/router.svelte";
  import { fmt } from "../lib/theme";
  import Expander from "../components/Expander.svelte";
  import GameLog from "../components/GameLog.svelte";
  import Md from "../components/Md.svelte";
  import NewsLine from "../components/NewsLine.svelte"; // ---- N1
  import PlayerCardView from "../components/PlayerCard.svelte";
  import SectionBox from "../components/Section.svelte";
  import ScheduleTable from "../components/ScheduleTable.svelte"; // ---- IF-4
  import { isRef, PANE_FOOT, refLabel } from "../lib/refleague"; // ---- IN-2: browsing without a league

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
    <PlayerCardView
      player={{ gsis_id: data.gsis_id, player_name: data.player_name, position: data.position, team: data.team, headshot_url: data.headshot_url ?? null }}
      number={fmt.pts(data.proj_points)}
      numberLabel={projLabel(data.week, data.proj_points)}
      line={headLine}
      context={data.injury_status ?? null}
      testid="player-header"
    />
    <div class="grid grid-cols-1 gap-3 wide:grid-cols-2 wide:items-start">
      <div class="space-y-3">
        {#each sections.slice(0, 1) as x (x.key)}
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
                    <p class="mt-1 text-sm text-ink-2">His projected stat line, each piece counted in {data.league_name} scoring: they add up to the {fmt.pts(data.why.points)}.</p>
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
            {#if x.key === "availability"}<NewsLine card={data} testid="player-news" />{/if}<!-- ---- N1 -->
          </SectionBox>
        {/each}
        <!-- ---- IF-4: the compact schedule (week · opponent · projected) behind "Schedule" -->
        {#if data.schedule?.length}
          <Expander title="Schedule" testid="player-schedule"><ScheduleTable rows={data.schedule} position={data.position} /></Expander>
        {/if}
        <!-- ---- end IF-4 -->
        {#if league}<GameLog gsis={data.gsis_id} {league} season={data.season} {onauth} leagueName={data.league_name} />{/if}
      </div>
      <div class="space-y-3">
        {#each sections.slice(1) as x (x.key)}
          <SectionBox section={x.sec} {ctx} testid={`section-${x.key}`}>
            <!-- ---- N1 (Wave I-D): the news line under the availability lines -->
            {#if x.key === "availability"}<NewsLine card={data} testid="player-news" />{/if}
            <!-- ---- end N1 -->
          </SectionBox>
        {/each}
      </div>
    </div>
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
