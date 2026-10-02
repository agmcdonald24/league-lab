<script lang="ts">
  // An NFL team chip in the team's own color (white or ink text, whichever reads). "FA" for no team.
  import { onColor, team as teamColors, teamLabel } from "../lib/theme";

  let { team, size = "sm" }: { team: string | null | undefined; size?: "sm" | "md" } = $props();
  const c = $derived(teamColors(team));
  const label = $derived(teamLabel(team) ?? "FA");
</script>

<span
  class="inline-flex items-center rounded-sm font-bold tracking-wide ring-1 ring-line-strong ring-inset {size === 'md' ? 'px-2 py-0.5 text-sm' : 'px-1.5 text-[11px] leading-[18px]'}"
  style="background:{c.primary};color:{onColor(c.primary)}"
  title={c.name}
  data-testid="team-badge">{label}</span
>
