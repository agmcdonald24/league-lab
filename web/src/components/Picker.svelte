<script lang="ts">
  import type { Roster } from "../lib/api";
  import type { LeagueOption } from "../lib/leagues";

  let {
    leagues,
    league,
    rosters,
    team,
    onleague,
    onteam,
  }: {
    leagues: LeagueOption[];
    league: string | null;
    rosters: Roster[];
    team: number | null;
    onleague: (league: string) => void;
    onteam: (team: number | null) => void;
  } = $props();

  const sel =
    "min-w-0 flex-1 truncate rounded-xl border border-zinc-300 bg-white px-2.5 py-2 text-[15px] font-medium dark:border-zinc-700 dark:bg-zinc-900";
</script>

<div class="flex gap-2" data-testid="picker">
  <label class="sr-only" for="ll-league">League</label>
  <select id="ll-league" class={sel} value={league ?? ""} onchange={(e) => onleague(e.currentTarget.value)} data-testid="pick-league">
    {#each leagues as l (l.league_id)}
      <option value={l.league_id}>{l.name}</option>
    {/each}
  </select>
  <label class="sr-only" for="ll-team">Team</label>
  <select
    id="ll-team"
    class={sel}
    value={team === null ? "" : String(team)}
    onchange={(e) => onteam(e.currentTarget.value === "" ? null : Number(e.currentTarget.value))}
    data-testid="pick-team"
  >
    <option value="">Pick your team</option>
    {#each rosters as r (r.roster_id)}
      <option value={String(r.roster_id)}>{r.team_name}{r.manager_name ? ` (${r.manager_name})` : ""}</option>
    {/each}
  </select>
</div>
