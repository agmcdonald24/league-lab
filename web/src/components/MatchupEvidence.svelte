<script lang="ts">
  // ---- IF-3 (Wave I-F, the decision-quality review § Priority 1): the matchup evidence in two sentences — the
  // defense's history with the corners it was earned with, then what that means this week and whether the forecast
  // knows it ("contextual only; not in the forecast") — and the three parts behind "The evidence". One component for
  // Compare, the player card / pane's matchup section and Matchups' cornerback rows (IF-4 places it in the pane).
  import type { MatchupEvidence } from "../lib/api";
  import { teamLabel } from "../lib/theme";

  let {
    ev,
    who = null,
    details = true,
    testid = "matchup-evidence",
  }: { ev: MatchupEvidence | null | undefined; who?: string | null; details?: boolean; testid?: string } = $props();

  const slotWords: Record<string, string> = { LCB: "left", RCB: "right", NB: "slot" };
  const changed = $derived(ev?.implication.kind === "less_representative");
  const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
</script>

{#if ev && ev.sentences?.length}
  <div class="space-y-1.5 text-sm leading-snug" data-testid={testid} data-kind={ev.implication.kind}>
    {#if who || changed}
      <p class="flex flex-wrap items-center gap-x-2 gap-y-1">
        {#if who}<span class="font-semibold text-ink">{who} {ev.is_home === false ? "at" : "vs"} {teamLabel(ev.opponent) ?? ev.opponent}</span>{/if}
        {#if changed}<span class="rounded bg-warn-soft px-1.5 py-0.5 text-xs font-semibold text-warn" data-testid="evidence-flag">Corners changed</span>{/if}
      </p>
    {/if}
    <p class="text-ink-2" data-testid="evidence-history">{ev.sentences[0]}</p>
    {#if ev.sentences[1]}<p class="text-ink-2" data-testid="evidence-implication">{ev.sentences[1]}</p>{/if}
    {#if details}
      <details class="text-xs text-ink-3" data-testid="evidence-details">
        <summary class="inline-flex min-h-11 cursor-pointer items-center font-semibold">The evidence</summary>
        <dl class="space-y-1.5 pb-1">
          <div>
            <dt class="font-semibold text-ink-2">History</dt>
            <dd>
              {ev.opponent_name}
              {ev.history.words ?? "no games to rank yet"}{#if ev.history.period}: {ev.history.period}, {ev.history.games} game{ev.history.games === 1 ? "" : "s"}{/if}, {ev.history.scoring};
              {ev.history.adjusted_words}{ev.history.adjusted_rank?.words
                ? ` (counting the offenses it faced it ${ev.history.adjusted_rank.words}, ${ev.history.adjusted_rank.scoring})`
                : ""}.
            </dd>
          </div>
          {#if ev.changed.kind !== "not_checked"}
            <div>
              <dt class="font-semibold text-ink-2">What changed</dt>
              <dd>
                {#if ev.changed.regulars.length}Its regular corners this season: {ev.changed.regulars.map((r) => r.name).join(", ")}.{/if}
                {#each ev.changed.missing as m (m.gsis_id)}
                  <span class="block" data-testid="evidence-missing"
                    >{m.name}: {m.reason === "status" ? m.status : "not listed as a starter"}{m.source ? ` · ${m.source}${m.date_words ? `, ${m.date_words}` : ""}` : ""}</span
                  >
                {/each}
                {#if ev.changed.expected.length}
                  <span class="block" data-testid="evidence-expected"
                    >Expected this week: {ev.changed.expected
                      .map((e) => `${e.name} (${slotWords[e.slot] ?? e.slot}${e.replaces ? `, for ${e.replaces}` : ""}): ${e.rank_words ?? "unranked"}`)
                      .join("; ")}.</span
                  >
                {/if}
                {#if ev.changed.depth_chart_at}<span class="block">Depth chart of {new Date(ev.changed.depth_chart_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}.</span>{/if}
                {#if ev.changed.kind === "unknown"}{ev.changed.words}{/if}
              </dd>
            </div>
          {/if}
          <div>
            <dt class="font-semibold text-ink-2">The forecast</dt>
            <dd data-testid="evidence-forecast">{cap(ev.forecast_treatment.words)}. {ev.forecast_treatment.detail}</dd>
          </div>
        </dl>
      </details>
    {/if}
  </div>
{/if}
<!-- ---- end IF-3 -->
