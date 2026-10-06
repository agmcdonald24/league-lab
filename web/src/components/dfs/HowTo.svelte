<script lang="ts">
  // ---- IM-5: where each site's salary file is (the three steps). The sites' own words as remembered (docs/DFS.md says
  // which are unverified until a real file is checked).
  import type { Site } from "./dfs";

  let { site }: { site: Site } = $props();
  const STEPS: Record<Site, string[]> = {
    dk: [
      "On DraftKings' website (a computer, not the app), open the contest and go to its draft page (Enter, or Draft team).",
      "Above the player list, tap Export to CSV: the file is DKSalaries.csv.",
      "Add that file here (or paste its text). We read it in this tab and keep nothing.",
    ],
    fd: [
      "On FanDuel's website (a computer, not the app), open the contest and go to its lineup page (Enter, or Create lineup).",
      "Above the player list, tap Download players list: a CSV of the contest's players.",
      "Add that file here (or paste its text). We read it in this tab and keep nothing.",
    ],
  };
</script>

<ol class="space-y-1.5 text-sm text-ink-2" data-testid="dfs-howto">
  {#each STEPS[site] as s, i (i)}
    <li class="flex gap-2"><span class="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-raised text-xs font-bold text-ink">{i + 1}</span><span>{s}</span></li>
  {/each}
</ol>
