<script lang="ts">
  // List on the left, detail on the right from 900 px (the free-agent screens); stacked on a phone. The detail stays
  // in view while the list scrolls (sticky). On a phone the detail comes first when `detailFirst` (the answer first).
  import type { Snippet } from "svelte";

  let { list, detail, detailFirst = false, testid = "list-detail" }: { list: Snippet; detail: Snippet; detailFirst?: boolean; testid?: string } =
    $props();
</script>

<div class="grid gap-4 wide:grid-cols-[minmax(20rem,26rem)_minmax(0,1fr)] wide:items-start" data-testid={testid}>
  <div class="min-w-0 {detailFirst ? 'order-2 wide:order-1' : ''}">{@render list()}</div>
  <div class="min-w-0 wide:sticky wide:top-4 {detailFirst ? 'order-1 wide:order-2' : ''}">{@render detail()}</div>
</div>
