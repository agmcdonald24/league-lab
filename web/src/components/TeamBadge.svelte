<script lang="ts">
  // An NFL team chip in the team's own color (white or ink text, whichever reads), named for screen readers.
  // IE-0 (Wave I-E): a missing NFL team is never shown as "FA" / "Free agent" (the review saw a rostered team QB unit
  // labelled "Free agent"): no team → no chip. `fa` (the caller knows he is on no NFL team) shows "FA", named so.
  import { onColor, team as teamColors, teamKey, teamLabel } from "../lib/theme";

  let { team, size = "sm", fa = false }: { team: string | null | undefined; size?: "sm" | "md"; fa?: boolean } = $props();
  const c = $derived(teamColors(team));
  const label = $derived(teamLabel(team) ?? (fa ? "FA" : null));
  const name = $derived(teamKey(team) ? c.name : teamLabel(team) ?? "Not on an NFL team");
</script>

{#if label}
  <span
    class="inline-flex items-center rounded-sm font-bold tracking-wide ring-1 ring-line-strong ring-inset {size === 'md' ? 'px-2 py-0.5 text-sm' : 'px-1.5 text-[11px] leading-[18px]'}"
    style="background:{c.primary};color:{onColor(c.primary)}"
    title={name}
    role="img"
    aria-label={name}
    data-testid="team-badge">{label}</span
  >
{/if}
