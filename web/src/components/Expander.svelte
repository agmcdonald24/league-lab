<script lang="ts">
  import type { Snippet } from "svelte";

  let { title, children, testid }: { title: string; children: Snippet; testid?: string } = $props();
</script>

<details class="rounded-2xl border border-zinc-200 dark:border-zinc-800" data-testid={testid}>
  <summary class="flex min-h-11 items-center gap-2 px-4 py-2.5 text-[15px] font-medium">
    <span class="chev text-zinc-400" aria-hidden="true">›</span>
    <span>{title}</span>
  </summary>
  <div class="px-4 pb-4">{@render children()}</div>
</details>
