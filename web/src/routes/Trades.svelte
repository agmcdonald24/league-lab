<script lang="ts">
  // Trade Finder (plan G4; app/pages/6_Trade_Finder.py on G2's routes): the answer first — the best partner (the trade
  // that raises both lineups the most, GET /api/trades/partners) with "Try this trade" — then "Try a trade": pick a
  // partner, tick players both ways (both rosters from GET /api/team), and POST /api/trades/evaluate answers with the
  // before / after of both lineups, the fit, the market, rest of season and the verdict in the page's words. Then the
  // partner finder ("who should I trade with for a WR") as a list. The package is the URL (?partner=&give=&get=,
  // Sleeper ids), so a copied link opens the same trade.
  import { ApiError, get, paths, peek, postEvaluate, Unauthorized, decisionPaths, type Partners, type Roster, type Team, type TeamRosterRow, type TradeEval, type TradePlayer } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { md, withContext } from "../lib/md";
  import { errorWords, f1, f2, names, parseIds, partnerLine, s1, slotLabel } from "../lib/decisions";
  import { restoreScroll, route, setParams } from "../lib/router.svelte";
  import { fmt } from "../lib/theme";
  import Bar from "../components/Bar.svelte";
  import Card from "../components/Card.svelte";
  import Expander from "../components/Expander.svelte";
  import Headshot from "../components/Headshot.svelte";
  import Md from "../components/Md.svelte";
  import PosBadge from "../components/PosBadge.svelte";
  import ScreenHead from "../components/ScreenHead.svelte";
  import StatTile from "../components/StatTile.svelte";
  import Tabs from "../components/Tabs.svelte";
  import TeamBadge from "../components/TeamBadge.svelte";

  let { league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  const ctx = $derived({ league, team });
  const params = $derived(route.current.params);
  const want = $derived((params.get("want") ?? "ALL").toUpperCase());

  let best = $state<Partners | null>(null); // want = ALL: the answer card
  let finder = $state<Partners | null>(null); // the partner finder's list (want)
  let rosters = $state<Roster[]>([]);
  let mine = $state<Team | null>(null);
  let theirs = $state<Team | null>(null);
  let result = $state<TradeEval | null>(null);
  let resultKey = $state("");
  let evaluating = $state(false);
  let evalError = $state<string | null>(null);
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

  // the answer (best partner), the league's rosters, my roster
  $effect(() => {
    const l = league;
    const t = team;
    error = null;
    best = null;
    mine = null;
    if (t === null) return;
    const still = () => league === l && team === t;
    load<Partners>(decisionPaths.partners(l, t, "ALL"), (v) => (best = v), still);
    load<Team>(decisionPaths.team(l, t), (v) => (mine = v), still);
    load<Roster[]>(paths.rosters(l), (v) => (rosters = v), () => league === l);
  });

  // the partner finder at the position asked
  $effect(() => {
    const l = league;
    const t = team;
    const w = want;
    if (t === null) return;
    finder = peek<Partners>(decisionPaths.partners(l, t, w)) ?? null;
    load<Partners>(decisionPaths.partners(l, t, w), (v) => (finder = v), () => league === l && team === t && want === w);
  });

  const others = $derived(rosters.filter((r) => r.roster_id !== team));
  const partner = $derived.by(() => {
    const p = Number(params.get("partner"));
    if (p && others.some((r) => r.roster_id === p)) return p;
    return best?.partners[0]?.roster_id ?? others[0]?.roster_id ?? null;
  });

  // the partner's roster
  $effect(() => {
    const l = league;
    const p = partner;
    theirs = null;
    if (p === null) return;
    load<Team>(decisionPaths.team(l, p), (v) => (theirs = v), () => league === l && partner === p);
  });

  const playable = (rows: TeamRosterRow[] | undefined) =>
    (rows ?? []).filter((r) => r.role !== "empty" && r.sleeper_player_id).sort((a, b) => (b.player_value ?? -1) - (a.player_value ?? -1));
  const myPlayers = $derived(playable(mine?.roster));
  const theirPlayers = $derived(playable(theirs?.roster));
  const give = $derived(parseIds(params.get("give")).filter((id) => myPlayers.some((r) => r.sleeper_player_id === id)));
  const getIds = $derived(parseIds(params.get("get")).filter((id) => theirPlayers.some((r) => r.sleeper_player_id === id)));
  const pkgKey = $derived(partner !== null && give.length && getIds.length ? `${league}|${team}|${partner}|${[...give].sort()}|${[...getIds].sort()}` : "");

  // evaluate the package when it is complete (a short pause, so ticking two players asks once)
  $effect(() => {
    const key = pkgKey;
    if (!key || team === null || partner === null) {
      result = null;
      evalError = null;
      return;
    }
    if (key === resultKey && result) return;
    const body = { league, team, partner, give: [...give], get: [...getIds] };
    const timer = setTimeout(() => {
      evaluating = true;
      evalError = null;
      postEvaluate(body)
        .then((r) => {
          if (pkgKey !== key) return;
          result = r;
          resultKey = key;
          restoreScroll();
        })
        .catch((e) => {
          if (pkgKey !== key) return;
          result = null;
          if (e instanceof Unauthorized) onauth();
          else evalError = e instanceof ApiError && e.status === 404 ? "This trade cannot be evaluated: a player is not on these rosters any more." : errorWords(e);
        })
        .finally(() => (evaluating = false));
    }, 250);
    return () => clearTimeout(timer);
  });

  function toggle(side: "give" | "get", id: string) {
    const cur = side === "give" ? give : getIds;
    const next = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
    setParams({ [side]: next.length ? next.join(",") : null });
  }

  function pickPartner(p: number) {
    setParams({ partner: String(p), get: null });
  }

  function tryTrade(p: { roster_id: number; give: TradePlayer[]; get: TradePlayer[] }) {
    setParams({ partner: String(p.roster_id), give: p.give.map((x) => x.sleeper_id).join(","), get: p.get.map((x) => x.sleeper_id).join(",") });
    requestAnimationFrame(() => document.getElementById("try-a-trade")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  const top = $derived(best?.partners[0] ?? null);
  const mmax = $derived(Math.max(1, result?.market.give ?? 0, result?.market.get ?? 0));
  const rmax = $derived(Math.max(1, result?.ros.give ?? 0, result?.ros.get ?? 0));
  const teamName = (id: number | null) => rosters.find((r) => r.roster_id === id)?.team_name ?? `Team ${id}`;
  const wantTabs = [
    { key: "ALL", label: "Any" },
    { key: "QB", label: "QB" },
    { key: "RB", label: "RB" },
    { key: "WR", label: "WR" },
    { key: "TE", label: "TE" },
  ];
  const href = (g: string | null | undefined) => (g ? withContext(`/player/${g}`, ctx) : null);
</script>

{#snippet face(p: TradePlayer)}
  <span class="inline-flex min-w-0 items-center gap-1.5">
    <Headshot url={p.headshot_url} name={p.player_name ?? ""} team={p.team} size={28} />
    {#if href(p.gsis_id)}<a class="ll-name truncate font-semibold" href={href(p.gsis_id)}>{p.player_name}</a>{:else}<span class="truncate font-semibold">{p.player_name}</span>{/if}
    <PosBadge pos={p.position} />
  </span>
{/snippet}

{#snippet picker(side: "give" | "get", rows: TeamRosterRow[], picked: string[], title: string)}
  <Card title={title} pad={false} testid={`pick-${side}`}>
    {#if picked.length}
      <p class="-mt-1 px-4 pb-2 text-sm text-ink-2" data-testid={`picked-${side}`}>
        {rows.filter((r) => picked.includes(r.sleeper_player_id ?? "")).map((r) => r.player_name).join(" + ")}
      </p>
    {/if}
    {#if !rows.length}
      <div class="space-y-2 p-3"><div class="ll-skel h-10"></div><div class="ll-skel h-10"></div></div>
    {:else}
      <ul class="max-h-[26rem] divide-y divide-line overflow-y-auto">
        {#each rows as r (r.sleeper_player_id)}
          {@const on = picked.includes(r.sleeper_player_id ?? "")}
          <li>
            <label class="flex min-h-12 cursor-pointer items-center gap-2.5 px-3 py-1.5 {on ? 'bg-accent-soft' : 'hover:bg-raised'}" data-testid={`${side}-option`} data-id={r.sleeper_player_id}>
              <input type="checkbox" class="h-5 w-5 shrink-0 accent-[var(--ll-accent)]" checked={on} onchange={() => toggle(side, r.sleeper_player_id ?? "")} />
              <Headshot url={r.headshot_url} name={r.player_name ?? ""} team={r.team} size={32} />
              <span class="min-w-0 flex-1">
                <span class="block truncate text-base font-semibold">{r.player_name}</span>
                <span class="flex items-center gap-1.5 text-xs text-ink-3">
                  <PosBadge pos={r.position} />
                  {#if r.position !== "DEF"}<TeamBadge team={r.team} />{/if}
                  <span class="truncate">{r.role === "starter" ? slotLabel(r.slot) : r.role === "bench" ? "bench" : (r.reason ?? "out")}</span>
                </span>
              </span>
              <span class="tabnum shrink-0 text-right text-base font-semibold">{r.role === "unplayable" ? "—" : f1(r.player_value)}</span>
            </label>
          </li>
        {/each}
      </ul>
    {/if}
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
          <p data-testid="best-partner"><strong class="text-ink">Best partner: {top.team_name}.</strong> <Md text={partnerLine(top, best.span)} {ctx} /></p>
        {:else}
          <p data-testid="best-partner"><strong class="text-ink">No trade raises both lineups.</strong> Nobody in the league has a player who would improve your lineup over {best.span} and also needs one of yours. Try a trade you have in mind below.</p>
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

    <section id="try-a-trade" class="scroll-mt-20 space-y-3" data-testid="try">
      <div class="flex flex-wrap items-end justify-between gap-2">
        <h2 class="text-xl font-bold">Try a trade</h2>
        <label class="flex min-w-0 items-center gap-2 text-sm text-ink-2">
          <span class="shrink-0">Trade partner</span>
          <select class="ll-input min-w-0" value={partner === null ? "" : String(partner)} onchange={(e) => pickPartner(Number(e.currentTarget.value))} data-testid="partner">
            {#each others as r (r.roster_id)}<option value={String(r.roster_id)}>{r.team_name}{r.manager_name ? ` (${r.manager_name})` : ""}</option>{/each}
          </select>
        </label>
      </div>
      <div class="grid grid-cols-1 gap-3 wide:grid-cols-2">
        {@render picker("give", myPlayers, give, "You give")}
        {@render picker("get", theirPlayers, getIds, `You get · ${teamName(partner)}`)}
      </div>

      {#if !give.length || !getIds.length}
        <p class="ll-empty" data-testid="tick-both">Tick at least one player on each side to see what the trade does to both lineups.</p>
      {:else if evalError}
        <p class="ll-error" data-testid="eval-error">{evalError}</p>
      {:else if !result || evaluating}
        <div class="ll-skel h-40" aria-label="Re-solving both lineups" data-testid="evaluating"></div>
      {:else}
        {@const r = result}
        <Card tone="accent" testid="trade-result">
          <p class="text-lg leading-snug" data-testid="trade-headline"><Md text={r.headline ?? `**You give ${names(r.give)}; you get ${names(r.get)}.**`} {ctx} /></p>
          <p class="mt-2 text-lg leading-snug font-semibold text-ink" data-testid="verdict">{r.verdict}</p>

          <div class="mt-4 grid grid-cols-2 gap-2 wide:grid-cols-4" data-testid="fit-tiles">
            <StatTile label="You · this week" value={s1(r.fit.mine.week)} caption={`${f2(r.before.mine.week)} → ${f2(r.after.mine.week)}`} />
            <StatTile label={`You · ${r.span}`} value={s1(r.fit.mine.horizon)} caption={`${f1(r.before.mine.horizon)} → ${f1(r.after.mine.horizon)}`} />
            <StatTile label={`${r.partner_team_name} · this week`} value={s1(r.fit.theirs.week)} caption={`${f2(r.before.theirs.week)} → ${f2(r.after.theirs.week)}`} />
            <StatTile label={`${r.partner_team_name} · ${r.span}`} value={s1(r.fit.theirs.horizon)} caption={`${f1(r.before.theirs.horizon)} → ${f1(r.after.theirs.horizon)}`} />
          </div>
          {#if r.fit.line}<p class="mt-2 text-sm text-ink-2"><Md text={r.fit.line} {ctx} /></p>{/if}

          <div class="mt-4 grid gap-4 wide:grid-cols-2">
            <div data-testid="market">
              <div class="ll-label mb-2">Market: season points above a free agent</div>
              <div class="space-y-2">
                <Bar label="You give" value={r.market.give} max={mmax} display={fmt.whole(r.market.give)} color="var(--ll-div-hot)" />
                <Bar label="You get" value={r.market.get} max={mmax} display={fmt.whole(r.market.get)} />
              </div>
              {#if r.market.line}<p class="mt-2 text-sm text-ink-2"><Md text={r.market.line} {ctx} /></p>{/if}
            </div>
            <div data-testid="ros">
              <div class="ll-label mb-2">Rest of season{r.ros.window ? ` · ${r.ros.window}` : ""}</div>
              <div class="space-y-2">
                <Bar label="You give" value={r.ros.give} max={rmax} display={fmt.whole(r.ros.give)} color="var(--ll-div-hot)" />
                <Bar label="You get" value={r.ros.get} max={rmax} display={fmt.whole(r.ros.get)} />
              </div>
              <p class="mt-2 text-sm text-ink-2">
                The players' plain totals up to this league's final ({(r.ros.get ?? 0) - (r.ros.give ?? 0) >= 0 ? "+" : "−"}{Math.abs((r.ros.get ?? 0) - (r.ros.give ?? 0))}), before the roster spot a lopsided trade frees or fills.
              </p>
            </div>
          </div>

          {#if r.sides}
            {@const sizes = [
              ...r.sides.mine.cuts.map((c) => `you must cut ${c.player_name} (costs ${f1(c.horizon_loss)} over ${r.span})`),
              ...(r.sides.mine.opened ? [`you open ${r.sides.mine.opened === 1 ? "a spot" : `${r.sides.mine.opened} spots`}`] : []),
              ...r.sides.theirs.cuts.map((c) => `they must cut ${c.player_name} (costs ${f1(c.horizon_loss)} over ${r.span})`),
              ...(r.sides.theirs.opened ? [`they open ${r.sides.theirs.opened === 1 ? "a spot" : `${r.sides.theirs.opened} spots`}`] : []),
            ]}
            <p class="mt-3 text-sm text-ink-2" data-testid="roster-size">Roster size: {sizes.length ? sizes.join("; ") : `no change (${r.give.length} for ${r.get.length})`}.</p>
          {/if}
        </Card>

        {#if r.sides}
          <div class="grid grid-cols-1 gap-3 wide:grid-cols-2">
            {#each [{ s: r.sides.mine, who: "Your lineup", b: r.before.mine, a: r.after.mine }, { s: r.sides.theirs, who: `${r.partner_team_name}'s lineup`, b: r.before.theirs, a: r.after.theirs }] as side (side.who)}
              <Card title={`${side.who}, week ${r.week}`} pad={false} testid="lineup-after">
                <p class="px-4 pb-2 text-base">
                  <strong class="tabnum">{f2(side.b.week)} → {f2(side.a.week)}</strong>
                  <span class="text-ink-2">({s1(side.s.gain_week)}) · depth {f1(side.b.bench)} → {f1(side.a.bench)}</span>
                </p>
                <ul class="divide-y divide-line">
                  {#each side.s.lineup as row, i (`${row.slot}-${i}`)}
                    <li class="grid min-h-11 grid-cols-[4.5rem_minmax(0,1fr)_3.25rem_3.25rem] items-center gap-2 px-3 py-1 {row.is_new ? 'bg-accent-soft' : ''}">
                      <span class="text-sm font-semibold text-ink-3">{slotLabel(row.slot)}</span>
                      <span class="min-w-0 truncate text-base">
                        {#if href(row.gsis_id)}<a class="ll-name" href={href(row.gsis_id)}>{row.player_name ?? "—"}</a>{:else}{row.player_name ?? "—"}{/if}
                        {#if row.is_new}<span class="ml-1 rounded-sm bg-accent px-1 text-[10px] font-bold text-on-accent uppercase">new</span>{/if}
                      </span>
                      <span class="tabnum text-right text-base">{f2(row.value)}</span>
                      <span class="tabnum text-right text-sm {row.change == null ? 'text-ink-3' : row.change > 0 ? 'text-good' : 'text-bad'}">{row.change == null ? "" : s1(row.change)}</span>
                    </li>
                  {/each}
                </ul>
                {#if side.s.closest_after}
                  <p class="px-4 py-2 text-xs text-ink-3">Closest call after: {side.s.closest_after.player_name} at {slotLabel(side.s.closest_after.slot)}, {f2(side.s.closest_after.margin)} ahead of the next option.</p>
                {/if}
              </Card>
            {/each}
          </div>
        {/if}

        {#if r.weekly?.length}
          <Expander title={`Week by week (${r.span})`} testid="weekly">
            <table class="w-full table-fixed text-base" data-testid="weekly-table">
              <thead>
                <tr class="text-left text-label font-semibold tracking-[0.08em] text-ink-3 uppercase">
                  <th class="w-12 py-1">Week</th><th class="py-1 text-right">You now</th><th class="py-1 text-right">You after</th><th class="py-1 text-right">Them now</th><th class="py-1 text-right">Them after</th>
                </tr>
              </thead>
              <tbody>
                {#each r.weekly as w (w.week)}
                  <tr class="border-t border-line">
                    <td class="py-1.5">{w.week}</td><td class="tabnum text-right">{f1(w.you_before)}</td><td class="tabnum text-right font-semibold">{f1(w.you_after)}</td><td class="tabnum text-right">{f1(w.them_before)}</td><td class="tabnum text-right font-semibold">{f1(w.them_after)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
            <p class="mt-2 text-sm text-ink-3">Each week is re-solved on its own: byes, injuries and taxi squads as in that week's lineup.</p>
          </Expander>
        {/if}
      {/if}
    </section>

    <section class="space-y-3" data-testid="finder">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h2 class="text-xl font-bold">Who should I trade with?</h2>
        {#if finder}<p class="text-sm text-ink-3">Trades that raise both lineups over {finder.span}, best first</p>{/if}
      </div>
      <Tabs items={wantTabs} current={want} onpick={(w) => setParams({ want: w === "ALL" ? null : w })} size="sm" label="You want" testid="want" />
      {#if !finder}
        <div class="ll-skel h-32" aria-label="Loading"></div>
      {:else if !finder.partners.length}
        <p class="ll-empty" data-testid="finder-empty">No trade that raises both lineups brings you {want === "ALL" ? "anyone" : `a ${want}`}. Try a trade you have in mind above.</p>
      {:else}
        {@const gmax = Math.max(1, ...finder.partners.flatMap((p) => [p.my_horizon, p.their_horizon]))}
        <div class="grid grid-cols-1 gap-3 wide:grid-cols-2">
          {#each finder.partners.slice(0, 12) as p, i (`${p.roster_id}-${p.shape}-${i}`)}
            <Card testid="partner-row">
              <div class="flex items-baseline justify-between gap-2">
                <span class="min-w-0 truncate text-lg font-bold">{p.team_name}</span>
                <span class="ll-label shrink-0">{p.shape}</span>
              </div>
              <div class="mt-2 space-y-1.5 text-base">
                <div class="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1"><span class="ll-label w-14">You get</span>{#each p.get as x (x.sleeper_id)}{@render face(x)}{/each}</div>
                <div class="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1"><span class="ll-label w-14">You give</span>{#each p.give as x (x.sleeper_id)}{@render face(x)}{/each}</div>
              </div>
              <div class="mt-3 grid grid-cols-2 gap-3">
                <Bar label="You" value={p.my_horizon} max={gmax} display={s1(p.my_horizon)} thick={6} />
                <Bar label="Them" value={p.their_horizon} max={gmax} display={s1(p.their_horizon)} thick={6} />
              </div>
              <div class="mt-3 flex items-center justify-between gap-2">
                <span class="text-xs text-ink-3">Market: give {fmt.whole(p.market_out)}, get {fmt.whole(p.market_in)} · this week you {s1(p.my_week)}</span>
                <button type="button" class="min-h-9 shrink-0 rounded-md border border-line-strong px-3 text-sm font-semibold" onclick={() => tryTrade(p)} data-testid="try-partner">Try it</button>
              </div>
            </Card>
          {/each}
        </div>
        {#if finder.none.length}<p class="text-sm text-ink-3">No trade helps both lineups with: {finder.none.join(", ")}.</p>{/if}
      {/if}
    </section>

    <Expander title="How to read this" testid="howto">
      <div class="text-base leading-snug">
        {@html md(
          "- **Who to call**: the first line names the team where one trade raises *both* lineups the most over the next four weeks, and the trade. Teams are ranked by the smaller of the two gains, so the other manager has a reason to say yes too.\n" +
            "- **Try a trade**: pick the team, tick players both ways. You see both best lineups this week before and after (every slot re-picked, FLEX and superflex included), the four-week totals and the depth.\n" +
            "- **Fit** is what the starting lineups gain. **Market** is what the players are worth on the market: their projected points for the rest of the season above the best free agent at their position. They are never added together: a player can be worth a lot and still sit on your bench. The verdict reads both. It knows nothing of draft picks, next season or what the other manager believes.\n" +
            "- **Roster size**: if a team gets more players than it gives, it has to cut someone: the player it would miss least, and that loss is in the numbers.\n" +
            "- Copy the page's link to share a trade: the link opens the same trade.",
        )}
      </div>
    </Expander>
  {/if}
</main>
