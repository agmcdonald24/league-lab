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
  import Chips from "../components/Chips.svelte";
  import PosBadge from "../components/PosBadge.svelte";
  import TeamBadge from "../components/TeamBadge.svelte";
  import Md from "../components/Md.svelte";

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


<main class="space-y-4" data-testid="ros">
  <header class="space-y-1.5">
    <p class="text-label font-bold tracking-[0.08em] text-accent uppercase">Rest of season · {leagueName}</p>
    <h1 class="text-2xl leading-tight font-extrabold tracking-tight wide:text-3xl">Who scores the most from here</h1>
  </header>
  <Chips label="Position" testid="ros-pos" current={position} onpick={pick} items={positions.map((p) => ({ key: p, label: label(p) }))} />

  {#if error}
    <p class="ll-error">{error}</p>
  {:else if !data}
    <div class="space-y-3" aria-label="Loading" data-testid="loading">
      <div class="ll-skel h-16"></div>
      {#each [0, 1, 2, 3, 4] as i (i)}<div class="ll-skel h-8"></div>{/each}
    </div>
  {:else if players.length === 0}
    <p class="rounded-lg bg-raised p-4 text-base" data-testid="ros-empty">
      No weeks left in {leagueName}'s season: rest-of-season totals come back with next season's schedule.
    </p>
  {:else}
    <section class="relative space-y-1.5 overflow-hidden rounded-lg border border-line bg-surface p-4 pl-5" style="box-shadow:var(--ll-shadow)" data-testid="ros-answer">
      <p class="text-lg leading-snug"><Md text={answerLine(players[0], position)} {ctx} /></p>
      {#if team !== null}<p class="text-base leading-snug" data-testid="ros-yours">{yoursLine(players, team, position)}</p>{/if}
      <p class="text-sm leading-snug text-ink-3">
        {span ? `${span[0].toUpperCase()}${span.slice(1)}` : "The weeks left"} in {leagueName} scoring, up to the league's final. A bye
        is a week with no game: he plays one fewer. Ranked among everyone at the position, rostered or free agent.
        {#if data?.lines_note}{" " + data.lines_note}{/if}
      </p>
      <span class="absolute inset-y-0 left-0 w-1 bg-accent" aria-hidden="true"></span>
    </section>

    <div class="overflow-hidden rounded-lg border border-line bg-surface" style="box-shadow:var(--ll-shadow)">
    <table class="w-full table-fixed border-collapse text-base" data-testid="ros-table">
      <thead>
        <tr class="ll-label border-b border-line bg-raised text-left">
          <th class="w-[3rem] py-2 pr-1 pl-3 font-semibold">Rank</th>
          <th class="py-2 pr-1 font-semibold">Player</th>
          <th class="w-[3.75rem] py-2 text-right font-semibold">Points</th>
          <th class="w-[3.5rem] py-2 text-right font-semibold">Games</th>
          <th class="w-[4.5rem] py-2 pr-3 text-right font-semibold">Playoffs</th>
        </tr>
      </thead>
      <tbody>
        {#each players as p, i (p.gsis_id ?? `${p.player_name}-${i}`)}
          {@const yours = team !== null && p.rostered_by_roster_id === team}
          <tr class="border-b border-line align-middle last:border-0 {yours ? 'bg-accent-soft' : ''}">
            <td class="tabnum py-2 pr-1 pl-3 font-semibold text-ink-3">{rankOf(p, i, position) ?? "—"}</td>
            <td class="py-2 pr-1 leading-snug break-words">
              {#if p.gsis_id}
                <a class="ll-name font-semibold" href={withContext(`/player/${p.gsis_id}`, ctx)}>{p.player_name}</a>
              {:else}
                {p.player_name}
              {/if}
              <div class="mt-0.5 flex min-w-0 items-center gap-1 text-xs text-ink-3">
                <PosBadge pos={p.position} />{#if p.position !== "DEF"}<TeamBadge team={p.team} />{/if}
                <span class="truncate {yours ? 'font-semibold text-accent' : ''}">{yours ? "yours" : (p.rostered_by_team ?? "free agent")}</span>
              </div>
            </td>
            <td class="tabnum py-2 text-right font-bold">{whole(p.ros_points) ?? "—"}</td>
            <td class="tabnum py-2 text-right text-ink-2">{p.ros_games ?? "—"}</td>
            <td class="tabnum py-2 pr-3 text-right text-ink-2">{whole(p.playoff_points) ?? "—"}</td>
          </tr>
        {/each}
      </tbody>
    </table>
    </div>

    <Expander title="How to read this" testid="howto">
      <div class="text-base leading-snug">
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
