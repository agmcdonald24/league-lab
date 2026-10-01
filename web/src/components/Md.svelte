<script lang="ts">
  import { md, type LinkContext } from "../lib/md";

  let { text, ctx = {}, block = false, class: cls = "" }: { text: string | null | undefined; ctx?: LinkContext; block?: boolean; class?: string } =
    $props();
  const html = $derived(md(text, ctx));
</script>

<svelte:element this={block ? "div" : "span"} class={cls}>{@html html}</svelte:element>
