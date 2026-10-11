<script lang="ts">
  // IX-2 (Wave I-X): his targets, target share, carries and carry share by game situation — when his team trails by 9
  // or more, within a score (8 points either way, tied included), leads by 9 or more — with his team's plays behind
  // each group, so a small sample shows; a group with too few plays says so and shows no share.
  import type { Situations } from "../../lib/api";

  let { s, testid = "situations" }: { s: Situations; testid?: string } = $props();
  const pct = (v: number | null, few: boolean) => (few || v === null ? "—" : `${Math.round(100 * v)}%`);
  // a receiver with no carries (or a passer with no targets) gets no column of zeros: the columns that have a number
  const showT = $derived(s.groups.some((g) => g.targets > 0));
  const showC = $derived(s.groups.some((g) => g.carries > 0));
</script>

<section class="rounded-lg border border-line bg-surface p-3" data-testid={testid} aria-labelledby={`${testid}-title`}>
  <h3 id={`${testid}-title`} class="text-base font-bold">By game situation · {s.season}</h3>
  <table class="mt-2 w-full table-fixed text-sm" data-testid={`${testid}-table`}>
    <thead>
      <tr class="ll-label text-left">
        <th class="w-[40%] py-1 font-medium">When</th>
        {#if showT}<th class="py-1 pl-1 text-right font-medium">Targets</th><th class="py-1 pl-1 text-right font-medium">Share</th>{/if}
        {#if showC}<th class="py-1 pl-1 text-right font-medium">Carries</th><th class="py-1 pl-1 text-right font-medium">Share</th>{/if}
      </tr>
    </thead>
    <tbody>
      {#each s.groups as g (g.key)}
        <tr class="border-t border-line align-top" data-testid={`${testid}-row`} data-key={g.key}>
          <td class="py-1.5 pr-1">
            <span class="font-semibold">{g.label}</span>
            <span class="block text-xs leading-snug text-ink-3" data-testid={`${testid}-plays`}>{g.words}</span>
          </td>
          {#if showT}<td class="tabnum py-1.5 text-right">{g.targets}</td><td class="tabnum py-1.5 text-right">{pct(g.target_share, g.too_few)}</td>{/if}
          {#if showC}<td class="tabnum py-1.5 text-right">{g.carries}</td><td class="tabnum py-1.5 text-right">{pct(g.carry_share, g.too_few)}</td>{/if}
        </tr>
      {/each}
    </tbody>
  </table>
  <p class="mt-2 text-xs leading-snug text-ink-3" data-testid={`${testid}-how`}>{s.how}</p>
</section>
