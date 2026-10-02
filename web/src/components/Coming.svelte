<script lang="ts">
  // A screen that is on its way (the Decisions tabs until Wave G's G4 lands them): what it will answer, in plain words.
  import Card from "./Card.svelte";

  let { title, what }: { title: string; what: string } = $props();
</script>

<Card testid="coming">
  <p class="ll-label">Coming</p>
  <h1 class="mt-1 text-xl font-bold">{title}</h1>
  <p class="mt-1 text-base leading-snug text-ink-2">{what}</p>
</Card>
