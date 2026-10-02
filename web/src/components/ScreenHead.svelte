<script lang="ts">
  // The top of a screen: an eyebrow (where you are), the title, and the answer in one or two lines — the screen's
  // first job (WORDS.md: say what to do first).
  import type { Snippet } from "svelte";

  let { eyebrow, title, answer, children, testid = "screen-head" }: { eyebrow?: string; title: string; answer?: Snippet; children?: Snippet; testid?: string } =
    $props();
</script>

<header class="space-y-1.5" data-testid={testid}>
  {#if eyebrow}<p class="text-label font-bold tracking-[0.08em] text-accent uppercase">{eyebrow}</p>{/if}
  <h1 class="text-2xl leading-tight font-extrabold tracking-tight wide:text-3xl">{title}</h1>
  {#if answer}<div class="text-base leading-snug text-ink-2" data-testid="answer">{@render answer()}</div>{/if}
  {#if children}{@render children()}{/if}
</header>
