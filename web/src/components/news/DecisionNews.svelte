<script lang="ts">
  // ---- IZ-4 (Wave I-Z; the review's Pass 2): a news item on the decision it affects — who, the words, the source (a
  // link when there is one), how long ago (the exact time on hover), and what the projection does with it ("Context
  // only: not in the projection" where that is true). The feed's own line (myweek.decision_feed), moved; nothing reads it.
  import type { ChangedLine } from "../../lib/api";
  import { ago } from "../../lib/card";

  let { lines, testid = "decision-news", names = true }: { lines: ChangedLine[]; testid?: string; names?: boolean } = $props();
  type Line = ChangedLine & { forecast_words?: string | null; forecast_status?: string | null };
  const SEP = " · ";
  function exact(iso: string | null): string {
    if (!iso) return "";
    const t = new Date(iso);
    return Number.isNaN(t.getTime()) ? "" : `${t.toLocaleString("en-US", { timeZone: "America/New_York", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} ET`;
  }
</script>

{#if lines.length}
  <ul class="space-y-1.5 border-l-2 border-line-strong pl-2.5" data-testid={testid}>
    {#each lines as l, i (i)}
      {@const x = l as Line}
      <li class="text-sm leading-snug" data-testid="decision-news-line" data-kind={l.kind} data-forecast={x.forecast_status ?? ""}>
        <p>
          <span class="font-semibold text-ink-3" aria-hidden="true">News</span>{" "}{#if names && l.player_name}<span class="font-semibold">{l.player_name}:</span>{" "}{/if}<span
            class={l.kind === "status" ? "text-warn" : "text-ink"}>{l.text}</span>
          <span class="text-ink-3"
            >{#if l.source}{SEP}{#if l.url}<a class="ll-link" href={l.url} target="_blank" rel="noopener noreferrer">{l.source} ↗</a>{:else}{l.source}{/if}{/if}{#if l.at}{SEP}<time
                datetime={l.at}
                title={exact(l.at)}>{ago(l.at)}</time
              >{/if}</span
          >
        </p>
        {#if x.forecast_words}<p class="text-xs text-ink-3" data-testid="decision-news-forecast">{x.forecast_words}</p>{/if}
      </li>
    {/each}
  </ul>
{/if}
