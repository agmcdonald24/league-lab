<script lang="ts">
  // The panel everything sits in: a surface, a hairline, a small uppercase title (optional) with an action on its
  // right (a link, a toggle), and an optional team-color stripe on the left edge.
  import type { Snippet } from "svelte";

  let {
    title,
    action,
    children,
    accent,
    tone = "plain",
    pad = true,
    testid,
    class: cls = "",
  }: {
    title?: string;
    action?: Snippet;
    children: Snippet;
    accent?: string | null;
    tone?: "plain" | "raised" | "accent";
    pad?: boolean;
    testid?: string;
    class?: string;
  } = $props();
</script>

<section
  class="relative overflow-hidden rounded-lg border border-line {tone === 'raised' ? 'bg-raised' : 'bg-surface'} {tone === 'accent'
    ? 'ring-1 ring-accent/50'
    : ''} {pad ? 'p-4' : ''} {cls}"
  style="box-shadow:var(--ll-shadow)"
  data-testid={testid}
>
  {#if accent}<span class="absolute inset-y-0 left-0 w-1" style="background:{accent}" aria-hidden="true"></span>{/if}
  {#if title || action}
    <header class="mb-3 flex items-baseline justify-between gap-2 {pad ? '' : 'px-4 pt-4'}">
      {#if title}<h2 class="ll-label">{title}</h2>{/if}
      {#if action}<div class="text-sm">{@render action()}</div>{/if}
    </header>
  {/if}
  {@render children()}
</section>
