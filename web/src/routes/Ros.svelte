<script lang="ts">
  // Rest of season (plan F2): the answer first (#1 at the position), then "Yours", then the list
  // (Rank · Player · Points · Games · Playoffs) from GET /api/ros. Position switch: QB RB WR TE, K and DEF only when
  // the league starts them, All = the overall rank. The switch rewrites the URL in place (no Back step).
  import { ApiError, get, paths, peek, Unauthorized, type MyWeek, type RosList } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";
  import { md, withContext } from "../lib/md";
  import { answerLine, rankOf, weeksSpan, whole, yoursLine } from "../lib/ros";
  import { restoreScroll, route, setParams } from "../lib/router.svelte";
  import Expander from "../components/Expander.svelte";
  import Md from "../components/Md.svelte";
  import TopBar from "../components/TopBar.svelte";

  let {
    options,
    league,
    team,
    onauth,
  }: { options: LeagueOption[]; league: string; team: number | null; onauth: () => void } = $props();

  const BASE = ["QB", "RB", "WR", "TE"];
  let data = $state<RosList | null>(null);
  let error = $state<string | null>(null);
  let slots = $state<string[]>([]); // the league's lineup slots (from My Week): K / DEF tabs only when it has them

  const ctx = $derived({ league, team });
  const position = $derived.by(() => {
    const p = (route.current.params.get("position") ?? "ALL").toUpperCase();
    return [...BASE, "K", "DEF", "ALL"].includes(p) ? p : "ALL";
  });
  const positions = $derived.by(() => {
    if (data?.positions?.length) return [...data.positions.filter((p) => p !== "ALL"), "ALL"];
    const extra = ["K", "DEF"].filter((p) => slots.includes(p) || position === p);
    return [...BASE, ...extra, "ALL"];
  });
  const leagueName = $derived(options.find((o) => o.league_id === league)?.name ?? "this league");
  const players = $derived(data?.players ?? []);
  const span = $derived(data ? weeksSpan(data.from_week, data.last_week) : null);

  // K / DEF: does this league start them? The /api/ros contract does not say (requested of F3: `positions`); My Week's
  // lineup does, and it is usually in memory already (the user came from My Week).
  $effect(() => {
    const l = league;
    const t = team;
    if (t === null) return;
    const path = paths.myWeek(l, t);
    const hit = peek<MyWeek>(path);
    const take = (d: MyWeek) => (slots = d.lineup_full.map((r) => r.position ?? "").concat(d.lineup_full.map((r) => r.slot)));
    if (hit) take(hit);
    else
      get<MyWeek>(path)
        .then((d) => league === l && take(d))
        .catch(() => {});
  });

  $effect(() => {
    const l = league;
    const p = position;
    error = null;
    const path = paths.ros(l, p);
    const hit = peek<RosList>(path);
    if (hit) {
      data = hit;
      restoreScroll();
      return;
    }
    data = null;
    get<RosList>(path)
      .then((d) => {
        if (league !== l || position !== p) return;
        data = d;
        restoreScroll();
      })
      .catch((e) => {
        if (league !== l || position !== p) return;
        if (e instanceof Unauthorized) onauth();
        else if (e instanceof ApiError && e.status === 404) error = "League Lab cannot find this league on Sleeper. Pick another above.";
        else if (e instanceof ApiError && e.status === 502) error = "Sleeper did not answer. Try again in a minute.";
        else if (e instanceof ApiError && e.status === 503) error = "The numbers are not ready yet. Try again in a few minutes.";
        else error = e instanceof Error ? e.message : String(e);
      });
  });

  function pick(p: string) {
    setParams({ position: p });
  }
  const label = (p: string) => (p === "ALL" ? "All" : p);
</script>

<TopBar {options} {league} {team} {onauth} />

<main class="space-y-4 px-4 pb-10" data-testid="ros">
  <div class="flex flex-wrap gap-1.5" role="group" aria-label="Position" data-testid="ros-positions">
    {#each positions as p (p)}
      <button
        type="button"
        class="min-h-9 rounded-full border px-3 text-[14px] font-medium {p === position
          ? 'border-green-700 bg-green-700 text-white dark:border-green-600 dark:bg-green-600'
          : 'border-zinc-300 dark:border-zinc-700'}"
        aria-pressed={p === position}
        onclick={() => pick(p)}
        data-testid={`ros-pos-${p}`}>{label(p)}</button
      >
    {/each}
  </div>

  {#if error}
    <p class="rounded-2xl border border-red-200 p-4 text-[15px] text-red-800 dark:border-red-900 dark:text-red-300">{error}</p>
  {:else if !data}
    <div class="animate-pulse space-y-3" aria-label="Loading" data-testid="loading">
      <div class="h-16 rounded-2xl bg-zinc-100 dark:bg-zinc-900"></div>
      {#each [0, 1, 2, 3, 4] as i (i)}<div class="h-8 rounded bg-zinc-100 dark:bg-zinc-900"></div>{/each}
    </div>
  {:else if players.length === 0}
    <p class="rounded-2xl bg-zinc-100 p-4 text-[15px] dark:bg-zinc-900" data-testid="ros-empty">
      No weeks left in {leagueName}'s season: rest-of-season totals come back with next season's schedule.
    </p>
  {:else}
    <section class="space-y-1.5 rounded-2xl border border-zinc-200 p-4 dark:border-zinc-800" data-testid="ros-answer">
      <p class="text-[16px] leading-snug"><Md text={answerLine(players[0], position)} {ctx} /></p>
      {#if team !== null}<p class="text-[15px] leading-snug" data-testid="ros-yours">{yoursLine(players, team, position)}</p>{/if}
      <p class="text-[13px] leading-snug text-zinc-500 dark:text-zinc-400">
        {span ? `${span[0].toUpperCase()}${span.slice(1)}` : "The weeks left"} in {leagueName} scoring, up to the league's final. A bye
        is a week with no game: he plays one fewer. Ranked among everyone at the position, rostered or free agent.
      </p>
    </section>

    <table class="w-full table-fixed border-collapse text-[15px]" data-testid="ros-table">
      <thead>
        <tr class="border-b border-zinc-200 text-left text-[11px] tracking-wide text-zinc-500 uppercase dark:border-zinc-800 dark:text-zinc-400">
          <th class="w-[2.75rem] py-1.5 pr-1 font-medium">Rank</th>
          <th class="py-1.5 pr-1 font-medium">Player</th>
          <th class="w-[3.5rem] py-1.5 text-right font-medium">Points</th>
          <th class="w-[3.5rem] py-1.5 text-right font-medium">Games</th>
          <th class="w-[4.25rem] py-1.5 text-right font-medium">Playoffs</th>
        </tr>
      </thead>
      <tbody>
        {#each players as p, i (p.gsis_id ?? `${p.player_name}-${i}`)}
          {@const yours = team !== null && p.rostered_by_roster_id === team}
          <tr class="border-b border-zinc-100 align-top last:border-0 dark:border-zinc-800/70 {yours ? 'bg-green-50 dark:bg-green-950/40' : ''}">
            <td class="tabnum py-2 pr-1 text-zinc-500 dark:text-zinc-400">{rankOf(p, i, position) ?? "—"}</td>
            <td class="py-2 pr-1 leading-snug break-words">
              {#if p.gsis_id}
                <a class="ll-link" href={withContext(`/player/${p.gsis_id}`, ctx)}>{p.player_name}</a>
              {:else}
                {p.player_name}
              {/if}
              <div class="text-[12px] text-zinc-500 dark:text-zinc-400">
                {[position === "ALL" ? p.position : null, p.team, yours ? "yours" : (p.rostered_by_team ?? "free agent")].filter(Boolean).join(" · ")}
              </div>
            </td>
            <td class="tabnum py-2 text-right font-medium">{whole(p.ros_points) ?? "—"}</td>
            <td class="tabnum py-2 text-right">{p.ros_games ?? "—"}</td>
            <td class="tabnum py-2 text-right">{whole(p.playoff_points) ?? "—"}</td>
          </tr>
        {/each}
      </tbody>
    </table>

    <Expander title="How to read this" testid="howto">
      <div class="text-[14px] leading-snug">
        {@html md(
          "- **Rest of season** adds up every week left in your league's season, up to its final: the list for trades and waivers.\n" +
            "- A bye is a week with no game: he plays one fewer, it is not a low score.\n" +
            "- **Likely** is where 8 seasons in 10 would land if every week were its own roll of the dice; a role change or an injury moves the weeks together, so the real range is wider.\n" +
            "- **Playoffs** is the part of the total that falls in your league's playoff weeks.",
        )}
      </div>
    </Expander>
  {/if}
</main>
