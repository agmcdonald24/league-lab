<script lang="ts" module>
  /** The league select's last option: the sign-in / league picker screen. */
  export const OTHER = "__leagues";
</script>

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

  const sel = "ll-input min-w-0 flex-1 truncate py-1.5 pr-7 text-sm font-semibold";
</script>

<div class="flex min-w-0 gap-2" data-testid="picker">
  <label class="sr-only" for="ll-league">League</label>
  <select id="ll-league" class={sel} value={league ?? ""} onchange={(e) => onleague(e.currentTarget.value)} data-testid="pick-league">
    {#each leagues as l, ix (`${l.league_id}#${ix}`)}
      <option value={l.league_id}>{l.name}</option>
    {/each}
    <option value={OTHER}>Other leagues (Sleeper or MFL)…</option><!-- IE-0: both platforms -->
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
    {#each rosters as r, ix (`${r.roster_id}#${ix}`)}
      <option value={String(r.roster_id)}>{r.team_name}{r.manager_name ? ` (${r.manager_name})` : ""}</option>
    {/each}
  </select>
</div>
