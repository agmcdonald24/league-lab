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
  import { unavailableOf, type UnavailableAsset } from "../../lib/api"; // ---- IE-0
  import type { LeagueOption } from "../../lib/leagues";
  import { md, withContext } from "../../lib/md";
  import { errorWords, f1, f2, names, parseIds, s1, slotLabel } from "../../lib/decisions";
  import { windowOf, windowWhy } from "../../lib/decisions";
  import { openPlayer } from "../../lib/decisions";
  import { effectTone } from "../../lib/decisions"; // ---- IE-1
  import WeekStrip from "./WeekStrip.svelte"; // ---- IF-2: the week strip, both sides
  import TradeCard from "./TradeCard.svelte"; // ---- II-1: the trade card (plausibility, both sides, the reasons each way)
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
  import FreeTrade from "../../components/scoring/FreeTrade.svelte"; // ---- IN-2: the calculator without a league
  import { isRef } from "../../lib/refleague"; // ---- IN-2
  import ProvenanceLine from "../../components/provenance/ProvenanceLine.svelte"; // ---- IR-4

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
  // ---- IE-0 (Wave I-E): the package is the URL's keys, every one kept — a key is opaque ("mfl:0682", the Houston
  // Texans QB unit, like "12490"). The review's P0 #1: `parseIds` dropped the colon and this filter dropped what was
  // left off the rosters, so the Finder's "Houston Texans QB + Tuten for Rice" opened as Tuten alone. Now the request
  // carries every key; one the API cannot analyse comes back named (`unavailable`) and shows instead of a verdict.
  const give = $derived(parseIds(params.get("give")));
  const getIds = $derived(parseIds(params.get("get")));
  const loaded = $derived(mine !== null && theirs !== null && mine.roster_id === team && theirs.roster_id === partner);
  let unavailable = $state<UnavailableAsset[]>([]);
  const rowOf = (side: "give" | "get", key: string) => (side === "give" ? myPlayers : theirPlayers).find((r) => r.sleeper_id === key);
  const nameOf = (side: "give" | "get", key: string) => rowOf(side, key)?.player_name ?? unavailable.find((u) => u.key === key)?.name ?? key;
  const isUnitRow = (r: TeamRosterRow | undefined) => !!r && (r.unit === true || r.position === "TMQB" || r.position === "TMPK");
  // ---- end IE-0
  const pkgKey = $derived(
    partner !== null && loaded && give.length && getIds.length ? `${league}|${team}|${partner}|${[...give].sort()}|${[...getIds].sort()}|${win}` : "",
  );

  // evaluate on every change (a 250 ms pause, so ticking two players asks once); the last answer stays on screen while
  // the next one is asked, so the dial swings from where it was
  $effect(() => {
    const key = pkgKey;
    if (!key || team === null || partner === null) {
      result = null;
      evalError = null;
      unavailable = [];
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
          unavailable = [];
          restoreScroll();
        })
        .catch((e) => {
          if (pkgKey !== key) return;
          result = null;
          unavailable = unavailableOf(e); // ---- IE-0: named, never dropped
          if (e instanceof Unauthorized) onauth();
          else if (unavailable.length) evalError = null;
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
  // ---- IR-2 (Wave I-R): every primary number and sentence below is the answer's `decision` (one basis: against realistic
  // replacements); the roster-only result is its `unfilled` explanation, labelled as such
  const verdictLess = (r: TradeEval) => (r.decision ? r.decision.headline.replace(r.decision.verdict, "") : `**You give ${names(r.give)}; you get ${names(r.get)}.**`).trim();
  const shown = $derived(pkgKey && result ? result : null); // the answer on screen (the last one while the next is asked)
  const weekly = $derived(
    shown?.decision
      ? shown.decision.weeks.map((w, i) => ({ week: w, you_before: shown.decision!.mine.before.by_week[i], you_after: shown.decision!.mine.after.by_week[i], them_before: shown.decision!.theirs.before.by_week[i], them_after: shown.decision!.theirs.after.by_week[i] }))
      : [],
  ); // ---- IR-2: the decision's weeks
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
  // ---- IE-0: every key of the package, in the link's order; a unit by its short name ("Texans QB", not "QB")
  const shortOf = (side: "give" | "get", key: string) => {
    const r = rowOf(side, key);
    const n = nameOf(side, key);
    return isUnitRow(r) ? n.split(/\s+/).slice(-2).join(" ") : r ? lastName(n) : n;
  };
  const pkgWords = $derived(`${give.map((k) => shortOf("give", k)).join(" + ")} → ${getIds.map((k) => shortOf("get", k)).join(" + ")}`);
  function drop(side: "give" | "get", key: string) {
    const next = (side === "give" ? give : getIds).filter((x) => x !== key);
    setParams({ [side]: next.length ? next.join(",") : null });
  }
  const labelTone = (l: string) => effectTone(l); // ---- IE-1: the effect on their starters' tone
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
      <!-- IE-0: every key of the package in the link's order, the ones off this roster named as such -->
      <p class="-mt-1 px-4 pb-2 text-sm text-ink-2" data-testid={`picked-${side}`}>
        {#each picked as k, i (k)}{i ? " + " : ""}{nameOf(side, k)}{#if rows.length && !rowOf(side, k)}<span class="text-bad">&nbsp;(not on this roster)</span>{/if}{/each}
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
          <span class="tabnum text-right text-base" title={row.value == null && row.player_name ? "no projection" : undefined}>{f2(row.value)}</span><!-- IG-1 -->
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

<!-- ---- IN-2 (Wave I-N): browsing without a league (`ref:` keys) the calculator is FreeTrade; the league path below is
     unchanged -->
{#if isRef(league)}
  <FreeTrade {league} {onauth} />
{:else}
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
          <p>Pick a team and tick players both ways. The dial shows the effect on their starters, by our numbers.</p>
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
    {:else if unavailable.length}
      <!-- IE-0: an asset the analysis cannot use is named, with why, and there is no verdict (never a silent one-for-one) -->
      <div class="ll-error space-y-2" role="alert" data-testid="unavailable">
        {#each unavailable as u (u.side + u.key)}
          <p class="flex flex-wrap items-center gap-x-3 gap-y-1" data-testid="unavailable-row" data-key={u.key}>
            <span>Can't analyse <strong>{u.name ?? u.key}</strong> ({u.side === "give" ? "you give" : "you get"}): {u.why}.</span>
            <button type="button" class="min-h-10 rounded-md border border-line-strong px-3 text-sm font-semibold" onclick={() => drop(u.side, u.key)} data-testid="unavailable-remove">Take out of the trade</button>
          </p>
        {/each}
        <p class="text-sm">No verdict until every player in the trade can be analysed.</p>
      </div>
    {:else if evalError}
      <p class="ll-error" data-testid="eval-error">{evalError}</p>
    {:else if !shown}
      <div class="ll-skel h-48" aria-label="Re-solving both lineups" data-testid="evaluating"></div>
    {:else if !shown.decision}
      <p class="ll-error" data-testid="eval-error">This answer has no verdict: ask again.</p>
    {:else}
      {@const r = shown}
      {@const d = shown.decision}
      <Card tone="accent" testid="trade-result">
        <div class="grid items-center gap-4 wide:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]" data-testid="dial-row" aria-busy={evaluating} {@attach watchDial}>
          <Dial score={d.dial.score} label={d.dial.label} caption={d.dial.caption} need={d.dial.need ?? null} you={d.dial.you} youLabel={`You · ${d.span}`} busy={evaluating} /><!-- IR-2: the decision's dial -->
          <div class="min-w-0">
            <div class="grid grid-cols-2 gap-2" data-testid="fit-tiles">
              <StatTile label="You · this week" value={s1(d.mine.gain_week)} caption={`${f2(d.mine.before.this_week)} → ${f2(d.mine.after.this_week)}`} size="sm" />
              <StatTile label={d.window === "week" ? `You · ${d.span}` : `You · ${d.span} in total`} value={s1(d.mine.gain_window)} caption={`${f1(d.mine.before.window)} → ${f1(d.mine.after.window)}`} size="sm" />
              <StatTile label={`${r.partner_team} · this week`} value={s1(d.theirs.gain_week)} caption={`${f2(d.theirs.before.this_week)} → ${f2(d.theirs.after.this_week)}`} size="sm" />
              <StatTile label={d.window === "week" ? `${r.partner_team} · ${d.span}` : `${r.partner_team} · ${d.span} in total`} value={s1(d.theirs.gain_window)} caption={`${f1(d.theirs.before.window)} → ${f1(d.theirs.after.window)}`} size="sm" />
            </div>
            <p class="mt-2 text-sm text-ink-2" data-testid="basis"><span class="font-semibold text-ink">{d.basis_label}.</span> {d.basis_words}</p>
            <p class="mt-3 text-lg leading-snug font-semibold text-ink" data-testid="verdict">{d.verdict}</p>
            <p class="mt-2 text-base leading-snug {d.recommendation.credible ? 'text-good' : 'text-ink'}" data-testid="recommendation"><span class="font-semibold">{d.recommendation.label}:</span> {d.recommendation.words.replace(`${d.recommendation.label}: `, "")}</p>
            <div class="mt-2"><ProvenanceLine p={r.provenance} caveats={r.caveats} testid="trade-provenance" /></div><!-- ---- IR-4: beta, what is verified, the starter caveats -->
            {#if r.sanity}
              <p class="mt-2 rounded-md bg-warn-soft p-2 text-sm text-ink" data-testid="sanity">We would not suggest this one: {r.sanity}.</p>
            {/if}
          </div>
        </div>
        <!-- ---- IE-2 / IR-2 result: what the trade does, slot by slot, on the decision's basis -->
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
          <p class="text-lg leading-snug font-semibold text-ink" data-testid="trade-effect">{d.effect_words}</p>
          <p class="text-base leading-snug {d.alternative.beats ? 'text-ink' : 'text-warn'}" data-testid="trade-alternative"><span class="font-semibold">Against your best waiver move:</span> {d.alternative.words}</p>
          {#if d.strip.weeks.length > 1}
            <div data-testid="trade-strip-block">
              <h3 class="ll-label mb-1">Starter points, week by week</h3>
              <WeekStrip strip={d.strip} them={r.partner_team} testid="trade-strip" />
            </div>
          {/if}
          {#if r.card}
            <div class="rounded-md border border-line p-3" data-testid="calc-card">
              <h3 class="ll-label mb-1">Worth proposing? {d.recommendation.label}</h3>
              <TradeCard card={r.card} testid="calc-trade-card" />
            </div>
          {/if}
          <div data-testid="trade-starters">
            <h3 class="ll-label mb-1">Your starters this week, slot by slot</h3>
            <ul class="space-y-1 text-base">
              {#each d.changes.mine as x, i (`${x.slot}-${i}`)}
                <li data-testid="starter-change">{x.words}.</li>
              {/each}
              {#if !d.changes.mine.length}
                <li class="text-ink-2">The same players start this week.</li>
              {/if}
            </ul>
            <p class="mt-1 text-sm text-ink-2" data-testid="trade-total">Starting lineup this week: {f1(d.mine.before.this_week)} → <strong class="text-ink">{f1(d.mine.after.this_week)}</strong> ({s1(d.mine.gain_week)} projected points)</p>
          </div>
          {#if d.depth.mine.words}<p class="text-base text-ink" data-testid="trade-backup">Backup coverage: {d.depth.mine.words}.</p>{/if}
          <div class="text-base text-ink" data-testid="trade-their-side">
            <p>{d.their_effect_words}</p>
            {#if d.changes.theirs.length}<ul class="mt-1 space-y-1 text-ink-2">{#each d.changes.theirs as x, i (`t-${x.slot}-${i}`)}<li data-testid="their-change">{x.words}.</li>{/each}</ul>{/if}
            {#if d.depth.theirs.words}<p class="mt-1 text-ink-2" data-testid="their-backup">Backup coverage: {d.depth.theirs.words}.</p>{/if}
          </div>
          {#if d.fills.mine.words || d.fills.theirs.words}
            <div class="text-sm text-ink-2" data-testid="trade-fills">
              {#if d.fills.mine.words}<p>{d.fills.mine.words}</p>{/if}
              {#if d.fills.theirs.words}<p class="mt-1">{d.fills.theirs.words}</p>{/if}
            </div>
          {/if}
          <Expander title={d.unfilled.label} testid="unfilled">
            <p class="text-base leading-snug" data-testid="unfilled-words">{d.unfilled.words}</p>
          </Expander>
        </div>
        <!-- ---- end IE-2 result -->
      </Card>
    {/if}

    <!-- IB-2: the verdict bar — pinned to the top once the dial has scrolled away (fixed: nothing in the flow moves when
         it appears); open on desktop, a tap opens it on a phone -->
    {#if shown?.decision && give.length && getIds.length && !dialInView}
      {@const r = shown}
      {@const d = shown.decision}
      {@const open = barOpen || wideNow}
      <div class="pointer-events-none fixed inset-x-0 top-0 z-30 pt-[env(safe-area-inset-top)]" data-testid="verdict-bar-slot">
        <div class="mx-auto max-w-6xl px-3">
          <div class="pointer-events-auto rounded-b-lg border border-t-0 border-line-strong bg-surface shadow-lg" data-testid="verdict-bar" aria-live="polite">
            <button type="button" class="flex min-h-12 w-full items-center gap-2 px-3 py-2 text-left text-sm" aria-expanded={open} onclick={() => (barOpen = !barOpen)} data-testid="verdict-bar-toggle">
              <span class="min-w-0 flex-1 truncate font-semibold text-ink" data-testid="verdict-bar-package">{pkgWords}</span>
              <span class="flex shrink-0 items-center gap-1.5" data-testid="dial-chip">
                <strong class={labelTone(d.dial.label)}>{d.dial.label}</strong><!-- IE-1: no 0–100 score; IR-2: the decision's -->
                <span class="ll-label">You</span><strong class="tabnum">{s1(d.dial.you)}</strong>
              </span>
              <span class="chev shrink-0 text-ink-3 wide:hidden {open ? 'rotate-90' : ''}" aria-hidden="true">›</span>
            </button>
            {#if open}
              <div class="max-h-[60vh] overflow-y-auto border-t border-line px-3 pt-2 pb-3" data-testid="verdict-bar-detail">
                <div class="grid grid-cols-2 gap-2 wide:grid-cols-4">
                  <StatTile label="You · this week" value={s1(d.mine.gain_week)} caption={`${f2(d.mine.before.this_week)} → ${f2(d.mine.after.this_week)}`} size="sm" />
                  <StatTile label={`You · ${d.span}`} value={s1(d.mine.gain_window)} caption={`${f1(d.mine.before.window)} → ${f1(d.mine.after.window)}`} size="sm" />
                  <StatTile label={`${r.partner_team} · this week`} value={s1(d.theirs.gain_week)} size="sm" />
                  <StatTile label={`${r.partner_team} · ${d.span}`} value={s1(d.theirs.gain_window)} size="sm" />
                </div>
                <p class="mt-2 text-base leading-snug font-semibold text-ink">{d.verdict}</p>
                <p class="mt-1 text-sm text-ink" data-testid="bar-recommendation">{d.recommendation.label}.</p>
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
            <div class="ll-label mb-2">{r.values?.season_value.label ?? "Projected value above available replacements"}</div><!-- IF-2 -->
            <div class="space-y-2">
              <Bar label="You give" value={r.market.give} max={mmax} display={fmt.whole(r.market.give)} color="var(--ll-div-hot)" />
              <Bar label="You get" value={r.market.get} max={mmax} display={fmt.whole(r.market.get)} />
            </div>
            {#if r.values?.season_value.words}<p class="mt-2 text-sm text-ink-2" data-testid="season-value-words">{r.values.season_value.words} The fairness test.</p>
            {:else if r.market.words}<p class="mt-2 text-sm text-ink-2"><Md text={r.market.words} {ctx} /></p>{/if}<!-- IF-2 -->
          </div>
          {#if r.ros}
            <div data-testid="ros">
              <div class="ll-label mb-2">{r.values?.ros_points.label ?? "Rest of season"}{r.ros.window ? ` · ${r.ros.window}` : ""}</div><!-- IF-2 -->
              <div class="space-y-2">
                <Bar label="You give" value={r.ros.give} max={rmax} display={fmt.whole(r.ros.give)} color="var(--ll-div-hot)" />
                <Bar label="You get" value={r.ros.get} max={rmax} display={fmt.whole(r.ros.get)} />
              </div>
              <p class="mt-2 text-sm text-ink-2">
                All positions added up — not a fairness test: a kicker's points and a receiver's count the same here, and a free agent could replace either. The fairness test is the season value above replacement.<!-- IF-2 -->
              </p>
            </div>
          {/if}
        </div>
        {#if r.decision?.fit_words}<p class="mt-3 text-sm text-ink-2" data-testid="fit-words"><Md text={r.decision.fit_words} {ctx} /></p>{/if}
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
          <p class="mt-2 text-sm text-ink-3">Each week is re-solved on its own: byes, injuries and taxi squads as in that week's lineup, an empty starting slot filled with the best free agent for that week.</p>
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
            "- **One basis for every number** (against realistic replacements): an empty starting slot (a bye, a cut, a player traded away) is filled with the best free agent who can play it that week, for both teams, never the same free agent for both. Those pickups are assumed, not sure: another team can add the player first. **If empty slots were left empty** shows the result with nobody added, as an explanation.\n" +
            `- **The weeks**: ${windowWhy(win, span)} Pick another span above: this week, the next four, the rest of the season (every week to this league's final) or the playoffs.\n` +
            "- **Your starters this week, slot by slot**: who takes each starting slot and whom he replaces there (a starter who moves to the FLEX is a link in that chain). A starter who only moves from one numbered slot to another (WR/TE 2 to WR/TE 3) is not a change.\n" +
            "- **Four numbers, never added together** (IF-2): **projected points** (one player, one week), **starter points** (what enters your best legal lineup over the weeks), **backup coverage** (your bench's best lineup) and **season value above replacement** (rest-of-season projected points above the best free agent at the position: the fairness test). **Rest-of-season projected points** with all positions added up are shown for reference only: not a fairness test.\n" +
            "- **Against your best waiver move**: the same weeks, the same scoring — the best claim (a free agent for an open spot, or for the player you would drop). A trade that does not beat it says so, and names any other reason the numbers give.\n" +
            "- **Roster size**: if a team gets more players than it gives, it has to cut someone: the player it would miss least, and that loss is in the numbers.\n" +
            "- Copy the page's link to share a trade: the link opens the same trade, over the same weeks.",
        )}
      </div>
    </Expander>
  {/if}
</main>
{/if}
<!-- ---- end IN-2 -->
