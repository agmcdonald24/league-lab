<script lang="ts">
  // Trade Finder (plan G4; app/pages/6_Trade_Finder.py on G2's routes): the answer first — the best partner (the trade
  // that raises both lineups the most, GET /api/trades/partners) with "Try this trade", which opens the trade calculator
  // (IA-2: its own screen, /trade-calc, with the package in the link) — then the partner finder ("who should I trade
  // with for a WR") as a list, then buy low / sell high (IA-2: moved here from Waivers, GET /api/trades/lists).
  // IA-2: the weeks the suggestions are priced over are a segmented control (this week · next 4 · rest of season ·
  // playoffs; ?window=), with one line saying why; suggestions the sanity bound set aside are counted under the list.
  // IB-2 (Wave I-B): each suggestion's card is the package, the dial's label, your gain and ONE reason (when the gain
  // comes, or who cannot play); "Try it" opens the calculator. A name opens the research pane ("Add to trade").
  import { get, peek, Unauthorized, tradePaths, type Partners, type PartnerRow, type TradeLists, type TradePlayer, type TradeWindow } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { md, withContext } from "../lib/md";
  import { errorWords, f1, partnerLine, s1, windowOf } from "../lib/decisions";
  import { paneAt, partnerReason } from "../lib/decisions";
  import { effectTone } from "../lib/decisions"; // ---- IE-1: the effect on their starters
  import { navigate, route, setParams } from "../lib/router.svelte";
  import Card from "../components/Card.svelte";
  import Expander from "../components/Expander.svelte";
  import Headshot from "../components/Headshot.svelte";
  import Md from "../components/Md.svelte";
  import PlayerRow from "../components/PlayerRow.svelte";
  import PosBadge from "../components/PosBadge.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import Tabs from "../components/Tabs.svelte";
  import WindowControl from "./decisions/WindowControl.svelte";
  import WeekStrip from "./decisions/WeekStrip.svelte"; // ---- IF-2: the week strip, both sides
  import TradeCard from "./decisions/TradeCard.svelte"; // ---- II-1: the trade card (plausibility, both sides, reasons)
  import { isRef } from "../lib/refleague"; // ---- IN-2

  let { options, league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  const ctx = $derived({ league, team });
  const params = $derived(route.current.params);
  const want = $derived((params.get("want") ?? "ALL").toUpperCase());
  const win = $derived<TradeWindow>(windowOf(params.get("window")));
  // "in League of Scrubs scoring" (WORDS.md: name the league's scoring)
  const scoring = $derived.by(() => {
    const n = options.find((o) => o.league_id === league)?.name;
    return n && n !== "This league" ? `${n} scoring` : "your league's scoring";
  });

  let best = $state<Partners | null>(null); // want = ALL: the answer card
  let finder = $state<Partners | null>(null); // the partner finder's list (want)
  let lists = $state<TradeLists | null>(null); // buy low / sell high
  let error = $state<string | null>(null);

  function fail(e: unknown) {
    if (e instanceof Unauthorized) onauth();
    else error = errorWords(e);
  }

  function load<T>(path: string, set: (v: T) => void, still: () => boolean) {
    const hit = peek<T>(path);
    if (hit) {
      set(hit);
      return;
    }
    get<T>(path)
      .then((v) => still() && set(v))
      .catch((e) => still() && fail(e));
  }

  // ---- IN-2 (Wave I-N): browsing without a league, Trades is the calculator (never the invitation card)
  $effect(() => {
    if (isRef(league)) navigate(`/trade-calc?league=${encodeURIComponent(league)}`, { replace: true });
  });
  // ---- end IN-2

  // the answer (best partner over the window)
  $effect(() => {
    const l = league;
    const t = team;
    const w = win;
    error = null;
    best = null;
    if (t === null) return;
    load<Partners>(tradePaths.partners(l, t, "ALL", w), (v) => (best = v), () => league === l && team === t && win === w);
  });

  // buy low / sell high (independent of the window: the lists read the next four weeks, as on Waivers before)
  $effect(() => {
    const l = league;
    const t = team;
    lists = null;
    if (t === null) return;
    const path = tradePaths.lists(l, t);
    const hit = peek<TradeLists>(path);
    if (hit) {
      lists = hit;
      return;
    }
    get<TradeLists>(path)
      .then((v) => league === l && team === t && (lists = v))
      .catch((e) => {
        if (e instanceof Unauthorized) onauth();
      });
  });

  // the partner finder at the position asked
  $effect(() => {
    const l = league;
    const t = team;
    const w = want;
    const wn = win;
    if (t === null) return;
    finder = peek<Partners>(tradePaths.partners(l, t, w, wn)) ?? null;
    load<Partners>(tradePaths.partners(l, t, w, wn), (v) => (finder = v), () => league === l && team === t && want === w && win === wn);
  });

  /** Open the trade calculator on this package (the link carries it, and the window). */
  function tryTrade(p: { partner: number; give: TradePlayer[]; get: TradePlayer[] }) {
    const enc = encodeURIComponent;
    const ids = (ps: TradePlayer[]) => ps.map((x) => enc(x.sleeper_id)).join(",");
    navigate(`/trade-calc?league=${enc(league)}&team=${team}&partner=${p.partner}&give=${ids(p.give)}&get=${ids(p.get)}${win === "next4" ? "" : `&window=${win}`}`);
  }

  // ---- IF-2: the headline is the first card (rank 1: the most starter points beyond your best waiver move)
  // (an answer without IF-2's ordering — an older recording — keeps the old pick: the partner's best package)
  const top0 = $derived(best?.ordering ? (best.partners[0] ?? null) : (best?.partners.find((p) => p.is_best) ?? best?.partners[0] ?? null));
  // ---- II-1: the headline is the first CREDIBLE trade (beats both teams' alternatives, a plausible offer or a roster-fit
  // idea), or the honest answer "No compelling trade found" with its reason; an answer without `verdict` keeps IF-2's
  const noneFound = $derived(best?.verdict?.kind === "none");
  const top = $derived(best?.verdict ? (noneFound ? null : (best.partners.find((p) => p.tier === "credible") ?? null)) : top0);
  const credibleRows = $derived(finder?.verdict ? finder.partners.filter((p) => p.tier === "credible") : (finder?.partners.slice(0, 12) ?? []));
  const exploreRows = $derived(finder?.verdict ? finder.partners.filter((p) => p.tier !== "credible") : []);
  // ---- end II-1
  const lowerFirst = (t: string) => t.charAt(0).toLowerCase() + t.slice(1); // ---- II-6: "For a WR: none of the 5 trades …"
  const wantTabs = [
    { key: "ALL", label: "Any" },
    { key: "QB", label: "QB" },
    { key: "RB", label: "RB" },
    { key: "WR", label: "WR" },
    { key: "TE", label: "TE" },
  ];
  const href = (g: string | null | undefined) => (g ? withContext(`/player/${g}`, ctx) : null);
  const calcHref = $derived(withContext("/trade-calc", ctx));
</script>

{#snippet face(p: TradePlayer)}
  <span class="inline-flex min-w-0 items-center gap-1.5">
    <Headshot url={p.headshot_url} name={p.player_name ?? ""} team={p.team} size={28} />
    {#if href(p.gsis_id)}<a
        class="ll-name truncate font-semibold"
        href={href(p.gsis_id)}
        {@attach paneAt(p.gsis_id, { from: "trade", context: { sleeper_id: p.sleeper_id, side: p.roster_id === team ? "give" : "get", partner: p.roster_id === team ? null : p.roster_id, name: p.player_name } })}
        >{p.player_name}</a
      >{:else}<span class="truncate font-semibold">{p.player_name}</span>{/if}
    <PosBadge pos={p.position} />
  </span>
{/snippet}

<!-- ---- II-1: one Finder card (the IF-2 / IE-1 lines, then the trade card); `compact` behind "Explore alternatives" -->
{#snippet partnerCard(p: PartnerRow, compact: boolean)}
  <Card testid="partner-row">
    <div class="flex items-baseline justify-between gap-2">
      <span class="min-w-0 truncate text-lg font-bold">{p.partner_team}</span>
      {#if p.interest}
        <span class="shrink-0 text-sm" data-testid="partner-label"
          ><span class="ll-label">Their starters</span> <strong class={effectTone(p.interest.label)}>{p.interest.label}</strong></span
        >
      {:else}
        <span class="ll-label shrink-0">{p.shape}</span>
      {/if}
    </div>
    <div class="mt-2 space-y-1.5 text-base">
      <div class="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1"><span class="ll-label w-14">You get</span>{#each p.get as x (x.sleeper_id)}{@render face(x)}{/each}</div>
      <div class="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1"><span class="ll-label w-14">You give</span>{#each p.give as x (x.sleeper_id)}{@render face(x)}{/each}</div>
    </div>
    {#if p.strip}<div class="mt-2"><WeekStrip strip={p.strip} them={p.partner_team} testid="partner-strip" /></div>{/if}
    <div class="mt-3 flex items-end justify-between gap-3">
      <div class="min-w-0">
        <div class="flex items-baseline gap-2">
          <span class="tabnum text-2xl leading-none font-extrabold {p.you_gain_horizon >= 0.05 ? 'text-good' : 'text-ink'}" data-testid="partner-gain">{s1(p.you_gain_horizon)}</span>
          <span class="ll-label">you · {finder?.span ?? ""}</span>
        </div>
        <p class="mt-1.5 text-sm leading-snug text-ink-2" data-testid="partner-reason">{partnerReason(p, finder?.span ?? "")}</p>
        <!-- ---- IF-2: against the best alternative; a trade that does not beat it is marked -->
        {#if p.alternative_words}<p class="mt-1 text-sm leading-snug {p.demoted ? 'text-warn' : 'text-ink'}" data-testid="partner-alternative">{#if p.demoted}<strong data-testid="partner-demoted">Below your best waiver move.</strong> {/if}{p.alternative_words}</p>{/if}
        <!-- ---- IE-1: the least costly package first; the extra asset named as optional (what it costs you) -->
        {#if p.cheaper_than}<p class="mt-1 text-sm leading-snug font-semibold text-good" data-testid="partner-cheaper">{p.cheaper_than.words}</p>{/if}
        {#if p.optional}<p class="mt-1 text-sm leading-snug text-ink-2" data-testid="partner-optional">{p.optional.words}</p>{/if}
      </div>
      <button type="button" class="min-h-10 shrink-0 rounded-md bg-accent px-4 text-sm font-semibold text-on-accent" onclick={() => tryTrade(p)} data-testid="try-partner">Try it</button>
    </div>
    <!-- ---- II-1: the card's fields (the label, both sides, the reasons each way) -->
    {#if p.card}<div class="mt-3 border-t border-line pt-2"><TradeCard card={p.card} {compact} /></div>{/if}
  </Card>
{/snippet}

<main class="space-y-4" data-testid="trades">
  {#if team === null}
    <p class="ll-empty" data-testid="pick-team-first">Pick your team above: this screen then finds the trades that raise both lineups, and lets you try your own.</p>
  {:else if error}
    <p class="ll-error" data-testid="error">{error}</p>
  {:else}
    <ScreenHead eyebrow={best ? `Trades · ${best.span}` : "Trades"} title="Trade Finder">
      {#snippet answer()}
        {#if !best}
          <div class="ll-skel h-12" aria-label="Loading" data-testid="loading"></div>
        {:else if top}
          <p data-testid="best-partner"><Md text={best.words?.headline ?? `**Best partner: ${top.partner_team}.** ${partnerLine(top, best.span)}`} {ctx} /></p>
          <!-- ---- IF-2: the trade against the best alternative (standing pat, the best waiver move) -->
          {#if top.alternative_words}<p class="mt-1 text-base leading-snug {top.beats_alternative ? 'text-ink' : 'text-warn'}" data-testid="best-alternative">{top.alternative_words}</p>{/if}
        {:else if noneFound}
          <!-- ---- II-1: "No compelling trade found" is a first-class answer, with the reason -->
          <p data-testid="best-partner"><strong class="text-ink" data-testid="no-compelling">{best.verdict?.headline ?? "No compelling trade found"}.</strong> {best.verdict?.reason ?? ""} Try one you have in mind in the <a class="ll-name" href={calcHref}>trade calculator</a>.</p>
        {:else}
          <p data-testid="best-partner"><strong class="text-ink">No trade raises both lineups.</strong> Nobody in the league has a player who would improve your lineup over {best.span} and also needs one of yours. Try one you have in mind in the <a class="ll-name" href={calcHref}>trade calculator</a>.</p>
        {/if}
      {/snippet}
      {#if top}
        <div class="flex flex-wrap items-center gap-3 pt-1">
          <div class="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span class="ll-label">You get</span>
            {#each top.get as p (p.sleeper_id)}{@render face(p)}{/each}
            <span class="ll-label">for</span>
            {#each top.give as p (p.sleeper_id)}{@render face(p)}{/each}
          </div>
          <button type="button" class="min-h-10 rounded-md bg-accent px-4 font-semibold text-on-accent" onclick={() => tryTrade(top)} data-testid="try-best">Try this trade</button>
        </div>
      {/if}
    </ScreenHead>

    <!-- IA-2: the weeks the suggestions are priced over, and why -->
    <WindowControl current={win} span={best?.window === win ? best.span : null} onpick={(w) => setParams({ window: w === "next4" ? null : w })} />

    <section class="space-y-3" data-testid="finder">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h2 class="text-xl font-bold">Who should I trade with?</h2>
        {#if finder}<p class="text-sm text-ink-3" data-testid="finder-ordering">{finder.ordering?.words ?? `Trades that raise both lineups over ${finder.span}, best first`}</p>{/if}
      </div>
      <Tabs items={wantTabs} current={want} onpick={(w) => setParams({ want: w === "ALL" ? null : w })} size="sm" label="You want" testid="want" />
      {#if !finder}
        <div class="ll-skel h-32" aria-label="Loading"></div>
      {:else if !finder.partners.length}
        <p class="ll-empty" data-testid="finder-empty">No trade that raises both lineups brings you {want === "ALL" ? "anyone" : `a ${want}`}. Try one you have in mind in the <a class="ll-name" href={calcHref}>trade calculator</a>.</p>
      {:else}
        {#if finder.verdict && !credibleRows.length}
          <!-- ---- II-1: the honest empty state, with the reason; the trades found are behind "Explore alternatives" -->
          <!-- ---- II-6 (Wave I-J): said once. When the answer above already says "No compelling trade found" (with its
               reason and your best move), the Finder does not say it again: for Any nothing (the same answer), for a
               position one line — that position's reason, without the best move the answer above names. -->
          {#if !noneFound}
            <p class="ll-empty" data-testid="finder-none"><strong>{finder.verdict.headline ?? "No compelling trade found"}{want === "ALL" ? "" : ` for a ${want}`}.</strong> {finder.verdict.reason ?? ""}</p>
          {:else if want !== "ALL" && finder.verdict.reason}
            <p class="text-base leading-snug text-ink-2" data-testid="finder-none-why"><strong class="text-ink">For a {want}:</strong> {lowerFirst(finder.verdict.reason.split(" Your best move:")[0])}</p>
          {/if}
          <!-- ---- end II-6 -->
        {:else}
          <div class="grid grid-cols-1 gap-3 wide:grid-cols-2">
            {#each credibleRows as p, i (`${p.partner}-${p.shape}-${i}`)}{@render partnerCard(p, false)}{/each}
          </div>
        {/if}
        {#if exploreRows.length}
          <Expander title={`Explore alternatives · ${exploreRows.length} ${exploreRows.length === 1 ? "trade" : "trades"} that did not pass`} testid="explore">
            <p class="mb-2 text-sm text-ink-2" data-testid="explore-why">Each raises both starting lineups, but does not beat both teams' own best alternative by {finder.margin ?? 1} point, or is not a plausible offer: ideas to look at, not trades to propose.</p>
            <div class="grid grid-cols-1 gap-3 wide:grid-cols-2">
              {#each exploreRows.slice(0, 12) as p, i (`x-${p.partner}-${p.shape}-${i}`)}{@render partnerCard(p, true)}{/each}
            </div>
          </Expander>
        {/if}
        {#if finder.no_trade_with?.length}<p class="text-sm text-ink-3">No trade helps both lineups with: {finder.no_trade_with.join(", ")}.</p>{/if}
      {/if}
      {#if finder?.rejected_count}
        <!-- IA-2: the sanity bound — what was set aside, and why (three examples) -->
        <Expander title={`${finder.rejected_count} lopsided ${finder.rejected_count === 1 ? "trade" : "trades"} left out`} testid="rejected">
          <!-- ---- IG-1: rule (a) is the value gap (season value above replacement); the API says it -->
          <p class="text-sm text-ink-2" data-testid="rejected-rule">
            {finder.sanity?.words ??
              "We do not suggest a trade that gives away much more season value above replacement than it brings back (over a quarter of what you give, and not about even), or one that only works because our number for a player you give is far under Sleeper's."}
          </p>
          <ul class="mt-2 space-y-1.5 text-sm" data-testid="rejected-list">
            {#each finder.rejected ?? [] as x, i (i)}
              <li data-testid="rejected-row"><strong>{x.give.join(" + ")}</strong> for <strong>{x.get.join(" + ")}</strong> ({x.partner_team}): {x.why}.</li>
            {/each}
          </ul>
        </Expander>
      {/if}
      <p class="text-sm"><a class="ll-name font-semibold" href={calcHref} data-testid="calc-link">Build your own in the trade calculator ›</a></p>
    </section>

    <!-- IA-2: buy low / sell high, moved here from Waivers (Wave H's lists: GET /api/trades/lists) -->
    {#if lists && (lists.buy_line || lists.buy_low.length)}
      {@const tl = lists}
      <section class="space-y-3" data-testid="buy-sell">
        <h2 class="text-xl font-bold">Buy low, sell high</h2>
        <p class="text-sm text-ink-3">Players scoring below (or above) what their work is worth, in {scoring}: trades to ask about.</p>
        <div class="grid grid-cols-1 gap-3 wide:grid-cols-2">
          <Card title="Buy low" testid="buy-low">
            {#if tl.buy_line}<p class="text-base leading-snug" data-testid="buy-line"><Md text={tl.buy_line} {ctx} /></p>{/if}
            {#if tl.best_buy_by_position && Object.keys(tl.best_buy_by_position).length}
              <h3 class="ll-label mt-3">Best by position</h3>
              <ul class="-mx-4 divide-y divide-line">
                {#each Object.entries(tl.best_buy_by_position) as [pos, r] (pos)}
                  <li>
                    <PlayerRow
                      player={{ ...r.player, player_name: r.player.player_name ?? "" }}
                      href={r.player.gsis_id ? withContext(`/player/${r.player.gsis_id}`, ctx) : null}
                      context={`${r.team_name ?? "another team"} · ${s1(r.diff_per_game)} per game vs his work · you gain ${s1(r.gain_week)} this week`}
                      value={s1(r.fit_horizon)}
                      valueLabel="Fit"
                      testid="buy-best"
                    />
                  </li>
                {/each}
              </ul>
            {/if}
          </Card>
          <Card title="Sell high" testid="sell-high">
            {#if tl.sell_line}<p class="text-base leading-snug" data-testid="sell-line"><Md text={tl.sell_line} {ctx} /></p>{/if}
            {#if tl.sell_high.length}
              <ul class="-mx-4 mt-2 divide-y divide-line">
                {#each tl.sell_high.slice(0, 4) as r (r.player.sleeper_id ?? r.player.gsis_id)}
                  <li>
                    <PlayerRow
                      player={{ ...r.player, player_name: r.player.player_name ?? "" }}
                      href={r.player.gsis_id ? withContext(`/player/${r.player.gsis_id}`, ctx) : null}
                      context={`${s1(r.diff_per_game)} per game vs his work · best fit ${r.team_name ?? "—"}`}
                      value={s1(r.fit_horizon)}
                      valueLabel="Fit"
                      testid="sell-row"
                    />
                  </li>
                {/each}
              </ul>
            {/if}
          </Card>
        </div>
        {#if tl.buy_low.length}
          <Expander title={`Buy low · ${tl.buy_low.length} players scoring below their usage`} testid="buy-list">
            <ul class="-mx-3 divide-y divide-line">
              {#each tl.buy_low as r, i (`${r.player.sleeper_id}|${i}`)}
                <li>
                  <PlayerRow
                    player={{ ...r.player, player_name: r.player.player_name ?? "" }}
                    href={r.player.gsis_id ? withContext(`/player/${r.player.gsis_id}`, ctx) : null}
                    context={`${r.team_name ?? "—"} · PPG ${f1(r.ppg)} vs ${f1(r.xppg)} expected · you gain ${s1(r.gain_week)}, they lose ${f1(r.loss_week)}`}
                    value={s1(r.fit_horizon)}
                    valueLabel={tl.weeks ? `Fit ${tl.weeks}` : "Fit"}
                    testid="buy-row"
                  />
                </li>
              {/each}
            </ul>
          </Expander>
        {/if}
      </section>
    {/if}

    <Expander title="How to read this" testid="howto">
      <div class="text-base leading-snug">
        {@html md(
          "- **Worth proposing** (II-1): a trade is shown up top only when it beats **both** teams' own best alternative (standing pat or their best waiver move, over the same weeks) by at least a point, with every empty slot — a bye — filled from the free pool for both sides (never counted as zero), and when it is a plausible offer: a kicker or defense for a starter is not, unless they really need one; nor is a trade that gives them much less season value than it takes. Otherwise the answer is **No compelling trade found**, with the reason, and the trades we found are under **Explore alternatives**. Each card says why they might consider it and why they might refuse — never a chance that they accept. Without a market price for a player it is labelled **a roster-fit idea**.\n" +
            "- **Who to call**: the first line and the first card are the same trade: of the trades that raise *both* starting lineups over the weeks you picked above, the one that adds the most **starter points beyond your best waiver move** (a free agent for an open spot, or for the player you would drop). A trade that does not beat that claim comes after those that do, marked, with any other reason the numbers give (more this week, more season value above replacement). When a smaller package gets you the same gain, it comes first and the extra player is shown as optional, with what he costs you.\n" +
            "- **The strip** under each trade is the starter points it adds each week, for you and for them: a gain over four weeks can hide a loss this week.\n" +
            "- **The weeks**: this week, the next four (the default: far enough to matter, near enough to trust), the rest of the season (every week to this league's final) or the playoffs. A longer span sees more of the season and is less sure.\n" +
            "- **Left out**: a trade that gives away much more rest-of-season value than it brings back (over a quarter of what you give), or that works only because our projection for a player you give is far under Sleeper's (under 65% of it), is never suggested, however much it helps the lineups.\n" +
            "- **Try it** opens the trade calculator with the trade filled in: tick players both ways and the dial shows the **effect on their starters** — what the other team's best lineup gains or loses over the weeks you picked, by our numbers (about even under 2 points, improves 2 to 6, a lot over 6). It is lineup fit, not a guess at whether they would accept.\n" +
            "- **Fit** is what the starting lineups gain. **Market** is what the players are worth on the market: their projected points for the rest of the season above the best free agent at their position. They are never added together: a player can be worth a lot and still sit on your bench. The verdict reads both. It knows nothing of draft picks, next season or what the other manager believes.\n" +
            "- **Roster size**: if a team gets more players than it gives, it has to cut someone: the player it would miss least, and that loss is in the numbers.\n" +
            "- **Buy low**: players on other teams scoring *less* than their work is worth (points minus expected points per game, below zero). Their manager sees a bad box score; the work says it should turn around. **Sell high**: your players scoring *more* than their work supports. **Fit** is what the new team gains minus what the old team loses over the next four weeks.",
        )}
      </div>
    </Expander>
  {/if}
</main>
