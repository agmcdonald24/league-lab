<script lang="ts">
  // N1 (Wave I-D): the news line under the availability lines — "News · 2 h ago · <headline> · ESPN ›". The newest
  // headline only (lib/card.ts newsLine; a long one cut at a word), linked out in a new tab, the source named. Nothing
  // when there is none.
  import type { PlayerCard } from "../lib/api";
  import { newsLine } from "../lib/card";

  let { card, testid }: { card: Pick<PlayerCard, "news">; testid: string } = $props();
  const line = $derived(newsLine(card));
  // ---- IF-4: the API puts the item about him first (RotoWire's blurb, or a headline that names him); an article-level
  // headline that does not name him is labelled "League news" so it does not read as news about him
  const league = $derived((card.news ?? []).find((x) => x.headline && x.url?.startsWith("https://"))?.about === "league");
  const SEP = " · ";
  const MORE = " ›";
</script>

{#if line}
  <p class="border-t border-line pt-2.5 text-sm leading-snug text-ink-2" data-testid={testid}>
    <span class="font-semibold text-ink" data-testid={`${testid}-label`}>{league ? "League news" : "News"}</span>{#if line.ago}<span class="text-ink-3">{SEP}{line.ago}</span>{/if}<span
      class="text-ink-3">{SEP}</span
    ><em title={line.full} data-testid={`${testid}-headline`}>{line.headline}</em><span class="text-ink-3">{SEP}</span><a
      href={line.url}
      target="_blank"
      rel="noopener noreferrer"
      class="font-semibold whitespace-nowrap text-accent"
      aria-label={`${line.source}: ${line.full} (opens in a new tab)`}
      data-testid={`${testid}-link`}>{line.source}{MORE}</a
    >
  </p>
{/if}
