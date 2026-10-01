<script lang="ts">
  import type { Section } from "../lib/api";
  import type { LinkContext } from "../lib/md";
  import Md from "./Md.svelte";
  import Metrics from "./Metrics.svelte";

  let { section, ctx, testid }: { section: Section; ctx: LinkContext; testid: string } = $props();
</script>

<section class="space-y-2.5 rounded-2xl border border-zinc-200 p-4 dark:border-zinc-800" data-testid={testid}>
  <h2 class="text-[15px] leading-snug"><Md text={section.title} {ctx} /></h2>
  {#each section.blocks as b, i (i)}
    {#if b.kind === "metrics" && b.metrics}
      <Metrics metrics={b.metrics} />
    {:else if b.kind === "caption"}
      {#if b.text}<p class="text-[13px] leading-snug text-zinc-500 dark:text-zinc-400"><Md text={b.text} {ctx} /></p>{/if}
    {:else if b.kind === "unavailable"}
      <p class="text-[13px] text-zinc-500 italic dark:text-zinc-400">{b.text}</p>
    {:else if b.text}
      <p class="text-[15px] leading-snug"><Md text={b.text} {ctx} /></p>
    {/if}
  {/each}
</section>
