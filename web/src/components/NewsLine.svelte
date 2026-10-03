<script lang="ts">
  // N1 (Wave I-D): the news line under the availability lines — "News · 2 h ago · <headline> · ESPN ›". The newest
  // headline only (lib/card.ts newsLine; a long one cut at a word), linked out in a new tab, the source named. Nothing
  // when there is none.
  // N2: a PlayerWire brief (the API sends them first) adds its one-sentence news under the headline (muted, the full
  // width, cut at a word to 220 characters) and a small verification tag after its source ("Minnesota Vikings via
  // PlayerWire › OFFICIAL"). An ESPN item renders exactly as in N1.
  import type { PlayerCard } from "../lib/api";
  import { newsLine } from "../lib/card";

  let { card, testid }: { card: Pick<PlayerCard, "news">; testid: string } = $props();
  const line = $derived(newsLine(card));
  const SEP = " · ";
  const MORE = " ›";
</script>

{#if line}
  <p class="border-t border-line pt-2.5 text-sm leading-snug text-ink-2" data-testid={testid}>
    <span class="font-semibold text-ink">News</span>{#if line.ago}<span class="text-ink-3">{SEP}{line.ago}</span>{/if}<span
      class="text-ink-3">{SEP}</span
    ><em title={line.full} data-testid={`${testid}-headline`}>{line.headline}</em><span class="text-ink-3">{SEP}</span><a
      href={line.url}
      target="_blank"
      rel="noopener noreferrer"
      class="font-semibold whitespace-nowrap text-accent"
      aria-label={`${line.source}: ${line.full} (opens in a new tab)`}
      data-testid={`${testid}-link`}>{line.source}{MORE}</a
    >{#if line.verification}<span
        class="ml-1.5 inline-block rounded-sm px-1 align-[1px] text-[10px] leading-[16px] font-bold tracking-wide uppercase {line.verification ===
        'disputed'
          ? 'bg-warn-soft text-warn'
          : 'bg-accent-soft text-accent'}"
        title={`PlayerWire marks this brief ${line.verification}`}
        data-testid={`${testid}-verification`}>{line.verification}</span
      >{/if}{#if line.summary}<span
        class="mt-1 block w-full text-ink-3"
        title={line.summaryFull ?? undefined}
        data-testid={`${testid}-summary`}>{line.summary}</span
      >{/if}
  </p>
{/if}
