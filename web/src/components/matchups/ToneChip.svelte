<script lang="ts">
  // ---- IN-3 (Wave I-N): a matchup's tone as a chip — the word in the state color on its wash, a glyph so color never
  // carries it alone (lib/research.ts' IB-3 tokens); "No read" when there is none (unknown is not neutral).
  import { TONE_COLOR, TONE_GLYPH, TONE_WORD, toneWash, type Tone } from "../../lib/research";

  let { tone, small = "", testid = "tone-chip", size = "md" }: { tone: Tone | null; small?: string; testid?: string; size?: "md" | "sm" } = $props();
</script>

<span class="inline-flex flex-col items-start" data-testid={testid} data-tone={tone ?? "none"}>
  <span
    class="inline-block rounded-sm px-2 py-0.5 font-bold whitespace-nowrap {size === 'sm' ? 'text-xs' : 'text-sm'}"
    style="background:{toneWash(tone)};color:{tone ? TONE_COLOR[tone] : 'var(--ll-ink-3)'}"
  >
    {#if tone && TONE_GLYPH[tone]}<span aria-hidden="true">{TONE_GLYPH[tone]} </span>{/if}{tone ? TONE_WORD[tone] : "No read"}
  </span>
  {#if small}<span class="tabnum mt-0.5 text-[11px] leading-tight text-ink-3">{small}</span>{/if}
</span>
