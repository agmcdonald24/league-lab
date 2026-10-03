<script lang="ts">
  import { ApiError, get, paths, peek, Unauthorized, type MyWeek, type Status, type UserLeagues } from "../lib/api";
  import { decisionPaths, type Waivers } from "../lib/api"; // ---- IE-1
  import { ACTION_WORD, homeActions } from "../lib/week"; // ---- IE-1
  import type { LeagueOption } from "../lib/leagues";
  import { withContext } from "../lib/md";
  import { learnLeagueName } from "../lib/names.svelte";
  import { checkedLine, opponentLine, recordLine } from "../lib/week";
  // ---- IB-3: the card's default content (status, the call, strength, one reason, Compare; the rest behind Why?)
  import { cardCall, cardStatus, cardStrength, compareHref, STATUS_WORD, STRENGTH_WORD, whyBlocks } from "../lib/week";
  import type { Availability, AvailabilityStatus } from "../lib/shapes";
  import { restoreScroll } from "../lib/router.svelte";
  import { ago } from "../lib/card"; // ---- IF-4: "What changed" times
  import { lineupPane } from "../lib/pane.svelte"; // ---- IB-1: a lineup name opens the research pane
  import Expander from "../components/Expander.svelte";
  import LineupTable from "../components/LineupTable.svelte";
  import Md from "../components/Md.svelte";

  let {
    options,
    league,
    team,
    mine,
    status,
    onauth,
  }: {
    options: LeagueOption[];
    league: string;
    team: number | null;
    mine: UserLeagues | null;
    status: Status | null;
    onauth: () => void;
  } = $props();

  let data = $state<MyWeek | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(false);

  const ctx = $derived({ league, team });
  const leagueRow = $derived(options.find((l) => l.league_id === league) ?? null);
  // the user signed in with a username and has no team in this league (a commissioner-only league)
  const noTeamHere = $derived(!!mine && !!leagueRow?.mine && leagueRow.roster_id === null);
  // Home's line "**Team** · 0-2, #10 in the league · week 4 vs **X**" without the team (shown as the heading); the
  // opponent gets its own line when the API sends the contract's object
  const record = $derived(data ? recordLine(data) : "");
  const versus = $derived(data ? opponentLine(data) : "");
  // I0-A: the availability overlay — when injuries were last checked, and who moved since the nightly build
  const avail = $derived((data as (MyWeek & { availability?: Availability | null }) | null)?.availability ?? null);
  const checked = $derived(
    checkedLine(avail?.checked_at ?? (status as (Status & { availability?: AvailabilityStatus }) | null)?.availability?.checked_at),
  );

  // ---- IE-1: the actions (the API's, plus Waivers' claim when there is room: fetched after the page shows, never
  // blocking it); `actions` undefined = an answer from before Wave I-E (the cards are shown as they were)
  let waivers = $state<Waivers | null>(null);
  $effect(() => {
    const l = league;
    const t = team;
    waivers = null;
    if (t === null || !data || data.actions === undefined) return;
    const path = decisionPaths.waivers(l, t);
    const hit = peek<Waivers>(path);
    if (hit) {
      waivers = hit;
      return;
    }
    get<Waivers>(path)
      .then((w) => league === l && team === t && (waivers = w))
      .catch(() => {});
  });
  const actions = $derived(data && data.actions !== undefined ? homeActions(data, waivers) : null);
  // ---- IF-4: the close calls the lineup already follows ("No clear upgrade") and what changed since the morning build
  const review = $derived(data?.review ?? []);
  const changed = $derived(data?.changed ?? null);
  const allSet = $derived(!!actions && actions.length === 0 && review.length === 0);
  function reviewHref(r: { compare: { a: string; b: string } | null }): string | null {
    return r.compare ? `/compare?a=${encodeURIComponent(r.compare.a)}&b=${encodeURIComponent(r.compare.b)}` : null;
  }
  const SEP = " · ";
  function changedTime(iso: string | null): { ago: string; exact: string } | null {
    if (!iso) return null;
    const t = new Date(iso);
    if (Number.isNaN(t.getTime())) return null;
    const exact = t.toLocaleString("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
    return { ago: ago(iso), exact: `${exact} ET` };
  }
  // ---- end IF-4
  // ---- end IE-1

  $effect(() => {
    const l = league;
    const t = team;
    error = null;
    if (t === null) {
      data = null;
      return;
    }
    const path = paths.myWeek(l, t);
    const hit = peek<MyWeek>(path);
    if (hit) {
      data = hit;
      learnLeagueName(hit.league_id, hit.league_name);
      loading = false;
      restoreScroll();
      return;
    }
    loading = true;
    get<MyWeek>(path)
      .then((d) => {
        if (league !== l || team !== t) return;
        data = d;
        learnLeagueName(d.league_id, d.league_name);
        loading = false;
        restoreScroll();
      })
      .catch((e) => {
        if (league !== l || team !== t) return;
        loading = false;
        data = null;
        if (e instanceof Unauthorized) onauth();
        else if (e instanceof ApiError && e.status === 404)
          error = /league/i.test(e.message) && !/team/i.test(e.message) ? "Sleeper has no league with that id. Check the link, or pick a league above."
                                                                       : "That team is not in this league. Pick your team above.";
        else if (e instanceof ApiError && e.status === 502) error = "Sleeper did not answer. Try again in a minute.";
        else if (e instanceof ApiError && e.status === 503) error = "The numbers are not ready yet. Try again in a few minutes.";
        else error = e instanceof Error ? e.message : String(e);
      });
  });
</script>


<main class="space-y-4" data-testid="my-week">
  {#if team === null}
    <div class="ll-empty" data-testid="pick-prompt">
      {#if noTeamHere}
        <p data-testid="no-team">
          You have no team in <strong>{leagueRow?.name}</strong> (you may run it without playing in it). Pick the team to see above: its
          lineup to start and its closest calls.
        </p>
      {:else}
        Pick your team above to see your week: the lineup to start and the closest calls.
      {/if}
      {#if leagueRow?.scoring_label}<p class="mt-1 text-sm text-ink-3">{leagueRow.scoring_label}</p>{/if}
    </div>
  {:else if error}
    <p class="ll-error">{error}</p>
  {:else if !data}
    <div class="space-y-3" aria-label="Loading" data-testid="loading">
      <div class="ll-skel h-7 w-2/3"></div>
      <div class="ll-skel h-4 w-1/2"></div>
      {#each [0, 1, 2] as i (i)}<div class="ll-skel h-24"></div>{/each}
    </div>
  {:else}
    <section class="space-y-1" class:opacity-60={loading}>
      <p class="text-label font-bold tracking-[0.08em] text-accent uppercase">
        {data.week ? `My week · week ${data.week}` : "My week"}
      </p>
      <h1 class="text-2xl leading-tight font-extrabold tracking-tight wide:text-3xl" data-testid="team-name">{data.team_name}</h1>
      {#if record}<p class="text-sm text-ink-2" data-testid="record-line"><Md text={record} {ctx} /></p>{/if}
      {#if versus}<p class="text-base leading-snug" data-testid="opponent-line"><Md text={versus} {ctx} /></p>{/if}
      {#if data.league_line}<p class="text-sm text-ink-2" data-testid="league-line"><Md text={data.league_line} {ctx} /></p>{/if}
      {#if checked}<p class="text-sm text-ink-3" data-testid="injuries-checked">{checked}</p>{/if}
      {#if status?.warning}
        <details class="text-sm text-warn" data-testid="stale-warning">
          <summary class="inline-flex items-center gap-1">⚠️ Injury news may be stale <span class="chev" aria-hidden="true">›</span></summary>
          <p class="mt-1 leading-snug">{status.warning}</p>
        </details>
      {/if}
    </section>

    {#if data.week !== null}
      <div class="grid grid-cols-1 gap-4 wide:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] wide:items-start">
        <section class="space-y-2.5">
          {#if actions}
            <!-- ---- IE-1: the weekly action list — at most three actions, the most urgent first, each in three layers (the
                 action, the reason and consequence, the analysis behind Why?); "your lineup is set" is a complete answer -->
            <div class="space-y-2.5" data-testid="week-actions">
              <h2 class="ll-label">This week</h2>
              {#if allSet}
                <p class="rounded-lg border border-line bg-surface p-4 text-lg leading-snug font-semibold" style="box-shadow:var(--ll-shadow)" data-testid="week-answer">
                  <span class="text-good" aria-hidden="true">✓ </span>{data.set_line ?? (data.cards.length === 0 && data.notice ? "" : "Your lineup is set — nothing to change.")}
                  {#if data.cards.length === 0 && data.notice}<Md text={data.notice} {ctx} />{/if}
                </p>
              {/if}
              {#each actions as a, i (`${a.kind}-${i}`)}
                {@const why = a.cards.map((k) => data!.cards[k]).filter(Boolean)}
                <article class="relative space-y-2 overflow-hidden rounded-lg border border-line bg-surface p-4 pl-5" style="box-shadow:var(--ll-shadow)"
                  data-testid="action-card" data-kind={a.kind} data-submitted={a.submitted === null ? "unknown" : String(a.submitted)}>
                  <div class="flex flex-wrap items-center gap-1.5">
                    <span class="rounded-sm px-2 py-0.5 text-sm font-bold {a.kind === 'change' ? 'bg-warn-soft text-warn' : a.kind === 'close' ? 'bg-raised text-ink-2' : 'bg-accent-soft text-accent'}"
                      data-testid="action-kind">{a.kind === "change" ? "⚠︎ " : a.kind === "close" ? "≈ " : "+ "}{ACTION_WORD[a.kind]}</span>
                    {#if a.slot_label}<span class="ll-label text-ink-2" data-testid="action-slot">{a.slot_label}</span>{/if}
                    {#if a.lock}<span class="ml-auto text-sm font-semibold text-ink-2" data-testid="action-lock">{a.lock.words}</span>{/if}
                  </div>
                  <p class="text-lg leading-snug font-semibold" data-testid="action-text"><Md text={a.action} {ctx} /></p>
                  {#if a.reason}<p class="text-base leading-snug text-ink-2" data-testid="action-reason"><Md text={a.reason} {ctx} /></p>{/if}
                  {#if a.submitted_words}
                    <p class="text-sm leading-snug font-semibold {a.submitted ? 'text-good' : 'text-warn'}" data-testid="action-submitted">
                      {a.submitted ? "✓ " : "→ "}{a.submitted_words}
                    </p>
                  {/if}
                  {#if a.href}
                    <a class="inline-flex min-h-9 items-center rounded-sm border border-line-strong px-3 text-sm font-semibold hover:bg-raised"
                      href={withContext(a.href, ctx)} data-testid="action-open">See it on Waivers ›</a>
                  {/if}
                  {#if why.length}
                    <details class="group" data-testid="action-why">
                      <summary class="inline-flex min-h-9 cursor-pointer items-center gap-1 text-sm font-semibold text-accent">
                        <span class="chev" aria-hidden="true">›</span>Why? The numbers behind it
                      </summary>
                      <div class="mt-1 space-y-3">
                        {#each why as c (c.slot)}
                          {@const cmp = compareHref(c)}
                          <div class="space-y-1 border-t border-line pt-2" data-testid="action-call">
                            <p class="text-base leading-snug"><span class="ll-label text-ink-3">{c.slot_label}</span> <Md text={cardCall(c, cardStatus(c, data!.lineup_full))} {ctx} /></p>
                            {#if c.why}<p class="text-sm leading-snug text-ink-2"><Md text={c.why} {ctx} /></p>{/if}
                            {#each whyBlocks(c) as b, j (j)}<p class="text-sm leading-snug text-ink-3"><Md text={b.text} {ctx} /></p>{/each}
                            {#if cmp}<a class="ll-link text-sm" href={withContext(cmp, ctx)}>Compare these players ›</a>{/if}
                          </div>
                        {/each}
                      </div>
                    </details>
                  {/if}
                  <span class="absolute inset-y-0 left-0 w-1 {a.kind === 'change' ? 'bg-warn' : 'bg-accent'}" aria-hidden="true"></span>
                </article>
              {/each}
              <!-- ---- IF-4: Decisions worth reviewing — a close call the lineup already follows stays in view ("No clear
                   upgrade", not "nothing to change"): the two names, the gap, who the lineup has, Compare -->
              {#each review as r, i (`review-${i}`)}
                {@const cmp = reviewHref(r)}
                <article class="relative space-y-1.5 overflow-hidden rounded-lg border border-line bg-surface p-4 pl-5" style="box-shadow:var(--ll-shadow)"
                  data-testid="review-line" data-uncertain={String(r.matchup_uncertain)}>
                  <div class="flex flex-wrap items-center gap-1.5">
                    <span class="rounded-sm bg-raised px-2 py-0.5 text-sm font-bold text-ink-2" data-testid="review-kind">≈ No clear upgrade</span>
                    {#if r.slot_label}<span class="ll-label text-ink-2">{r.slot_label}</span>{/if}
                  </div>
                  <p class="text-base leading-snug" data-testid="review-words"><Md text={r.words} {ctx} /></p>
                  {#if cmp}
                    <a class="inline-flex min-h-9 items-center text-sm font-semibold text-accent" href={withContext(cmp, ctx)} data-testid="review-compare">Compare ›</a>
                  {/if}
                  <span class="absolute inset-y-0 left-0 w-1 bg-line-strong" aria-hidden="true"></span>
                </article>
              {/each}
              <!-- ---- end IF-4 -->
              {#if !allSet && data.set_line}
                <p class="px-1 text-base leading-snug text-ink-2" data-testid="set-line"><span class="text-good" aria-hidden="true">✓ </span>{data.set_line}</p>
              {/if}
              <div class="space-y-1 px-1" data-testid="where-to-change">
                {#if data.edit_link}
                  <a class="inline-flex min-h-10 items-center rounded-md bg-accent px-4 font-semibold text-on-accent" href={data.edit_link.url} target="_blank" rel="noopener noreferrer"
                    data-testid="edit-link">{data.edit_link.label} ↗</a>
                {/if}
                {#if data.nothing_submitted}<p class="text-sm leading-snug text-ink-2" data-testid="nothing-submitted">{data.nothing_submitted}</p>{/if}
              </div>
              {#if changed}
                <!-- ---- IF-4: What changed — the overlay's moves since the morning build and the week's news from the last
                     24 hours (at most five lines, the source and the time on each) -->
                <section class="space-y-1.5 rounded-lg border border-line bg-surface p-4" data-testid="what-changed">
                  <h2 class="ll-label">What changed</h2>
                  {#if changed.lines.length === 0}
                    <p class="text-sm text-ink-2" data-testid="changed-empty">{changed.empty}</p>
                  {:else}
                    <ul class="space-y-1.5">
                      {#each changed.lines as l, i (i)}
                        {@const when = changedTime(l.at)}
                        <li class="text-sm leading-snug" data-testid="changed-line" data-kind={l.kind}>
                          {#if l.kind === "news" && l.player_name}<span class="font-semibold">{l.player_name}:</span>{/if}
                          <span class={l.kind === "status" ? "text-warn" : "text-ink"}>{l.text}</span>
                          <span class="text-ink-3"
                            >{SEP}{#if l.url}<a class="ll-link" href={l.url} target="_blank" rel="noopener noreferrer">{l.source ?? "source"} ↗</a
                              >{:else}{l.source ?? ""}{/if}{#if when}{SEP}<time datetime={l.at} title={when.exact}>{when.ago}</time>{/if}</span
                          >
                        </li>
                      {/each}
                    </ul>
                  {/if}
                </section>
              {/if}
              <!-- ---- end IF-4 -->
            </div>
          {:else}
          <h2 class="ll-label">The calls that matter</h2>
          {#if data.cards.length === 0 && data.notice}
            <p class="rounded-lg bg-raised p-4 text-base" data-testid="no-calls"><Md text={data.notice} {ctx} /></p>
          {/if}
          {#each data.cards as c (c.slot)}
            <!-- ---- IB-3: the status chip first, the call in one line (both names), the strength, IA-1's one reason (last
                 names), Compare these players; the odds, the ranges and the numbers behind Why? -->
            {@const st = cardStatus(c, data.lineup_full)}
            {@const strength = cardStrength(c)}
            {@const cmp = compareHref(c)}
            {@const more = whyBlocks(c)}
            <article class="relative space-y-2 overflow-hidden rounded-lg border border-line bg-surface p-4 pl-5" style="box-shadow:var(--ll-shadow)"
              data-testid="decision-card" data-status={st ?? "unknown"}>
              <div class="flex flex-wrap items-center gap-1.5">
                {#if st}
                  <span class="rounded-sm px-2 py-0.5 text-sm font-bold {st === 'change' ? 'bg-warn-soft text-warn' : st === 'set' ? 'bg-accent-soft text-accent' : 'bg-raised text-ink-2'}"
                    data-testid="card-status">{st === "change" ? "⚠︎ " : st === "set" ? "✓ " : "≈ "}{STATUS_WORD[st]}</span>
                {/if}
                <span class="ll-label text-ink-3" data-testid="card-slot">{c.slot_label}</span>
                <span class="ml-auto text-sm font-semibold text-ink-2" data-testid="card-strength">{STRENGTH_WORD[strength]}</span>
              </div>
              <p class="text-lg leading-snug" data-testid="card-call"><Md text={cardCall(c, st)} {ctx} /></p>
              {#if c.why}
                <p class="text-base leading-snug text-ink-2" data-testid="card-why"><Md text={c.why} {ctx} /></p>
              {/if}
              <div class="flex flex-wrap items-center gap-2 pt-0.5">
                {#if cmp}
                  <a class="inline-flex min-h-9 items-center rounded-sm border border-line-strong px-3 text-sm font-semibold hover:bg-raised"
                    href={withContext(cmp, ctx)} data-testid="card-compare">Compare these players</a>
                {/if}
              </div>
              {#if more.length}
                <details class="group" data-testid="card-why-more">
                  <summary class="inline-flex min-h-9 cursor-pointer items-center gap-1 text-sm font-semibold text-accent">
                    <span class="chev" aria-hidden="true">›</span>Why?
                  </summary>
                  <div class="mt-1 space-y-1.5">
                    {#each more as b, i (i)}
                      <p class="text-sm leading-snug text-ink-3" data-testid="card-small-print"><Md text={b.text} {ctx} /></p>
                    {/each}
                  </div>
                </details>
              {/if}
              <span class="absolute inset-y-0 left-0 w-1 {st === 'change' ? 'bg-warn' : 'bg-accent'}" aria-hidden="true"></span>
            </article>
          {/each}
          {/if}
        </section>

        <div class="space-y-3">
          <section class="space-y-2 rounded-lg border border-line bg-surface p-4" style="box-shadow:var(--ll-shadow)">
            <!-- IA-1: one plain header (Andrew did not understand "Your full lineup: every slot, how close each call is …") -->
            <div>
              <h2 class="text-lg leading-tight font-bold" data-testid="lineup-head">Your lineup</h2>
              <p class="text-sm leading-snug text-ink-3" data-testid="lineup-caption">Starters, the bench, who can't play — tap a name for his card.</p>
            </div>
            {#if avail?.changes?.length && !changed}<!-- IF-4: What changed carries them (an answer from before keeps them here) -->
              <ul class="space-y-1 text-sm leading-snug text-warn" data-testid="availability-changes">
                {#each avail.changes as c, i (i)}<li>{c}</li>{/each}
              </ul>
            {/if}
            {#if data.lineup.length}
              <LineupTable rows={data.lineup} {ctx} testid="lineup" margins pane={(row) => lineupPane(row, data!.lineup_full)} /><!-- IF-4: margins -->
            {:else}
              <p class="text-sm text-ink-3">No proposed lineup for this week yet.</p>
            {/if}
          </section>

          <!-- ---- IF-4 (the review's table: the bench section repeated every starter first): the bench and who can't play only -->
          <Expander title="The bench and who can't play" testid="lineup-full">
            <LineupTable rows={data.lineup_full.filter((r) => r.role !== "starter")} full {ctx} testid="lineup-full-table" pane={(row) => lineupPane(row, data!.lineup_full)} />
          </Expander>
          {#if data.howto}
            <Expander title="How to read this" testid="howto"><Md text={data.howto} {ctx} block class="text-base leading-snug" /></Expander>
          {/if}
          <Expander title="Movers on your roster (last 3 games vs before)" testid="movers">
            {#if data.movers.length === 0}
              <p class="text-sm text-ink-3">No trend calls yet — nothing is called before a player's fourth game.</p>
            {:else}
              <ul class="divide-y divide-line text-base">
                {#each data.movers as m, i (i)}
                  <li class="py-2">
                    {#if m.gsis_id}<a class="ll-link" href={withContext(`/player/${m.gsis_id}`, ctx)}>{m.player_name}</a>{:else}{m.player_name}{/if}
                    <span class="text-ink-3"> · {m.position}</span>
                    {#if m.momentum !== null}<span class="tabnum float-right text-ink-2">{m.momentum > 0 ? "+" : ""}{m.momentum.toFixed(2)}</span>{/if}
                    <div class="text-sm text-ink-3">{m.tags ?? ""}</div>
                  </li>
                {/each}
              </ul>
            {/if}
          </Expander>
          <a class="block rounded-lg border border-line bg-surface p-4 text-base font-semibold" href={withContext("/trends?who=mine", ctx)} data-testid="to-research"
            >Who's above or below expectation <span class="text-accent">›</span></a
          >
        </div>
      </div>
    {:else if data.notice}
      <p class="rounded-lg bg-raised p-4">{data.notice}</p>
    {/if}
  {/if}

  {#if status?.freshness}
    <!-- ---- IF-4: "Updated 3 h ago" (the exact time and the feed names behind a tap) in place of the feed list -->
    {@const upd = changedTime(status.updated_at ?? null)}
    <footer class="pt-2 text-xs leading-snug text-ink-3" data-testid="freshness">
      {#if upd}
        <details data-testid="updated">
          <summary class="inline-flex min-h-9 cursor-pointer items-center gap-1"
            >Updated <time datetime={status.updated_at} title={upd.exact} data-testid="updated-ago">{upd.ago}</time> <span class="chev" aria-hidden="true">›</span></summary
          >
          <p class="mt-1" data-testid="updated-exact">Last data load {upd.exact}.</p>
          <p class="mt-1"><Md text={status.freshness} /></p>
        </details>
      {:else}
        <Md text={status.freshness} />
      {/if}
    </footer>
  {/if}
</main>
