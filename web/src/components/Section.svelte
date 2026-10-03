<script lang="ts">
  import type { Section } from "../lib/api";
  import type { LinkContext } from "../lib/md";
  import Md from "./Md.svelte";
  import Metrics from "./Metrics.svelte";

  import type { Snippet } from "svelte";

  // ---- IA-3 (Wave I-A): `children` — more of the section after its blocks (the Projection's "why this number")
  let { section, ctx, testid, children }: { section: Section; ctx: LinkContext; testid: string; children?: Snippet } = $props();
</script>

<section class="space-y-2.5 rounded-lg border border-line bg-surface p-4" style="box-shadow:var(--ll-shadow)" data-testid={testid}>
  <h2 class="text-base leading-snug"><Md text={section.title} {ctx} /></h2>
  {#each section.blocks as b, i (i)}
    {#if b.kind === "metrics" && b.metrics}
      <Metrics metrics={b.metrics} />
    {:else if b.kind === "caption"}
      {#if b.text}<p class="text-sm leading-snug text-ink-3"><Md text={b.text} {ctx} /></p>{/if}
    {:else if b.kind === "unavailable"}
      <p class="text-sm text-ink-3 italic">{b.text}</p>
    {:else if b.text}
      <p class="text-base leading-snug"><Md text={b.text} {ctx} /></p>
    {/if}
  {/each}
  {@render children?.()}
</section>
