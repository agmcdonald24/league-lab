<script lang="ts" module>
  // Which expanders are open, per page (path + query): Back re-creates the page, and an expander that was open must
  // be open again, or the page is shorter and the scroll position cannot be restored. In memory only.
  // eslint-disable-next-line svelte/prefer-svelte-reactivity -- a plain lookup read once per mount, never observed
  const opened = new Map<string, boolean>();
</script>

<script lang="ts">
  import type { Snippet } from "svelte";

  let { title, children, testid }: { title: string; children: Snippet; testid?: string } = $props();
  const key = $derived(`${location.pathname}${location.search}|${testid ?? title}`);
</script>

<details
  class="rounded-2xl border border-zinc-200 dark:border-zinc-800"
  data-testid={testid}
  open={opened.get(key) ?? false}
  ontoggle={(e) => opened.set(key, e.currentTarget.open)}
>
  <summary class="flex min-h-11 items-center gap-2 px-4 py-2.5 text-[15px] font-medium">
    <span class="chev text-zinc-400" aria-hidden="true">›</span>
    <span>{title}</span>
  </summary>
  <div class="px-4 pb-4">{@render children()}</div>
</details>
