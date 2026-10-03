<script lang="ts">
  // IA-2 (Wave I-A): the trade calculator, its own link in the Decisions row (it was the Trades screen's "Try a trade").
  // Pick a partner, tick players both ways (both rosters from GET /api/team); every change asks POST
  // /api/trades/evaluate (a 250 ms pause, so ticking two players asks once) and the dial swings to the other manager's
  // interest — by our numbers over the window — with your own gain beside it. The window (this week · next 4 · rest of
  // season · playoffs) is a segmented control with one line saying why; the lineups are shown once (yours, then theirs
  // under an expander). The package and the window are the URL (?partner=&give=&get=&window=), so a copied link opens
  // the same trade.
  // IB-2 (Wave I-B): the decision stays in view while you browse the rosters — once the dial's row scrolls away, the
  // verdict bar is pinned to the top of the screen: the package, the dial's label, your gain; on desktop open (the four
  // tiles and the verdict beside them), on a phone collapsed, a tap opens it. (Pinned with position: fixed — html / body
  // clip sideways with overflow-x: hidden, which turns off position: sticky for the whole page.) The page leads with the decision and
  // the lineup impact (this week / the window); the explanation (market, rest of season, ranks, roster size, week by
  // week) is behind "Why?" and both lineups behind "Lineups", collapsed. A name in the lists opens the research pane.
  import { ApiError, decisionPaths, evaluateIn, get, paths, peek, Unauthorized, type Roster, type Team, type TeamRosterRow, type TradeEval, type TradeLineupX, type TradeWindow } from "../../lib/api";
  import type { LeagueOption } from "../../lib/leagues";
  import { md, withContext } from "../../lib/md";
  import { errorWords, f1, f2, names, parseIds, s1, slotLabel } from "../../lib/decisions";
  import { windowOf, windowWhy } from "../../lib/decisions";
  import { openPlayer } from "../../lib/decisions";
  import { restoreScroll, route, setParams } from "../../lib/router.svelte";
  import { fmt } from "../../lib/theme";
  import Bar from "../../components/Bar.svelte";
  import Card from "../../components/Card.svelte";
  import Expander from "../../components/Expander.svelte";
  import Headshot from "../../components/Headshot.svelte";
  import Md from "../../components/Md.svelte";
  import PosBadge from "../../components/PosBadge.svelte";
  import ScreenHead from "../../components/ScreenHead.svelte";
  import StatTile from "../../components/StatTile.svelte";
  import TeamBadge from "../../components/TeamBadge.svelte";
  import Dial from "./Dial.svelte";
  import WindowControl from "./WindowControl.svelte";

  let { league, team, onauth }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  const ctx = $derived({ league, team });
  const params = $derived(route.current.params);
  const win = $derived<TradeWindow>(windowOf(params.get("window")));

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

  $effect(() => {
    const l = league;
    const t = team;
    error = null;
    mine = null;
    if (t === null) return;
    load<Team>(decisionPaths.team(l, t), (v) => (mine = v), () => league === l && team === t);
    load<Roster[]>(paths.rosters(l), (v) => (rosters = v), () => league === l);
  });

  const others = $derived(rosters.filter((r) => r.roster_id !== team));
  const partner = $derived.by(() => {
    const p = Number(params.get("partner"));
    if (p && others.some((r) => r.roster_id === p)) return p;
    return others[0]?.roster_id ?? null;
  });

  $effect(() => {
    const l = league;
    const p = partner;
    theirs = null;
    if (p === null) return;
    load<Team>(decisionPaths.team(l, p), (v) => (theirs = v), () => league === l && partner === p);
  });

  const playable = (rows: TeamRosterRow[] | undefined) =>
    (rows ?? []).filter((r) => r.role !== "empty" && r.sleeper_id).sort((a, b) => (b.value ?? -1) - (a.value ?? -1));
  const myPlayers = $derived(playable(mine?.roster));
  const theirPlayers = $derived(playable(theirs?.roster));
  const give = $derived(parseIds(params.get("give")).filter((id) => myPlayers.some((r) => r.sleeper_id === id)));
  const getIds = $derived(parseIds(params.get("get")).filter((id) => theirPlayers.some((r) => r.sleeper_id === id)));
  const pkgKey = $derived(
    partner !== null && give.length && getIds.length ? `${league}|${team}|${partner}|${[...give].sort()}|${[...getIds].sort()}|${win}` : "",
  );

  // evaluate on every change (a 250 ms pause, so ticking two players asks once); the last answer stays on screen while
  // the next one is asked, so the dial swings from where it was
  $effect(() => {
    const key = pkgKey;
    if (!key || team === null || partner === null) {
      result = null;
      evalError = null;
      return;
    }
    if (key === resultKey && result) return;
    const body = { league, team, partner, give: [...give], get: [...getIds] };
    const w = win;
    const timer = setTimeout(() => {
      evaluating = true;
      evalError = null;
      evaluateIn(body, w)
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
        .finally(() => {
          if (pkgKey === key) evaluating = false;
        });
    }, 250);
    return () => clearTimeout(timer);
  });

  function toggle(side: "give" | "get", id: string) {
    const cur = side === "give" ? give : getIds;
    const next = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
    setParams({ [side]: next.length ? next.join(",") : null });
  }

  const teamName = (id: number | null) => rosters.find((r) => r.roster_id === id)?.team_name ?? `Team ${id}`;
  const verdictLess = (r: TradeEval) => (r.headline ?? `**You give ${names(r.give)}; you get ${names(r.get)}.**`).replace(r.verdict, "").trim();
  const shown = $derived(pkgKey && result ? result : null); // the answer on screen (the last one while the next is asked)
  const weekly = $derived(
    shown ? shown.weeks.map((w, i) => ({ week: w, you_before: shown.before.mine.by_week[i], you_after: shown.after.mine.by_week[i], them_before: shown.before.theirs.by_week[i], them_after: shown.after.theirs.by_week[i] })) : [],
  );
  const mmax = $derived(Math.max(1, shown?.market.give ?? 0, shown?.market.get ?? 0));
  const rmax = $derived(Math.max(1, shown?.ros?.give ?? 0, shown?.ros?.get ?? 0));
  const href = (g: string | null | undefined) => (g ? withContext(`/player/${g}`, ctx) : null);
  const span = $derived(shown?.span ?? null);
  // the bar (a phone) shows the dial's reading only while the dial itself is off screen (no number twice)
  let dialInView = $state(true);
  let barOpen = $state(false);
  let wideNow = $state(false);
  $effect(() => {
    if (dialInView) barOpen = false;
  });
  $effect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia("(min-width: 56.25rem)");
    const set = () => (wideNow = mq.matches);
    set();
    mq.addEventListener("change", set);
    return () => mq.removeEventListener("change", set);
  });
  // ---- IB-2: the package in a few words for the bar ("Jefferson → Lloyd + Pacheco")
  const lastName = (n: string | null | undefined) => {
    const p = (n ?? "").trim().split(/\s+/);
    return p.length > 1 && !/^(Jr\.|Sr\.|II|III|IV)$/.test(p[p.length - 1]) ? p[p.length - 1] : p.length > 2 ? p[p.length - 2] : (n ?? "");
  };
  const pkgWords = $derived(
    `${myPlayers.filter((r) => give.includes(r.sleeper_id ?? "")).map((r) => lastName(r.player_name)).join(" + ")} → ${theirPlayers
      .filter((r) => getIds.includes(r.sleeper_id ?? ""))
      .map((r) => lastName(r.player_name))
      .join(" + ")}`,
  );
  const labelTone = (l: string) => (l === "No deal" ? "text-bad" : l === "Maybe" ? "text-warn" : "text-good");
  // ---- IE-2: the result through the starting lineup — the package's names with positions, a starter's points in one
  // decimal, the lineup rows' per-player change (the answer's; a slot move is none)
  const posOf = (p: { position?: string | null; team?: string | null }) => [p.position, p.team].filter(Boolean).join(" · ");
  const lx = (l: TradeEval["lineups"]["mine"]) => l as TradeLineupX;
  // ---- end IE-2
  // a name in the roster lists: the research pane (IB-1, "Add to trade"), else nothing (the checkbox is the row's tap)
  function paneFor(side: "give" | "get", r: TeamRosterRow) {
    openPlayer(r.gsis_id, { from: "trade", context: { sleeper_id: r.sleeper_id, side, partner: side === "get" ? partner : null, name: r.player_name } }, () => {});
  }
  // ---- end IB-2
  function watchDial(el: HTMLElement) {
    if (typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((es) => (dialInView = es.some((e) => e.isIntersecting)), { threshold: 0.2 });
    io.observe(el);
    return () => {
      io.disconnect();
      dialInView = true;
    };
  }
</script>

{#snippet picker(side: "give" | "get", rows: TeamRosterRow[], picked: string[], title: string)}
  <Card {title} pad={false} testid={`pick-${side}`}>
    {#if picked.length}
      <p class="-mt-1 px-4 pb-2 text-sm text-ink-2" data-testid={`picked-${side}`}>
        {rows.filter((r) => picked.includes(r.sleeper_id ?? "")).map((r) => r.player_name).join(" + ")}
      </p>
    {/if}
    {#if !rows.length}
      <div class="space-y-2 p-3"><div class="ll-skel h-10"></div><div class="ll-skel h-10"></div></div>
    {:else}
      <ul class="max-h-[26rem] divide-y divide-line overflow-y-auto">
        {#each rows as r (r.sleeper_id)}
          {@const on = picked.includes(r.sleeper_id ?? "")}
          <li>
            <label class="flex min-h-12 cursor-pointer items-center gap-2.5 px-3 py-1.5 {on ? 'bg-accent-soft' : 'hover:bg-raised'}" data-testid={`${side}-option`} data-id={r.sleeper_id}>
              <input type="checkbox" class="h-5 w-5 shrink-0 accent-[var(--ll-accent)]" checked={on} onchange={() => toggle(side, r.sleeper_id ?? "")} />
              <Headshot url={r.headshot_url} name={r.player_name ?? ""} team={r.team} size={32} />
              <span class="min-w-0 flex-1">
                <span class="block truncate text-base font-semibold">
                  {#if r.gsis_id}
                    <a
                      class="ll-name"
                      href={href(r.gsis_id)}
                      onclick={(e) => {
                        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
                        e.preventDefault();
                        e.stopPropagation();
                        paneFor(side, r);
                      }}
                      data-testid={`${side}-name`}>{r.player_name}</a
                    >
                  {:else}{r.player_name}{/if}
                </span>
                <span class="flex items-center gap-1.5 text-xs text-ink-3">
                  <PosBadge pos={r.position} />
                  {#if r.position !== "DEF"}<TeamBadge team={r.team} />{/if}
                  <span class="truncate">{r.role === "starter" ? slotLabel(r.slot) : r.role === "bench" ? "bench" : (r.reason ?? "out")}</span>
                </span>
              </span>
              <span class="tabnum shrink-0 text-right text-base font-semibold">{r.role === "unplayable" ? "—" : f1(r.value)}</span>
            </label>
          </li>
        {/each}
      </ul>
    {/if}
  </Card>
{/snippet}

{#snippet pickers()}
  <div class="grid grid-cols-1 gap-3 wide:grid-cols-2">
    {@render picker("give", myPlayers, give, "You give")}
    {@render picker("get", theirPlayers, getIds, `You get · ${teamName(partner)}`)}
  </div>
{/snippet}

{#snippet lineup(l: TradeEval["lineups"]["mine"], who: string, week: number)}
  <Card title={`${who}, week ${week}`} pad={false} testid="lineup-after">
    <ul class="divide-y divide-line">
      {#each l.slots as row, i (`${row.slot}-${i}`)}
        {@const isNew = (row.player_name ?? "").endsWith(" (new)")}
        <li class="grid min-h-11 grid-cols-[4.5rem_minmax(0,1fr)_3.25rem_3.25rem] items-center gap-2 px-3 py-1 {isNew ? 'bg-accent-soft' : ''}">
          <span class="text-sm font-semibold text-ink-3">{slotLabel(row.slot)}</span>
          <span class="min-w-0 truncate text-base">
            {#if href(row.gsis_id)}<a class="ll-name" href={href(row.gsis_id)}>{row.player_name ?? "—"}</a>{:else}{row.player_name ?? "—"}{/if}
          </span>
          <span class="tabnum text-right text-base">{f2(row.value)}</span>
          <span class="tabnum text-right text-sm {row.change == null ? 'text-ink-3' : row.change > 0 ? 'text-good' : 'text-bad'}">{row.change == null ? "" : s1(row.change)}</span>
        </li>
      {/each}
    </ul>
    <!-- ---- IE-2: the starters who left (their points as the change), the slot moves as detail (no points) -->
    {#if lx(l).out?.length}
      <ul class="divide-y divide-line border-t border-line" data-testid="lineup-out">
        {#each lx(l).out ?? [] as row, i (`out-${i}`)}
          <li class="grid min-h-11 grid-cols-[4.5rem_minmax(0,1fr)_3.25rem_3.25rem] items-center gap-2 px-3 py-1 text-ink-2">
            <span class="text-sm font-semibold">{row.slot}</span>
            <span class="min-w-0 truncate text-base"><s>{row.player_name}</s> <span class="text-sm">({row.why})</span></span>
            <span class="tabnum text-right text-base">{f2(row.value)}</span>
            <span class="tabnum text-right text-sm text-bad">{s1(row.change)}</span>
          </li>
        {/each}
      </ul>
    {/if}
    {#if lx(l).total}<p class="px-4 pt-2 text-sm text-ink" data-testid="lineup-total">Lineup total: {f2(lx(l).total!.before)} → {f2(lx(l).total!.after)} ({s1(lx(l).total!.change)}). The changes are by player: a starter who only moves to another {lx(l).reshuffled?.length ? "numbered slot" : "slot"} shows none.</p>{/if}
    {#if lx(l).reshuffled?.length}<p class="px-4 pt-1 text-sm text-ink-2" data-testid="lineup-reshuffled">Slot moves only (no points): {lx(l).reshuffled!.join("; ")}.</p>{/if}
    <!-- ---- end IE-2 -->
    {#each l.notes as note, i (i)}<p class="px-4 pt-2 text-sm text-ink-2">{note}</p>{/each}
    {#if l.closest_call}<p class="px-4 py-2 text-sm text-ink-2">Closest call after: {l.closest_call}.</p>{/if}
  </Card>
{/snippet}

<main class="space-y-4" data-testid="trade-calc">
  {#if team === null}
    <p class="ll-empty" data-testid="pick-team-first">Pick your team above: the calculator then shows what a trade does to both lineups, and how much the other team would want it.</p>
  {:else if error}
    <p class="ll-error" data-testid="error">{error}</p>
  {:else}
    <ScreenHead eyebrow="Trades · calculator" title="Trade calculator">
      {#snippet answer()}
        {#if shown}
          <p data-testid="trade-headline"><Md text={verdictLess(shown)} {ctx} /></p>
        {:else}
          <p>Pick a team and tick players both ways. The dial shows how much they would want the trade, by our numbers.</p>
        {/if}
      {/snippet}
    </ScreenHead>

    <!-- the window: which weeks the trade is priced over, and why -->
    <WindowControl current={win} span={shown?.window === win ? shown.span : null} onpick={(w) => setParams({ window: w === "next4" ? null : w })} />

    <div class="flex flex-wrap items-end justify-between gap-2">
      <label class="flex min-w-0 items-center gap-2 text-sm text-ink-2">
        <span class="shrink-0">Trade partner</span>
        <select class="ll-input min-w-0" value={partner === null ? "" : String(partner)} onchange={(e) => setParams({ partner: e.currentTarget.value, get: null })} data-testid="partner">
          {#each others as r (r.roster_id)}<option value={String(r.roster_id)}>{r.team_name}{r.manager_name ? ` (${r.manager_name})` : ""}</option>{/each}
        </select>
      </label>
    </div>

    <!-- the dial's row: their interest, your gain, the differences this week and over the window -->
    {#if !give.length || !getIds.length}
      <p class="ll-empty" data-testid="tick-both">Tick at least one player on each side: the dial shows how much they would want it.</p>
    {:else if evalError}
      <p class="ll-error" data-testid="eval-error">{evalError}</p>
    {:else if !shown}
      <div class="ll-skel h-48" aria-label="Re-solving both lineups" data-testid="evaluating"></div>
    {:else}
      {@const r = shown}
      <Card tone="accent" testid="trade-result">
        <div class="grid items-center gap-4 wide:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]" data-testid="dial-row" aria-busy={evaluating} {@attach watchDial}>
          {#if r.interest}
            <Dial score={r.interest.score} label={r.interest.label} caption={r.interest.caption} you={r.interest.you} youLabel={`You · ${r.span}`} busy={evaluating} />
          {/if}
          <div class="min-w-0">
            <div class="grid grid-cols-2 gap-2" data-testid="fit-tiles">
              <StatTile label="You · this week" value={s1(r.fit.this_week.mine)} caption={`${f2(r.before.mine.this_week)} → ${f2(r.after.mine.this_week)}`} size="sm" />
              <StatTile label={r.window === "week" ? `You · ${r.span}` : `You · ${r.span} in total`} value={s1(r.fit.next_4.mine)} caption={`${f1(r.before.mine.horizon)} → ${f1(r.after.mine.horizon)}`} size="sm" />
              <StatTile label={`${r.partner_team} · this week`} value={s1(r.fit.this_week.theirs)} caption={`${f2(r.before.theirs.this_week)} → ${f2(r.after.theirs.this_week)}`} size="sm" />
              <StatTile label={r.window === "week" ? `${r.partner_team} · ${r.span}` : `${r.partner_team} · ${r.span} in total`} value={s1(r.fit.next_4.theirs)} caption={`${f1(r.before.theirs.horizon)} → ${f1(r.after.theirs.horizon)}`} size="sm" />
            </div>
            <p class="mt-3 text-lg leading-snug font-semibold text-ink" data-testid="verdict">{r.verdict}</p>
            {#if r.sanity}
              <p class="mt-2 rounded-md bg-warn-soft p-2 text-sm text-ink" data-testid="sanity">We would not suggest this one: {r.sanity}.</p>
            {/if}
          </div>
        </div>
        <!-- ---- IE-2 result: what the trade does, through your starting lineup (the review: assets and cut → the effect →
             who starts and who sits → backup coverage → their side → the window and the alternatives); the arithmetic is
             under "How we calculated this" -->
        {#if r.effect_words}
          <div class="mt-4 space-y-3 border-t border-line pt-3" data-testid="trade-story">
            <dl class="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-2 gap-y-1 text-base" data-testid="trade-assets">
              <dt class="font-semibold text-ink-2">You give</dt>
              <dd class="min-w-0">{#each r.give as p, i (p.sleeper_id)}{i ? ", " : ""}<strong>{p.player_name}</strong> <span class="text-sm text-ink-2">({posOf(p)})</span>{/each}</dd>
              <dt class="font-semibold text-ink-2">You get</dt>
              <dd class="min-w-0">{#each r.get as p, i (p.sleeper_id)}{i ? ", " : ""}<strong>{p.player_name}</strong> <span class="text-sm text-ink-2">({posOf(p)})</span>{/each}</dd>
              {#each r.cut ?? [] as c (c.player.sleeper_id)}
                <dt class="font-semibold text-bad">Cut</dt>
                <dd class="min-w-0" data-testid="trade-cut">{c.words}</dd>
              {/each}
            </dl>
            <p class="text-lg leading-snug font-semibold text-ink" data-testid="trade-effect">{r.effect_words}</p>
            <div data-testid="trade-starters">
              <h3 class="ll-label mb-1">Your starters this week</h3>
              <ul class="space-y-1 text-base">
                {#each r.starters_in ?? [] as x (x.player.sleeper_id)}
                  <li class="flex items-baseline gap-2" data-testid="starter-in"><span class="w-10 shrink-0 font-semibold text-good">In</span><span class="min-w-0 flex-1"><strong>{x.player.player_name}</strong> at {x.slot} <span class="text-sm text-ink-2">({x.how === "trade" ? "from the trade" : "from your bench"})</span></span><span class="tabnum shrink-0">{f1(x.value)}</span></li>
                {/each}
                {#each r.starters_out ?? [] as x (x.player.sleeper_id)}
                  <li class="flex items-baseline gap-2" data-testid="starter-out"><span class="w-10 shrink-0 font-semibold text-bad">Out</span><span class="min-w-0 flex-1"><strong>{x.player.player_name}</strong> from {x.slot} <span class="text-sm text-ink-2">({x.why})</span></span><span class="tabnum shrink-0">{f1(x.value)}</span></li>
                {/each}
                {#if !(r.starters_in ?? []).length && !(r.starters_out ?? []).length}
                  <li class="text-ink-2">The same players start this week.</li>
                {/if}
              </ul>
              {#if lx(r.lineups.mine).total}
                {@const t = lx(r.lineups.mine).total!}
                <p class="mt-1 text-sm text-ink-2" data-testid="trade-total">Starting lineup this week: {f1(t.before)} → <strong class="text-ink">{f1(t.after)}</strong> ({s1(t.change)} projected points)</p>
              {/if}
            </div>
            {#if r.backup_words}<p class="text-base text-ink" data-testid="trade-backup">{r.backup_words}</p>{/if}
            {#if r.their_change}
              <p class="text-base text-ink" data-testid="trade-their-side">{r.their_change.effect_words} <span class="text-ink-2">{r.their_change.lineup_words}</span></p>
            {/if}
            {#if r.hold_words}
              <p class="text-base text-ink" data-testid="trade-hold"><span class="font-semibold">The alternatives{r.window_words ? ` (${r.window_words})` : ""}:</span> {r.hold_words}</p>
            {/if}
          </div>
        {/if}
        <!-- ---- end IE-2 result -->
      </Card>
    {/if}

    <!-- IB-2: the verdict bar — pinned to the top once the dial has scrolled away (fixed: nothing in the flow moves when
         it appears); open on desktop, a tap opens it on a phone -->
    {#if shown?.interest && give.length && getIds.length && !dialInView}
      {@const r = shown}
      {@const open = barOpen || wideNow}
      <div class="pointer-events-none fixed inset-x-0 top-0 z-30 pt-[env(safe-area-inset-top)]" data-testid="verdict-bar-slot">
        <div class="mx-auto max-w-6xl px-3">
          <div class="pointer-events-auto rounded-b-lg border border-t-0 border-line-strong bg-surface shadow-lg" data-testid="verdict-bar" aria-live="polite">
            <button type="button" class="flex min-h-12 w-full items-center gap-2 px-3 py-2 text-left text-sm" aria-expanded={open} onclick={() => (barOpen = !barOpen)} data-testid="verdict-bar-toggle">
              <span class="min-w-0 flex-1 truncate font-semibold text-ink" data-testid="verdict-bar-package">{pkgWords}</span>
              <span class="flex shrink-0 items-center gap-1.5" data-testid="dial-chip">
                <strong class={labelTone(r.interest!.label)}>{r.interest!.label}</strong>
                <span class="tabnum text-ink-3">{r.interest!.score}</span>
                <span class="ll-label">You</span><strong class="tabnum">{s1(r.interest!.you)}</strong>
              </span>
              <span class="chev shrink-0 text-ink-3 wide:hidden {open ? 'rotate-90' : ''}" aria-hidden="true">›</span>
            </button>
            {#if open}
              <div class="max-h-[60vh] overflow-y-auto border-t border-line px-3 pt-2 pb-3" data-testid="verdict-bar-detail">
                <div class="grid grid-cols-2 gap-2 wide:grid-cols-4">
                  <StatTile label="You · this week" value={s1(r.fit.this_week.mine)} caption={`${f2(r.before.mine.this_week)} → ${f2(r.after.mine.this_week)}`} size="sm" />
                  <StatTile label={`You · ${r.span}`} value={s1(r.fit.next_4.mine)} caption={`${f1(r.before.mine.horizon)} → ${f1(r.after.mine.horizon)}`} size="sm" />
                  <StatTile label={`${r.partner_team} · this week`} value={s1(r.fit.this_week.theirs)} size="sm" />
                  <StatTile label={`${r.partner_team} · ${r.span}`} value={s1(r.fit.next_4.theirs)} size="sm" />
                </div>
                <p class="mt-2 text-base leading-snug font-semibold text-ink">{r.verdict}</p>
                {#if r.sanity}<p class="mt-1 text-sm text-ink-2">We would not suggest this one: {r.sanity}.</p>{/if}
              </div>
            {/if}
          </div>
        </div>
      </div>
    {/if}

    {@render pickers()}

    {#if shown && give.length && getIds.length && !evalError}
      {@const r = shown}
      <Expander title="How we calculated this" testid="why">
      {#if verdictLess(r)}<p class="mb-3 text-base leading-snug" data-testid="why-headline"><Md text={verdictLess(r)} {ctx} /></p>{/if}
      <Card testid="trade-details">
        <div class="grid gap-4 wide:grid-cols-2">
          <div data-testid="market">
            <div class="ll-label mb-2">Projected value above available replacements</div>
            <div class="space-y-2">
              <Bar label="You give" value={r.market.give} max={mmax} display={fmt.whole(r.market.give)} color="var(--ll-div-hot)" />
              <Bar label="You get" value={r.market.get} max={mmax} display={fmt.whole(r.market.get)} />
            </div>
            {#if r.market.words}<p class="mt-2 text-sm text-ink-2"><Md text={r.market.words} {ctx} /></p>{/if}
          </div>
          {#if r.ros}
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
          {/if}
        </div>
        {#if r.fit.words}<p class="mt-3 text-sm text-ink-2" data-testid="fit-words"><Md text={r.fit.words} {ctx} /></p>{/if}
        {#if r.ranks?.words}<p class="mt-3 text-sm text-ink-2" data-testid="rank-change"><Md text={r.ranks.words} {ctx} /></p>{/if}
        {#if r.size_words}<p class="mt-2 text-sm text-ink-2" data-testid="roster-size"><Md text={r.size_words} {ctx} /></p>{/if}
      </Card>
      {#if weekly.length > 1}
        <div class="mt-3" data-testid="weekly">
          <div class="ll-label mb-1">Week by week ({r.span})</div>
          <table class="w-full table-fixed text-base" data-testid="weekly-table">
            <thead>
              <tr class="text-left text-label font-semibold tracking-[0.08em] text-ink-3 uppercase">
                <th class="w-12 py-1">Week</th><th class="py-1 text-right">You now</th><th class="py-1 text-right">You after</th><th class="py-1 text-right">Them now</th><th class="py-1 text-right">Them after</th>
              </tr>
            </thead>
            <tbody>
              {#each weekly as w (w.week)}
                <tr class="border-t border-line">
                  <td class="py-1.5">{w.week}</td><td class="tabnum text-right">{f1(w.you_before)}</td><td class="tabnum text-right font-semibold">{f1(w.you_after)}</td><td class="tabnum text-right">{f1(w.them_before)}</td><td class="tabnum text-right font-semibold">{f1(w.them_after)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
          <p class="mt-2 text-sm text-ink-3">Each week is re-solved on its own: byes, injuries and taxi squads as in that week's lineup.</p>
        </div>
      {/if}
      </Expander>

      <!-- the lineups, once: yours, then theirs under an expander — both behind "Lineups", collapsed -->
      {#if r.lineups}
        <Expander title={`Lineups, week ${r.week}`} testid="lineups-x">
          <div class="grid grid-cols-1 gap-3 wide:grid-cols-2" data-testid="lineups">
            {@render lineup(r.lineups.mine, "Your lineup", r.week)}
            <Expander title={`${r.partner_team}'s lineup, week ${r.week}`} testid="lineup-theirs">
              {@render lineup(r.lineups.theirs, `${r.partner_team}'s lineup`, r.week)}
            </Expander>
          </div>
        </Expander>
      {/if}
    {/if}

    <Expander title="How to read this" testid="howto">
      <div class="text-base leading-snug">
        {@html md(
          "- **Effect on their starters** is what *their* best lineup gains over the weeks you picked, by our numbers: **Makes their lineup weaker** (it loses points), **About even** (under 2 points), **Improves their lineup** (2 to 6), **Improves it a lot** (more than 6). It describes their lineup, not their answer: we cannot know how another manager rates his players.\n" +
            "- **You** under it is what *your* best lineup gains over the same weeks: the improvement to your starting lineup, the best lineup each week, added up (+9.5 over weeks 4–7 is in total, not per week).\n" +
            `- **The weeks**: ${windowWhy(win, span)} Pick another span above: this week, the next four, the rest of the season (every week to this league's final) or the playoffs.\n` +
            "- **Your starters this week** lists who enters your starting lineup and who leaves it. A starter who only moves from one numbered slot to another (WR/TE 2 to WR/TE 3) is not a change: the gain is the lineup total's difference.\n" +
            "- **Projected value above available replacements** is their projected points for the rest of the season above the best free agent at their position. It is not a trade price, and it is never added to the lineup gains: a player can be worth a lot and still sit on your bench.\n" +
            "- **Roster size**: if a team gets more players than it gives, it has to cut someone: the player it would miss least, and that loss is in the numbers.\n" +
            "- Copy the page's link to share a trade: the link opens the same trade, over the same weeks.",
        )}
      </div>
    </Expander>
  {/if}
</main>
