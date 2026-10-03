<script lang="ts">
  // Trade Finder (plan G4; app/pages/6_Trade_Finder.py on G2's routes): the answer first — the best partner (the trade
  // that raises both lineups the most, GET /api/trades/partners) with "Try this trade", which opens the trade calculator
  // (IA-2: its own screen, /trade-calc, with the package in the link) — then the partner finder ("who should I trade
  // with for a WR") as a list, then buy low / sell high (IA-2: moved here from Waivers, GET /api/trades/lists).
  // IA-2: the weeks the suggestions are priced over are a segmented control (this week · next 4 · rest of season ·
  // playoffs; ?window=), with one line saying why; suggestions the sanity bound set aside are counted under the list.
  import { get, peek, Unauthorized, tradePaths, type Partners, type TradeLists, type TradePlayer, type TradeWindow } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { md, withContext } from "../lib/md";
  import { errorWords, f1, partnerLine, s1, windowOf } from "../lib/decisions";
  import { navigate, route, setParams } from "../lib/router.svelte";
  import { fmt } from "../lib/theme";
  import Bar from "../components/Bar.svelte";
  import Card from "../components/Card.svelte";
  import Expander from "../components/Expander.svelte";
  import Headshot from "../components/Headshot.svelte";
  import Md from "../components/Md.svelte";
  import PlayerRow from "../components/PlayerRow.svelte";
  import PosBadge from "../components/PosBadge.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import Tabs from "../components/Tabs.svelte";
  import WindowControl from "./decisions/WindowControl.svelte";

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

  const top = $derived(best?.partners.find((p) => p.is_best) ?? best?.partners[0] ?? null);
  const wantTabs = [
    { key: "ALL", label: "Any" },
    { key: "QB", label: "QB" },
    { key: "RB", label: "RB" },
    { key: "WR", label: "WR" },
    { key: "TE", label: "TE" },
  ];
  const href = (g: string | null | undefined) => (g ? withContext(`/player/${g}`, ctx) : null);
  const calcHref = $derived(withContext("/trade-calc", ctx));
  const theirWeek = (x: number | null | undefined) => (x == null ? "" : ` · this week you ${s1(x)}`);
</script>

{#snippet face(p: TradePlayer)}
  <span class="inline-flex min-w-0 items-center gap-1.5">
    <Headshot url={p.headshot_url} name={p.player_name ?? ""} team={p.team} size={28} />
    {#if href(p.gsis_id)}<a class="ll-name truncate font-semibold" href={href(p.gsis_id)}>{p.player_name}</a>{:else}<span class="truncate font-semibold">{p.player_name}</span>{/if}
    <PosBadge pos={p.position} />
  </span>
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
        {#if finder}<p class="text-sm text-ink-3">Trades that raise both lineups over {finder.span}, best first</p>{/if}
      </div>
      <Tabs items={wantTabs} current={want} onpick={(w) => setParams({ want: w === "ALL" ? null : w })} size="sm" label="You want" testid="want" />
      {#if !finder}
        <div class="ll-skel h-32" aria-label="Loading"></div>
      {:else if !finder.partners.length}
        <p class="ll-empty" data-testid="finder-empty">No trade that raises both lineups brings you {want === "ALL" ? "anyone" : `a ${want}`}. Try one you have in mind in the <a class="ll-name" href={calcHref}>trade calculator</a>.</p>
      {:else}
        {@const gmax = Math.max(1, ...finder.partners.flatMap((p) => [p.you_gain_horizon, p.they_gain_horizon]))}
        <div class="grid grid-cols-1 gap-3 wide:grid-cols-2">
          {#each finder.partners.slice(0, 12) as p, i (`${p.partner}-${p.shape}-${i}`)}
            <Card testid="partner-row">
              <div class="flex items-baseline justify-between gap-2">
                <span class="min-w-0 truncate text-lg font-bold">{p.partner_team}</span>
                <span class="ll-label shrink-0">{p.shape}</span>
              </div>
              <div class="mt-2 space-y-1.5 text-base">
                <div class="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1"><span class="ll-label w-14">You get</span>{#each p.get as x (x.sleeper_id)}{@render face(x)}{/each}</div>
                <div class="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1"><span class="ll-label w-14">You give</span>{#each p.give as x (x.sleeper_id)}{@render face(x)}{/each}</div>
              </div>
              <div class="mt-3 grid grid-cols-2 gap-3">
                <Bar label={`You · ${finder.span}`} value={p.you_gain_horizon} max={gmax} display={s1(p.you_gain_horizon)} thick={6} />
                <Bar label="Them" value={p.they_gain_horizon} max={gmax} display={s1(p.they_gain_horizon)} thick={6} />
              </div>
              <div class="mt-3 flex items-center justify-between gap-2">
                <span class="text-xs text-ink-3">Market: give {fmt.whole(p.price_out)}, get {fmt.whole(p.price_in)}{theirWeek(p.you_gain_week)}{p.interest ? ` · they: ${p.interest.label}` : ""}</span>
                <button type="button" class="min-h-9 shrink-0 rounded-md border border-line-strong px-3 text-sm font-semibold" onclick={() => tryTrade(p)} data-testid="try-partner">Try it</button>
              </div>
            </Card>
          {/each}
        </div>
        {#if finder.no_trade_with?.length}<p class="text-sm text-ink-3">No trade helps both lineups with: {finder.no_trade_with.join(", ")}.</p>{/if}
      {/if}
      {#if finder?.rejected_count}
        <!-- IA-2: the sanity bound — what was set aside, and why (three examples) -->
        <Expander title={`${finder.rejected_count} lopsided ${finder.rejected_count === 1 ? "trade" : "trades"} left out`} testid="rejected">
          <p class="text-sm text-ink-2">
            We do not suggest a trade that gives away much more rest-of-season value than it brings back (over a quarter of what you give), or one that only works because our number for a player you give is far under Sleeper's.
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
                      context={`${r.team_name ?? "another team"} · ${s1(r.diff_per_game)} a game vs his work · you gain ${s1(r.gain_week)} this week`}
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
                      context={`${s1(r.diff_per_game)} a game vs his work · best fit ${r.team_name ?? "—"}`}
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
          "- **Who to call**: the first line names the team where one trade raises *both* lineups the most over the weeks you picked above, and the trade. Teams are ranked by the smaller of the two gains, so the other manager has a reason to say yes too.\n" +
            "- **The weeks**: this week, the next four (the default: far enough to matter, near enough to trust), the rest of the season (every week to this league's final) or the playoffs. A longer span sees more of the season and is less sure.\n" +
            "- **Left out**: a trade that gives away much more rest-of-season value than it brings back (over a quarter of what you give), or that works only because our projection for a player you give is far under Sleeper's (under 65% of it), is never suggested, however much it helps the lineups.\n" +
            "- **Try it** opens the trade calculator with the trade filled in: tick players both ways and the dial shows how much the other team would want it.\n" +
            "- **Fit** is what the starting lineups gain. **Market** is what the players are worth on the market: their projected points for the rest of the season above the best free agent at their position. They are never added together: a player can be worth a lot and still sit on your bench. The verdict reads both. It knows nothing of draft picks, next season or what the other manager believes.\n" +
            "- **Roster size**: if a team gets more players than it gives, it has to cut someone: the player it would miss least, and that loss is in the numbers.\n" +
            "- **Buy low**: players on other teams scoring *less* than their work is worth (points minus expected points per game, below zero). Their manager sees a bad box score; the work says it should turn around. **Sell high**: your players scoring *more* than their work supports. **Fit** is what the new team gains minus what the old team loses over the next four weeks.",
        )}
      </div>
    </Expander>
  {/if}
</main>
