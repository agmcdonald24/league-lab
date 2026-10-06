<script lang="ts">
  // ---- IN-1 (Wave I-N): the home page — what this is in five seconds, then something real to look at before asking
  // for anything. "/home" always; "/" when no league is remembered on this device (a returning manager's "/" is his
  // week). Above the fold: the name, one sentence, two actions, and this week's top projections. Below: matchups to
  // target, how the projections have done (the bad numbers too), the newest posts, the tools. Every module reads an
  // existing route on Half PPR (`ref:half`) and hides itself when its call fails: never an error card on the home.
  import { APP_MARK, APP_NAME } from "../lib/brand";
  import { get, aboutPath, blogPaths, homePaths, paths, type AboutAnswer, type BlogMeta, type Board, type RecordAnswer, type RosList } from "../lib/api";
  import { BROWSE_HREF, REF_DEFAULT, refLabel } from "../lib/refleague";
  import { recordView, STARTS } from "../lib/record";
  import { withContext } from "../lib/md";
  import { fmt } from "../lib/theme";
  import Headshot from "../components/Headshot.svelte";
  import PosBadge from "../components/PosBadge.svelte";
  import TeamBadge from "../components/TeamBadge.svelte";
  import Tabs from "../components/Tabs.svelte";
  import { fromBoard, fromRos, gradeLead, gradeRows, longDate, posWords, TONE_WORDS, toneOf, type TopRow } from "../components/home/home";

  const L = REF_DEFAULT; // the home's numbers: Half PPR, one scale for every visitor
  const scoring = refLabel(L);
  const ctx = { league: L, team: null };
  const link = (path: string) => withContext(path, ctx);

  // ---- this week's top projections, by position: IN-3's board when it answers (it carries this week's range), else
  // the rest-of-season list's `week_points` (this week's projection) with the season's range beside it
  const POSITIONS = ["QB", "RB", "WR", "TE"] as const;
  let pos = $state<(typeof POSITIONS)[number]>("WR");
  let top = $state<Record<string, TopRow[] | "loading" | "failed">>({});
  async function loadTop(p: string) {
    if (top[p] && top[p] !== "failed") return;
    top[p] = "loading";
    try {
      const b = await get<Board>(homePaths.board(L, p, null, 5));
      const rows = (b.rows ?? b.players ?? []).map(fromBoard).filter((r): r is TopRow => r !== null);
      if (rows.length) {
        top[p] = rows.slice(0, 5);
        return;
      }
    } catch {
      /* no board on this server: the rest-of-season list below */
    }
    try {
      const r = await get<RosList>(homePaths.ros(L, p, 40));
      const rows = fromRos(r.players, 5);
      top[p] = rows.length ? rows : "failed";
    } catch {
      top[p] = "failed";
    }
  }
  $effect(() => void loadTop(pos));
  const topRows = $derived(top[pos]);

  // ---- matchups to target this week (IN-3's board, sorted by the matchup's tone); hidden without the route
  let board = $state<ReturnType<typeof fromBoardWithTone> | null>(null);
  function fromBoardWithTone(b: Board) {
    return (b.rows ?? b.players ?? []).filter((r) => r.gsis_id).slice(0, 5).map((r) => ({ r, t: toneOf(r) }));
  }
  $effect(() => {
    get<Board>(homePaths.board(L, "WR", "tone", 5))
      .then((b) => {
        const rows = fromBoardWithTone(b);
        board = rows.length ? rows : null;
      })
      .catch(() => (board = null));
  });

  // ---- how the projections have done (About's grades) and the record's line (the route About uses)
  let about = $state<AboutAnswer | null>(null);
  let recordLine = $state<string | null>(null);
  $effect(() => {
    get<AboutAnswer>(aboutPath(L))
      .then((a) => (about = a))
      .catch(() => (about = null));
    get<RecordAnswer>(paths.record(L))
      .then((d) => {
        const v = recordView(d, scoring);
        recordLine = v.kind === "scored" && v.lines[0] ? v.lines.slice(0, 2).join(" ").replace(/\*\*/g, "") : STARTS;
      })
      .catch(() => (recordLine = null));
  });
  const grades = $derived(gradeRows(about?.grades ?? null));
  const lead = $derived(gradeLead(grades, about?.grades?.weeks ?? null));

  // ---- from the blog: the newest three
  let posts = $state<BlogMeta[] | null>(null);
  $effect(() => {
    get<{ posts: BlogMeta[] }>(blogPaths.list(3))
      .then((d) => (posts = d.posts.length ? d.posts : null))
      .catch(() => (posts = null));
  });

  const TOOLS = [
    { key: "players", title: "Players", what: "Every player's stats, trends and this week's projection.", href: link("/players") },
    { key: "trade", title: "Trade calculator", what: "Weigh a trade in PPR, Half PPR or Standard.", href: link("/trade-calc") },
    { key: "matchups", title: "Matchups", what: "Who each receiver faces this week, and how tough it is.", href: link("/matchups") },
    { key: "dfs", title: "DFS", what: "DraftKings and FanDuel values for this week's slate.", href: link("/dfs") },
  ];
</script>

<main class="space-y-6 pb-6" data-testid="home">
  <div class="grid gap-5 wide:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] wide:items-start wide:gap-8">
    <!-- the five-second answer: the name, one sentence, two actions -->
    <section class="space-y-3 wide:pt-4" data-testid="home-hero">
      <h1 class="flex items-center gap-2 text-3xl font-extrabold tracking-tight wide:text-[2.5rem] wide:leading-tight">
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-sm bg-accent text-sm font-black text-on-accent wide:h-11 wide:w-11" aria-hidden="true">{APP_MARK}</span>{APP_NAME}
      </h1>
      <p class="text-lg leading-snug text-ink-2 wide:text-xl" data-testid="home-sentence">
        Our own projections for every player, his trends and his matchups, priced in your scoring — then your lineup, waivers and trades once you
        open your league.
      </p>
      <div class="flex flex-wrap gap-2">
        <a href="/leagues" class="inline-flex min-h-11 items-center rounded-md bg-accent px-4 font-semibold text-on-accent" data-testid="home-open">Open your league</a>
        <a href={BROWSE_HREF} class="inline-flex min-h-11 items-center rounded-md border border-line px-4 font-semibold" data-testid="home-browse">Browse players</a>
      </div>
      <p class="hidden text-sm leading-snug text-ink-3 wide:block">Sleeper, MyFantasyLeague, ESPN or Yahoo. No account, no password to your league.</p>
    </section>

    <!-- live content above the fold: this week's top projections -->
    <section class="rounded-lg border border-line bg-surface" style="box-shadow:var(--ll-shadow)" data-testid="home-top">
      <div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 pt-3">
        <h2 class="text-lg leading-tight font-bold">This week's top projections <span class="text-sm font-semibold text-ink-3">· {scoring}</span></h2>
        <Tabs items={POSITIONS.map((p) => ({ key: p, label: p }))} current={pos} onpick={(k) => (pos = k as typeof pos)} size="sm" label="Position" testid="home-top-pos" />
      </div>
      {#if topRows === "loading" || topRows === undefined}
        <ul class="space-y-1 p-4" aria-label="Loading">
          {#each [0, 1, 2] as i (i)}<li class="ll-skel h-12"></li>{/each}
        </ul>
      {:else if topRows === "failed"}
        <p class="p-4 text-sm text-ink-3" data-testid="home-top-none">No projections to show at {posWords(pos).toLowerCase()} right now.</p>
      {:else}
        <ol class="divide-y divide-line" data-testid="home-top-rows">
          {#each topRows as p, i (p.gsis_id)}
            <li class="flex min-h-14 items-center gap-3 px-4 py-2" data-testid="home-top-row">
              <span class="tabnum w-4 shrink-0 text-sm text-ink-3">{i + 1}</span>
              <span class="hidden shrink-0 sm:block"><Headshot url={p.headshot_url} name={p.player_name} team={p.team} size={36} /></span>
              <div class="min-w-0 flex-1">
                <a href={link(`/player/${p.gsis_id}`)} class="block truncate font-semibold hover:underline" data-testid="home-top-name">{p.player_name}</a>
                <div class="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-ink-3">
                  <PosBadge pos={p.position} /><TeamBadge team={p.team} />
                  {#if p.low !== null && p.high !== null}
                    <span class="tabnum w-full whitespace-nowrap sm:w-auto" data-testid="home-top-range">range {fmt.pts(p.low)}–{fmt.pts(p.high)}</span>
                  {:else if p.ros !== null}
                    <span class="tabnum w-full whitespace-nowrap sm:w-auto" data-testid="home-top-range">season {fmt.whole(p.ros)} ({fmt.whole(p.rosLow)}–{fmt.whole(p.rosHigh)})</span>
                  {/if}
                </div>
              </div>
              <div class="shrink-0 text-right">
                <div class="tabnum text-xl leading-none font-bold">{fmt.pts(p.week)}</div>
                <div class="mt-0.5 text-xs text-ink-3">this week</div>
              </div>
            </li>
          {/each}
        </ol>
        <p class="border-t border-line px-4 py-2.5 text-sm leading-snug text-ink-3" data-testid="home-top-note">
          {#if topRows[0]?.low !== null}
            Projected points this week in {scoring} scoring, with the low-end to high-end outcome (8 weeks in 10 land between).
          {:else}
            Projected points this week in {scoring} scoring; beside it the rest of the season and its low-end to high-end range (8 in 10 land between).
          {/if}
          <a class="ll-link" href={link("/players")}>Every player ›</a>
        </p>
      {/if}
    </section>
  </div>

  <div class="grid gap-5 wide:grid-cols-2 wide:items-start">
    <!-- two across from 900 px: the board and the record; without the board, the record and the blog -->
    {#if board}
      <!-- matchups to target this week (IN-3's board; hidden when the route is missing) -->
      <section class="rounded-lg border border-line bg-surface" data-testid="home-matchups">
        <div class="px-4 pt-3">
          <h2 class="text-lg leading-tight font-bold">Matchups to target this week</h2>
          <p class="text-sm text-ink-3">Wide receivers, the easiest matchups first. Context beside the projection, not added to it.</p>
        </div>
        <ul class="divide-y divide-line">
          {#each board as { r, t } (r.gsis_id)}
            <li class="flex items-start gap-3 px-4 py-2.5" data-testid="home-matchup-row">
              <Headshot url={r.headshot_url ?? null} name={r.player_name} team={r.team} size={32} />
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-baseline gap-x-2">
                  <a href={link(`/player/${r.gsis_id}`)} class="font-semibold hover:underline">{r.player_name}</a>
                  {#if r.opponent}<span class="text-sm text-ink-3">{r.home === false ? "at" : "vs"} {r.opponent}</span>{/if}
                </div>
                {#if t.words}<p class="text-sm leading-snug text-ink-2">{t.words}</p>{/if}
              </div>
              {#if t.tone}
                <span
                  class="shrink-0 rounded-sm px-2 py-0.5 text-xs font-semibold {t.tone === 'favorable' ? 'bg-good/20 text-good' : t.tone === 'difficult' ? 'bg-bad/20 text-bad' : 'bg-raised text-ink-3'}"
                  >{t.tone === "favorable" ? "▲ " : t.tone === "difficult" ? "▼ " : ""}{TONE_WORDS[t.tone]}</span
                >
              {/if}
            </li>
          {/each}
        </ul>
        <p class="border-t border-line px-4 py-2.5 text-sm"><a class="ll-link" href={link("/matchups")}>Every matchup ›</a></p>
      </section>
    {/if}

    {#if grades.length || recordLine}
      <!-- how the projections have done: the record's own numbers, the bad ones too -->
      <section class="rounded-lg border border-line bg-surface p-4" data-testid="home-record">
        <h2 class="text-lg leading-tight font-bold">How the projections have done</h2>
        {#if lead}<p class="mt-1 leading-snug" data-testid="home-record-lead">{lead}</p>{/if}
        {#if grades.length}
          <table class="mt-3 w-full border-collapse text-sm" data-testid="home-grades">
            <thead>
              <tr class="text-left text-ink-3">
                <th scope="col" class="ll-label py-1 pr-2">Position</th>
                <th scope="col" class="ll-label py-1 pr-2 text-right">Average miss</th>
                <th scope="col" class="ll-label py-1 text-right">Inside the range</th>
              </tr>
            </thead>
            <tbody>
              {#each grades as g (g.position)}
                <tr class="border-t border-line" data-testid="home-grade" data-verdict={g.verdict}>
                  <th scope="row" class="py-1.5 pr-2 text-left font-semibold">{g.position}</th>
                  <td class="tabnum py-1.5 pr-2 text-right">
                    <span class={g.verdict === "worse" ? "font-semibold text-bad" : ""}>{fmt.pts(g.miss)}</span>
                    <span class="text-ink-3">(before {fmt.pts(g.missBefore)})</span>
                  </td>
                  <td class="tabnum py-1.5 text-right">{fmt.pct(g.inside)} <span class="text-ink-3">(aim 80%)</span></td>
                </tr>
              {/each}
            </tbody>
          </table>
          <p class="mt-2 text-sm leading-snug text-ink-3">
            Average miss: points between the projection and what he scored, per player. Inside the range: how often he landed between the
            low-end and high-end outcome. "Before": the same model on {about?.grades?.backtest_seasons ?? "past seasons"}.
          </p>
        {/if}
        {#if recordLine}<p class="mt-2 text-sm leading-snug text-ink-2" data-testid="home-record-line">{recordLine}</p>{/if}
        <p class="mt-2 text-sm"><a class="ll-link" href={link("/about")} data-testid="home-about">How we keep score ›</a></p>
      </section>
    {/if}

    {#if !board && posts}{@render blogPosts(true)}{/if}
  </div>
  {#if board && posts}{@render blogPosts(false)}{/if}

  {#snippet blogPosts(narrow: boolean)}
    <!-- from the blog: the newest three -->
    <section class="space-y-3" data-testid="home-blog">
      <div class="flex items-baseline justify-between gap-3">
        <h2 class="text-lg leading-tight font-bold">From the blog</h2>
        <a class="ll-link text-sm" href="/blog">All posts ›</a>
      </div>
      <ul class="grid gap-3 sm:grid-cols-2 {narrow ? 'wide:grid-cols-1' : 'wide:grid-cols-3'}">
        {#each posts ?? [] as p (p.slug)}
          <li>
            <a href={`/blog/${p.slug}`} class="block h-full rounded-lg border border-line bg-surface p-4 hover:border-line-strong" data-testid="home-post">
              <div class="text-xs text-ink-3">{longDate(p.date)} · {p.minutes} min read</div>
              <div class="mt-1 text-base leading-snug font-bold">{p.title}</div>
              {#if p.summary}<p class="mt-1 line-clamp-3 text-sm leading-snug text-ink-2">{p.summary}</p>{/if}
            </a>
          </li>
        {/each}
      </ul>
    </section>
  {/snippet}

  <!-- the tools -->
  <section class="space-y-3" data-testid="home-tools">
    <h2 class="text-lg leading-tight font-bold">The tools, open to everyone</h2>
    <ul class="grid grid-cols-2 gap-3 wide:grid-cols-4">
      {#each TOOLS as t (t.key)}
        <li>
          <a href={t.href} class="block h-full rounded-lg border border-line bg-surface p-4 hover:border-accent" data-testid="home-tool" data-tool={t.key}>
            <div class="font-bold">{t.title} <span class="text-accent" aria-hidden="true">›</span></div>
            <p class="mt-1 text-sm leading-snug text-ink-2">{t.what}</p>
          </a>
        </li>
      {/each}
    </ul>
    <p class="text-sm leading-snug text-ink-3">Every number here is in {scoring} scoring. Open your league and they are priced in its own rules.</p>
  </section>
</main>
